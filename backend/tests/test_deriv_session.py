"""Regressões da sessão Deriv: shape oficial, conta real, 401 e simulador explícito."""

import io
import json
from email.message import Message
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.core.errors import (
    DerivAuthError,
    DerivConfigError,
    DerivOperationalError,
    TraderSecurityError,
)
from backend.app.modules.contract_executor.executor import ContractExecutor
from backend.app.modules.contract_executor.models import OrderRequest
from backend.app.modules.deriv_client.client import (
    DerivWebSocketClient,
    classify_options_account,
    parse_options_accounts,
)
from backend.app.modules.deriv_client.models import DerivAuthorizeResponse, DerivConnectionState
from backend.app.modules.risk_manager.risk_rules import RiskManager


def test_parse_official_accounts_payload():
    payload = {
        "data": [
            {"account_id": "CR1", "account_type": "real", "balance": 10, "currency": "USD"},
            {"account_id": "VRTC9001", "account_type": "demo", "balance": "10000.00", "currency": "USD"},
        ]
    }
    accounts = parse_options_accounts(payload)
    assert [classify_options_account(account) for account in accounts] == ["real", "demo"]
    assert parse_options_accounts({"accounts": [{"is_virtual": 1, "loginid": "VRTC1"}]})


class _Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error(status: int, payload: dict):
    import urllib.error

    return urllib.error.HTTPError(
        url="http://offline.test/accounts",
        code=status,
        msg="error",
        hdrs=Message(),
        fp=io.BytesIO(json.dumps(payload).encode()),
    )


