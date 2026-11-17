"""Estratégia quantitativa acoplada a agentes de inteligência artificial supervisionados."""

import time
from typing import List, Optional

from backend.app.modules.ai_agents.features import extract_features_single
from backend.app.modules.ai_agents.models import BaseAIModel
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment
from backend.app.modules.statistical_engine.ev_calculator import calculate_wilson_lower_bound
from backend.app.modules.strategy_lab.base import BaseStrategy, SignalDirection, StrategySignal


class AIPredictiveStrategy(BaseStrategy):
    """Estratégia que utiliza inferência probabilística calibrada de modelos de IA."""

    def __init__(
        self,
        strategy_id: str,
        name: str,
        model: BaseAIModel,
        min_ticks_required: int = 50,
        min_ev_ratio: float = 0.01,
        enabled: bool = True,
    ):
        super().__init__(
            strategy_id=strategy_id,
            name=name,
            description=f"Estratégia supervisionada baseada no estimador {model.model_name}.",
            min_ticks_required=min_ticks_required,
            min_ev_ratio=min_ev_ratio,
            enabled=enabled,
        )
        self.model = model

    def evaluate(
        self,
        ticks: List[TickData],
        stats: StatisticalAssessment,
        stake: float = 1.0,
        payout: float = 1.95,
    ) -> Optional[StrategySignal]:
        if not self.enabled or len(ticks) < self.min_ticks_required:
            return None

        # O modelo DEVE estar treinado e aprovado no teste de calibração (Brier < 0.25)
        if not self.model.is_trained or not self.model.metrics or not self.model.metrics.is_calibrated:
            return None

        latest_tick = ticks[-1]
        now_epoch = latest_tick.epoch if latest_tick else int(time.time())

        # Extração de features estritamente no tempo t
        x_vec = extract_features_single(ticks)
        p_even, p_odd = self.model.predict_probability(x_vec)

        # Amostra de validação do modelo para cálculo do intervalo de confiança Wilson
        n_samples = max(20, self.model.metrics.sample_count // 4)

        # 1. Avalia hipótese EVEN
        ci_lower_even = calculate_wilson_lower_bound(
            successes=int(round(p_even * n_samples)),
            total=n_samples,
            confidence=0.95,
        )

        if ci_lower_even > stats.break_even_prob:
            return self.validate_and_build_signal(
                direction=SignalDirection.EVEN,
                estimated_prob=p_even,
                confidence_lower_bound=ci_lower_even,
                stake=stake,
                payout=payout,
                timestamp=now_epoch,
                rationale=(
                    f"Agente IA ({self.model.model_name}) estimou P(EVEN)={p_even:.2%} "
                    f"com Wilson Lower={ci_lower_even:.2%} > Break-even={stats.break_even_prob:.2%} "
                    f"(Brier Score do modelo={self.model.metrics.brier_score:.4f})."
                ),
            )

        # 2. Avalia hipótese ODD
        ci_lower_odd = calculate_wilson_lower_bound(
            successes=int(round(p_odd * n_samples)),
            total=n_samples,
            confidence=0.95,
        )

        if ci_lower_odd > stats.break_even_prob:
            return self.validate_and_build_signal(
                direction=SignalDirection.ODD,
                estimated_prob=p_odd,
                confidence_lower_bound=ci_lower_odd,
                stake=stake,
                payout=payout,
                timestamp=now_epoch,
                rationale=(
                    f"Agente IA ({self.model.model_name}) estimou P(ODD)={p_odd:.2%} "
                    f"com Wilson Lower={ci_lower_odd:.2%} > Break-even={stats.break_even_prob:.2%} "
                    f"(Brier Score do modelo={self.model.metrics.brier_score:.4f})."
                ),
            )

        return None
