"""Catálogo e orquestrador de registro de estratégias quantitativas."""

from typing import Dict, List, Optional

from backend.app.core.logging import logger
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment
from backend.app.modules.strategy_lab.base import BaseStrategy, StrategySignal
from backend.app.modules.strategy_lab.markov_strategy import MarkovEdgeStrategy
from backend.app.modules.strategy_lab.runs_strategy import RunsAnomalyStrategy
from backend.app.modules.strategy_lab.streak_strategy import StreakPersistenceStrategy


class StrategyRegistry:
    """Gerenciador central de ciclo de vida e avaliação de estratégias."""

    def __init__(self, register_defaults: bool = True):
        self._strategies: Dict[str, BaseStrategy] = {}
        if register_defaults:
            self._register_default_strategies()

    def _register_default_strategies(self) -> None:
        """Registra as estratégias nativas do ODD/EVEN AI TRADER."""
        self.register(MarkovEdgeStrategy())
        self.register(RunsAnomalyStrategy())
        self.register(StreakPersistenceStrategy())

    def register(self, strategy: BaseStrategy) -> None:
        """Adiciona uma nova estratégia ao registro."""
        self._strategies[strategy.strategy_id] = strategy
        logger.info("Estratégia quantitativa registrada: %s (%s)", strategy.name, strategy.strategy_id)

    def unregister(self, strategy_id: str) -> bool:
        """Remove uma estratégia do registro."""
        if strategy_id in self._strategies:
            del self._strategies[strategy_id]
            logger.info("Estratégia desregistrada: %s", strategy_id)
            return True
        return False

    def get(self, strategy_id: str) -> Optional[BaseStrategy]:
        """Obtém uma estratégia pelo seu identificador."""
        return self._strategies.get(strategy_id)

    def toggle(self, strategy_id: str, enabled: bool) -> bool:
        """Habilita ou desabilita uma estratégia em tempo de execução."""
        strategy = self.get(strategy_id)
        if not strategy:
            return False
        strategy.enabled = enabled
        logger.info("Estratégia %s alterada para enabled=%s", strategy_id, enabled)
        return True

    def list_strategies(self) -> List[dict]:
        """Lista todas as estratégias registradas e seus metadados."""
        return [
            {
                "strategy_id": s.strategy_id,
                "name": s.name,
                "description": s.description,
                "enabled": s.enabled,
                "min_ticks_required": s.min_ticks_required,
                "min_ev_ratio": s.min_ev_ratio,
            }
            for s in self._strategies.values()
        ]

    def evaluate_all(
        self,
        ticks: List[TickData],
        stats: StatisticalAssessment,
        stake: float = 1.0,
        payout: float = 1.95,
    ) -> List[StrategySignal]:
        """Avalia todas as estratégias ativas e consolida os sinais válidos emitidos."""
        active_signals: List[StrategySignal] = []

        for strat in self._strategies.values():
            if not strat.enabled:
                continue
            try:
                signal = strat.evaluate(ticks=ticks, stats=stats, stake=stake, payout=payout)
                if signal is not None:
                    active_signals.append(signal)
            except Exception as exc:
                logger.error("Erro ao avaliar estratégia %s: %s", strat.strategy_id, exc)

        return active_signals
