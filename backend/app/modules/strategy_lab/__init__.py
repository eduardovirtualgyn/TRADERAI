"""Módulo 4: Laboratório e registro de estratégias quantitativas."""

from backend.app.modules.strategy_lab.base import (
    BaseStrategy,
    SignalDirection,
    StrategySignal,
)
from backend.app.modules.strategy_lab.markov_strategy import MarkovEdgeStrategy
from backend.app.modules.strategy_lab.registry import StrategyRegistry
from backend.app.modules.strategy_lab.runs_strategy import RunsAnomalyStrategy
from backend.app.modules.strategy_lab.streak_strategy import StreakPersistenceStrategy

__all__ = [
    "BaseStrategy",
    "SignalDirection",
    "StrategySignal",
    "MarkovEdgeStrategy",
    "RunsAnomalyStrategy",
    "StreakPersistenceStrategy",
    "StrategyRegistry",
]
