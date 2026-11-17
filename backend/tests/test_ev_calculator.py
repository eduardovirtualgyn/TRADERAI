"""Testes unitários do motor de Expectativa Matemática Líquida (Net EV)."""

import pytest
from backend.app.modules.statistical_engine.ev_calculator import (
    calculate_break_even_probability,
    calculate_net_ev_ratio,
    calculate_net_expected_value,
    calculate_wilson_lower_bound,
    validate_trade_expectation,
)


def test_calculate_break_even_probability():
    """Para stake $1.00 e payout $1.95, break-even deve ser ~51.28%."""
    p_be = calculate_break_even_probability(stake=1.0, payout=1.95)
    assert pytest.approx(p_be, 0.0001) == 1.0 / 1.95
    assert p_be > 0.50  # Vantagem da casa presente


def test_negative_ev_on_fair_coin():
    """Com probabilidade 50% e payout 1.95, a expectativa matemática DEVE ser negativa."""
    ev = calculate_net_expected_value(prob=0.50, stake=10.0, payout=19.50)
    ev_ratio = calculate_net_ev_ratio(prob=0.50, stake=10.0, payout=19.50)

    # EV = 0.5 * 19.50 - 10.0 = 9.75 - 10.0 = -0.25 USD
    assert pytest.approx(ev, 0.001) == -0.25
    assert pytest.approx(ev_ratio, 0.001) == -0.025  # -2.5%


def test_validate_trade_expectation_rejects_negative_ev():
    """Garante que propostas sem vantagem matemática são rejeitadas."""
    result = validate_trade_expectation(prob=0.50, stake=5.0, payout=9.75)
    assert result.is_viable is False
    assert result.net_ev < 0.0
    assert result.rejection_reason is not None
    assert "Expectativa matemática não positiva" in result.rejection_reason


def test_validate_trade_expectation_approves_positive_ev():
    """Garante que propostas com edge real comprovado são aprovadas."""
    # Se a probabilidade for 55% e payout 1.95 -> EV = 0.55 * 1.95 - 1.0 = 0.0725 (+7.25%)
    result = validate_trade_expectation(
        prob=0.55,
        stake=1.0,
        payout=1.95,
        min_ev_ratio=0.01,
    )
    assert result.is_viable is True
    assert result.net_ev > 0.0
    assert result.net_ev_ratio > 0.01
    assert result.rejection_reason is None


def test_wilson_lower_bound_properties():
    """Testa consistência e propriedades assintóticas do Wilson Score Interval."""
    # Com 55 acertos em 100 tentativas
    lower_100 = calculate_wilson_lower_bound(successes=55, total=100, confidence=0.95)
    # Com 550 acertos em 1000 tentativas (mesma proporção, maior amostra)
    lower_1000 = calculate_wilson_lower_bound(successes=550, total=1000, confidence=0.95)

    assert lower_100 <= 0.55
    assert lower_1000 <= 0.55
    # Maior amostra deve estreitar o intervalo (limite inferior maior)
    assert lower_1000 > lower_100


def test_invalid_parameters_handling():
    """Testa tratamento de parâmetros anômalos ou inválidos."""
    with pytest.raises(ValueError, match="Payout .* deve ser superior ao stake"):
        calculate_break_even_probability(stake=10.0, payout=8.0)

    with pytest.raises(ValueError, match="Probabilidade inválida"):
        calculate_net_expected_value(prob=1.5, stake=10.0, payout=19.5)
