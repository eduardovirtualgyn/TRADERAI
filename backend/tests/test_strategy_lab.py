"""Testes unitários para o laboratório de estratégias e gerador de sinais quantitativos."""

import random
import pytest

from backend.app.api.v1.strategies import (
    StrategyTogglePayload,
    get_active_signals,
    list_strategies,
    toggle_strategy,
)
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment, StatisticalEvaluator
from backend.app.modules.statistical_engine.randomness_tests import (
    ChiSquareResult,
    EntropyResult,
    RunsTestResult,
)
from backend.app.modules.strategy_lab.base import BaseStrategy, SignalDirection
from backend.app.modules.strategy_lab.markov_strategy import MarkovEdgeStrategy
from backend.app.modules.strategy_lab.registry import StrategyRegistry
from backend.app.modules.strategy_lab.runs_strategy import RunsAnomalyStrategy
from backend.app.modules.strategy_lab.streak_strategy import StreakPersistenceStrategy
from backend.app.modules.tick_collector.collector import TickCollector


def _make_ticks(digits: list) -> list:
    """Helper para criar lista de TickData."""
    return [
        TickData.from_api_payload({
            "epoch": 1700000000 + i,
            "quote": 100.0 + (d / 100.0),
            "pip_size": 2,
            "symbol": "R_100",
        })
        for i, d in enumerate(digits)
    ]


def _dummy_stats(
    p_even: float = 0.50,
    wilson_even: float = 0.45,
    p_odd: float = 0.50,
    wilson_odd: float = 0.45,
    break_even: float = 0.5128,
    z_score: float = 0.0,
    p_value: float = 1.0,
) -> StatisticalAssessment:
    """Helper para criar StatisticalAssessment sintético."""
    chi2 = ChiSquareResult(statistic=0.0, p_value=1.0, degrees_of_freedom=9, is_uniform=True, observed_counts={}, expected_count_per_digit=10.0)
    runs = RunsTestResult(runs_count=50, even_count=50, odd_count=50, expected_runs=51.0, variance_runs=24.0, z_score=z_score, p_value=p_value, is_independent=abs(z_score) < 1.96)
    entropy = EntropyResult(entropy_bits=3.32, max_entropy_bits=3.32, entropy_ratio=1.0, is_high_entropy=True)

    net_ev_even = p_even * 1.95 - 1.0
    net_ev_odd = p_odd * 1.95 - 1.0

    return StatisticalAssessment(
        sample_size=100,
        chi2=chi2,
        runs_test=runs,
        entropy=entropy,
        conditional_p_even=p_even,
        conditional_p_odd=p_odd,
        state_sample_size=50,
        wilson_lower_even=wilson_even,
        wilson_lower_odd=wilson_odd,
        break_even_prob=break_even,
        net_ev_ratio_even=net_ev_even,
        net_ev_ratio_odd=net_ev_odd,
        recommended_direction=None,
        is_trade_recommended=False,
        rationale="Dummy stats",
    )


def test_base_strategy_mathematical_validation_rejection():
    """Garante que a classe base recusa a emissão de sinal se Wilson Lower <= Break-even ou EV negativo."""
    strat = MarkovEdgeStrategy()

    # Cenário 1: Probabilidade aparente de 55%, mas Wilson Lower de 49% (inferior a break-even 51.28%)
    sig1 = strat.validate_and_build_signal(
        direction=SignalDirection.EVEN,
        estimated_prob=0.55,
        confidence_lower_bound=0.49,
        stake=1.0,
        payout=1.95,
        timestamp=1700000000,
        rationale="Teste",
    )
    assert sig1 is None  # Rejeitado!

    # Cenário 2: Expectativa líquida negativa (payout baixo ou prob insuficiente)
    sig2 = strat.validate_and_build_signal(
        direction=SignalDirection.EVEN,
        estimated_prob=0.50,
        confidence_lower_bound=0.52,  # Irreal, mas testa o filtro de EV
        stake=1.0,
        payout=1.95,  # EV = 0.50 * 1.95 - 1 = -0.025
        timestamp=1700000000,
        rationale="Teste",
    )
    assert sig2 is None  # Rejeitado!