@pytest.mark.asyncio
async def test_pat_official_shape_opens_demo_otp_socket():
    client = DerivWebSocketClient(app_id=1089, rest_base_url="http://offline.test")
    calls = []

    def fake_urlopen(request, timeout=8):
        calls.append((request.get_method(), request.full_url))
        if request.get_method() == "GET":
            return _Response(
                {
                    "data": [
                        {
                            "account_id": "VRTC9001",
                            "account_type": "demo",
                            "currency": "USD",
                            "balance": "10000.00",
                        }
                    ]
                }
            )
        return _Response(
            {
                "data": {
                    "otp": "otp-test",
                    "url": "ws://127.0.0.1/trading/v1/options/ws/demo?otp=otp-test",
                }
            }
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client._connect_exact = AsyncMock()
        auth = await client.authorize("pat_unit_test_token_not_real")

    assert auth.loginid == "VRTC9001"
    assert auth.is_virtual is True
    assert auth.balance == 10000.0
    assert client.session_mode == "demo"
    assert client.is_simulated is False
    assert client.trading_channel == "demo"
    opened = client._connect_exact.await_args.args[0]
    assert "/ws/demo" in opened and "otp=" in opened
    assert "/ws/real" not in opened
    assert any(method == "POST" and "/VRTC9001/otp" in url for method, url in calls)
    assert client.auth_info.loginid != "VRTC_SIMULATOR"


@pytest.mark.asyncio
async def test_real_only_token_is_refused_and_not_simulated():
    client = DerivWebSocketClient(rest_base_url="http://offline.test")

    def fake_urlopen(request, timeout=8):
        return _Response(
            {
                "data": [
                    {
                        "account_id": "CR999999",
                        "account_type": "real",
                        "currency": "USD",
                        "balance": 50,
                    }
                ]
            }
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(TraderSecurityError, match="conta REAL"):
            await client.authorize("pat_unit_test_token_not_real")

    assert client.is_authorized is False
    assert client.auth_info is None
    assert client.session_mode == "error"
    assert "SIMULATOR" not in (client.last_error or "")
    assert client.last_error


@pytest.mark.asyncio
async def test_otp_real_websocket_is_refused():
    client = DerivWebSocketClient(rest_base_url="http://offline.test")

    def fake_urlopen(request, timeout=8):
        if request.get_method() == "GET":
            return _Response(
                {
                    "data": [
                        {
                            "account_id": "VRTC9001",
                            "account_type": "demo",
                            "currency": "USD",
                            "balance": 10000,
                        }
                    ]
                }
            )
        return _Response(
            {"data": {"otp": "nope", "url": "wss://api.derivws.com/trading/v1/options/ws/real?otp=nope"}}
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(TraderSecurityError, match="/ws/real"):
            await client.authorize("pat_unit_test_token_not_real")

    assert client.is_authorized is False
    assert client.session_mode == "error"


@pytest.mark.asyncio
async def test_http_401_does_not_create_simulator():
    client = DerivWebSocketClient(rest_base_url="http://offline.test")

    def fake_urlopen(request, timeout=8):
        raise _http_error(401, {"errors": [{"code": "Unauthorized", "message": "Invalid token"}]})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(DerivAuthError, match="401"):
            await client.authorize("pat_unit_test_token_not_real")

    assert client.auth_info is None
    assert client.session_mode == "error"
    assert client.is_simulated is False


@pytest.mark.asyncio
async def test_missing_token_does_not_invent_simulator():
    client = DerivWebSocketClient(demo_token=None, simulator_enabled=False)
    with pytest.raises(DerivConfigError, match="ausente"):
        await client.authorize(None)
    assert client.auth_info is None
    assert client.session_mode == "error"


@pytest.mark.asyncio
async def test_unknown_method_does_not_simulate():
    client = DerivWebSocketClient()
    client.state = DerivConnectionState.CONNECTED
    client._ws = type("WS", (), {"closed": False})()

    async def fake_send(payload):
        return {"error": {"code": "UnknownMethod", "message": "authorize is not supported"}}

    client.send_raw_request = fake_send
    with pytest.raises(DerivOperationalError, match="não aceita authorize"):
        await client.authorize("legacy_token_not_a_pat")
    assert client.auth_info is None
    assert client.session_mode == "error"


@pytest.mark.asyncio
async def test_buy_on_public_channel_is_refused():
    client = DerivWebSocketClient()
    client.state = DerivConnectionState.AUTHORIZED
    client.session_mode = "demo"
    client._trading_channel = "public"
    client._auth_info = DerivAuthorizeResponse(True, "VRTC1", "USD", 10000.0)

    async def fake_send(payload):
        raise AssertionError("buy não pode sair no canal público")

    client.send_raw_request = fake_send
    with pytest.raises(DerivOperationalError, match="WebSocket DEMO"):
        await client.buy("prop-1", 1.0)
    assert client.auth_info.balance == 10000.0


@pytest.mark.asyncio
async def test_buy_authorization_required_is_not_simulated():
    client = DerivWebSocketClient()
    client.state = DerivConnectionState.AUTHORIZED
    client.session_mode = "demo"
    client._trading_channel = "demo"
    client._ws = type("WS", (), {"closed": False})()
    client._auth_info = DerivAuthorizeResponse(True, "VRTC1", "USD", 10000.0)

    async def fake_send(payload):
        return {"error": {"code": "AuthorizationRequired", "message": "Please log in"}}

    client.send_raw_request = fake_send
    with pytest.raises(DerivOperationalError, match="recusou a compra") as exc_info:
        await client.buy("prop-1", 1.0)
    assert "Nenhuma ordem simulada" in exc_info.value.detail
    assert client.auth_info.balance == 10000.0


@pytest.mark.asyncio
async def test_simulator_is_opt_in_and_debits_once():
    client = DerivWebSocketClient(simulator_enabled=True)
    client.enable_explicit_simulator(100.0)
    assert client.is_simulated is True
    assert client.auth_info.loginid == "SIMULATOR"

    risk = RiskManager(
        initial_balance_usd=100.0,
        max_stake_usd=5.0,
        max_stake_percent=0.05,
        max_daily_loss_usd=50.0,
        max_consecutive_losses=5,
    )
    executor = ContractExecutor(deriv_client=client, risk_manager=risk)
    order = OrderRequest(
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.0,
        estimated_probability=0.60,
        wilson_lower_bound=0.55,
        strategy_name="simulador",
    )
    bought = await executor.execute_order(order)
    assert bought.success is True
    assert str(bought.contract_id).startswith("SIM_")
    assert client.auth_info.balance == pytest.approx(100.0)

    lost = executor.settle_contract(bought.contract_id, won=False, exit_digit=1)
    assert lost.net_pnl == pytest.approx(-1.0)
    assert client.auth_info.balance == pytest.approx(99.0)
    assert risk.balance_usd == pytest.approx(99.0)

    won_order = await executor.execute_order(order)
    won = executor.settle_contract(won_order.contract_id, won=True, exit_digit=2)
    assert won.net_pnl == pytest.approx(0.95)
    assert client.auth_info.balance == pytest.approx(99.95)
    assert risk.balance_usd == pytest.approx(99.95)


def test_manual_balance_requires_simulator():
    client = DerivWebSocketClient(simulator_enabled=False)
    with pytest.raises(DerivOperationalError, match="simulador"):
        client.set_balance(250)
    assert client.auth_info is None
