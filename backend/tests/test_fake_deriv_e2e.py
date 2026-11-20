"""Servidor Deriv falso, sem rede externa: o robô abre e liquida um contrato demo."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import websockets

from backend.app.modules.auto_trader.engine import AutoTraderEngine
from backend.app.modules.auto_trader.models import AutoTraderConfig
from backend.app.modules.contract_executor.executor import ContractExecutor
from backend.app.modules.deriv_client.client import DerivWebSocketClient
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.model_ensemble.ensemble import ModelEnsemble
from backend.app.modules.model_ensemble.ensemble_strategy import EnsembleStrategy
from backend.app.modules.risk_manager.risk_rules import RiskManager
from backend.app.modules.statistical_engine.evaluator import StatisticalEvaluator
from backend.app.modules.strategy_lab.base import SignalDirection, StrategySignal
from backend.app.modules.tick_collector.collector import TickCollector


class _RestHandler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path.endswith("/trading/v1/options/accounts"):
            self._send(
                200,
                {
                    "data": [
                        {
                            "account_id": "VRTC9001",
                            "account_type": "demo",
                            "currency": "USD",
                            "balance": 10000,
                        }
                    ]
                },
            )
            return
        self._send(404, {"errors": [{"code": "AccountNotFound", "message": "not found"}]})

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path.endswith("/otp"):
            self._send(200, {"data": {"otp": "otp-test", "url": self.server.ws_url}})
            return
        self._send(404, {"errors": [{"code": "AccountNotFound", "message": "not found"}]})

    def log_message(self, fmt, *args):
        return


@pytest.mark.asyncio
async def test_offline_demo_session_places_and_settles_a_loss():
    state = {"balance": 10000.0, "proposals": [], "buys": []}

    async def ws_handler(connection):
        async for raw in connection:
            message = json.loads(raw)
            req_id = message.get("req_id")
            if "ping" in message:
                await connection.send(json.dumps({"req_id": req_id, "msg_type": "ping", "ping": "pong"}))
            elif "ticks" in message:
                await connection.send(json.dumps({"req_id": req_id, "msg_type": "ticks", "echo_req": message}))
                await connection.send(
                    json.dumps(
                        {
                            "tick": {
                                "symbol": message["ticks"],
                                "epoch": 1_700_000_100,
                                "quote": 1234.56,
                                "pip_size": 2,
                            }
                        }
                    )
                )
            elif "proposal" in message:
                state["proposals"].append(message)
                amount = float(message.get("amount", 1))
                await connection.send(
                    json.dumps(
                        {
                            "req_id": req_id,
                            "msg_type": "proposal",
                            "proposal": {
                                "id": "prop-e2e-1",
                                "ask_price": amount,
                                "payout": round(amount * 1.95, 2),
                                "spot": 1234.56,
                                "spot_time": 1_700_000_100,
                            },
                        }
                    )
                )
            elif "buy" in message:
                price = float(message.get("price", 1))
                state["balance"] = round(state["balance"] - price, 2)
                state["buys"].append(message)
                await connection.send(
                    json.dumps(
                        {
                            "req_id": req_id,
                            "msg_type": "buy",
                            "buy": {
                                "contract_id": "C1001",
                                "transaction_id": "T1001",
                                "buy_price": price,
                                "payout": round(price * 1.95, 2),
                                "balance_after": state["balance"],
                                "shortcode": "DIGITEVEN_R_100_1T",
                                "start_time": 1_700_000_100,
                            },
                        }
                    )
                )
            elif "proposal_open_contract" in message:
                await connection.send(
                    json.dumps(
                        {
                            "req_id": req_id,
                            "proposal_open_contract": {
                                "contract_id": message.get("contract_id"),
                                "status": "lost",
                                "is_sold": 1,
                                "profit": -1.0,
                                "exit_tick": 1234.51,
                            },
                        }
                    )
                )
            else:
                await connection.send(
                    json.dumps(
                        {
                            "req_id": req_id,
                            "error": {"code": "UnknownMethod", "message": "not implemented"},
                        }
                    )
                )

    ws_server = await websockets.serve(ws_handler, "127.0.0.1", 0)
    ws_port = ws_server.sockets[0].getsockname()[1]
    ws_url = f"ws://127.0.0.1:{ws_port}/trading/v1/options/ws/demo?otp=otp-test"

    http_server = ThreadingHTTPServer(("127.0.0.1", 0), _RestHandler)
    http_server.ws_url = ws_url
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()
    http_port = http_server.server_address[1]

    client = DerivWebSocketClient(
        ws_url="ws://127.0.0.1/unused",
        app_id=1089,
        rest_base_url=f"http://127.0.0.1:{http_port}",
        simulator_enabled=False,
    )
    try:
        auth = await client.authorize("pat_offline_test_token")
        assert auth.loginid == "VRTC9001"
        assert auth.balance == 10000.0
        assert client.session_mode == "demo"
        assert client.is_simulated is False
        assert "/ws/demo" in (client._connected_url or "")
        assert "otp=" in (client._connected_url or "")
        assert "/ws/real" not in (client._connected_url or "")

        await client.subscribe_ticks("R_100")

        risk = RiskManager(
            initial_balance_usd=auth.balance,
            max_stake_usd=5.0,
            max_stake_percent=0.01,
            min_operable_stake_usd=1.0,
            max_daily_loss_usd=100.0,
            max_consecutive_losses=5,
        )
        executor = ContractExecutor(deriv_client=client, risk_manager=risk)
        collector = TickCollector()
        for i in range(60):
            digit = i % 10
            collector.buffer.append(
                TickData(
                    epoch=1_700_000_000 + i,
                    quote=1000.0 + i,
                    symbol="R_100",
                    last_digit=digit,
                    is_even=(digit % 2 == 0),
                )
            )
        engine = AutoTraderEngine(
            deriv_client=client,
            tick_collector=collector,
            evaluator=StatisticalEvaluator(min_sample_size=30),
            ensemble_strategy=EnsembleStrategy(ensemble=ModelEnsemble(), min_ticks_required=30),
            contract_executor=executor,
            risk_manager=risk,
            config=AutoTraderConfig(
                enabled=True,
                symbol="R_100",
                stake=1.0,
                min_probability=0.52,
                min_wilson_lower_bound=0.51,
                cooldown_seconds=1.0,
            ),
        )
        engine.ensemble_strategy.evaluate = lambda **kwargs: StrategySignal(
            strategy_id="e2e",
            direction=SignalDirection.EVEN,
            estimated_prob=0.60,
            confidence_lower_bound=0.55,
            net_ev_ratio=0.17,
            stake=1.0,
            payout=1.95,
            break_even_prob=0.5128,
            timestamp=0,
            rationale="servidor falso",
        )
        engine.on_tick_received(
            TickData(epoch=1_700_000_200, quote=1234.58, symbol="R_100", last_digit=8, is_even=True)
        )

        for _ in range(40):
            if engine.total_trades:
                break
            await _sleep()

        assert engine.total_trades == 1, engine.last_decision
        assert engine.lost_trades == 1
        assert engine.session_pnl == pytest.approx(-1.0)
        assert "DERROTA" in engine.last_decision
        assert "SIMULADOR" not in engine.last_decision
        assert "C1001" in engine.last_decision
        assert state["proposals"], "nenhuma proposta chegou ao servidor falso"
        assert state["proposals"][0].get("underlying_symbol") == "R_100"
        assert state["buys"], "nenhuma compra chegou ao servidor falso"
        assert client.auth_info.balance == pytest.approx(9999.0)
        assert risk.balance_usd == pytest.approx(9999.0)
        assert state["balance"] == pytest.approx(9999.0)
    finally:
        await client.disconnect()
        ws_server.close()
        await ws_server.wait_closed()
        http_server.shutdown()
        http_thread.join(timeout=2)


async def _sleep():
    import asyncio

    await asyncio.sleep(0.1)
