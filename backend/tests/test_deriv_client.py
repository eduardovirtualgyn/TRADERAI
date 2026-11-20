"""Testes unitários para o cliente WebSocket da Deriv e modelos de dados."""

import json
from unittest.mock import MagicMock
import pytest

from backend.app.core.errors import TraderSecurityError
from backend.app.modules.deriv_client.client import (
    DerivWebSocketClient,
    extract_last_digit,
)
from backend.app.modules.deriv_client.models import (
    ContractBuyResult,
    DerivConnectionState,
    ProposalData,
    TickData,
)


def test_extract_last_digit_precision():
    """Garante que a extração de dígitos respeita o pip_size inclusive em zeros à direita."""
    assert extract_last_digit(1024.58, pip_size=2) == 8
    assert extract_last_digit(1024.60, pip_size=2) == 0  # Zero trailing
    assert extract_last_digit(984.31, pip_size=2) == 1
    assert extract_last_digit(12.34567, pip_size=5) == 7
    assert extract_last_digit(50.0, pip_size=2) == 0


def test_tick_data_from_api_payload():
    """Testa criação e tipagem de TickData a partir do formato da Deriv API."""
    even_payload = {
        "epoch": 1700000001,
        "quote": 2501.84,
        "pip_size": 2,
        "symbol": "R_100",
    }
    tick_even = TickData.from_api_payload(even_payload)
    assert tick_even.symbol == "R_100"
    assert tick_even.epoch == 1700000001
    assert tick_even.quote == 2501.84
    assert tick_even.last_digit == 4
    assert tick_even.is_even is True

    odd_payload = {
        "epoch": 1700000002,
        "quote": 2501.87,
        "pip_size": 2,
        "symbol": "R_100",
    }
    tick_odd = TickData.from_api_payload(odd_payload)
    assert tick_odd.last_digit == 7
    assert tick_odd.is_even is False


def test_proposal_data_calculations():
    """Valida cálculo de payout líquido e multiplicador de payout em propostas."""
    proposal_dict = {
        "id": "prop_998877",
        "ask_price": 10.00,
        "payout": 19.50,
        "spot": 2500.12,
        "spot_time": 1700000010,
    }
    proposal = ProposalData.from_api_payload(
        proposal_dict=proposal_dict,
        contract_type="DIGITEVEN",
        symbol="R_100",
    )
    assert proposal.proposal_id == "prop_998877"
    assert proposal.ask_price == 10.00
    assert proposal.payout == 19.50
    assert pytest.approx(proposal.net_payout) == 9.50
    assert pytest.approx(proposal.payout_ratio) == 1.95


def test_contract_buy_result_parsing():
    """Valida parsing e cálculo de retorno pós-compra do contrato."""
    buy_dict = {
        "contract_id": "cnt_12345",
        "transaction_id": "tx_67890",
        "buy_price": 5.00,
        "payout": 9.75,
        "balance_after": 995.00,
        "shortcode": "DIGITEVEN_R_100_1t",
        "start_time": 1700000020,
    }
    res = ContractBuyResult.from_api_payload(buy_dict, price=5.00)
    assert res.contract_id == "cnt_12345"
    assert res.transaction_id == "tx_67890"
    assert res.buy_price == 5.00
    assert res.payout == 9.75
    assert res.balance_after == 995.00


def test_tick_callback_dispatch():
    """Testa o registro e despacho de eventos de novos ticks para múltiplos callbacks."""
    client = DerivWebSocketClient()
    received_ticks = []

    def on_tick(tick: TickData):
        received_ticks.append(tick)

    client.register_tick_callback(on_tick)

    # Simula mensagem de tick recebida
    tick_raw = json.dumps({
        "tick": {
            "epoch": 1700000050,
            "quote": 3410.22,
            "pip_size": 2,
            "symbol": "R_100",
        }
    })
    client._handle_message(tick_raw)

    assert len(received_ticks) == 1
    assert received_ticks[0].last_digit == 2
    assert received_ticks[0].is_even is True

    # Desregistra e garante que não recebe mais
    client.unregister_tick_callback(on_tick)
    client._handle_message(tick_raw)
    assert len(received_ticks) == 1


def test_handle_pending_request_future():
    """Testa se mensagens de resposta resolvem o Future correto através do req_id."""
    client = DerivWebSocketClient()
    mock_future = MagicMock()
    mock_future.done.return_value = False
    client._pending_requests[42] = mock_future

    reply = {"req_id": 42, "ping": "pong"}
    client._handle_message(json.dumps(reply))

    mock_future.set_result.assert_called_once_with(reply)
    assert 42 not in client._pending_requests


def test_reject_invalid_proposal_contract_type():
    """Garante que apenas DIGITEVEN e DIGITODD são aceitos na proposta."""
    client = DerivWebSocketClient()

    with pytest.raises(ValueError, match="Tipo de contrato inválido"):
        coro = client.get_proposal(
            symbol="R_100",
            contract_type="CALL",  # Proibido no escopo Odd/Even
            amount=5.0,
        )
        try:
            coro.send(None)
        except StopIteration:
            pass


def test_authorize_safeguard_accepts_virtual_account():
    """Testa aprovação de autorização quando a conta é virtual (DEMO: is_virtual=1)."""
    client = DerivWebSocketClient()
    auth_data = {
        "is_virtual": 1,
        "loginid": "VRTC123456",
        "currency": "USD",
        "balance": 10000.0,
        "email": "demo@user.com",
    }
    auth_resp = client._validate_auth_payload(auth_data)
    assert auth_resp.is_virtual is True
    assert auth_resp.loginid == "VRTC123456"
    assert auth_resp.balance == 10000.0
    assert auth_resp.currency == "USD"


def test_authorize_safeguard_blocks_real_account():
    """Garante que se a Deriv retornar is_virtual=0 (conta REAL), o sistema aborta com erro crítico."""
    client = DerivWebSocketClient()
    real_auth_data = {
        "is_virtual": 0,  # CONTA REAL!
        "loginid": "CR999999",
        "currency": "USD",
        "balance": 5000.0,
    }
    with pytest.raises(TraderSecurityError, match="A conta conectada é REAL"):
        client._validate_auth_payload(real_auth_data)


def test_client_initial_state():
    """Valida estado inicial e propriedades do cliente."""
    client = DerivWebSocketClient(ws_url="wss://ws.derivws.com/websockets/v3", app_id="1089")
    assert client.state == DerivConnectionState.DISCONNECTED
    assert client.is_connected is False
    assert client.is_authorized is False
    assert client.auth_info is None

    # Valida detecção ativa da propriedade is_connected
    client.state = DerivConnectionState.CONNECTED
    fake_ws = MagicMock()
    fake_ws.closed = False
    client._ws = fake_ws
    assert client.is_connected is True

    fake_ws.closed = True
    assert client.is_connected is False
