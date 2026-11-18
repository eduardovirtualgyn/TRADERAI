"""Módulo de Negociação Autônoma (Auto-Trader)."""

from backend.app.modules.auto_trader.engine import AutoTraderEngine
from backend.app.modules.auto_trader.models import (
    AutoTraderConfig,
    AutoTraderStatusResponse,
    AutoTraderTogglePayload,
)

__all__ = [
    "AutoTraderEngine",
    "AutoTraderConfig",
    "AutoTraderStatusResponse",
    "AutoTraderTogglePayload",
]
