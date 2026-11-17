"""Testes avançados de Gestão de Risco: Critério de Kelly Fracionário, Circuit Breaker e VaR."""

import time
import pytest
from backend.app.modules.risk_manager.circuit_breaker import CircuitBreaker
from backend.app.modules.risk_manager.kelly_criterion import calculate_fractional_kelly
from backend.app.modules.risk_manager.risk_rules import RiskManager
from backend.app.api.v1.risk import (
    trigger_circuit_breaker,
    reset_circuit_breaker,
    calculate_kelly,
    CircuitBreakerTriggerPayload,
    KellyCalculationPayload,
)


def test_fractional_kelly_positive_edge():
    """Valida o cálculo do Kelly Fracionário com probabilidade vantajosa."""
    # Ex: P=0.55, Payout=1.95, Stake=1.00 (b = 0.95)
    # f* = (0.55 * 0.95 - 0.45) / 0.95 = (0.5225 - 0.45) / 0.95 = 0.0725 / 0.95 = ~0.0763 (7.63%)
    # Kelly Fracionário 20%: f_frac = 0.0763 * 0.20 = 0.01526 (1.526%)
    # Em banca de $1000: raw_stake = $15.26
    # Mas o teto absoluto é $5.00 e max percent é 1% ($10.00). O stake deve ser limitado pelo teto de $5.00.
    rec = calculate_fractional_kelly(
        win_probability=0.55,
        payout=1.95,
        stake_ref=1.0,
        balance=1000.0,
        fraction_factor=0.20,
        min_stake=0.35,
        max_stake_usd=5.00,
        max_stake_percent=0.01,
    )
    assert rec.approved is True
    assert rec.edge > 0
    assert rec.full_kelly_f > 0
    assert rec.recommended_stake == 5.00  # limitado pelo teto absoluto


def test_fractional_kelly_conservative_stake():
    """Valida dimensionamento proporcional quando dentro dos tetos."""
    # Em banca de $100: 1% é $1.00.
    # f_frac = 0.01526 -> raw_stake = $1.52 -> limitado por 1% ($1.00)
    rec = calculate_fractional_kelly(
        win_probability=0.55,
        payout=1.95,
        stake_ref=1.0,
        balance=100.0,
        fraction_factor=0.20,
        min_stake=0.35,
        max_stake_usd=5.00,
        max_stake_percent=0.01,
    )
    assert rec.approved is True
    assert rec.recommended_stake == 1.00


def test_fractional_kelly_negative_or_zero_edge():
    """Rejeita categoricamente qualquer aposta sem vantagem matemática comprovada."""
    # P=0.50 (moeda honesta) com Payout=1.95 (EV negativo)
    rec = calculate_fractional_kelly(
        win_probability=0.50,
        payout=1.95,
        stake_ref=1.0,
        balance=1000.0,
    )
    assert rec.approved is False
    assert rec.recommended_stake == 0.0
    assert "Sem vantagem estatística" in rec.reason


def test_fractional_kelly_below_minimum():
    """Rejeita se a stake calculada for menor que o mínimo da corretora ($0.35)."""
    # Banca muito pequena ($10.00), 1% = $0.10 < $0.35
    rec = calculate_fractional_kelly(
        win_probability=0.55,
        payout=1.95,
        stake_ref=1.0,
        balance=10.0,
        min_stake=0.35,
        max_stake_percent=0.01,
    )
    assert rec.approved is False
    assert rec.recommended_stake == 0.0
    assert "inferior ao mínimo regulamentar" in rec.reason


def test_circuit_breaker_lifecycle():
    """Testa ativação, persistência e desarme do Circuit Breaker."""
    cb = CircuitBreaker(default_cooldown_seconds=2.0)
    assert cb.is_active() is False

    cb.trigger(reason="Teste de volatilidade alta", duration_seconds=1.5)
    assert cb.is_active() is True
    assert cb.remaining_seconds() > 0
    status = cb.get_status()
    assert status.active is True
    assert status.reason == "Teste de volatilidade alta"

    # Reset manual
    cb.reset()
    assert cb.is_active() is False
    assert cb.remaining_seconds() == 0.0


def test_circuit_breaker_blocks_risk_manager(risk_manager: RiskManager):
    """Garante que com Circuit Breaker ativo, o evaluate_trade bloqueia novas ordens."""
    risk_manager.circuit_breaker.trigger("Pausa após draw rápido", duration_seconds=60.0)
    decision = risk_manager.evaluate_trade(stake=1.00, net_ev_ratio=0.05)
    assert decision.approved is False
    assert "Circuit Breaker ATIVO" in decision.reason
    assert decision.circuit_breaker_active is True


def test_historical_var_calculation(risk_manager: RiskManager):
    """Testa o cálculo do VaR histórico a 95% a partir de perdas reais."""
    assert risk_manager.calculate_historical_var_95() == 0.0  # < 10 trades

    # Simula 20 operações
    for i in range(16):
        risk_manager.record_trade_result(won=True, pnl_usd=0.95, stake_used=1.00)
    for i in range(4):
        risk_manager.record_trade_result(won=False, pnl_usd=-1.00, stake_used=1.00)

    var_95 = risk_manager.calculate_historical_var_95()
    assert var_95 >= 0.0
    status = risk_manager.get_status()
    assert status["total_trades_recorded"] == 20
    assert status["win_rate"] == 0.80


def test_api_risk_advanced_endpoints(risk_manager: RiskManager):
    """Testa as novas rotas de Kelly e Circuit Breaker diretamente."""
    # Rota de Kelly
    payload_k = KellyCalculationPayload(win_probability=0.55, payout=1.95, fraction_factor=0.20)
    res_k = calculate_kelly(payload=payload_k, risk_manager=risk_manager)
    assert res_k["approved"] is True
    assert res_k["recommended_stake"] > 0

    # Trigger Circuit Breaker
    payload_cb = CircuitBreakerTriggerPayload(duration_seconds=45.0, reason="Teste de API")
    res_cb = trigger_circuit_breaker(payload=payload_cb, risk_manager=risk_manager)
    assert res_cb["circuit_breaker_active"] is True
    assert res_cb["remaining_seconds"] > 0

    # Reset Circuit Breaker
    res_rst = reset_circuit_breaker(risk_manager=risk_manager)
    assert res_rst["circuit_breaker_active"] is False
