"""Modelos de dados para o Livro-Razão de Auditoria e Telemetria."""

import hashlib
import json
import time
from typing import Optional
from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    """Registro imutável com encadeamento de integridade criptográfica (Hash-Chained)."""

    record_id: str = Field(..., description="Identificador único sequencial ou UUID")
    timestamp: float = Field(default_factory=time.time, description="Timestamp UTC de registro")
    event_type: str = Field(..., description="Tipo de evento: EXECUTION, SETTLEMENT, REJECTION, etc.")
    symbol: str = Field(default="R_100")
    contract_type: str = Field(default="N/A")
    stake: float = 0.0
    payout: float = 0.0
    net_pnl: float = 0.0
    status: str = Field(..., description="Estado do contrato ou ordem")
    strategy_name: str = "manual"
    reason: Optional[str] = None
    contract_id: Optional[str] = None
    proposal_id: Optional[str] = None
    prev_hash: str = Field(default="0" * 64, description="Hash SHA-256 do registro anterior")
    record_hash: str = Field(default="", description="Hash SHA-256 deste registro")

    @classmethod
    def create(
        cls,
        record_id: str,
        event_type: str,
        symbol: str,
        contract_type: str,
        stake: float,
        payout: float,
        net_pnl: float,
        status: str,
        strategy_name: str,
        prev_hash: str,
        reason: Optional[str] = None,
        contract_id: Optional[str] = None,
        proposal_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> "AuditRecord":
        """Cria e assina criptograficamente um registro com SHA-256."""
        ts = timestamp if timestamp is not None else time.time()
        payload = (
            f"{record_id}|{ts:.4f}|{event_type}|{symbol}|{contract_type}|"
            f"{stake:.2f}|{payout:.2f}|{net_pnl:.2f}|{status}|{strategy_name}|"
            f"{reason or ''}|{contract_id or ''}|{proposal_id or ''}|{prev_hash}"
        )
        record_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        return cls(
            record_id=record_id,
            timestamp=ts,
            event_type=event_type,
            symbol=symbol,
            contract_type=contract_type,
            stake=stake,
            payout=payout,
            net_pnl=net_pnl,
            status=status,
            strategy_name=strategy_name,
            reason=reason,
            contract_id=contract_id,
            proposal_id=proposal_id,
            prev_hash=prev_hash,
            record_hash=record_hash,
        )


class AuditMetrics(BaseModel):
    """Métricas consolidadas de conformidade e performance do ledger."""

    total_records: int = 0
    executed_trades: int = 0
    settled_trades: int = 0
    rejected_by_math: int = 0
    rejected_by_risk: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    gross_profit_usd: float = 0.0
    gross_loss_usd: float = 0.0
    net_pnl_usd: float = 0.0
    profit_factor: float = 0.0
    ledger_integrity_verified: bool = True
