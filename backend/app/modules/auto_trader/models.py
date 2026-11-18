"""Modelos de dados para o módulo de Auto-Trader Autônomo."""

from typing import Optional
from pydantic import BaseModel, Field


class AutoTraderConfig(BaseModel):
    """Configurações operacionais do robô autônomo."""

    enabled: bool = Field(default=False, description="Liga ou desliga o Auto-Trader")
    symbol: str = Field(default="R_100", description="Índice sintético operado")
    stake: float = Field(default=1.0, ge=0.35, le=5.0, description="Stake por operação em USD")
    min_probability: float = Field(default=0.52, ge=0.50, le=0.90, description="Probabilidade mínima calculada")
    min_wilson_lower_bound: float = Field(default=0.51, ge=0.50, le=0.85, description="Limite inferior de Wilson mínimo")
    cooldown_seconds: float = Field(default=2.0, ge=1.0, le=60.0, description="Intervalo mínimo entre trades em segundos")


class AutoTraderTogglePayload(BaseModel):
    """Payload para ligar ou desligar o Auto-Trader."""

    enabled: bool = Field(..., description="True para ligar, False para desligar")


class AutoTraderStatusResponse(BaseModel):
    """Estado em tempo real e telemetria do robô autônomo."""

    enabled: bool
    state: str = Field(
        description="Estado da máquina de estados: STOPPED, SEARCHING_EDGE, EXECUTING, COOLDOWN, PAUSED_BY_RISK"
    )
    symbol: str
    stake: float
    min_probability: float
    cooldown_seconds: float
    last_decision: str
    last_action_timestamp: Optional[float] = None
    total_trades: int = 0
    won_trades: int = 0
    lost_trades: int = 0
    session_pnl: float = 0.0
    active_contract_id: Optional[str] = None
