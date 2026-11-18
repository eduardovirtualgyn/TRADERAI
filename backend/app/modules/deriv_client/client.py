"""Cliente assíncrono para comunicação com a Deriv WebSocket API.

Implementa salvaguardas de conta DEMO, extração precisa de dígitos e heartbeat contínuo.
"""

import asyncio
import json
import ssl
from typing import Any, Callable, Dict, List, Optional
import websockets
from websockets.client import WebSocketClientProtocol

from backend.app.core.errors import DerivApiError, TraderSecurityError
from backend.app.core.logging import logger
from backend.app.modules.deriv_client.models import (
    ContractBuyResult,
    DerivAuthorizeResponse,
    DerivConnectionState,
    ProposalData,
    TickData,
)


def extract_last_digit(quote: float, pip_size: int = 2) -> int:
    """Extrai o último dígito decimal do quote considerando o pip_size oficial.

    Exemplo: quote=1024.58, pip_size=2 -> '1024.58' -> 8
             quote=1024.6, pip_size=2  -> '1024.60' -> 0 (Zero relevante!)
    """
    formatted = f"{quote:.{pip_size}f}"
    return int(formatted[-1])


class DerivWebSocketClient:
    """Cliente oficial para Deriv WebSocket API com guardas ativas de segurança."""

    def __init__(
        self,
        ws_url: str = "wss://ws.derivws.com/websockets/v3",
        app_id: int = 1089,
        demo_token: Optional[str] = None,
    ):
        self.ws_url = ws_url
        self.app_id = app_id
        self.demo_token = demo_token

        self.state = DerivConnectionState.DISCONNECTED
        self._ws: Optional[WebSocketClientProtocol] = None
        self._auth_info: Optional[DerivAuthorizeResponse] = None

        self._req_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._tick_callbacks: List[Callable[[TickData], None]] = []
        self._listener_task: Optional[asyncio.Task] = None
        self._active_symbols: List[str] = []

    @property
    def is_connected(self) -> bool:
        """Indica se a conexão WebSocket com a Deriv está ativa."""
        return (
            self.state in (DerivConnectionState.CONNECTED, DerivConnectionState.AUTHORIZED)
            and self._ws is not None
            and not getattr(self._ws, "closed", True)
        )

    @property
    def is_authorized(self) -> bool:
        """Indica se o cliente está autenticado em conta virtual DEMO."""
        return self.state == DerivConnectionState.AUTHORIZED and self._auth_info is not None

    @property
    def auth_info(self) -> Optional[DerivAuthorizeResponse]:
        """Retorna os dados cadastrais da sessão autenticada."""
        return self._auth_info

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

    def _build_url(self, base_url: str) -> str:
        """Formata a URL do WebSocket garantindo endpoint v3 e parâmetros oficiais."""
        clean = base_url.strip().strip("'\"").rstrip("/")
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

    def _get_candidate_endpoints(self) -> List[str]:
        """Gera lista ordenada de endpoints WebSocket com failover automático."""
        endpoints: List[str] = []
        if self.ws_url:
            endpoints.append(self._build_url(self.ws_url))

        fallbacks = [
            "wss://ws.derivws.com/websockets/v3",
            "wss://frontend.binaryws.com/websockets/v3",
            "wss://ws.binaryws.com/websockets/v3",
        ]
        for fb in fallbacks:
            candidate = self._build_url(fb)
            if candidate not in endpoints:
                endpoints.append(candidate)
        return endpoints

    async def connect(self) -> None:
        """Estabelece a conexão WebSocket com o gateway da Deriv usando failover e headers defensivos."""
        self.state = DerivConnectionState.CONNECTING
        candidates = self._get_candidate_endpoints()
        last_error: Optional[Exception] = None

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2

        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        )
        origin = "https://app.deriv.com"
        headers = {
            "Accept-Language": "en-US,en;q=0.9",
        }

        for url in candidates:
            logger.info("Tentando conexão WebSocket com Deriv em %s...", url)
            try:
                self._ws = await websockets.connect(
                    url,
                    origin=origin,
                    user_agent_header=user_agent,
                    additional_headers=headers,
                    ssl=ssl_ctx,
                    open_timeout=8.0,
                    ping_interval=30,
                    ping_timeout=10,
                )
                self.state = DerivConnectionState.CONNECTED
                logger.info("✅ Conexão WebSocket estabelecida com sucesso via %s.", url)
                self._listener_task = asyncio.create_task(self._listen_loop())
                return
            except Exception as exc:
                last_error = exc
                logger.warning("Falha ao conectar via %s: %s. Tentando próximo endpoint...", url, exc)

        self.state = DerivConnectionState.ERROR
        logger.error("Todos os endpoints WebSocket da Deriv falharam. Último erro: %s", last_error)
        raise DerivApiError(f"Falha de conexão com a Deriv: {last_error}") from last_error

    async def disconnect(self) -> None:
        """Encerra a conexão WebSocket e cancela tarefas de segundo plano."""
        logger.info("Desconectando cliente Deriv...")
        self.state = DerivConnectionState.DISCONNECTED

        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()
            self._ws = None

        # Rejeita requisições pendentes
        for req_id, future in self._pending_requests.items():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()
        self._auth_info = None

    async def send_raw_request(self, payload: dict) -> dict:
        """Envia um comando JSON com rastreamento por req_id e aguarda a resposta."""
        if not self._ws or self._ws.closed:
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

    async def authorize(self, token: Optional[str] = None) -> DerivAuthorizeResponse:
        """Autentica na API e valida estritamente a salvaguarda de conta DEMO."""
        auth_token = token or self.demo_token
        if not auth_token:
            raise TraderSecurityError(
                "Nenhum token fornecido. O token de conta DEMO é obrigatório."
            )

        response = await self.send_raw_request({"authorize": auth_token})

        if "error" in response:
            err = response["error"]
            raise DerivApiError(f"Erro de autenticação na Deriv: {err.get('message', err)}")

        auth_data = response.get("authorize", {})
        self._auth_info = self._validate_auth_payload(auth_data)
        self.state = DerivConnectionState.AUTHORIZED
        logger.info(
            "✅ Autenticado com sucesso em conta DEMO: %s (Saldo: %s %s)",
            self._auth_info.loginid,
            self._auth_info.balance,
            self._auth_info.currency,
        )
        return self._auth_info

    def _validate_auth_payload(self, auth_data: dict) -> DerivAuthorizeResponse:
        """Valida se o payload de autorização cumpre a salvaguarda de conta DEMO."""
        is_virtual = bool(auth_data.get("is_virtual", 0))

        # SALVAGUARDA CARDINAL: Se a conta não for virtual (demo), abortar com erro crítico!
        if not is_virtual:
            logger.critical(
                "🚨 VIOLAÇÃO GRAVE: Conta REAL (%s) conectada! Abortando imediatamente.",
                auth_data.get("loginid", "desconhecido"),
            )
            raise TraderSecurityError(
                "VIOLAÇÃO DE SEGURANÇA: A conta conectada é REAL (is_virtual=0). "
                "O ODD/EVEN AI TRADER opera EXCLUSIVAMENTE em ambiente DEMO."
            )

        return DerivAuthorizeResponse(
            is_virtual=True,
            loginid=str(auth_data.get("loginid", "")),
            currency=str(auth_data.get("currency", "USD")),
            balance=float(auth_data.get("balance", 0.0)),
            email=auth_data.get("email"),
            user_id=auth_data.get("user_id"),
        )

    async def subscribe_ticks(self, symbol: str) -> None:
        """Assina o feed de cotações em tempo real para um símbolo sintético."""
        response = await self.send_raw_request({"ticks": symbol, "subscribe": 1})

        if "error" in response:
            err = response["error"]
            raise DerivApiError(f"Erro ao assinar ticks de {symbol}: {err.get('message', err)}")

        if symbol not in self._active_symbols:
            self._active_symbols.append(symbol)
        logger.info("Subscrição de ticks ativada para %s.", symbol)

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

        payload = {
            "proposal": 1,
            "amount": float(amount),
            "basis": "stake",
            "currency": "USD",
            "symbol": symbol,
            "duration": int(duration),
            "duration_unit": duration_unit,
            "contract_type": contract_type,
        }

        response = await self.send_raw_request(payload)

        if "error" in response:
            err = response["error"]
            raise DerivApiError(f"Erro ao obter proposta: {err.get('message', err)}")

        proposal_dict = response.get("proposal", {})
        return ProposalData.from_api_payload(
            proposal_dict=proposal_dict,
            contract_type=contract_type,
            symbol=symbol,
        )

    async def buy(self, proposal_id: str, price: float) -> ContractBuyResult:
        """Executa a compra de um contrato previamente cotado via proposta."""
        if not self.is_authorized:
            raise TraderSecurityError("Operação de compra requer sessão DEMO autorizada.")

        payload = {
            "buy": str(proposal_id),
            "price": float(price),
        }

        response = await self.send_raw_request(payload)

        if "error" in response:
            err = response["error"]
            raise DerivApiError(f"Erro ao comprar contrato: {err.get('message', err)}")

        buy_dict = response.get("buy", {})
        return ContractBuyResult.from_api_payload(buy_dict, price)

    async def _listen_loop(self) -> None:
        """Loop de escuta e distribuição de mensagens assíncronas do WebSocket."""
        try:
            while self._ws and not self._ws.closed:
                raw_msg = await self._ws.recv()
                self._handle_message(raw_msg)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Erro no loop de escuta Deriv: %s", exc)
            self.state = DerivConnectionState.ERROR

    def _handle_message(self, raw_msg: str) -> None:
        """Processa e despacha mensagens recebidas do WebSocket."""
        try:
            data = json.loads(raw_msg)
        except Exception as exc:
            logger.error("Erro ao decodificar JSON recebido: %s", exc)
            return

        # 1. Trata respostas a requisições com req_id
        req_id = data.get("req_id")
        if req_id is not None and req_id in self._pending_requests:
            future = self._pending_requests.pop(req_id)
            if not future.done():
                future.set_result(data)

        # 2. Trata feed contínuo de ticks
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
                callback(tick)
            except Exception as exc:
                logger.exception("Erro ao executar callback de tick: %s", exc)
