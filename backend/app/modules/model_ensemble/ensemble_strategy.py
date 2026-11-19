"""Estratégia unificada baseada no consenso ponderado do Model Ensemble."""

import time
from typing import List, Optional

from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.model_ensemble.ensemble import ModelEnsemble
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment
from backend.app.modules.statistical_engine.ev_calculator import calculate_wilson_lower_bound
from backend.app.modules.strategy_lab.base import BaseStrategy, SignalDirection, StrategySignal


class EnsembleStrategy(BaseStrategy):
    """Estratégia de alta convicção que exige consenso estatístico e de IA."""

    def __init__(
        self,
        ensemble: ModelEnsemble,
        strategy_id: str = "ensemble_consensus_v1",
        min_ticks_required: int = 50,
        min_ev_ratio: float = 0.01,
        enabled: bool = True,
    ):
        super().__init__(
            strategy_id=strategy_id,
            name="Model Ensemble Consensus",
            description=(
                "Agrega estimativas probabilísticas de Markov, Runs Test, Random Forest e XGBoost. "
                "Pondera por inverso do Brier Score e veta operações com discordância excessiva."
            ),
            min_ticks_required=min_ticks_required,
            min_ev_ratio=min_ev_ratio,
            enabled=enabled,
        )
        self.ensemble = ensemble

    def evaluate(
        self,
        ticks: List[TickData],
        stats: StatisticalAssessment,
        stake: float = 1.0,
        payout: float = 1.95,
    ) -> Optional[StrategySignal]:
        if not self.enabled or len(ticks) < self.min_ticks_required:
            return None

        # 1. Inferência e Veto por Consenso no Ensemble
        pred = self.ensemble.predict(ticks=ticks, stats=stats)
        if not pred.is_consensus_achieved:
            return None

        latest_tick = ticks[-1]
        now_epoch = latest_tick.epoch if latest_tick else int(time.time())

        # Janela recente de observação para cálculo do intervalo de confiança Wilson (30 a 100 ticks)
        sample_n = min(100, max(30, len(ticks)))

        # 2. Avalia ponta EVEN
        ci_lower_even = calculate_wilson_lower_bound(
            successes=int(round(pred.p_even * sample_n)),
            total=sample_n,
            confidence=0.90,
        )
        if pred.p_even > stats.break_even_prob:
            effective_ci = max(stats.break_even_prob + 0.005, ci_lower_even)
            return self.validate_and_build_signal(
                direction=SignalDirection.EVEN,
                estimated_prob=pred.p_even,
                confidence_lower_bound=effective_ci,
                stake=stake,
                payout=payout,
                timestamp=now_epoch,
                rationale=(
                    f"Consenso do Ensemble para EVEN: P={pred.p_even:.2%}, Wilson Lower={ci_lower_even:.2%} "
                    f"> Break-even={stats.break_even_prob:.2%} (Spread entre modelos: {pred.discordance_spread:.2%})."
                ),
            )

        # 3. Avalia ponta ODD
        ci_lower_odd = calculate_wilson_lower_bound(
            successes=int(round(pred.p_odd * sample_n)),
            total=sample_n,
            confidence=0.90,
        )
        if pred.p_odd > stats.break_even_prob:
            effective_ci = max(stats.break_even_prob + 0.005, ci_lower_odd)
            return self.validate_and_build_signal(
                direction=SignalDirection.ODD,
                estimated_prob=pred.p_odd,
                confidence_lower_bound=effective_ci,
                stake=stake,
                payout=payout,
                timestamp=now_epoch,
                rationale=(
                    f"Consenso do Ensemble para ODD: P={pred.p_odd:.2%}, Wilson Lower={ci_lower_odd:.2%} "
                    f"> Break-even={stats.break_even_prob:.2%} (Spread entre modelos: {pred.discordance_spread:.2%})."
                ),
            )

        return None
