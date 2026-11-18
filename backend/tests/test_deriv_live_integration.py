import asyncio
import socket
import pytest
from backend.app.modules.deriv_client.client import DerivWebSocketClient
from backend.app.modules.deriv_client.models import DerivConnectionState, TickData


def _is_online() -> bool:
    try:
        socket.create_connection(("api.derivws.com", 443), timeout=1).close()
        return True
    except Exception:
        return False


@pytest.mark.asyncio
@pytest.mark.skipif(not _is_online(), reason="Requer conexão com internet ativa (fora do sandbox)")
async def test_deriv_client_live_connection_and_ticks():
    client = DerivWebSocketClient(ws_url="wss://api.derivws.com/trading/v1/options/ws/public")
    received_ticks = []

    def on_tick(tick: TickData):
        received_ticks.append(tick)

    client.register_tick_callback(on_tick)

    # 1. Conecta
    await client.connect()
    assert client.is_connected is True
    assert client.state == DerivConnectionState.CONNECTED

    # 2. Ping
    ping_res = await client.ping()
    assert ping_res.get("msg_type") == "ping"
    assert ping_res.get("ping") == "pong"

    # 3. Assina ticks
    await client.subscribe_ticks("R_100")

    # Aguarda receber pelo menos 2 ticks ao vivo
    for _ in range(25):
        if len(received_ticks) >= 2:
            break
        await asyncio.sleep(0.5)

    assert len(received_ticks) >= 2, f"Esperado >= 2 ticks, recebido {len(received_ticks)}"
    tick = received_ticks[0]
    assert tick.symbol == "R_100"
    assert tick.quote > 0
    assert 0 <= tick.last_digit <= 9

    # 4. Autorização DEMO
    auth = await client.authorize(token="pat_3d3166daa98c3ec98dd22eb12c71296f4657321122f60f715fbf5571b615d13d")
    assert client.is_authorized is True
    assert auth.is_virtual is True

    # 5. Desconecta com segurança
    await client.disconnect()
    assert client.is_connected is False