def test_markov_edge_strategy_decision():
    """Valida que MarkovEdgeStrategy emite sinal somente quando há edge confirmado."""
    strat = MarkovEdgeStrategy(min_ticks_required=10)
    ticks = _make_ticks(list(range(10)) * 2)

    # 1. Sem edge (passeio normal)
    stats_neutral = _dummy_stats(p_even=0.50, wilson_even=0.45)
    sig_neutral = strat.evaluate(ticks, stats_neutral)
    assert sig_neutral is None

    # 2. Com edge estatístico comprovado para EVEN (P=62%, Wilson Lower=54% > Break-even=51.28%)
    stats_edge = _dummy_stats(p_even=0.62, wilson_even=0.54)
    sig_edge = strat.evaluate(ticks, stats_edge)
    assert sig_edge is not None
    assert sig_edge.direction == SignalDirection.EVEN
    assert sig_edge.confidence_lower_bound == 0.54
    assert sig_edge.net_ev_ratio > 0.01


def test_runs_anomaly_strategy_decision():
    """Valida que RunsAnomalyStrategy detecta e opera desvios extremos de alternância/agrupamento."""
    strat = RunsAnomalyStrategy(z_threshold=2.58, min_ticks_required=10)

    # Cria sequência de alternância perfeita
    ticks_alt = _make_ticks([0, 1] * 30)

    # Z = 3.5 (> 2.58): Alternância excessiva
    stats_runs_high = _dummy_stats(z_score=3.5, p_value=0.0004)
    sig = strat.evaluate(ticks_alt, stats_runs_high)

    assert sig is not None
    # Último dígito foi 1 (ODD) -> em alternância excessiva, projeta EVEN
    assert sig.direction == SignalDirection.EVEN
    assert sig.confidence_lower_bound > sig.break_even_prob


def test_streak_persistence_strategy_random_walk_rejection():
    """Garante que a estratégia de streaks NÃO cai na falácia do apostador em dados aleatórios."""
    rng = random.Random(42)
    random_digits = [rng.randint(0, 9) for _ in range(300)]
    ticks = _make_ticks(random_digits)

    strat = StreakPersistenceStrategy(min_streak_trigger=3, min_historical_occurrences=5, min_ticks_required=50)
    stats = _dummy_stats()

    sig = strat.evaluate(ticks, stats)
    # Em ruído aleatório uniforme, a taxa de continuação/reversão gravita em torno de 50%, sem edge
    assert sig is None


def test_strategy_registry_management():
    """Valida cadastro, ativação, desativação e consulta de estratégias no Registry."""
    reg = StrategyRegistry(register_defaults=True)
    strats = reg.list_strategies()
    assert len(strats) == 3

    # Desativa markov
    success = reg.toggle("markov_edge_v1", enabled=False)
    assert success is True
    assert reg.get("markov_edge_v1").enabled is False

    # Toggle em ID inexistente
    fail = reg.toggle("inexistent_id", enabled=True)
    assert fail is False


def test_strategy_api_endpoints():
    """Testa endpoints REST da API do laboratório de estratégias."""
    reg = StrategyRegistry(register_defaults=True)

    # 1. Listagem
    list_res = list_strategies(registry=reg)
    assert len(list_res) == 3
    ids = [s["strategy_id"] for s in list_res]
    assert "markov_edge_v1" in ids

    # 2. Toggle via API
    toggle_res = toggle_strategy(
        strategy_id="runs_anomaly_v1",
        payload=StrategyTogglePayload(enabled=False),
        registry=reg,
    )
    assert toggle_res["success"] is True
    assert toggle_res["enabled"] is False

    # 3. Consulta de sinais com buffer vazio
    collector = TickCollector()
    evaluator = StatisticalEvaluator(min_sample_size=50)
    signals_res = get_active_signals(collector=collector, evaluator=evaluator, registry=reg)
    assert signals_res["total_signals"] == 0
    assert signals_res["signals"] == []
