"""Teste ao vivo da Deriv. Fica desligado sem ordem explícita e sem token no ambiente.

Não há token no código. A variável DERIV_DEMO_TOKEN, se existir, não é impressa.
Este teste não roda na suíte padrão: exige DERIV_LIVE_TESTS=1.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("DERIV_LIVE_TESTS") != "1" or not os.getenv("DERIV_DEMO_TOKEN"),
    reason="Teste ao vivo desligado. Defina DERIV_LIVE_TESTS=1 e DERIV_DEMO_TOKEN fora do código.",
)


@pytest.mark.asyncio
async def test_deriv_client_live_connection_and_ticks():
    import asyncio

    from backend.app.modules.deriv_client.client import DerivWebSocketClient
    from backend.app.modules.deriv_client.models import DerivConnectionState, TickData

    token = os.environ["DERIV_DEMO_TOKEN"]
    client = DerivWebSocketClient(
        ws_url=os.getenv(
            "DERIV_WS_URL",
            "wss://api.derivws.com/trading/v1/options/ws/public",
        ),
        app_id=int(os.getenv("DERIV_APP_ID", "1089")),
        rest_base_url=os.getenv("DERIV_REST_BASE_URL", "https://api.derivws.com"),
    )
    received_ticks = []

    def on_tick(tick: TickData):
        received_ticks.append(tick)

    client.register_tick_callback(on_tick)
    try:
        auth = await client.authorize(token=token)
        assert client.is_authorized is True
        assert auth.is_virtual is True
        assert client.session_mode == "demo"
        assert client.is_simulated is False
        assert "/ws/real" not in (client.redacted_endpoint or "")

        await client.subscribe_ticks(os.getenv("DERIV_DEFAULT_SYMBOL", "R_100"))
        for _ in range(25):
            if len(received_ticks) >= 2:
                break
            await asyncio.sleep(0.5)

        assert len(received_ticks) >= 2
        assert received_ticks[0].quote > 0
        assert client.state == DerivConnectionState.AUTHORIZED
    finally:
        await client.disconnect()
