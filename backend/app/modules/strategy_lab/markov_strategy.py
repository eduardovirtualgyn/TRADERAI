"""Estratégia baseada em assimetria de transição em Cadeias de Markov de 2ª ordem."""

import time
from typing import List, Optional

from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment
from backend.app.modules.strategy_lab.base import BaseStrategy, SignalDirection, StrategySignal


class MarkovEdgeStrategy(BaseStrategy):
    """Explora assimetrias estatisticamente válidas nas probabilidades de transição de Markov."""

    def __init__(
        self,
        strategy_id: str = "markov_edge_v1",
        min_ticks_required: int = 50,
        min_ev_ratio: float = 0.01,
        enabled: bool = True,
    ):
        super().__init__(
            strategy_id=strategy_id,
            name="Markov Conditional Edge",
            description=(
                "Avalia se a probabilidade condicional de 2ª ordem P(S_t | S_{t-2}, S_{t-1}) "
                "supera o break-even com significância estatística (Wilson Lower Bound > P_be)."
            ),
            min_ticks_required=min_ticks_required,
            min_ev_ratio=min_ev_ratio,
            enabled=enabled,
        )

    def evaluate(
        self,
        ticks: List[TickData],
        stats: StatisticalAssessment,
        stake: float = 1.0,
        payout: float = 1.95,
    ) -> Optional[StrategySignal]:
        if not self.enabled or len(ticks) < self.min_ticks_required:
            return None

        latest_tick = ticks[-1]
        now_epoch = latest_tick.epoch if latest_tick else int(time.time())

        # Avaliação da ponta EVEN
        if stats.wilson_lower_even > stats.break_even_prob and stats.net_ev_ratio_even >= self.min_ev_ratio:
            return self.validate_and_build_signal(
                direction=SignalDirection.EVEN,
                estimated_prob=stats.conditional_p_even,
                confidence_lower_bound=stats.wilson_lower_even,
                stake=stake,
                payout=payout,
                timestamp=now_epoch,
                rationale=(
                    f"Markov Ordem 2 confirmou vantagem para EVEN: P_cond={stats.conditional_p_even:.2%}, "
                    f"Wilson Lower={stats.wilson_lower_even:.2%} > Break-even={stats.break_even_prob:.2%} "
                    f"(N_estado={stats.state_sample_size}, Net EV={stats.net_ev_ratio_even:+.2%})."
                ),
            )

        # Avaliação da ponta ODD
        if stats.wilson_lower_odd > stats.break_even_prob and stats.net_ev_ratio_odd >= self.min_ev_ratio:
            return self.validate_and_build_signal(
                direction=SignalDirection.ODD,
                estimated_prob=stats.conditional_p_odd,
                confidence_lower_bound=stats.wilson_lower_odd,
                stake=stake,
                payout=payout,
                timestamp=now_epoch,
                rationale=(
                    f"Markov Ordem 2 confirmou vantagem para ODD: P_cond={stats.conditional_p_odd:.2%}, "
                    f"Wilson Lower={stats.wilson_lower_odd:.2%} > Break-even={stats.break_even_prob:.2%} "
                    f"(N_estado={stats.state_sample_size}, Net EV={stats.net_ev_ratio_odd:+.2%})."
                ),
            )

        return None
