"""Interface base e modelos de dados para estratégias quantitativas."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment
from backend.app.modules.statistical_engine.ev_calculator import (
    calculate_break_even_probability,
    calculate_net_ev_ratio,
)


class SignalDirection(str, Enum):
    """Direção da aposta contratual de dígito."""

    EVEN = "EVEN"
    ODD = "ODD"


@dataclass(frozen=True)
class StrategySignal:
    """Sinal quantitativo tipado emitido por uma estratégia avaliada."""

    strategy_id: str
    direction: SignalDirection
    estimated_prob: float
    confidence_lower_bound: float
    net_ev_ratio: float
    stake: float
    payout: float
    break_even_prob: float
    timestamp: int
    rationale: str


class BaseStrategy(ABC):
    """Classe base abstrata para todas as estratégias do ODD/EVEN AI TRADER."""

    def __init__(
        self,
        strategy_id: str,
        name: str,
        description: str,
        min_ticks_required: int = 50,
        min_ev_ratio: float = 0.01,
        enabled: bool = True,
    ):
        self.strategy_id = strategy_id
        self.name = name
        self.description = description
        self.min_ticks_required = min_ticks_required
        self.min_ev_ratio = min_ev_ratio
        self.enabled = enabled

    @abstractmethod
    def evaluate(
        self,
        ticks: List[TickData],
        stats: StatisticalAssessment,
        stake: float = 1.0,
        payout: float = 1.95,
    ) -> Optional[StrategySignal]:
        """Avalia a série temporal de ticks e métricas estatísticas para gerar sinal."""
        pass

    def validate_and_build_signal(
        self,
        direction: SignalDirection,
        estimated_prob: float,
        confidence_lower_bound: float,
        stake: float,
        payout: float,
        timestamp: int,
        rationale: str,
    ) -> Optional[StrategySignal]:
        """Aplica o filtro matemático estrito antes de autorizar a emissão do sinal.

        REGRA CARDEAL: O sinal SÓ é emitido se CI_lower > P_be e Net EV ratio > min_ev_ratio.
        """
        p_be = calculate_break_even_probability(stake, payout)
        ev_ratio = calculate_net_ev_ratio(estimated_prob, stake, payout)

        # 1. Validação de Expectativa Líquida Positiva
        if ev_ratio < self.min_ev_ratio:
            return None

        # 2. Validação de Significância Estatística (Wilson Lower Bound deve superar o Break-Even)
        if confidence_lower_bound <= p_be:
            return None

        return StrategySignal(
            strategy_id=self.strategy_id,
            direction=direction,
            estimated_prob=round(estimated_prob, 4),
            confidence_lower_bound=round(confidence_lower_bound, 4),
            net_ev_ratio=round(ev_ratio, 4),
            stake=stake,
            payout=payout,
            break_even_prob=round(p_be, 4),
            timestamp=timestamp,
            rationale=rationale,
        )
