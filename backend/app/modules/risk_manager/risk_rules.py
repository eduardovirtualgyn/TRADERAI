"""Módulo de Gestão de Risco, Limites Operacionais e Proteção Anti-Martingale.

Implementa os freios de emergência mandatórios, Circuit Breaker temporal,
dimensionamento fracionário de Kelly e prevenção da ruína matemática da conta.
"""

from dataclasses import dataclass
from typing import List, Optional
import numpy as np

from backend.app.core.errors import (
    AntiMartingaleViolationError,
    KillSwitchActiveError,
    RiskLimitExceededError,
)
from backend.app.core.logging import logger
from backend.app.modules.risk_manager.circuit_breaker import CircuitBreaker, CircuitBreakerStatus
from backend.app.modules.risk_manager.kelly_criterion import (
    KellyRecommendation,
    calculate_fractional_kelly,
)


@dataclass(frozen=True)
class RiskDecision:
    """Resultado da avaliação de risco para uma intenção de operação."""

    approved: bool
    reason: Optional[str] = None
    stake: float = 0.0
    consecutive_losses: int = 0
    daily_drawdown_usd: float = 0.0
    kill_switch_active: bool = False
    circuit_breaker_active: bool = False


class RiskManager:
    """Controlador central de exposição, limites, freios temporais e salvaguardas."""

    def __init__(
        self,
        max_stake_usd: float = 5.00,
        max_stake_percent: float = 0.01,
        max_consecutive_losses: int = 3,
        max_daily_loss_usd: float = 25.00,
        ban_martingale: bool = True,
        initial_balance_usd: float = 100.00,
        kill_switch_initially_active: bool = False,
        cooldown_duration_seconds: float = 60.0,
    ):
        self.max_stake_usd = float(max_stake_usd)
        self.max_stake_percent = float(max_stake_percent)
        self.max_consecutive_losses = int(max_consecutive_losses)
        self.max_daily_loss_usd = float(max_daily_loss_usd)
        self.ban_martingale = bool(ban_martingale)

        # Estado dinâmico da conta
        self.balance_usd = float(initial_balance_usd)
        self.daily_drawdown_usd = 0.0
        self.consecutive_losses = 0
        self.last_trade_won: Optional[bool] = None
        self.last_stake_usd: Optional[float] = None

        # Histórico de PnL para análise estatística e VaR
        self.pnl_history: List[float] = []

        # Circuit Breaker temporal
        self.circuit_breaker = CircuitBreaker(default_cooldown_seconds=cooldown_duration_seconds)

        # Kill Switch emergencial
        self.kill_switch_active = bool(kill_switch_initially_active)
        self.kill_switch_reason: Optional[str] = (
            "Inicialização com Kill Switch ativado por segurança."
            if self.kill_switch_active
            else None
        )

    def set_kill_switch(self, active: bool, reason: str = "") -> None:
        """Arma ou desarma o Kill Switch manualmente ou por evento de segurança."""
        self.kill_switch_active = active
        self.kill_switch_reason = reason if active else None
        if active:
            logger.warning("🚨 KILL SWITCH ATIVADO: %s", reason)
        else:
            logger.info("✅ KILL SWITCH DESARMADO MANUALMENTE.")

    def evaluate_trade(
        self,
        stake: float,
        net_ev_ratio: float,
        raise_on_violation: bool = False,
    ) -> RiskDecision:
        """Avalia se uma ordem proposta cumpre todos os critérios de risco."""
        # 1. Verificação do Kill Switch
        if self.kill_switch_active:
            reason = f"Kill Switch ATIVO: {self.kill_switch_reason or 'Intervenção preventiva'}"
            if raise_on_violation:
                raise KillSwitchActiveError(reason)
            return self._decision(False, reason, stake)

        # 2. Salvaguarda Anti-Martingale (Proibição Absoluta de Escalonamento após Perda)
        if self.ban_martingale and self.last_trade_won is False and self.last_stake_usd is not None:
            if stake > (self.last_stake_usd + 1e-4):
                reason = (
                    f"VIOLAÇÃO ANTI-MARTINGALE: Tentativa de aumentar o stake de "
                    f"${self.last_stake_usd:.2f} para ${stake:.2f} após derrota. "
                    "Estratégia bloqueada pelo protocolo de segurança."
                )
                if raise_on_violation:
                    raise AntiMartingaleViolationError(reason)
                return self._decision(False, reason, stake)

        # 3. Verificação do Circuit Breaker Temporal
        if self.circuit_breaker.is_active():
            rem = self.circuit_breaker.remaining_seconds()
            reason = f"Circuit Breaker ATIVO: Pausa de resfriamento em andamento ({rem:.1f}s restantes). Motivo: {self.circuit_breaker.get_status().reason}"
            if raise_on_violation:
                raise RiskLimitExceededError(reason)
            return self._decision(False, reason, stake)

        # 4. Verificação de Vantagem Matemática
        if net_ev_ratio <= 0.0:
            reason = f"Rejeitado pelo Risco: Expectativa líquida não positiva (EV_ratio={net_ev_ratio:.2%})."
            return self._decision(False, reason, stake)

        # 5. Limite de Perdas Consecutivas
        if self.consecutive_losses >= self.max_consecutive_losses:
            reason = (
                f"Limite de {self.max_consecutive_losses} derrotas consecutivas atingido. "
                "Pausa mandatória para recalibração estatística."
            )
            if raise_on_violation:
                raise RiskLimitExceededError(reason)
            return self._decision(False, reason, stake)

        # 6. Limite de Drawdown Diário
        if self.daily_drawdown_usd >= self.max_daily_loss_usd:
            reason = (
                f"Limite de perda diária atingido (${self.daily_drawdown_usd:.2f} >= "
                f"${self.max_daily_loss_usd:.2f}). Operações suspensas pelo restante do dia."
            )
            if raise_on_violation:
                raise RiskLimitExceededError(reason)
            return self._decision(False, reason, stake)

        # 7. Teto Absoluto de Stake
        if stake > self.max_stake_usd:
            reason = (
                f"Stake de ${stake:.2f} excede o teto máximo absoluto de ${self.max_stake_usd:.2f}."
            )
            if raise_on_violation:
                raise RiskLimitExceededError(reason)
            return self._decision(False, reason, stake)

        # 8. Teto Proporcional à Banca
        allowed_by_balance = self.balance_usd * self.max_stake_percent
        if stake > allowed_by_balance:
            reason = (
                f"Stake de ${stake:.2f} excede o limite proporcional de {self.max_stake_percent:.1%} "
                f"da banca atual (${self.balance_usd:.2f} -> máx permitido: ${allowed_by_balance:.2f})."
            )
            if raise_on_violation:
                raise RiskLimitExceededError(reason)
            return self._decision(False, reason, stake)

        return self._decision(True, None, stake)

    def calculate_kelly_stake(
        self,
        win_probability: float,
        payout: float,
        stake_ref: float = 1.0,
        fraction_factor: float = 0.20,
    ) -> KellyRecommendation:
        """Calcula o dimensionamento conservador ótimo baseado em Kelly e restrições da conta."""
        return calculate_fractional_kelly(
            win_probability=win_probability,
            payout=payout,
            stake_ref=stake_ref,
            balance=self.balance_usd,
            fraction_factor=fraction_factor,
            min_stake=0.35,
            max_stake_usd=self.max_stake_usd,
            max_stake_percent=self.max_stake_percent,
        )

    def record_trade_result(self, won: bool, pnl_usd: float, stake_used: float) -> None:
        """Atualiza os contadores de risco após a resolução oficial de um contrato."""
        self.balance_usd += pnl_usd
        self.last_stake_usd = stake_used
        self.last_trade_won = won
        self.pnl_history.append(float(pnl_usd))

        if won:
            self.consecutive_losses = 0
            logger.info(
                "Trade VENCEDOR (+US$ %.2f). Saldo atual: US$ %.2f. Streak de perdas zerado.",
                pnl_usd,
                self.balance_usd,
            )
        else:
            self.consecutive_losses += 1
            loss_amount = abs(pnl_usd)
            self.daily_drawdown_usd += loss_amount
            logger.warning(
                "Trade DERROTADO (-US$ %.2f). Derrotas consecutivas: %d/%d. Perda diária: US$ %.2f/%.2f",
                loss_amount,
                self.consecutive_losses,
                self.max_consecutive_losses,
                self.daily_drawdown_usd,
                self.max_daily_loss_usd,
            )

            # Acionamento de Circuit Breaker em derrotas consecutivas intermediárias (a partir da 2ª derrota seguida)
            if 1 < self.consecutive_losses < self.max_consecutive_losses:
                self.circuit_breaker.trigger(
                    reason=f"Pausa preventiva por {self.consecutive_losses} derrotas seguidas.",
                    duration_seconds=30.0,
                )

            # Acionamento preventivo de salvaguarda em caso de limite estourado
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.set_kill_switch(
                    True,
                    f"Disparo automático por {self.consecutive_losses} derrotas consecutivas.",
                )
            elif self.daily_drawdown_usd >= self.max_daily_loss_usd:
                self.set_kill_switch(
                    True,
                    f"Disparo automático por perda diária acumulada de US$ {self.daily_drawdown_usd:.2f}.",
                )

    def calculate_historical_var_95(self) -> float:
        """Calcula o Value at Risk histórico a 95% de confiança para 1 trade."""
        if len(self.pnl_history) < 10:
            return 0.0
        # 5º percentil das perdas
        q5 = np.percentile(self.pnl_history, 5)
        return float(abs(min(0.0, q5)))

    def reset_daily_drawdown(self) -> None:
        """Reinicia os contadores diários (virada de dia UTC)."""
        logger.info("Reiniciando contador de drawdown diário.")
        self.daily_drawdown_usd = 0.0

    def get_status(self) -> dict:
        """Retorna o snapshot do estado de risco para auditoria e telemetria."""
        cb_status = self.circuit_breaker.get_status()
        total_trades = len(self.pnl_history)
        wins = sum(1 for p in self.pnl_history if p > 0)
        win_rate = (wins / total_trades) if total_trades > 0 else 0.0

        return {
            "balance_usd": round(self.balance_usd, 2),
            "daily_drawdown_usd": round(self.daily_drawdown_usd, 2),
            "max_daily_loss_usd": self.max_daily_loss_usd,
            "consecutive_losses": self.consecutive_losses,
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_stake_usd": self.max_stake_usd,
            "max_stake_percent": self.max_stake_percent,
            "ban_martingale": self.ban_martingale,
            "kill_switch_active": self.kill_switch_active,
            "kill_switch_reason": self.kill_switch_reason,
            "circuit_breaker_active": cb_status.active,
            "circuit_breaker_remaining_seconds": cb_status.remaining_seconds,
            "circuit_breaker_reason": cb_status.reason,
            "last_stake_usd": self.last_stake_usd,
            "last_trade_won": self.last_trade_won,
            "total_trades_recorded": total_trades,
            "win_rate": round(win_rate, 4),
            "historical_var_95_usd": round(self.calculate_historical_var_95(), 2),
        }

    def _decision(self, approved: bool, reason: Optional[str], stake: float) -> RiskDecision:
        return RiskDecision(
            approved=approved,
            reason=reason,
            stake=stake,
            consecutive_losses=self.consecutive_losses,
            daily_drawdown_usd=self.daily_drawdown_usd,
            kill_switch_active=self.kill_switch_active,
            circuit_breaker_active=self.circuit_breaker.is_active(),
        )
