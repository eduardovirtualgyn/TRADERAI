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


def test_one_dollar_stake_survives_single_loss_on_small_demo():
    """1% de US$ 99 é US$ 0,99 e travava para sempre o stake de US$ 1."""
    manager = RiskManager(
        max_stake_usd=5.00,
        max_stake_percent=0.01,
        max_consecutive_losses=3,
        max_daily_loss_usd=25.00,
        initial_balance_usd=100.00,
    )
    manager.record_trade_result(won=False, pnl_usd=-1.00, stake_used=1.00)
    assert manager.balance_usd == pytest.approx(99.00)
    decision = manager.evaluate_trade(stake=1.00, net_ev_ratio=0.05)
    assert decision.approved is True, decision.reason


def test_kill_switch_disarm_resets_loss_streak_and_drawdown():
    """Desarmar não pode deixar o robô preso nas 3 derrotas que armaram a trava."""
    manager = RiskManager(
        max_stake_usd=5.00,
        max_stake_percent=0.05,
        max_consecutive_losses=3,
        max_daily_loss_usd=25.00,
        initial_balance_usd=1000.00,
    )
    for _ in range(3):
        manager.record_trade_result(won=False, pnl_usd=-1.00, stake_used=1.00)

    assert manager.kill_switch_active is True
    assert manager.consecutive_losses == 3
    assert manager.daily_drawdown_usd == pytest.approx(3.00)

    manager.set_kill_switch(False)
    assert manager.kill_switch_active is False
    assert manager.consecutive_losses == 0
    assert manager.daily_drawdown_usd == pytest.approx(0.00)
    assert manager.circuit_breaker.is_active() is False

    decision = manager.evaluate_trade(stake=1.00, net_ev_ratio=0.05)
    assert decision.approved is True, decision.reason


def test_daily_drawdown_resets_on_utc_date_change():
    """O drawdown do dia zera na virada UTC, senão o teto bloqueia para sempre."""
    from datetime import date

    manager = RiskManager(
        max_stake_usd=5.00,
        max_stake_percent=0.05,
        max_consecutive_losses=3,
        max_daily_loss_usd=25.00,
        initial_balance_usd=1000.00,
    )
    manager.daily_drawdown_usd = 25.00
    manager._drawdown_utc_date = date(2020, 1, 1)

    decision = manager.evaluate_trade(stake=1.00, net_ev_ratio=0.05)
    assert manager.daily_drawdown_usd == pytest.approx(0.00)
    assert decision.approved is True, decision.reason
