"""Cliente assíncrono para a Deriv Options API e para o WebSocket legado v3.

Conta DEMO apenas. Token só com conta real é recusado. Falha de autenticação
ou de compra não cai num simulador silencioso.
"""

import asyncio
import inspect
import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional
import websockets
from websockets.client import WebSocketClientProtocol

from backend.app.core.errors import (
    DerivApiError,
    DerivAuthError,
    DerivConfigError,
    DerivConnectionError,
    DerivOperationalError,
    TraderSecurityError,
)
from backend.app.core.logging import logger
from backend.app.modules.deriv_client.models import (
    ContractBuyResult,
    DerivAuthorizeResponse,
    DerivConnectionState,
    ProposalData,
    TickData,
)

_REAL_LOGIN_PREFIXES = ("CR", "MF", "MLT")
_DEMO_LOGIN_PREFIXES = ("VRTC", "VR", "DOT")


def sanitize_token(token: Optional[str]) -> str:
    """Mascara o token para nunca vazar nos logs ou respostas."""
    if not token:
        return "[NENHUM]"
    clean = token.strip()
    if len(clean) <= 8:
        return "****"
    return f"{clean[:6]}...{clean[-4:]}"


def extract_last_digit(quote: float, pip_size: int = 2) -> int:
    """Extrai o último dígito decimal do quote considerando o pip_size oficial.

    Exemplo: quote=1024.58, pip_size=2 -> '1024.58' -> 8
             quote=1024.6, pip_size=2  -> '1024.60' -> 0 (Zero relevante!)
    """
    formatted = f"{quote:.{pip_size}f}"
    return int(formatted[-1])


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, dict):
            value = value.get("value", value.get("amount", default))
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_options_accounts(payload: Any) -> List[dict]:
    """Normaliza o JSON de GET /trading/v1/options/accounts.

    A Options API devolve `{"data": [{"account_id", "account_type": "demo"| "real", ...}]}`.
    `data` às vezes vem como objeto único. O formato antigo `accounts` também é aceito.
    """
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload.get("accounts"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and any(key in data for key in ("account_id", "loginid", "id", "account_type")):
        return [data]
    return []


def classify_options_account(account: dict) -> str:
    """Classifica uma conta como demo, real ou unknown. Conta real nunca vira demo."""
    account_type = str(account.get("account_type") or account.get("accountType") or "").strip().lower()
    loginid = str(
        account.get("account_id") or account.get("loginid") or account.get("id") or ""
    ).strip().upper()

    if account_type in ("real", "live", "actual"):
        return "real"
    if account.get("is_virtual") in (0, False) and "is_virtual" in account and account_type != "demo":
        return "real"
    if loginid.startswith(_REAL_LOGIN_PREFIXES) and account_type not in ("demo", "virtual"):
        return "real"
    if account_type in ("demo", "virtual"):
        return "demo"
    if account.get("is_virtual") in (1, True, "1"):
        return "demo"
    if loginid.startswith(_DEMO_LOGIN_PREFIXES):
        return "demo"
    return "unknown"


def _extract_api_message(body: str) -> str:
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return (body or "")[:300]
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            code = errors[0].get("code") or ""
            message = errors[0].get("message") or ""
            text = f"{code}: {message}".strip(": ")
            return text[:300]
        if payload.get("error"):
            return str(payload["error"])[:300]
    return (body or "")[:300]


class DerivWebSocketClient:
    """Cliente da Deriv com guarda de conta DEMO e canal de negociação explícito."""

    def __init__(
        self,
        ws_url: str = "wss://ws.derivws.com/websockets/v3",
        app_id: int = 1089,
        demo_token: Optional[str] = None,
        rest_base_url: str = "https://api.derivws.com",
        simulator_enabled: bool = False,
    ):
        self.ws_url = ws_url
        self.app_id = app_id
        self.demo_token = demo_token
        self.rest_base_url = rest_base_url.rstrip("/")
        self.simulator_enabled = bool(simulator_enabled)

        self.state = DerivConnectionState.DISCONNECTED
        self.session_mode = "disconnected"
        self.last_error: Optional[str] = None
        self._ws: Optional[WebSocketClientProtocol] = None
        self._auth_info: Optional[DerivAuthorizeResponse] = None
        self._connected_url: Optional[str] = None
        self._trading_channel = "none"
        self._open_balance_debits = 0

        self._req_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._tick_callbacks: List[Callable[[TickData], None]] = []
        self._listener_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._should_reconnect: bool = True
        self._is_reconnecting: bool = False
        self._suppress_reconnect: bool = False
        self._active_symbols: List[str] = []

    @property
    def is_connected(self) -> bool:
        """Indica se a conexão WebSocket com a Deriv está ativa."""
        if self._ws is None:
            return False
        if hasattr(self._ws, "closed"):
            is_closed = bool(self._ws.closed)
        elif hasattr(self._ws, "close_code"):
            is_closed = self._ws.close_code is not None
        else:
            is_closed = False

        return (
            self.state in (DerivConnectionState.CONNECTED, DerivConnectionState.AUTHORIZED)
            and not is_closed
        )

    @property
    def is_authorized(self) -> bool:
        """Indica sessão demo autenticada ou simulador explicitamente ligado."""
        return (
            self.state == DerivConnectionState.AUTHORIZED
            and self._auth_info is not None
            and self.session_mode in ("demo", "simulator")
        )

    @property
    def is_simulated(self) -> bool:
        return self.session_mode == "simulator" and self.simulator_enabled

    @property
    def auth_info(self) -> Optional[DerivAuthorizeResponse]:
        """Retorna os dados cadastrais da sessão autenticada."""
        return self._auth_info

    @property
    def trading_channel(self) -> str:
        return self._trading_channel

    @property
    def redacted_endpoint(self) -> str:
        """URL conectada sem o OTP, que é credencial de uso único."""
        if self.session_mode == "simulator":
            return "simulador-local (sem Deriv)"
        url = self._connected_url or self.ws_url or ""
        if "otp=" in url:
            base, _, _query = url.partition("?")
            return f"{base}?otp=***"
        return url

    def register_tick_callback(self, callback: Callable[[TickData], None]) -> None:
        """Registra um callback síncrono ou assíncrono para ser acionado a cada novo tick."""
        if callback not in self._tick_callbacks:
            self._tick_callbacks.append(callback)

    def unregister_tick_callback(self, callback: Callable[[TickData], None]) -> None:
        """Remove um callback registrado."""
        if callback in self._tick_callbacks:
            self._tick_callbacks.remove(callback)

    def _next_req_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _channel_for_url(self, url: str) -> str:
        lowered = (url or "").lower()
        if "/ws/real" in lowered:
            return "real"
        if "/ws/demo" in lowered:
            return "demo"
        if "/ws/public" in lowered:
            return "public"
        if "websockets/v3" in lowered or "binaryws.com" in lowered:
            return "legacy"
        return "unknown"

    def _assert_not_real_url(self, url: str) -> None:
        if "/ws/real" in (url or "").lower():
            raise TraderSecurityError(
                "VIOLAÇÃO DE SEGURANÇA: recusada conexão ao WebSocket de conta REAL (/ws/real). "
                "O robô opera exclusivamente em conta DEMO."
            )

    def _assert_demo_trading_url(self, url: str) -> None:
        """A URL devolvida pelo OTP precisa ser o canal demo, com o otp, e nunca /ws/real."""
        self._assert_not_real_url(url)
        lowered = (url or "").lower()
        if "/ws/demo" not in lowered or "otp=" not in lowered:
            raise DerivAuthError(
                message="A Deriv não devolveu um WebSocket de conta demo.",
                detail=(
                    "POST /trading/v1/options/accounts/{id}/otp deve responder data.url "
                    "no canal /ws/demo com o parâmetro otp. A URL recebida foi recusada."
                ),
                code="OTP_URL_INVALID",
            )

    def _prepare_ws_url(self, base_url: str) -> str:
        """Formata URL de mercado. Não mexe em URL da Options API nem em /ws/real."""
        clean = base_url.strip().strip("'\"").rstrip("/")
        self._assert_not_real_url(clean)
        if "api.derivws.com" in clean:
            return clean

        if "/websockets/v3" not in clean:
            clean = f"{clean}/websockets/v3"
        sep = "&" if "?" in clean else "?"
        params = []
        if "app_id=" not in clean:
            params.append(f"app_id={self.app_id}")
        if "l=" not in clean:
            params.append("l=EN")
        if "brand=" not in clean:
            params.append("brand=deriv")

        query = "&".join(params)
        return f"{clean}{sep}{query}" if query else clean

    def _build_url(self, base_url: str) -> str:
        return self._prepare_ws_url(base_url)

    def _get_candidate_endpoints(self) -> List[str]:
        """Endpoints de mercado. A URL configurada vem primeiro; /ws/real nunca entra.

        O canal público não executa ordens. A compra PAT usa o URL demo do OTP,
        aberto por authorize(), e não esta lista.
        """
        endpoints: List[str] = []
        if self.ws_url:
            candidate = self._prepare_ws_url(self.ws_url)
            endpoints.append(candidate)

        fallbacks = [
            "wss://ws.derivws.com/websockets/v3",
            "wss://frontend.binaryws.com/websockets/v3",
            "wss://ws.binaryws.com/websockets/v3",
            "wss://api.derivws.com/trading/v1/options/ws/public",
        ]
        for fb in fallbacks:
            candidate = self._prepare_ws_url(fb)
            if candidate not in endpoints:
                endpoints.append(candidate)
        return endpoints

    def _parse_connection_exception(self, exc: Exception) -> DerivConnectionError:
        """Classifica detalhadamente a falha de conexão de acordo com os padrões da Deriv/Cloudflare."""
        exc_str = str(exc)
        status_code = 520

        status_match = re.search(r"HTTP\s*(\d{3})", exc_str, re.IGNORECASE)
        if status_match:
            status_code = int(status_match.group(1))
        elif hasattr(exc, "status_code"):
            status_code = getattr(exc, "status_code")

        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return DerivConnectionError(
                message="Tempo limite esgotado ao tentar estabelecer conexão com a Deriv API.",
                detail="A requisição de handshake excedeu o tempo limite (timeout de conexão).",
                code="WS_TIMEOUT",
                http_status=504,
            )
        if isinstance(exc, socket.gaierror):
            return DerivConnectionError(
                message="Falha de resolução de DNS para o servidor da Deriv.",
                detail=f"Não foi possível resolver o hostname da Deriv: {exc}",
                code="WS_DNS_FAILED",
                http_status=502,
            )
        if isinstance(exc, ssl.SSLError):
            return DerivConnectionError(
                message="Falha na negociação de segurança TLS/SSL com a Deriv.",
                detail=f"Erro na camada de criptografia SSL/TLS: {exc}",
                code="WS_SSL_FAILED",
                http_status=525,
            )

        detail_msg = f"Handshake WebSocket rejeitado pelo servidor (HTTP {status_code})."
        if status_code == 520:
            detail_msg = (
                "Handshake WebSocket rejeitado pela infraestrutura de borda Cloudflare/Deriv (HTTP 520)."
            )

        return DerivConnectionError(
            message="Não foi possível estabelecer conexão com a Deriv API.",
            detail=detail_msg,
            code="WS_CONNECTION_FAILED",
            http_status=status_code,
        )

    def _reject_session(self, exc: Exception) -> None:
        """Limpa a sessão e guarda um erro visível. Nunca promove a sessão a simulador."""
        self._auth_info = None
        self.session_mode = "error"
        self._trading_channel = "none"
        self._open_balance_debits = 0
        self.state = DerivConnectionState.ERROR
        message = getattr(exc, "message", None) or str(exc)
        detail = getattr(exc, "detail", None)
        self.last_error = f"{message} {detail}".strip() if detail and detail != message else message
        logger.error("Sessão Deriv recusada: %s", self.last_error)

    def _http_error_to_deriv(self, status: int, body: str) -> DerivApiError:
        detail = _extract_api_message(body) or f"HTTP {status}"
        if status == 401:
            return DerivAuthError(
                message="A Deriv recusou o token (HTTP 401).",
                detail=(
                    f"{detail}. Gere um PAT novo de conta demo com escopo trade "
                    "e confira o Deriv-App-ID."
                ),
                code="AUTH_HTTP_401",
                http_status=401,
            )
        if status == 403:
            return DerivAuthError(
                message="A Deriv negou acesso à conta (HTTP 403).",
                detail=f"{detail}. O App ID ou o escopo do token não permite esta chamada.",
                code="AUTH_HTTP_403",
                http_status=403,
            )
        return DerivAuthError(
            message=f"Falha REST na Deriv (HTTP {status}).",
            detail=detail,
            code=f"AUTH_HTTP_{status}",
            http_status=status,
        )

    async def _rest_json(self, method: str, path: str, token: str) -> dict:
        """Chama a Options API REST. Não envia o token para log."""
        url = f"{self.rest_base_url}{path}"
        data = b"" if method.upper() == "POST" else None
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Deriv-App-ID": str(self.app_id),
                "Accept": "application/json",
                "User-Agent": "ODD-EVEN-AI-TRADER",
            },
            method=method.upper(),
        )
        loop = asyncio.get_running_loop()

        def _do() -> dict:
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise self._http_error_to_deriv(exc.code, body) from exc
            except urllib.error.URLError as exc:
                raise DerivConnectionError(
                    message="Não foi possível consultar a Options API da Deriv.",
                    detail=f"Falha de rede em {method.upper()} {path}: {exc.reason}",
                    code="REST_UNREACHABLE",
                    http_status=502,
                ) from exc

        return await loop.run_in_executor(None, _do)

    async def _stop_socket_tasks(self) -> None:
        listener = self._listener_task
        heartbeat = self._heartbeat_task
        self._listener_task = None
        self._heartbeat_task = None
        for task in (heartbeat, listener):
            if task and not task.done():
                task.cancel()
        for task in (heartbeat, listener):
            if task is None:
                continue
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

    async def _connect_exact(self, url: str) -> None:
        """Abre exatamente esta URL. Não faz failover para o canal público nem para /ws/real."""
        self._assert_not_real_url(url)
        self._suppress_reconnect = True
        try:
            await self._stop_socket_tasks()
            self.state = DerivConnectionState.CONNECTING
            headers = {"Accept-Language": "en-US,en;q=0.9"}
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            )
            kwargs: Dict[str, Any] = {
                "origin": "https://app.deriv.com",
                "user_agent_header": user_agent,
                "additional_headers": headers,
                "open_timeout": 8.0,
                "ping_interval": None,
                "ping_timeout": None,
            }
            if url.startswith("wss://"):
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                kwargs["ssl"] = ssl_ctx
            channel = self._channel_for_url(url)
            logger.info("Abrindo WebSocket no canal %s.", channel)
            self._ws = await websockets.connect(url, **kwargs)
            self._connected_url = url
            self._trading_channel = channel
            self.state = DerivConnectionState.CONNECTED
            self._should_reconnect = True
            self._listener_task = asyncio.create_task(self._listen_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        finally:
            self._suppress_reconnect = False

    async def connect(self) -> None:
        """Abre um WebSocket de mercado (ticks). Negociação PAT usa authorize(), não este failover."""
        self.state = DerivConnectionState.CONNECTING
        try:
            candidates = self._get_candidate_endpoints()
        except TraderSecurityError as exc:
            self._reject_session(exc)
            raise

        last_error: Optional[Exception] = None
        for url in candidates:
            try:
                await self._connect_exact(url)
                logger.info("Conexão WebSocket estabelecida no canal %s.", self._trading_channel)
                return
            except TraderSecurityError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Falha ao conectar no canal %s: %s. Tentando próximo endpoint...",
                    self._channel_for_url(url),
                    exc,
                )

        self.state = DerivConnectionState.ERROR
        classified_err = (
            self._parse_connection_exception(last_error) if last_error else DerivConnectionError()
        )
        self.last_error = classified_err.message
        logger.error(
            "Todos os endpoints WebSocket da Deriv falharam. Código: %s | Detalhe: %s",
            classified_err.code,
            classified_err.detail,
        )
        raise classified_err

    async def disconnect(self) -> None:
        """Encerra a conexão WebSocket e cancela tarefas de segundo plano."""
        logger.info("Desconectando cliente Deriv...")
        self._should_reconnect = False
        self.state = DerivConnectionState.DISCONNECTED
        self.session_mode = "disconnected"
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        await self._stop_socket_tasks()
        self._auth_info = None
        self._connected_url = None
        self._trading_channel = "none"
        self._open_balance_debits = 0

    async def send_raw_request(self, payload: dict) -> dict:
        """Envia um comando JSON com rastreamento por req_id e aguarda a resposta."""
        if not self._ws or not self.is_connected:
            raise DerivApiError("WebSocket desconectado. Impossível enviar comando.")

        req_id = self._next_req_id()
        payload["req_id"] = req_id

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[req_id] = future

        try:
            await self._ws.send(json.dumps(payload))
            response = await asyncio.wait_for(future, timeout=10.0)
            return response
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise DerivApiError(f"Timeout aguardando resposta para req_id={req_id}")
        except Exception as exc:
            self._pending_requests.pop(req_id, None)
            raise exc

    async def ping(self) -> dict:
        """Envia um ping para checar latência e vitalidade da sessão."""
        response = await self.send_raw_request({"ping": 1})
        if "error" in response:
            raise DerivApiError(f"Erro no ping: {response['error']}")
        return response

    def enable_explicit_simulator(self, balance: float = 100.0) -> DerivAuthorizeResponse:
        """Liga o simulador local. Só quando DERIV_SIMULATOR=true. Não é fallback."""
        if not self.simulator_enabled:
            raise DerivConfigError(
                message="Simulador desligado.",
                detail="Defina DERIV_SIMULATOR=true para optar. Falha de login não ativa o simulador.",
                code="SIMULATOR_DISABLED",
            )
        self._auth_info = DerivAuthorizeResponse(
            is_virtual=True,
            loginid="SIMULATOR",
            currency="USD",
            balance=round(float(balance), 2),
        )
        self.session_mode = "simulator"
        self._trading_channel = "simulator"
        self._open_balance_debits = 0
        self.state = DerivConnectionState.AUTHORIZED
        self.last_error = None
        logger.warning(
            "SIMULADOR OPT-IN ativo (loginid=SIMULATOR). Nenhuma ordem será enviada à Deriv. Saldo fictício US$ %.2f",
            self._auth_info.balance,
        )
        return self._auth_info

    async def authorize(self, token: Optional[str] = None) -> DerivAuthorizeResponse:
        """Autentica em conta DEMO. PAT usa REST + OTP + /ws/demo. Legado usa authorize no v3."""
        auth_token = (token or self.demo_token or "").strip()
        if auth_token == "seu_token_demo_aqui":
            auth_token = ""
        if not auth_token:
            if self.simulator_enabled:
                return self.enable_explicit_simulator()
            exc = DerivConfigError(
                message="Token de autorização ausente.",
                detail="Nenhum token fornecido. O token de conta DEMO é obrigatório.",
                code="MISSING_TOKEN",
            )
            self._reject_session(exc)
            raise exc

        logger.info("Enviando solicitação de autorização para token %s...", sanitize_token(auth_token))
        try:
            if auth_token.startswith("pat_"):
                return await self._authorize_pat(auth_token)
            return await self._authorize_legacy(auth_token)
        except (DerivAuthError, DerivConfigError, DerivConnectionError, DerivOperationalError, TraderSecurityError):
            raise
        except Exception as exc:
            err = DerivAuthError(
                message="Falha inesperada ao autorizar na Deriv.",
                detail=str(exc),
                code="AUTH_UNEXPECTED",
            )
            self._reject_session(err)
            raise err from exc

    async def _authorize_pat(self, token: str) -> DerivAuthorizeResponse:
        """Fluxo oficial da Options API: contas, OTP e WebSocket demo."""
        try:
            payload = await self._rest_json("GET", "/trading/v1/options/accounts", token)
        except (DerivAuthError, DerivConnectionError, TraderSecurityError) as exc:
            self._reject_session(exc)
            raise

        accounts = parse_options_accounts(payload)
        demo_accounts = [account for account in accounts if classify_options_account(account) == "demo"]
        real_accounts = [account for account in accounts if classify_options_account(account) == "real"]
        if not demo_accounts:
            if real_accounts:
                ids = ", ".join(
                    str(account.get("account_id") or account.get("loginid") or "?")
                    for account in real_accounts
                )
                exc = TraderSecurityError(
                    "VIOLAÇÃO DE SEGURANÇA: o token só possui conta REAL "
                    f"({ids}). O robô opera exclusivamente em conta DEMO e não entra em simulador."
                )
            elif not accounts:
                exc = DerivAuthError(
                    message="Nenhuma conta de opções encontrada para este token.",
                    detail=(
                        "GET /trading/v1/options/accounts devolveu uma lista vazia. "
                        "Gere um PAT novo, de conta demo, com escopo trade, e confira o Deriv-App-ID."
                    ),
                    code="NO_ACCOUNTS",
                )
            else:
                exc = DerivAuthError(
                    message="Não foi possível confirmar uma conta demo neste token.",
                    detail="A resposta não trouxe account_type=demo nem conta virtual. Conta real não é aceita.",
                    code="DEMO_ACCOUNT_NOT_CONFIRMED",
                )
            self._reject_session(exc)
            raise exc

        account = demo_accounts[0]
        account_id = str(account.get("account_id") or account.get("loginid") or account.get("id"))
        try:
            otp_payload = await self._rest_json(
                "POST",
                f"/trading/v1/options/accounts/{account_id}/otp",
                token,
            )
        except (DerivAuthError, DerivConnectionError, TraderSecurityError) as exc:
            self._reject_session(exc)
            raise

        data = otp_payload.get("data") if isinstance(otp_payload, dict) else None
        ws_url = str(data.get("url") or "") if isinstance(data, dict) else ""
        if not ws_url:
            exc = DerivAuthError(
                message="A Deriv não devolveu a URL autenticada do WebSocket.",
                detail="POST /accounts/{id}/otp deve responder data.url com o canal demo e o otp.",
                code="OTP_URL_MISSING",
            )
            self._reject_session(exc)
            raise exc

        try:
            self._assert_demo_trading_url(ws_url)
            await self._connect_exact(ws_url)
        except (TraderSecurityError, DerivAuthError, DerivConnectionError) as exc:
            self._reject_session(exc)
            raise

        balance = _as_float(account.get("balance"), 0.0)
        currency = str(account.get("currency") or "USD")
        self._auth_info = DerivAuthorizeResponse(
            is_virtual=True,
            loginid=account_id,
            currency=currency,
            balance=balance,
        )
        self.session_mode = "demo"
        self._trading_channel = "demo"
        self._open_balance_debits = 0
        self.state = DerivConnectionState.AUTHORIZED
        self.last_error = None
        self.demo_token = token
        logger.info(
            "Autenticado na conta DEMO %s via Options API. Canal demo com OTP. Saldo: %s %s",
            account_id,
            balance,
            currency,
        )
        return self._auth_info

    async def _authorize_legacy(self, token: str) -> DerivAuthorizeResponse:
        """Token que não é PAT: authorize no WebSocket v3, com bloqueio de conta real."""
        if not self.is_connected:
            await self.connect()
        try:
            response = await self.send_raw_request({"authorize": token})
        except Exception as exc:
            err = DerivConnectionError(
                message="Falha ao enviar authorize no WebSocket.",
                detail=str(exc),
                code="AUTHORIZE_SEND_FAILED",
            )
            self._reject_session(err)
            raise err from exc

        if "error" in response:
            err_body = response["error"] if isinstance(response["error"], dict) else {}
            err_code = err_body.get("code", "AUTH_FAILED")
            err_msg = err_body.get("message", "Token de API inválido ou não autorizado.")
            if err_code == "UnknownMethod":
                err = DerivOperationalError(
                    message="Este WebSocket não aceita authorize.",
                    detail=(
                        "O gateway público da Options API não autentica sessão e não executa compra. "
                        "Use um PAT (pat_...) com escopo trade: o robô pede o OTP e conecta em /ws/demo. "
                        "Token legado precisa de DERIV_WS_URL=wss://ws.derivws.com/websockets/v3."
                    ),
                    code="UnknownMethod",
                )
            else:
                err = DerivAuthError(
                    message="Falha de autenticação na Deriv API.",
                    detail=f"Deriv rejeitou o token: {err_msg} (Código: {err_code})",
                    code=str(err_code),
                    http_status=401,
                )
            self._reject_session(err)
            raise err

        auth_data = response.get("authorize", {})
        try:
            self._auth_info = self._validate_auth_payload(auth_data)
        except TraderSecurityError as exc:
            self._reject_session(exc)
            raise

        channel = self._channel_for_url(self._connected_url or self.ws_url)
        if channel == "real":
            exc = TraderSecurityError(
                "VIOLAÇÃO DE SEGURANÇA: authorize respondeu num canal de conta REAL."
            )
            self._reject_session(exc)
            raise exc
        if channel == "public":
            exc = DerivOperationalError(
                message="Authorize não é aceito no WebSocket público.",
                detail="Conecte um PAT no canal /ws/demo ou um token legado no WebSocket v3.",
                code="PUBLIC_CHANNEL_NOT_TRADING",
            )
            self._reject_session(exc)
            raise exc

        self.session_mode = "demo"
        self._trading_channel = channel
        self.state = DerivConnectionState.AUTHORIZED
        self.last_error = None
        self.demo_token = token
        logger.info(
            "Autenticado em conta DEMO legada: %s (Saldo: %s %s, canal %s)",
            self._auth_info.loginid,
            self._auth_info.balance,
            self._auth_info.currency,
            channel,
        )
        return self._auth_info

    def _validate_auth_payload(self, auth_data: dict) -> DerivAuthorizeResponse:
        """Valida se o payload de autorização cumpre a salvaguarda de conta DEMO."""
        is_virtual = bool(auth_data.get("is_virtual", 0))
        loginid = str(auth_data.get("loginid", ""))

        if not is_virtual or loginid.upper().startswith(_REAL_LOGIN_PREFIXES):
            logger.critical(
                "VIOLAÇÃO GRAVE: Conta REAL (%s) conectada. Abortando.",
                loginid or "desconhecido",
            )
            raise TraderSecurityError(
                "VIOLAÇÃO DE SEGURANÇA: A conta conectada é REAL (is_virtual=0). "
                "O ODD/EVEN AI TRADER opera EXCLUSIVAMENTE em ambiente DEMO."
            )

        return DerivAuthorizeResponse(
            is_virtual=True,
            loginid=loginid,
            currency=str(auth_data.get("currency", "USD")),
            balance=float(auth_data.get("balance", 0.0)),
            email=auth_data.get("email"),
            user_id=auth_data.get("user_id"),
        )

    async def subscribe_ticks(self, symbol: str) -> None:
        """Assina o feed de cotações em tempo real para um símbolo sintético."""
        if self.session_mode == "simulator":
            raise DerivOperationalError(
                message=f"Simulador opt-in não assina ticks de {symbol}.",
                detail="O simulador não fala com a Deriv. Para ticks e ordens reais use um PAT de conta demo.",
                code="SIMULATOR_NO_TICKS",
            )
        response = await self.send_raw_request({"ticks": symbol, "subscribe": 1})

        if "error" in response:
            err = response["error"]
            err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise DerivOperationalError(
                message=f"Falha ao assinar ticks de {symbol}.",
                detail=f"Servidor rejeitou subscrição de ticks: {err_msg}",
                code="SUBSCRIBE_FAILED",
            )

        if symbol not in self._active_symbols:
            self._active_symbols.append(symbol)
        logger.info("Subscrição de ticks ativada para %s.", symbol)

    def _uses_underlying_symbol(self) -> bool:
        if self._trading_channel in ("demo", "public"):
            return True
        url = f"{self._connected_url or ''} {self.ws_url or ''}"
        return "api.derivws.com" in url or "options" in url

    async def get_proposal(
        self,
        symbol: str,
        contract_type: str,
        amount: float,
        duration: int = 1,
        duration_unit: str = "t",
    ) -> ProposalData:
        """Consulta a cotação e o payout oficial para um contrato de dígito."""
        if contract_type not in ("DIGITEVEN", "DIGITODD"):
            raise ValueError(
                f"Tipo de contrato inválido: {contract_type}. Permitidos: DIGITEVEN, DIGITODD."
            )

        if self.session_mode == "simulator":
            payout = round(float(amount) * 1.95, 2)
            logger.warning(
                "SIMULADOR: cotação sintética %s %s stake %.2f payout %.2f. Não é preço da Deriv.",
                contract_type,
                symbol,
                amount,
                payout,
            )
            return ProposalData(
                proposal_id=f"SIMPROP_{int(time.time() * 1000)}",
                ask_price=float(amount),
                payout=payout,
                spot=0.0,
                spot_time=int(time.time()),
                contract_type=contract_type,
                symbol=symbol,
                net_payout=round(payout - float(amount), 2),
                payout_ratio=1.95,
            )

        currency = self._auth_info.currency if self._auth_info and self._auth_info.currency else "USD"
        payload: Dict[str, Any] = {
            "proposal": 1,
            "amount": float(amount),
            "basis": "stake",
            "currency": currency,
            "duration": int(duration),
            "duration_unit": duration_unit,
            "contract_type": contract_type,
        }
        if self._uses_underlying_symbol():
            payload["underlying_symbol"] = symbol
        else:
            payload["symbol"] = symbol

        response = await self.send_raw_request(payload)

        if "error" in response:
            err = response["error"]
            err_msg = str(err.get("message", err) if isinstance(err, dict) else err)
            if "underlying_symbol" in err_msg or "symbol" in err_msg:
                alt_payload = dict(payload)
                if "symbol" in alt_payload:
                    alt_payload["underlying_symbol"] = alt_payload.pop("symbol")
                elif "underlying_symbol" in alt_payload:
                    alt_payload["symbol"] = alt_payload.pop("underlying_symbol")
                response = await self.send_raw_request(alt_payload)

        if "error" in response:
            err = response["error"]
            err_msg = err.get("message", err) if isinstance(err, dict) else err
            raise DerivApiError(f"Erro ao obter proposta: {err_msg}")

        proposal_dict = response.get("proposal", {})
        return ProposalData.from_api_payload(
            proposal_dict=proposal_dict,
            contract_type=contract_type,
            symbol=symbol,
        )

    async def buy(self, proposal_id: str, price: float) -> ContractBuyResult:
        """Compra no canal demo (ou legado v3 já autorizado). Recusa o gateway público."""
        if self.session_mode == "simulator" and self.simulator_enabled:
            if not self._auth_info:
                self.enable_explicit_simulator()
            logger.warning(
                "SIMULADOR: compra local da proposta %s por US$ %.2f. Nada foi enviado à Deriv.",
                proposal_id,
                price,
            )
            sim_id = f"SIM_{int(time.time() * 1000)}"
            balance = self._auth_info.balance if self._auth_info else 0.0
            return ContractBuyResult(
                contract_id=sim_id,
                transaction_id=f"SIMTX_{sim_id}",
                buy_price=float(price),
                payout=round(float(price) * 1.95, 2),
                balance_after=balance,
                shortcode="SIMULATOR",
                start_time=int(time.time()),
            )

        if not self.is_authorized or self.session_mode != "demo":
            raise TraderSecurityError("Operação de compra requer sessão DEMO autorizada.")

        if self._trading_channel not in ("demo", "legacy"):
            raise DerivOperationalError(
                message="Compra recusada: a sessão não está num WebSocket DEMO autorizado.",
                detail=(
                    "Ordens não saem pelo gateway público e não são simuladas quando a Deriv recusa. "
                    f"Canal atual: {self._trading_channel or 'nenhum'}. "
                    "PAT: autentique para receber /ws/demo?otp=... "
                    "Token legado: use wss://ws.derivws.com/websockets/v3 com conta virtual."
                ),
                code="TRADING_CHANNEL_REQUIRED",
            )

        response = await self.send_raw_request({"buy": str(proposal_id), "price": float(price)})
        if "error" in response:
            err = response["error"] if isinstance(response["error"], dict) else {"message": str(response["error"])}
            err_code = err.get("code")
            err_msg = err.get("message", err)
            if err_code in ("AuthorizationRequired", "UnknownMethod"):
                raise DerivOperationalError(
                    message="A Deriv recusou a compra por falta de sessão autenticada.",
                    detail=(
                        f"{err_code}: {err_msg}. O WebSocket conectado não é o canal demo com OTP. "
                        "Nenhuma ordem simulada foi criada."
                    ),
                    code=str(err_code or "BUY_UNAUTHORIZED"),
                )
            raise DerivApiError(f"Erro ao comprar contrato: {err_msg}")

        buy_dict = response.get("buy", {})
        if not isinstance(buy_dict, dict):
            raise DerivApiError("Resposta de compra sem o objeto buy.")
        if "balance_after" in buy_dict and self._auth_info is not None:
            self._auth_info.balance = _as_float(buy_dict.get("balance_after"), self._auth_info.balance)
            self._open_balance_debits += 1
        return ContractBuyResult.from_api_payload(buy_dict, price)

    def update_balance(
        self,
        pnl: float,
        stake: Optional[float] = None,
        payout: Optional[float] = None,
        won: Optional[bool] = None,
    ) -> float:
        """Aplica o PnL uma única vez.

        Se a compra já gravou `balance_after`, o stake saiu naquele momento:
        na vitória entra só o payout; na derrota o saldo não é debitado de novo.
        """
        del stake  # o stake já está refletido em balance_after ou em pnl
        if not self._auth_info:
            return 0.0
        if self._open_balance_debits > 0 and won is not None and payout is not None:
            delta = float(payout) if won else 0.0
            self._open_balance_debits -= 1
        else:
            delta = float(pnl)
        self._auth_info.balance = round(self._auth_info.balance + delta, 2)
        return self._auth_info.balance

    def set_balance(self, new_balance: float) -> float:
        """Define saldo apenas no simulador opt-in. Conta demo usa o saldo da Deriv."""
        if self.session_mode != "simulator" or not self.simulator_enabled:
            raise DerivOperationalError(
                message="Saldo manual só existe no simulador opt-in.",
                detail=(
                    "Com sessão DEMO o saldo vem da Deriv e não é inventado. "
                    "DERIV_SIMULATOR=true sem token liga o simulador."
                ),
                code="SIMULATOR_ONLY",
                http_status=409,
            )
        bal = round(float(new_balance), 2)
        if self._auth_info is None:
            self.enable_explicit_simulator(bal)
        else:
            self._auth_info.balance = bal
        return bal

    async def get_open_contract(self, contract_id: int | str) -> dict:
        """Consulta o status atual ou final de um contrato em andamento."""
        if str(contract_id).startswith("SIM_"):
            return {}
        cid: int | str = int(contract_id) if str(contract_id).isdigit() else contract_id
        payload = {"proposal_open_contract": 1, "contract_id": cid}
        try:
            response = await self.send_raw_request(payload)
            if "error" in response:
                return {}
            return response.get("proposal_open_contract", {})
        except Exception as exc:
            logger.warning("Falha ao consultar status do contrato %s: %s", contract_id, exc)
            return {}

    async def _listen_loop(self) -> None:
        """Loop de escuta e distribuição de mensagens assíncronas do WebSocket."""
        try:
            while self._ws and self.is_connected:
                raw_msg = await self._ws.recv()
                self._handle_message(raw_msg)
        except asyncio.CancelledError:
            pass
        except websockets.exceptions.ConnectionClosed as cc:
            logger.warning("Conexão WebSocket com Deriv interrompida: %s. Acionando reconexão...", cc)
            self.state = DerivConnectionState.DISCONNECTED
        except Exception as exc:
            logger.error("Erro no loop de escuta Deriv: %s. Acionando reconexão...", exc)
            self.state = DerivConnectionState.ERROR
        finally:
            if self._should_reconnect and not self._is_reconnecting and not self._suppress_reconnect:
                if self._reconnect_task and not self._reconnect_task.done():
                    self._reconnect_task.cancel()
                self._reconnect_task = asyncio.create_task(self._trigger_reconnect())

    async def _heartbeat_loop(self) -> None:
        """Envia ping em nível de aplicação a cada 20s para manter a conexão WebSocket viva."""
        try:
            while self._should_reconnect:
                await asyncio.sleep(20.0)
                if self._ws and self.is_connected:
                    try:
                        await self.send_raw_request({"ping": 1})
                        logger.debug("Heartbeat ping enviado à Deriv.")
                    except Exception as ping_err:
                        logger.warning("Falha ao enviar heartbeat ping: %s", ping_err)
                        break
        except asyncio.CancelledError:
            pass

    async def _trigger_reconnect(self) -> None:
        """Reconecta, pede OTP novo no caso de PAT, e re-inscreve os símbolos."""
        if not self._should_reconnect or self._is_reconnecting:
            return

        self._is_reconnecting = True
        logger.info("Iniciando rotina de reconexão automática com a Deriv...")
        self.state = DerivConnectionState.CONNECTING

        delay = 1.5
        max_delay = 20.0
        while self._should_reconnect:
            try:
                if self.demo_token and str(self.demo_token).startswith("pat_"):
                    await self.authorize(self.demo_token)
                else:
                    await self.connect()
                    if self.demo_token:
                        await self.authorize(self.demo_token)
                for sym in list(self._active_symbols):
                    try:
                        await self.subscribe_ticks(sym)
                        logger.info("Re-subscrição de ticks para %s confirmada na reconexão.", sym)
                    except Exception as sub_err:
                        logger.error("Falha ao re-subscrever %s: %s", sym, sub_err)

                logger.info("Conexão com a Deriv restabelecida no canal %s.", self._trading_channel)
                break
            except Exception as rec_err:
                logger.warning("Tentativa de reconexão falhou (%s). Nova tentativa em %.1fs...", rec_err, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)

        self._is_reconnecting = False

    def _handle_message(self, raw_msg: str) -> None:
        """Processa e despacha mensagens recebidas do WebSocket."""
        try:
            data = json.loads(raw_msg)
        except Exception as exc:
            logger.error("Erro ao decodificar JSON recebido: %s", exc)
            return

        req_id = data.get("req_id")
        if req_id is not None and req_id in self._pending_requests:
            future = self._pending_requests.pop(req_id)
            if not future.done():
                future.set_result(data)

        if "tick" in data:
            try:
                tick = TickData.from_api_payload(data["tick"])
                self._dispatch_tick(tick)
            except Exception as exc:
                logger.error("Erro ao processar tick: %s", exc)

    def _dispatch_tick(self, tick: TickData) -> None:
        """Envia o tick estruturado para todos os ouvintes registrados."""
        for callback in self._tick_callbacks:
            try:
                res = callback(tick)
                if inspect.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception as exc:
                logger.exception("Erro ao executar callback de tick: %s", exc)
