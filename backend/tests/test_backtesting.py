"""Testes unitários para o motor de Backtesting com protocolo de Zero Data Leakage."""

import pytest
from backend.app.api.v1.backtest import BacktestRequest, run_backtest
from backend.app.modules.backtesting.engine import BacktestEngine
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment, StatisticalEvaluator
from backend.app.modules.strategy_lab.base import BaseStrategy, SignalDirection, StrategySignal
from backend.app.modules.strategy_lab.registry import StrategyRegistry
from backend.app.modules.strategy_lab.runs_strategy import RunsAnomalyStrategy
from backend.app.modules.tick_collector.collector import TickCollector


def _make_ticks(digits: list) -> list:
    """Helper para instanciar sequência cronológica de TickData."""
    return [
        TickData.from_api_payload({
            "epoch": 1700000000 + i,
            "quote": 100.0 + (d / 100.0),
            "pip_size": 2,
            "symbol": "R_100",
        })
        for i, d in enumerate(digits)
    ]


class ZeroLeakageSpyStrategy(BaseStrategy):
    """Estratégia espiã para provar matematicamente a ausência de Look-Ahead Bias."""

    def __init__(self):
        super().__init__(
            strategy_id="spy_strategy",
            name="Leakage Spy",
            description="Inspeciona a visibilidade de ticks no tempo t",
            min_ticks_required=10,
        )
        self.observed_lengths = []

    def evaluate(
        self,
        ticks: list,
        stats: StatisticalAssessment,
        stake: float = 1.0,
        payout: float = 1.95,
    ):
        # Registra o comprimento da janela visível em cada chamada
        self.observed_lengths.append(len(ticks))
        return None


def test_zero_data_leakage_guarantee():
    """Garante que o motor alimenta a estratégia estritamente com dados passados e presentes (t)."""
    ticks = _make_ticks(list(range(10)) * 5)  # 50 ticks
    spy = ZeroLeakageSpyStrategy()
    engine = BacktestEngine(initial_balance=1000.0)

    engine.run(ticks=ticks, strategy=spy)

    # Verifica que em cada passo t, o tamanho visível cresceu estritamente de 1 em 1
    # Começando em min_ticks_required (10) até len(ticks) (50)
    assert len(spy.observed_lengths) > 0
    assert spy.observed_lengths[0] == 11  # t=10 -> slice [:11]
    assert spy.observed_lengths[-1] == 50  # t=49 -> slice [:50]

    # Garante monotonicidade estrita
    for i in range(1, len(spy.observed_lengths)):
        assert spy.observed_lengths[i] == spy.observed_lengths[i - 1] + 1


def test_backtest_execution_accounting():
    """Valida a precisão contábil das vitórias, derrotas, saldo e PnL financeiro real."""
    # Sequência com forte alternância onde RunsAnomalyStrategy emite sinal
    alternating_digits = [0, 1] * 40  # 80 ticks
    ticks = _make_ticks(alternating_digits)

    strategy = RunsAnomalyStrategy(z_threshold=2.58, min_ticks_required=15)
    engine = BacktestEngine(
        initial_balance=1000.0,
        default_stake=10.0,
        default_payout_ratio=1.95,
        duration_ticks=1,
        enable_risk_manager=False,
    )

    report = engine.run(ticks=ticks, strategy=strategy)

    assert report.total_ticks_analyzed == 80
    assert report.metrics.total_trades > 0
    assert report.metrics.initial_balance == 1000.0

    # Cada vitória deve render +$9.50 e cada derrota -$10.00
    for t in report.trades:
        if t.won:
            assert pytest.approx(t.net_pnl) == 9.50
        else:
            assert pytest.approx(t.net_pnl) == -10.00

    # O saldo final deve bater com o saldo inicial + total_net_pnl
    expected_final = 1000.0 + report.metrics.total_net_pnl
    assert pytest.approx(report.metrics.final_balance) == expected_final


def test_drawdown_and_profit_factor_calculation():
    """Valida o cálculo de Max Drawdown e Profit Factor em cenário com oscilação patrimonial."""
    engine = BacktestEngine(initial_balance=1000.0)

    # Simula lista de trades com vitórias e derrotas
    from backend.app.modules.backtesting.models import BacktestTrade
    trades = [
        BacktestTrade(1, 10, 11, 100, 101, "strat", SignalDirection.EVEN, 0.6, 0.55, 10.0, 19.5, 2, True, 9.5, 1009.5, "w"),
        BacktestTrade(2, 11, 12, 101, 102, "strat", SignalDirection.EVEN, 0.6, 0.55, 10.0, 19.5, 1, False, -10.0, 999.5, "l"),
        BacktestTrade(3, 12, 13, 102, 103, "strat", SignalDirection.EVEN, 0.6, 0.55, 10.0, 19.5, 3, False, -10.0, 989.5, "l"),
        BacktestTrade(4, 13, 14, 103, 104, "strat", SignalDirection.EVEN, 0.6, 0.55, 10.0, 19.5, 4, True, 9.5, 999.0, "w"),
    ]
    curve = [1000.0, 1009.5, 999.5, 989.5, 999.0]

    metrics = engine._calculate_metrics(
        trades=trades,
        initial_balance=1000.0,
        final_balance=999.0,
        equity_curve=curve,
        risk_blocks_count=0,
    )

    assert metrics.total_trades == 4
    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 2
    assert metrics.win_rate == 0.50
    # Peak foi 1009.5, vale foi 989.5 -> Max DD = $20.00
    assert pytest.approx(metrics.max_drawdown_usd) == 20.00
    # Total wins = 19.0, Total loss = 20.0 -> Profit factor = 19 / 20 = 0.95
    assert pytest.approx(metrics.profit_factor) == 0.95


def test_api_backtest_run_endpoint():
    """Valida execução de backtest via endpoint REST da API."""
    registry = StrategyRegistry(register_defaults=True)
    collector = TickCollector()
    evaluator = StatisticalEvaluator(min_sample_size=10)

    # 1. Sucesso com dígitos customizados
    req = BacktestRequest(
        strategy_id="runs_anomaly_v1",
        ticks_source="custom",
        custom_digits=[0, 1] * 25,  # 50 ticks
        initial_balance=500.0,
        stake=2.0,
        payout_ratio=1.95,
        enable_risk_manager=False,
    )
    res = run_backtest(request=req, collector=collector, registry=registry, evaluator=evaluator)

    assert res["strategy_id"] == "runs_anomaly_v1"
    assert res["total_ticks_analyzed"] == 50
    assert "metrics" in res
    assert res["metrics"]["initial_balance"] == 500.0

    # 2. Erro 404 em estratégia desconhecida
    with pytest.raises(Exception):
        req_unknown = BacktestRequest(strategy_id="estrategia_inexistente")
        run_backtest(request=req_unknown, collector=collector, registry=registry, evaluator=evaluator)
