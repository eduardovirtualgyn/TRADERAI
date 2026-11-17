"""Estratégia baseada em anomalias de independência serial (Wald-Wolfowitz Runs Test)."""

import time
from typing import List, Optional

from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment
from backend.app.modules.statistical_engine.ev_calculator import calculate_wilson_lower_bound
from backend.app.modules.strategy_lab.base import BaseStrategy, SignalDirection, StrategySignal


class RunsAnomalyStrategy(BaseStrategy):
    """Detecta distorções extremas na alternância ou agrupamento de paridade (|Z| >= 2.58)."""

    def __init__(
        self,
        strategy_id: str = "runs_anomaly_v1",
        z_threshold: float = 2.58,  # Nível de significância p < 0.01
        min_ticks_required: int = 50,
        min_ev_ratio: float = 0.01,
        enabled: bool = True,
    ):
        super().__init__(
            strategy_id=strategy_id,
            name="Runs Serial Anomaly",
            description=(
                "Explora desvios de independência serial detectados pelo Runs Test (|Z| >= 2.58). "
                "Z > 2.58 indica alternância excessiva; Z < -2.58 indica persistência anômala."
            ),
            min_ticks_required=min_ticks_required,
            min_ev_ratio=min_ev_ratio,
            enabled=enabled,
        )
        self.z_threshold = z_threshold

    def evaluate(
        self,
        ticks: List[TickData],
        stats: StatisticalAssessment,
        stake: float = 1.0,
        payout: float = 1.95,
    ) -> Optional[StrategySignal]:
        if not self.enabled or len(ticks) < self.min_ticks_required:
            return None

        runs_res = stats.runs_test
        if abs(runs_res.z_score) < self.z_threshold:
            return None

        latest_tick = ticks[-1]
        now_epoch = latest_tick.epoch if latest_tick else int(time.time())
        current_is_even = latest_tick.is_even

        # 1. Caso Z fortemente positivo (> +2.58): Alternância excessiva
        # A tendência empírica anormal favorece alternar em relação ao dígito atual
        if runs_res.z_score >= self.z_threshold:
            target_direction = SignalDirection.ODD if current_is_even else SignalDirection.EVEN
            # Mensuração da taxa empírica de alternância na janela
            alternations = sum(1 for i in range(1, len(ticks)) if ticks[i].is_even != ticks[i - 1].is_even)
            total_transitions = len(ticks) - 1
            alt_rate = alternations / total_transitions if total_transitions > 0 else 0.5
            ci_lower = calculate_wilson_lower_bound(alternations, total_transitions, confidence=0.95)

            return self.validate_and_build_signal(
                direction=target_direction,
                estimated_prob=alt_rate,
                confidence_lower_bound=ci_lower,
                stake=stake,
                payout=payout,
                timestamp=now_epoch,
                rationale=(
                    f"Runs test detectou alternância anômala extrema (Z={runs_res.z_score:+.2f}, "
                    f"p={runs_res.p_value:.4f}). Taxa empírica de alternância: {alt_rate:.2%} "
                    f"(Wilson Lower: {ci_lower:.2%}). Direção projetada: {target_direction.value}."
                ),
            )

        # 2. Caso Z fortemente negativo (< -2.58): Agrupamento anômalo (Clustering)
        # A tendência empírica anormal favorece persistência na mesma paridade do dígito atual
        if runs_res.z_score <= -self.z_threshold:
            target_direction = SignalDirection.EVEN if current_is_even else SignalDirection.ODD
            persistences = sum(1 for i in range(1, len(ticks)) if ticks[i].is_even == ticks[i - 1].is_even)
            total_transitions = len(ticks) - 1
            persist_rate = persistences / total_transitions if total_transitions > 0 else 0.5
            ci_lower = calculate_wilson_lower_bound(persistences, total_transitions, confidence=0.95)

            return self.validate_and_build_signal(
                direction=target_direction,
                estimated_prob=persist_rate,
                confidence_lower_bound=ci_lower,
                stake=stake,
                payout=payout,
                timestamp=now_epoch,
                rationale=(
                    f"Runs test detectou agrupamento anômalo extremo (Z={runs_res.z_score:+.2f}, "
                    f"p={runs_res.p_value:.4f}). Taxa empírica de persistência: {persist_rate:.2%} "
                    f"(Wilson Lower: {ci_lower:.2%}). Direção projetada: {target_direction.value}."
                ),
            )

        return None
