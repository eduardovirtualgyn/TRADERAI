"""Testes unitários do RiskManager e salvaguardas Anti-Martingale."""

import pytest
from backend.app.core.errors import (
    AntiMartingaleViolationError,
    KillSwitchActiveError,
    RiskLimitExceededError,
)
from backend.app.modules.risk_manager.risk_rules import RiskManager


def test_risk_evaluation_approval(risk_manager: RiskManager):
    """Valida aprovação de trade dentro de todos os parâmetros regulamentares."""
    decision = risk_manager.evaluate_trade(stake=2.00, net_ev_ratio=0.03)
    assert decision.approved is True
    assert decision.reason is None


def test_reject_stake_exceeding_max_usd(risk_manager: RiskManager):
    """Garante rejeição se o stake ultrapassar o teto em USD (max: $5.00)."""
    decision = risk_manager.evaluate_trade(stake=10.00, net_ev_ratio=0.05)
    assert decision.approved is False
    assert "excede o teto máximo absoluto" in decision.reason

    with pytest.raises(RiskLimitExceededError):
        risk_manager.evaluate_trade(stake=10.00, net_ev_ratio=0.05, raise_on_violation=True)


def test_reject_stake_exceeding_proportional_limit(risk_manager: RiskManager):
    """Garante rejeição se o stake exceder o percentual da banca (1% de $1000 = $10, mas se banca for $200, 1% é $2)."""
    risk_manager.balance_usd = 200.00  # 1% = $2.00
    decision = risk_manager.evaluate_trade(stake=3.00, net_ev_ratio=0.05)
    assert decision.approved is False
    assert "excede o limite proporcional" in decision.reason


def test_kill_switch_blocking(risk_manager: RiskManager):
    """Garante bloqueio absoluto quando Kill Switch está ativado."""
    risk_manager.set_kill_switch(True, "Parada de emergência para teste")
    decision = risk_manager.evaluate_trade(stake=1.00, net_ev_ratio=0.05)
    assert decision.approved is False
    assert "Kill Switch ATIVO" in decision.reason

    with pytest.raises(KillSwitchActiveError):
        risk_manager.evaluate_trade(stake=1.00, net_ev_ratio=0.05, raise_on_violation=True)


def test_anti_martingale_guard_blocks_stake_escalation(risk_manager: RiskManager):
    """Garante que tentar dobrar ou aumentar stake após derrota seja terminantemente bloqueado."""
    # Simula derrota anterior com stake de $2.00
    risk_manager.record_trade_result(won=False, pnl_usd=-2.00, stake_used=2.00)

    # Tentativa de aplicar Martingale: apostar $4.00 após derrota de $2.00
    decision = risk_manager.evaluate_trade(stake=4.00, net_ev_ratio=0.05)
    assert decision.approved is False
    assert "VIOLAÇÃO ANTI-MARTINGALE" in decision.reason

    # Com raise_on_violation=True, deve lançar exceção específica
    with pytest.raises(AntiMartingaleViolationError, match="VIOLAÇÃO ANTI-MARTINGALE"):
        risk_manager.evaluate_trade(stake=4.00, net_ev_ratio=0.05, raise_on_violation=True)

    # No entanto, operar com o mesmo stake ($2.00) ou menor ($1.00) é permitido pelas regras de stake
    decision_same = risk_manager.evaluate_trade(stake=2.00, net_ev_ratio=0.05)
    assert decision_same.approved is True


def test_consecutive_losses_limit_and_auto_kill_switch(risk_manager: RiskManager):
    """Garante que atingir o teto de derrotas consecutivas dispara bloqueio e Kill Switch."""
    assert risk_manager.consecutive_losses == 0

    # 3 derrotas consecutivas
    risk_manager.record_trade_result(won=False, pnl_usd=-1.00, stake_used=1.00)
    assert risk_manager.kill_switch_active is False

    risk_manager.record_trade_result(won=False, pnl_usd=-1.00, stake_used=1.00)
    assert risk_manager.kill_switch_active is False

    risk_manager.record_trade_result(won=False, pnl_usd=-1.00, stake_used=1.00)
    # Atingiu 3 derrotas: o Kill Switch deve ser acionado automaticamente
    assert risk_manager.consecutive_losses == 3
    assert risk_manager.kill_switch_active is True

    # Nova tentativa de trade deve ser sumariamente bloqueada
    decision = risk_manager.evaluate_trade(stake=1.00, net_ev_ratio=0.05)
    assert decision.approved is False
