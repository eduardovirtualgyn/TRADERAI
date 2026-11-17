"""Módulo 1: Integração oficial com Deriv WebSocket API (Demo Guarded)."""

from backend.app.modules.deriv_client.client import (
    DerivWebSocketClient,
    extract_last_digit,
)
from backend.app.modules.deriv_client.models import (
    ContractBuyResult,
    DerivAuthorizeResponse,
    DerivConnectionState,
    ProposalData,
    TickData,
)

__all__ = [
    "DerivWebSocketClient",
    "DerivConnectionState",
    "DerivAuthorizeResponse",
    "TickData",
    "ProposalData",
    "ContractBuyResult",
    "extract_last_digit",
]
