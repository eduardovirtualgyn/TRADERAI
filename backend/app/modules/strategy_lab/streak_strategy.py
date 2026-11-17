"""Estratégia de análise empírica de sequências (Streaks) com rejeição da Falácia do Jogador."""

import time
from typing import List, Optional

from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment
from backend.app.modules.statistical_engine.ev_calculator import calculate_wilson_lower_bound
from backend.app.modules.strategy_lab.base import BaseStrategy, SignalDirection, StrategySignal
from backend.app.modules.tick_collector.streak_analyzer import calculate_current_streak


class StreakPersistenceStrategy(BaseStrategy):
    """Avalia o comportamento empírico de streaks sem incorrer na Falácia do Jogador.

    AVISO METODOLÓGICO: Nunca aposta em reversão presumida ('falácia do apostador').
    Apenas emite sinal se houver assimetria comprovada na taxa de continuação/reversão
    com Wilson Lower Bound > Break-even.
    """

    def __init__(
        self,
        strategy_id: str = "streak_persistence_v1",
        min_streak_trigger: int = 4,
        min_historical_occurrences: int = 15,
        min_ticks_required: int = 100,
        min_ev_ratio: float = 0.01,
        enabled: bool = True,
    ):
        super().__init__(
            strategy_id=strategy_id,
            name="Streak Empirical Analysis",
            description=(
                "Monitora sequências de paridade (streaks >= 4) e avalia a taxa empírica observada "
                "de continuação vs reversão no histórico recente, rejeitando a falácia do jogador."
            ),
            min_ticks_required=min_ticks_required,
            min_ev_ratio=min_ev_ratio,
            enabled=enabled,
        )
        self.min_streak_trigger = min_streak_trigger
        self.min_historical_occurrences = min_historical_occurrences

    def evaluate(
        self,
        ticks: List[TickData],
        stats: StatisticalAssessment,
        stake: float = 1.0,
        payout: float = 1.95,
    ) -> Optional[StrategySignal]:
        if not self.enabled or len(ticks) < self.min_ticks_required:
            return None

        streak = calculate_current_streak(ticks)
        if streak.length < self.min_streak_trigger:
            return None

        current_is_even = (streak.direction == "EVEN")
        latest_tick = ticks[-1]
        now_epoch = latest_tick.epoch if latest_tick else int(time.time())

        # Contagem histórica no buffer de ocorrências de streaks >= min_streak_trigger
        continued_count = 0
        reversed_count = 0

        # Rastreia histórico
        curr_run_len = 1
        for i in range(1, len(ticks) - 1):
            if ticks[i].is_even == ticks[i - 1].is_even:
                curr_run_len += 1
            else:
                curr_run_len = 1

            if curr_run_len >= self.min_streak_trigger and ticks[i].is_even == current_is_even:
                # O próximo tick continuou ou reverteu?
                next_is_same = (ticks[i + 1].is_even == current_is_even)
                if next_is_same:
                    continued_count += 1
                else:
                    reversed_count += 1

        total_occurrences = continued_count + reversed_count
        if total_occurrences < self.min_historical_occurrences:
            return None

        # Testa se a taxa de continuação supera o break-even
        continue_rate = continued_count / total_occurrences
        ci_lower_continue = calculate_wilson_lower_bound(continued_count, total_occurrences, confidence=0.95)

        if ci_lower_continue > stats.break_even_prob:
            target_dir = SignalDirection.EVEN if current_is_even else SignalDirection.ODD
            return self.validate_and_build_signal(
                direction=target_dir,
                estimated_prob=continue_rate,
                confidence_lower_bound=ci_lower_continue,
                stake=stake,
                payout=payout,
                timestamp=now_epoch,
                rationale=(
                    f"Assimetria empírica de persistência para streak {streak.direction} (len={streak.length}). "
                    f"Taxa de continuação histórica: {continue_rate:.2%} ({continued_count}/{total_occurrences}), "
                    f"Wilson Lower: {ci_lower_continue:.2%} > Break-even: {stats.break_even_prob:.2%}."
                ),
            )

        # Testa se a taxa de reversão supera o break-even
        reverse_rate = reversed_count / total_occurrences
        ci_lower_reverse = calculate_wilson_lower_bound(reversed_count, total_occurrences, confidence=0.95)

        if ci_lower_reverse > stats.break_even_prob:
            target_dir = SignalDirection.ODD if current_is_even else SignalDirection.EVEN
            return self.validate_and_build_signal(
                direction=target_dir,
                estimated_prob=reverse_rate,
                confidence_lower_bound=ci_lower_reverse,
                stake=stake,
                payout=payout,
                timestamp=now_epoch,
                rationale=(
                    f"Assimetria empírica de reversão comprovada para streak {streak.direction} (len={streak.length}). "
                    f"Taxa de reversão histórica: {reverse_rate:.2%} ({reversed_count}/{total_occurrences}), "
                    f"Wilson Lower: {ci_lower_reverse:.2%} > Break-even: {stats.break_even_prob:.2%}."
                ),
            )

        return None
