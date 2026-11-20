"""Testes unitários e de integração para o AutoTraderEngine e API."""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.modules.auto_trader.engine import AutoTraderEngine
from backend.app.modules.auto_trader.models import AutoTraderConfig
from backend.app.modules.contract_executor.executor import ContractExecutor
from backend.app.modules.contract_executor.models import (
    ContractStatus,
    ExecutionResult,
)
from backend.app.modules.deriv_client.client import DerivWebSocketClient
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.model_ensemble.ensemble import ModelEnsemble
from backend.app.modules.model_ensemble.ensemble_strategy import EnsembleStrategy
from backend.app.modules.risk_manager.risk_rules import RiskManager
from backend.app.modules.statistical_engine.evaluator import StatisticalEvaluator
from backend.app.modules.tick_collector.collector import TickCollector


@pytest.fixture
def mock_deriv_client():
    client = MagicMock(spec=DerivWebSocketClient)
    client._tick_callbacks = []

    def reg(cb):
        client._tick_callbacks.append(cb)

    client.register_tick_callback.side_effect = reg
    client.is_connected = True
    client.is_authorized = True
    client.get_open_contract = AsyncMock(return_value={"status": "won", "profit": 0.95, "is_sold": 1})
    client.update_balance = MagicMock(return_value=1000.95)
    return client


@pytest.fixture
def test_setup(mock_deriv_client):
    collector = TickCollector()
    collector.bind_client(mock_deriv_client)

    evaluator = StatisticalEvaluator(min_sample_size=30)
    risk_manager = RiskManager(
        max_stake_usd=5.0,
        max_stake_percent=0.05,
        max_consecutive_losses=3,
        max_daily_loss_usd=50.0,
        ban_martingale=True,
        kill_switch_initially_active=False,
    )
    executor = ContractExecutor(
        deriv_client=mock_deriv_client,
        risk_manager=risk_manager,
    )

    ensemble = ModelEnsemble(max_allowed_discordance=0.20)
    ensemble_strat = EnsembleStrategy(ensemble=ensemble, min_ticks_required=30)

    config = AutoTraderConfig(
        enabled=False,
        symbol="R_100",
        stake=1.0,
        min_probability=0.52,
        min_wilson_lower_bound=0.50,
        cooldown_seconds=1.0,
    )

    engine = AutoTraderEngine(
        deriv_client=mock_deriv_client,
        tick_collector=collector,
        evaluator=evaluator,
        ensemble_strategy=ensemble_strat,
        contract_executor=executor,
        risk_manager=risk_manager,
        config=config,
    )

    return {
        "engine": engine,
        "client": mock_deriv_client,
        "collector": collector,
        "risk_manager": risk_manager,
        "executor": executor,
    }


def test_auto_trader_initial_state(test_setup):
    engine = test_setup["engine"]
    status = engine.get_status()
    assert status.enabled is False
    assert status.state == "STOPPED"
    assert status.total_trades == 0
    assert status.session_pnl == 0.0


def test_auto_trader_toggle(test_setup):
    engine = test_setup["engine"]
    engine.set_enabled(True)
    assert engine.config.enabled is True
    assert engine.state == "SEARCHING_EDGE"

    engine.set_enabled(False)
    assert engine.config.enabled is False
    assert engine.state == "STOPPED"


def test_auto_trader_respects_kill_switch(test_setup):
    engine = test_setup["engine"]
    risk_manager = test_setup["risk_manager"]

    engine.set_enabled(True)
    risk_manager.set_kill_switch(True, reason="Teste de Emergência")

    tick = TickData(epoch=1000, quote=1234.56, symbol="R_100", last_digit=6, is_even=True)
    engine.on_tick_received(tick)

    assert engine.state == "PAUSED_BY_RISK"
    assert "Kill Switch" in engine.last_decision


def test_auto_trader_respects_circuit_breaker(test_setup):
    engine = test_setup["engine"]
    risk_manager = test_setup["risk_manager"]

    engine.set_enabled(True)
    risk_manager.circuit_breaker.trigger("3 derrotas consecutivas", duration_seconds=60)

    tick = TickData(epoch=1000, quote=1234.56, symbol="R_100", last_digit=6, is_even=True)
    engine.on_tick_received(tick)

    assert engine.state == "PAUSED_BY_RISK"
    assert "Circuit Breaker" in engine.last_decision


def test_auto_trader_vetoes_random_walk(test_setup):
    engine = test_setup["engine"]
    collector = test_setup["collector"]

    engine.set_enabled(True)

    # Alimenta com 60 ticks perfeitamente alternados (sem edge comprovada)
    for i in range(60):
        digit = i % 10
        tick = TickData(epoch=1000 + i, quote=100.0 + i, symbol="R_100", last_digit=digit, is_even=(digit % 2 == 0))
        collector.buffer.append(tick)

    # Dispara o processamento do tick
    last_tick = TickData(epoch=1061, quote=161.0, symbol="R_100", last_digit=2, is_even=True)
    engine.on_tick_received(last_tick)

    # Deve vetar por passeio aleatório ou ausência de borda estatística
    assert engine.state == "SEARCHING_EDGE"
    assert "VETO" in engine.last_decision
    assert engine.total_trades == 0


