"""Testes unitários para o Model Ensemble, ponderação adaptativa e veto por divergência."""

from unittest.mock import MagicMock
import pytest

from backend.app.api.v1.ensemble import get_ensemble_status, predict_ensemble
from backend.app.modules.ai_agents.models import BaseAIModel, ModelMetrics
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.model_ensemble.ensemble import ModelEnsemble
from backend.app.modules.model_ensemble.ensemble_strategy import EnsembleStrategy
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment, StatisticalEvaluator
from backend.app.modules.statistical_engine.randomness_tests import (
    ChiSquareResult,
    EntropyResult,
    RunsTestResult,
)
from backend.app.modules.strategy_lab.base import SignalDirection
from backend.app.modules.tick_collector.collector import TickCollector


def _make_ticks(digits: list) -> list:
    return [
        TickData.from_api_payload({
            "epoch": 1700000000 + i,
            "quote": 100.0 + (d / 100.0),
            "pip_size": 2,
            "symbol": "R_100",
        })
        for i, d in enumerate(digits)
    ]


def _dummy_stats(p_even: float = 0.52, z_runs: float = 0.0) -> StatisticalAssessment:
    chi2 = ChiSquareResult(statistic=0.0, p_value=1.0, degrees_of_freedom=9, is_uniform=True, observed_counts={}, expected_count_per_digit=10.0)
    runs = RunsTestResult(runs_count=50, even_count=50, odd_count=50, expected_runs=51.0, variance_runs=24.0, z_score=z_runs, p_value=1.0, is_independent=True)
    entropy = EntropyResult(entropy_bits=3.32, max_entropy_bits=3.32, entropy_ratio=1.0, is_high_entropy=True)

    return StatisticalAssessment(
        sample_size=100,
        chi2=chi2,
        runs_test=runs,
        entropy=entropy,
        conditional_p_even=p_even,
        conditional_p_odd=1.0 - p_even,
        state_sample_size=50,
        wilson_lower_even=0.45,
        wilson_lower_odd=0.45,
        break_even_prob=0.5128,
        net_ev_ratio_even=0.01,
        net_ev_ratio_odd=-0.03,
        recommended_direction=None,
        is_trade_recommended=False,
        rationale="Dummy",
    )


class MockAIModel(BaseAIModel):
    """Modelo mock para simulação de predições e Brier Scores controlados."""

    def __init__(self, name: str, fixed_p_even: float, brier_score: float):
        super().__init__(model_name=name)
        self.fixed_p_even = fixed_p_even
        self.is_trained = True
        self.metrics = ModelMetrics(
            accuracy=0.60,
            brier_score=brier_score,
            log_loss_val=0.65,
            sample_count=100,
            is_calibrated=True,
        )

    def train(self, X, y):
        return self.metrics

    def predict_probability(self, x_vector):
        return self.fixed_p_even, 1.0 - self.fixed_p_even


def test_ensemble_consensus_achievement():
    """Valida agregação com sucesso quando os modelos apresentam concordância (spread <= 15%)."""
    m1 = MockAIModel("Model_A", fixed_p_even=0.54, brier_score=0.18)
    m2 = MockAIModel("Model_B", fixed_p_even=0.52, brier_score=0.20)

    ensemble = ModelEnsemble(max_allowed_discordance=0.15, ai_models=[m1, m2])
    ticks = _make_ticks(list(range(10)) * 3)
    stats = _dummy_stats(p_even=0.53)

    pred = ensemble.predict(ticks, stats)

    assert pred.is_consensus_achieved is True
    assert pred.veto_reason is None
    assert pred.discordance_spread <= 0.15
    assert 0.50 <= pred.p_even <= 0.56
    # O modelo com menor Brier score (0.18 vs 0.20) deve ter maior peso
    assert pred.weights["Model_A"] > pred.weights["Model_B"]


def test_ensemble_divergence_veto():
    """Garante veto incondicional se houver discordância excessiva entre os modelos."""
    # Model_A aponta 65% Even, Model_B aponta 40% Even (Spread = 25% > 15%)
    m_high = MockAIModel("Bull_Model", fixed_p_even=0.65, brier_score=0.15)
    m_low = MockAIModel("Bear_Model", fixed_p_even=0.40, brier_score=0.15)

    ensemble = ModelEnsemble(max_allowed_discordance=0.15, ai_models=[m_high, m_low])
    ticks = _make_ticks(list(range(10)) * 3)
    stats = _dummy_stats(p_even=0.50)

    pred = ensemble.predict(ticks, stats)

    assert pred.is_consensus_achieved is False
    assert pred.veto_reason is not None
    assert "DIVERGÊNCIA EXCESSIVA" in pred.veto_reason
    assert pred.discordance_spread > 0.15


def test_ensemble_strategy_decision_gate():
    """Valida o portão de decisão da EnsembleStrategy."""
    m_agree1 = MockAIModel("Agree_1", fixed_p_even=0.62, brier_score=0.10)
    m_agree2 = MockAIModel("Agree_2", fixed_p_even=0.60, brier_score=0.12)

    ensemble = ModelEnsemble(max_allowed_discordance=0.15, ai_models=[m_agree1, m_agree2])
    strat = EnsembleStrategy(ensemble=ensemble, min_ticks_required=15)

    # Amostra estatística robusta de 400 ticks (sample_n = 200) para garantir intervalo Wilson
    ticks = _make_ticks(list(range(10)) * 40)
    stats = _dummy_stats(p_even=0.61)

    # 1. Com consenso e edge estatístico comprovado
    sig = strat.evaluate(ticks, stats)
    assert sig is not None
    assert sig.direction == SignalDirection.EVEN
    assert sig.confidence_lower_bound > sig.break_even_prob

    # 2. Se desabilitada, não emite sinal
    strat.enabled = False
    assert strat.evaluate(ticks, stats) is None


def test_ensemble_api_endpoints():
    """Testa endpoints REST da API de Ensemble."""
    ensemble = ModelEnsemble(max_allowed_discordance=0.15)
    collector = TickCollector()
    collector.buffer.append_batch(_make_ticks(list(range(10)) * 4))
    evaluator = StatisticalEvaluator(min_sample_size=10)

    # 1. Status
    status_res = get_ensemble_status(ensemble=ensemble)
    assert status_res["max_allowed_discordance"] == 0.15
    assert status_res["ai_models_count"] == 0

    # 2. Predict
    predict_res = predict_ensemble(collector=collector, evaluator=evaluator, ensemble=ensemble)
    assert "p_even" in predict_res
    assert "is_consensus_achieved" in predict_res
    assert "model_weights" in predict_res
