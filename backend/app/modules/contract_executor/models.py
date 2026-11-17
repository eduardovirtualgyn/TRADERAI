"""Modelos de dados para o Executor de Contratos da Deriv."""

from enum import Enum
import time
from typing import Optional
from pydantic import BaseModel, Field


class ContractStatus(str, Enum):
    """Estados do ciclo de vida de uma ordem de contrato."""

    PENDING_PROPOSAL = "PENDING_PROPOSAL"
    PROPOSAL_RECEIVED = "PROPOSAL_RECEIVED"
    REJECTED_BY_MATH = "REJECTED_BY_MATH"
    REJECTED_BY_RISK = "REJECTED_BY_RISK"
    BUY_SUBMITTED = "BUY_SUBMITTED"
    OPEN = "OPEN"
    WON = "WON"
    LOST = "LOST"
    ERROR = "ERROR"


class OrderRequest(BaseModel):
    """Parâmetros de uma intenção de execução de contrato."""

    symbol: str = Field(default="R_100", description="Símbolo do índice sintético ou ativo da Deriv")
    contract_type: str = Field(..., description="Tipo do contrato: 'DIGITEVEN' ou 'DIGITODD'")
    stake: float = Field(..., gt=0.0, description="Valor apostado em USD")
    duration: int = Field(default=1, ge=1, le=10, description="Duração do contrato em ticks")
    duration_unit: str = Field(default="t", description="Unidade temporal ('t' para ticks)")
    strategy_name: str = Field(default="manual", description="Nome da estratégia ou modelo emissor")
    estimated_probability: float = Field(..., ge=0.0, le=1.0, description="Probabilidade estimada P(Win)")
    wilson_lower_bound: float = Field(..., ge=0.0, le=1.0, description="Limite inferior do IC de Wilson")


class ExecutionResult(BaseModel):
    """Resultado detalhado do fluxo de execução do contrato."""

    success: bool = Field(..., description="Indica se a operação foi executada com sucesso")
    status: ContractStatus = Field(..., description="Estado final ou atual da ordem")
    symbol: str
    contract_type: str
    stake: float
    payout: float = 0.0
    net_pnl: float = 0.0
    contract_id: Optional[str] = None
    proposal_id: Optional[str] = None
    strategy_name: str = "manual"
    rejection_reason: Optional[str] = None
    execution_timestamp: float = Field(default_factory=time.time)
    completion_timestamp: Optional[float] = None
