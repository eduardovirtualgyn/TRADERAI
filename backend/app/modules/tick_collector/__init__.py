"""Módulo 2: Coleta, ring-buffer e persistência assíncrona de ticks."""

from backend.app.modules.tick_collector.buffer import TickBuffer
from backend.app.modules.tick_collector.collector import TickCollector
from backend.app.modules.tick_collector.storage import (
    BaseTickStorage,
    InMemoryTickStorage,
)
from backend.app.modules.tick_collector.streak_analyzer import (
    StreakInfo,
    WindowDistribution,
    calculate_current_streak,
    calculate_window_distribution,
)

__all__ = [
    "TickBuffer",
    "TickCollector",
    "BaseTickStorage",
    "InMemoryTickStorage",
    "StreakInfo",
    "WindowDistribution",
    "calculate_current_streak",
    "calculate_window_distribution",
]
