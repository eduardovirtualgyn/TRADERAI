"""Suíte de testes automatizados para diagnóstico, resiliência e tratamento de erros do Deriv WebSocket."""

import asyncio
import socket
import ssl
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

from backend.app.api.v1.deriv import DerivConnectPayload, connect_deriv
from backend.app.core.config import Settings
from backend.app.core.errors import (
    DerivAuthError,
    DerivConfigError,
    DerivConnectionError,
    DerivOperationalError,
    TraderSecurityError,
)
from backend.app.modules.deriv_client.client import (
    DerivConnectionState,
    DerivWebSocketClient,
    sanitize_token,
)
from backend.app.modules.deriv_client.models import DerivAuthorizeResponse


def run_coro(coro):
    """Helper síncrono para execução segura de corrotinas em ambiente Windows Sandbox."""
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value
    raise RuntimeError("Corrotina suspendeu sem finalizar.")


def test_classify_http_520_handshake_rejection():
    """Garante que HTTP 520 é classificado como Erro de Conectividade e NÃO de autenticação."""
    client = DerivWebSocketClient()
    mock_exc = Exception("server rejected WebSocket connection: HTTP 520")

    err = client._parse_connection_exception(mock_exc)
    assert isinstance(err, DerivConnectionError)
    assert err.error_type == "Falha de conectividade"
    assert err.code == "WS_CONNECTION_FAILED"
    assert err.http_status == 520
    assert err.stage == "CONNECTIVITY / HANDSHAKE"
    assert "Cloudflare/Deriv" in err.detail

    payload = err.to_dict()
    assert payload["success"] is False
    assert payload["http_status"] == 520


def test_classify_timeout_error():
    """Garante que timeout de handshake é classificado corretamente."""
    client = DerivWebSocketClient()
    timeout_exc = asyncio.TimeoutError("Connection timed out")

    err = client._parse_connection_exception(timeout_exc)
    assert isinstance(err, DerivConnectionError)
    assert err.code == "WS_TIMEOUT"
    assert err.http_status == 504
    assert err.stage == "CONNECTIVITY / HANDSHAKE"


def test_classify_dns_resolution_failure():
    """Garante que falha de DNS (socket.gaierror) é identificada."""
    client = DerivWebSocketClient()
    dns_exc = socket.gaierror(-3, "Temporary failure in name resolution")

    err = client._parse_connection_exception(dns_exc)
    assert isinstance(err, DerivConnectionError)
    assert err.code == "WS_DNS_FAILED"
    assert err.http_status == 502


def test_classify_tls_ssl_handshake_failure():
    """Garante que falha na negociação TLS/SSL é identificada."""
    client = DerivWebSocketClient()
    ssl_exc = ssl.SSLError("CERTIFICATE_VERIFY_FAILED")

    err = client._parse_connection_exception(ssl_exc)
    assert isinstance(err, DerivConnectionError)
    assert err.code == "WS_SSL_FAILED"
    assert err.http_status == 525


def test_token_sanitization_security():
    """Garante que tokens nunca são expostos em texto claro nos logs ou serializações."""
    raw_token = "pat_3d3166daa98c3ec98dd22eb12c71296f4657321122f60f715fbf5571b615d13d"
    masked = sanitize_token(raw_token)
    assert masked.startswith("pat_3d")
    assert masked.endswith("d13d")
    assert "..." in masked
    assert "98dd22eb" not in masked

    assert sanitize_token(None) == "[NENHUM]"
    assert sanitize_token("123") == "****"


def test_classify_invalid_token_authentication_error():
    """Garante que erro retornado pela Deriv em 'authorize' é classificado como Falha de Autenticação."""
    client = DerivWebSocketClient()
    client.state = DerivConnectionState.CONNECTED
    client._ws = MagicMock()
    client._ws.closed = False

    fake_response = {
        "error": {
            "code": "InvalidToken",
            "message": "The token provided is invalid or has expired.",
        }
    }

    async def fake_send_raw(payload):
        return fake_response

    client.send_raw_request = fake_send_raw

    with pytest.raises(DerivAuthError) as exc_info:
        run_coro(client.authorize(token="invalid_token_xyz"))

    err = exc_info.value
    assert err.error_type == "Falha de autenticação"
    assert err.code == "InvalidToken"
    assert err.http_status == 401
    assert err.stage == "AUTHORIZATION"


