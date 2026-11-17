"""Testes unitários para o motor estatístico de probabilidades, testes de hipóteses e Markov."""

import pytest
from backend.app.api.v1.stats import CustomEvaluationPayload, evaluate_custom_series
from backend.app.modules.statistical_engine.evaluator import StatisticalEvaluator
from backend.app.modules.statistical_engine.markov_chains import (
    calculate_first_order_markov,
    calculate_second_order_markov,
    get_conditional_probabilities,
)
from backend.app.modules.statistical_engine.randomness_tests import (
    calculate_shannon_entropy,
    chi_square_uniformity_test,
    wald_wolfowitz_runs_test,
)


def test_chi_square_uniform_distribution():
    """Garante que distribuição equilibrada de dígitos [0..9] passa no teste com p-valor alto."""
    # Cada dígito de 0 a 9 aparece exatamente 25 vezes (N=250)
    uniform_digits = list(range(10)) * 25
    res = chi_square_uniformity_test(uniform_digits)

    assert res.statistic == 0.0
    assert res.p_value == 1.0
    assert res.is_uniform is True
    assert res.degrees_of_freedom == 9


def test_chi_square_skewed_distribution():
    """Garante rejeição de H0 quando os dígitos apresentam viés extremo."""
    # Apenas dígitos 7 e 8 presentes
    skewed_digits = [7, 8] * 100
    res = chi_square_uniformity_test(skewed_digits)

    assert res.is_uniform is False
    assert res.p_value < 0.001
    assert res.statistic > 20.0


def test_runs_test_alternating_series():
    """Série perfeitamente alternada (EOEOEO...) tem excesso anormal de runs (Z alto)."""
    # 50 pares e 50 ímpares alternando
    alternating = [True, False] * 50
    res = wald_wolfowitz_runs_test(alternating)

    assert res.runs_count == 100
    assert res.is_independent is False
    assert res.z_score > 3.0  # Z fortemente positivo
    assert res.p_value < 0.01


def test_runs_test_clustered_series():
    """Série com aglomeração (EEEE...OOOO...) tem déficit anormal de runs (Z baixo)."""
    clustered = [True] * 50 + [False] * 50
    res = wald_wolfowitz_runs_test(clustered)

    assert res.runs_count == 2
    assert res.is_independent is False
    assert res.z_score < -3.0  # Z fortemente negativo
    assert res.p_value < 0.01


def test_shannon_entropy_limits():
    """Testa extremos da entropia: máxima em uniforme e nula em constante."""
    # 1. Uniforme (máxima desordem)
    uniform_digits = list(range(10)) * 30
    res_uniform = calculate_shannon_entropy(uniform_digits)
    assert pytest.approx(res_uniform.entropy_bits, 0.01) == 3.32
    assert pytest.approx(res_uniform.entropy_ratio, 0.01) == 1.0
    assert res_uniform.is_high_entropy is True

    # 2. Constante (zero informação)
    constant_digits = [5] * 100
    res_constant = calculate_shannon_entropy(constant_digits)
    assert res_constant.entropy_bits == 0.0
    assert res_constant.entropy_ratio == 0.0
    assert res_constant.is_high_entropy is False


def test_first_order_markov_properties():
    """Testa consistência e probabilidades da cadeia de 1ª ordem."""
    series = [True, True, True, False, False]
    m1 = calculate_first_order_markov(series, laplace_smoothing=1.0)

    # Probabilidades devem somar 1.0 para cada estado de origem
    assert pytest.approx(m1.p_even_given_even + m1.p_odd_given_even, 0.001) == 1.0
    assert pytest.approx(m1.p_even_given_odd + m1.p_odd_given_odd, 0.001) == 1.0
    assert m1.total_transitions == 4


def test_second_order_markov_properties():
    """Testa matriz de transição de 2ª ordem para estados de 2 passos."""
    series = [True, True, False, True, False, False, True]
    m2 = calculate_second_order_markov(series, laplace_smoothing=1.0)

    for state in ["EE", "EO", "OE", "OO"]:
        probs = m2.probabilities[state]
        assert pytest.approx(probs["EVEN"] + probs["ODD"], 0.001) == 1.0


def test_statistical_evaluator_insufficient_samples():
    """Garante bloqueio de recomendação se a amostra for inferior ao mínimo."""
    evaluator = StatisticalEvaluator(min_sample_size=50)
    few_digits = [1, 2, 3, 4]  # Apenas 4 dígitos
    assessment = evaluator.evaluate_series(few_digits)

    assert assessment.is_trade_recommended is False
    assert assessment.recommended_direction is None
    assert "Amostra insuficiente" in assessment.rationale


def test_statistical_evaluator_blocks_unproven_random_walk():
    """Em passeio aleatório normal com 50% de par/ímpar, Net EV é negativo e trade é bloqueado."""
    import random
    rng = random.Random(42)
    random_digits = [rng.randint(0, 9) for _ in range(500)]
    evaluator = StatisticalEvaluator(min_sample_size=100, default_payout=1.95)
    assessment = evaluator.evaluate_series(random_digits)

    assert assessment.is_trade_recommended is False
    assert assessment.recommended_direction is None
    assert "Sem vantagem matemática líquida comprovada" in assessment.rationale


def test_api_custom_test_endpoint():
    """Testa rota REST de avaliação de sequência customizada."""
    evaluator = StatisticalEvaluator(min_sample_size=20)
    payload = CustomEvaluationPayload(digits=list(range(10)) * 3, stake=1.0, payout=1.95)

    data = evaluate_custom_series(payload=payload, evaluator=evaluator)
    assert data["sample_size"] == 30
    assert "randomness_tests" in data
    assert "chi_square" in data["randomness_tests"]
    assert "shannon_entropy" in data["randomness_tests"]
    assert "runs_test" in data["randomness_tests"]