@pytest.mark.asyncio
async def test_auto_trader_executes_and_settles(test_setup):
    engine = test_setup["engine"]
    executor = test_setup["executor"]

    # Mock da execução da ordem
    mock_exec_res = ExecutionResult(
        success=True,
        status=ContractStatus.BUY_SUBMITTED,
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.0,
        payout=1.95,
        contract_id="999888",
    )
    executor.execute_order = AsyncMock(return_value=mock_exec_res)

    mock_settled_res = ExecutionResult(
        success=True,
        status=ContractStatus.WON,
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.0,
        payout=1.95,
        net_pnl=0.95,
        contract_id="999888",
    )
    executor.settle_contract = MagicMock(return_value=mock_settled_res)

    signal = MagicMock()
    signal.direction.value = "EVEN"
    signal.estimated_prob = 0.58
    signal.confidence_lower_bound = 0.53

    # Dispara o ciclo de execução e liquidação
    await engine._execute_and_settle(signal)

    assert engine.total_trades == 1
    assert engine.won_trades == 1
    assert engine.session_pnl == 0.95
    assert "VITÓRIA" in engine.last_decision


def test_auto_trader_api():
    app = create_app()
    client = TestClient(app)

    # 1. Status inicial
    res = client.get("/api/v1/auto-trader/status")
    assert res.status_code == 200
    data = res.json()
    assert "enabled" in data
    assert "state" in data
    assert "total_trades" in data

    # 2. Toggle Ligar
    res_toggle = client.post("/api/v1/auto-trader/toggle", json={"enabled": True})
    assert res_toggle.status_code == 200
    assert res_toggle.json()["enabled"] is True

    # 3. Configure
    res_cfg = client.post(
        "/api/v1/auto-trader/configure",
        json={
            "enabled": True,
            "symbol": "R_100",
            "stake": 2.0,
            "min_probability": 0.54,
            "min_wilson_lower_bound": 0.51,
            "cooldown_seconds": 3.0,
        },
    )
    assert res_cfg.status_code == 200
    assert res_cfg.json()["stake"] == 2.0
    assert res_cfg.json()["cooldown_seconds"] == 3.0

    # 4. Toggle Desligar
    res_off = client.post("/api/v1/auto-trader/toggle", json={"enabled": False})
    assert res_off.status_code == 200
    assert res_off.json()["enabled"] is False


@pytest.mark.asyncio
async def test_auto_trader_real_signal_reaches_executor(test_setup):
    """Um StrategySignal real precisa chegar ao executor. MagicMock escondia o AttributeError."""
    from backend.app.modules.strategy_lab.base import SignalDirection, StrategySignal

    engine = test_setup["engine"]
    collector = test_setup["collector"]
    engine.set_enabled(True)
    for i in range(60):
        digit = i % 10
        collector.buffer.append(
            TickData(
                epoch=1000 + i,
                quote=100.0 + i,
                symbol="R_100",
                last_digit=digit,
                is_even=(digit % 2 == 0),
            )
        )
    real_signal = StrategySignal(
        strategy_id="ensemble",
        direction=SignalDirection.EVEN,
        estimated_prob=0.56,
        confidence_lower_bound=0.52,
        net_ev_ratio=0.09,
        stake=1.0,
        payout=1.95,
        break_even_prob=0.5128,
        timestamp=0,
        rationale="teste",
    )
    engine.ensemble_strategy.evaluate = lambda **kwargs: real_signal
    called = []

    async def fake_exec(signal):
        called.append(signal.estimated_prob)

    engine._execute_and_settle = fake_exec
    engine.on_tick_received(TickData(epoch=2000, quote=1.0, symbol="R_100", last_digit=2, is_even=True))
    await asyncio.sleep(0)
    assert "SINAL DETECTADO" in engine.last_decision
    assert called == [0.56]


@pytest.mark.asyncio
async def test_symbol_mismatch_warns_and_resubscribes(test_setup):
    """Tick de outro símbolo não pode ser ignorado em silêncio."""
    engine = test_setup["engine"]
    client = test_setup["client"]
    client.subscribe_ticks = AsyncMock()
    engine.set_enabled(True)
    engine.last_decision = "Radar autônomo ativo. Monitorando ticks e calculando anomalias estatísticas..."

    engine.on_tick_received(TickData(epoch=3000, quote=1.0, symbol="R_50", last_digit=4, is_even=True))
    await asyncio.sleep(0)

    assert "Símbolo divergente" in engine.last_decision
    assert "R_50" in engine.last_decision
    assert "R_100" in engine.last_decision
    client.subscribe_ticks.assert_awaited_with("R_100")
    assert engine.total_trades == 0