def test_authorize_missing_token_raises_config_error():
    """Garante que ausência de token é tratada como erro de configuração."""
    client = DerivWebSocketClient(demo_token=None)
    with pytest.raises(DerivConfigError) as exc_info:
        run_coro(client.authorize(token=None))

    err = exc_info.value
    assert err.error_type == "Falha de configuração"
    assert err.code == "MISSING_TOKEN"


def test_api_connect_returns_structured_502_on_connection_error():
    """Valida que o endpoint POST /api/v1/deriv/connect retorna estrutura padronizada em falha de rede."""
    mock_client = MagicMock(spec=DerivWebSocketClient)
    mock_client.is_connected = False
    mock_client.demo_token = "token123"

    async def fake_connect():
        raise DerivConnectionError(
            message="Não foi possível estabelecer conexão com a Deriv API.",
            detail="Handshake WebSocket rejeitado pela infraestrutura de borda Cloudflare/Deriv (HTTP 520).",
            code="WS_CONNECTION_FAILED",
            http_status=520,
        )

    mock_client.connect = fake_connect

    with pytest.raises(HTTPException) as exc_info:
        run_coro(
            connect_deriv(
                payload=DerivConnectPayload(token="test_token"),
                settings=Settings(),
                client=mock_client,
                collector=MagicMock(),
                risk_manager=MagicMock(),
            )
        )

    exc = exc_info.value
    assert exc.status_code == 502
    assert exc.detail["error_type"] == "Falha de conectividade"
    assert exc.detail["code"] == "WS_CONNECTION_FAILED"
    assert exc.detail["http_status"] == 520
    assert exc.detail["stage"] == "CONNECTIVITY / HANDSHAKE"


def test_api_connect_returns_structured_401_on_auth_error():
    """Valida que o endpoint POST /api/v1/deriv/connect retorna 401 quando o token é rejeitado pela Deriv."""
    mock_client = MagicMock(spec=DerivWebSocketClient)
    mock_client.is_connected = True
    mock_client.demo_token = "token123"

    async def fake_authorize(token=None):
        raise DerivAuthError(
            message="Falha de autenticação na Deriv API.",
            detail="Deriv rejeitou o token: Token expirado (Código: InvalidToken)",
            code="InvalidToken",
            http_status=401,
        )

    mock_client.authorize = fake_authorize

    with pytest.raises(HTTPException) as exc_info:
        run_coro(
            connect_deriv(
                payload=DerivConnectPayload(token="expired_token"),
                settings=Settings(),
                client=mock_client,
                collector=MagicMock(),
                risk_manager=MagicMock(),
            )
        )

    exc = exc_info.value
    assert exc.status_code == 401
    assert exc.detail["error_type"] == "Falha de autenticação"
    assert exc.detail["code"] == "InvalidToken"
    assert exc.detail["http_status"] == 401
    assert exc.detail["stage"] == "AUTHORIZATION"


def test_api_connect_success_demo_account():
    """Valida que connect_deriv autoriza e assina ticks quando tudo está correto em conta virtual DEMO."""
    mock_client = MagicMock(spec=DerivWebSocketClient)
    mock_client.is_connected = True
    mock_client.demo_token = "token123"
    mock_client.state = DerivConnectionState.AUTHORIZED

    async def fake_authorize(token=None):
        return DerivAuthorizeResponse(
            is_virtual=True,
            loginid="VRTC9999",
            balance=5000.0,
            currency="USD",
        )

    mock_client.authorize = fake_authorize

    async def fake_sub(symbol):
        return None

    mock_client.subscribe_ticks = fake_sub

    mock_risk = MagicMock()

    res = run_coro(
        connect_deriv(
            payload=DerivConnectPayload(token="valid_demo_token", symbol="R_100"),
            settings=Settings(),
            client=mock_client,
            collector=MagicMock(),
            risk_manager=mock_risk,
        )
    )

    assert res["success"] is True
    assert res["is_authorized"] is True
    assert res["loginid"] == "VRTC9999"
    assert res["balance"] == 5000.0
    assert mock_risk.balance_usd == 5000.0
