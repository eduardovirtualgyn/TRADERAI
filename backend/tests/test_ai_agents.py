"""Testes unitários para os agentes de Inteligência Artificial, features e calibração de probabilidade."""

import random
import pytest

from backend.app.api.v1.agents import AITrainRequest, get_ai_status, predict_next_tick, train_ai_agents
from backend.app.modules.ai_agents.agent_strategy import AIPredictiveStrategy
from backend.app.modules.ai_agents.features import (
    build_training_dataset,
    extract_features_single,
)
from backend.app.modules.ai_agents.models import (
    CalibratedRandomForestModel,
    CalibratedXGBoostModel,
)
from backend.app.modules.ai_agents.trainer import AIAgentTrainer
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment
from backend.app.modules.statistical_engine.randomness_tests import (
    ChiSquareResult,
    EntropyResult,
    RunsTestResult,
)
from backend.app.modules.strategy_lab.base import SignalDirection
from backend.app.modules.strategy_lab.registry import StrategyRegistry
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


def _dummy_stats(break_even: float = 0.5128) -> StatisticalAssessment:
    chi2 = ChiSquareResult(statistic=0.0, p_value=1.0, degrees_of_freedom=9, is_uniform=True, observed_counts={}, expected_count_per_digit=10.0)
    runs = RunsTestResult(runs_count=50, even_count=50, odd_count=50, expected_runs=51.0, variance_runs=24.0, z_score=0.0, p_value=1.0, is_independent=True)
    entropy = EntropyResult(entropy_bits=3.32, max_entropy_bits=3.32, entropy_ratio=1.0, is_high_entropy=True)

    return StatisticalAssessment(
        sample_size=100,
        chi2=chi2,
        runs_test=runs,
        entropy=entropy,
        conditional_p_even=0.50,
        conditional_p_odd=0.50,
        state_sample_size=50,
        wilson_lower_even=0.45,
        wilson_lower_odd=0.45,
        break_even_prob=break_even,
        net_ev_ratio_even=-0.025,
        net_ev_ratio_odd=-0.025,
        recommended_direction=None,
        is_trade_recommended=False,
        rationale="Dummy",
    )


def test_feature_extraction_properties():
    """Valida formato, dimensionalidade e ausência de Look-Ahead no pipeline de features."""
    digits = list(range(10)) * 6  # 60 ticks
    ticks = _make_ticks(digits)

    # Extração pontual
    features = extract_features_single(ticks)
    assert features.shape == (22,)  # 22 features quantitativas
    assert not any(features == None)

    # Dataset completo para treino
    X, y = build_training_dataset(ticks, min_history=20)
    assert len(X) == len(y)
    assert len(X) == 60 - 20 - 1  # 39 amostras
    assert X.shape[1] == 22
    assert set(y).issubset({0, 1})


def test_calibrated_random_forest_training_and_probabilities():
    """Valida treino do Random Forest com calibração sigmoide de probabilidade."""
    # Gera dataset com padrão detectável
    pattern_digits = [0, 2, 4, 1, 3] * 25  # 125 ticks
    ticks = _make_ticks(pattern_digits)
    X, y = build_training_dataset(ticks, min_history=20)

    model = CalibratedRandomForestModel(n_estimators=30, max_depth=3)
    metrics = model.train(X, y)

    assert model.is_trained is True
    assert metrics.sample_count == len(X)
    assert 0.0 <= metrics.brier_score <= 1.0

    # Teste de inferência
    p_even, p_odd = model.predict_probability(X[0])
    assert 0.0 <= p_even <= 1.0
    assert 0.0 <= p_odd <= 1.0
    assert pytest.approx(p_even + p_odd, 0.001) == 1.0


def test_calibrated_xgboost_training_and_probabilities():
    """Valida treino do XGBoost com calibração probabilística."""
    pattern_digits = [8, 8, 1, 1] * 30  # 120 ticks
    ticks = _make_ticks(pattern_digits)
    X, y = build_training_dataset(ticks, min_history=20)

    model = CalibratedXGBoostModel(n_estimators=25, max_depth=2)
    metrics = model.train(X, y)

    assert model.is_trained is True
    assert metrics.sample_count == len(X)
    assert 0.0 <= metrics.brier_score <= 1.0

    p_even, p_odd = model.predict_probability(X[0])
    assert pytest.approx(p_even + p_odd, 0.001) == 1.0


def test_ai_predictive_strategy_gate():
    """Garante que AIPredictiveStrategy respeita o portão de segurança (não emite sinal sem modelo treinado)."""
    model = CalibratedRandomForestModel()
    strat = AIPredictiveStrategy(strategy_id="test_ai", name="Test AI", model=model, min_ticks_required=20)

    ticks = _make_ticks(list(range(10)) * 3)
    stats = _dummy_stats()

    # 1. Modelo não treinado -> deve retornar None
    sig_untrained = strat.evaluate(ticks, stats)
    assert sig_untrained is None

    # 2. Treina o modelo em ruído aleatório puro
    rng = random.Random(42)
    random_digits = [rng.randint(0, 9) for _ in range(200)]
    ticks_rand = _make_ticks(random_digits)
    X_rand, y_rand = build_training_dataset(ticks_rand, min_history=20)
    model.train(X_rand, y_rand)

    # Avaliação em dados aleatórios -> Wilson Lower Bound <= Break-even -> Nenhum sinal emitido!
    sig_random = strat.evaluate(ticks_rand, stats)
    assert sig_random is None


def test_ai_agent_trainer_orchestration():
    """Valida orquestração de ambos os modelos pelo AIAgentTrainer e integração com StrategyRegistry."""
    registry = StrategyRegistry(register_defaults=True)
    trainer = AIAgentTrainer(registry=registry)

    # As 2 estratégias de IA devem ter sido registradas no Registry
    strat_ids = [s["strategy_id"] for s in registry.list_strategies()]
    assert "ai_rf_v1" in strat_ids
    assert "ai_xgb_v1" in strat_ids

    # Treinamento com sequência padrão
    digits = [0, 2, 4, 6, 8, 1, 3, 5, 7, 9] * 15  # 150 ticks
    ticks = _make_ticks(digits)

    report = trainer.train_all(ticks=ticks, min_history=25)
    assert report["samples_trained"] > 0
    assert "random_forest" in report["models"]
    assert "xgboost" in report["models"]

    # Predição para o próximo tick
    preds = trainer.predict_next(ticks)
    assert "random_forest" in preds
    assert "xgboost" in preds
    assert preds["random_forest"]["is_trained"] is True
    assert preds["xgboost"]["is_trained"] is True


def test_ai_api_endpoints():
    """Valida rotas REST da API de Agentes de IA."""
    trainer = AIAgentTrainer()
    collector = TickCollector()

    # 1. Status inicial (não treinado)
    status_initial = get_ai_status(trainer=trainer)
    assert status_initial["random_forest"]["is_trained"] is False

    # 2. Treino via API com dígitos customizados
    req = AITrainRequest(
        ticks_source="custom",
        custom_digits=[0, 1] * 50,  # 100 ticks
        min_history=25,
    )
    train_res = train_ai_agents(request=req, collector=collector, trainer=trainer)
    assert train_res["success"] is True

    # 3. Predição via API
    collector.buffer.append_batch(_make_ticks([0, 1] * 10))
    preds = predict_next_tick(collector=collector, trainer=trainer)
    assert "random_forest" in preds
    assert "xgboost" in preds
