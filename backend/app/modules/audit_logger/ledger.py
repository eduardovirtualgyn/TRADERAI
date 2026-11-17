"""Módulo 10: Livro-Razão Imutável de Auditoria (AuditLedger).

Registra todas as propostas, decisões matemáticas, vetos de risco,
execuções na Deriv e liquidações financeiras em uma estrutura encadeada por SHA-256.
"""

import csv
import io
import json
import time
from typing import List, Optional

from backend.app.core.logging import logger
from backend.app.modules.audit_logger.models import AuditMetrics, AuditRecord
from backend.app.modules.contract_executor.models import (
    ContractStatus,
    ExecutionResult,
)


class AuditLedger:
    """Livro-razão append-only com verificação criptográfica de integridade."""

    def __init__(self):
        self._records: List[AuditRecord] = []
        self._seq: int = 0

    @property
    def last_hash(self) -> str:
        """Retorna o hash do registro mais recente ou o hash gênese."""
        if not self._records:
            return "0" * 64
        return self._records[-1].record_hash

    def record_event(
        self,
        event_type: str,
        symbol: str = "R_100",
        contract_type: str = "N/A",
        stake: float = 0.0,
        payout: float = 0.0,
        net_pnl: float = 0.0,
        status: str = "INFO",
        strategy_name: str = "system",
        reason: Optional[str] = None,
        contract_id: Optional[str] = None,
        proposal_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> AuditRecord:
        """Cria e encadeia um novo registro de auditoria."""
        self._seq += 1
        rec_id = f"REC-{self._seq:06d}"

        record = AuditRecord.create(
            record_id=rec_id,
            event_type=event_type,
            symbol=symbol,
            contract_type=contract_type,
            stake=stake,
            payout=payout,
            net_pnl=net_pnl,
            status=status,
            strategy_name=strategy_name,
            prev_hash=self.last_hash,
            reason=reason,
            contract_id=contract_id,
            proposal_id=proposal_id,
            timestamp=timestamp,
        )

        self._records.append(record)
        return record

    def record_execution_result(self, result: ExecutionResult) -> AuditRecord:
        """Converte e audita o resultado emitido pelo ContractExecutor."""
        event_type = "TRADE_EXECUTION"
        if result.status == ContractStatus.WON:
            event_type = "SETTLEMENT_WIN"
        elif result.status == ContractStatus.LOST:
            event_type = "SETTLEMENT_LOSS"
        elif "REJECTED" in result.status.value:
            event_type = "ORDER_REJECTION"
        elif result.status == ContractStatus.ERROR:
            event_type = "EXECUTION_ERROR"

        return self.record_event(
            event_type=event_type,
            symbol=result.symbol,
            contract_type=result.contract_type,
            stake=result.stake,
            payout=result.payout,
            net_pnl=result.net_pnl,
            status=result.status.value,
            strategy_name=result.strategy_name,
            reason=result.rejection_reason,
            contract_id=result.contract_id,
            proposal_id=result.proposal_id,
            timestamp=result.completion_timestamp or result.execution_timestamp,
        )

    def verify_integrity(self) -> bool:
        """Verifica se toda a cadeia de registros mantém integridade estrita (sem adulterações)."""
        expected_prev = "0" * 64

        for rec in self._records:
            # 1. Verifica encadeamento com o bloco anterior
            if rec.prev_hash != expected_prev:
                logger.error(
                    "Violação de integridade no registro %s: prev_hash esperado %s, encontrado %s",
                    rec.record_id,
                    expected_prev,
                    rec.prev_hash,
                )
                return False

            # 2. Recalcula o hash do registro com os dados atuais
            recalculated = AuditRecord.create(
                record_id=rec.record_id,
                event_type=rec.event_type,
                symbol=rec.symbol,
                contract_type=rec.contract_type,
                stake=rec.stake,
                payout=rec.payout,
                net_pnl=rec.net_pnl,
                status=rec.status,
                strategy_name=rec.strategy_name,
                prev_hash=rec.prev_hash,
                reason=rec.reason,
                contract_id=rec.contract_id,
                proposal_id=rec.proposal_id,
                timestamp=rec.timestamp,
            ).record_hash

            if recalculated != rec.record_hash:
                logger.error(
                    "Violação de assinatura no registro %s: hash adulterado!",
                    rec.record_id,
                )
                return False

            expected_prev = rec.record_hash

        return True

    def get_records(
        self,
        limit: int = 100,
        status_filter: Optional[str] = None,
        event_type_filter: Optional[str] = None,
    ) -> List[AuditRecord]:
        """Consulta os registros mais recentes com filtros opcionais."""
        filtered = self._records
        if status_filter:
            filtered = [r for r in filtered if r.status == status_filter]
        if event_type_filter:
            filtered = [r for r in filtered if r.event_type == event_type_filter]

        return list(reversed(filtered[-limit:]))

    def compute_metrics(self) -> AuditMetrics:
        """Calcula métricas agregadas de desempenho e auditoria."""
        total = len(self._records)
        executed = sum(1 for r in self._records if r.status == ContractStatus.BUY_SUBMITTED.value)
        rejected_math = sum(1 for r in self._records if r.status == ContractStatus.REJECTED_BY_MATH.value)
        rejected_risk = sum(1 for r in self._records if r.status == ContractStatus.REJECTED_BY_RISK.value)
        wins = sum(1 for r in self._records if r.status == ContractStatus.WON.value)
        losses = sum(1 for r in self._records if r.status == ContractStatus.LOST.value)
        settled = wins + losses

        win_rate = (wins / settled) if settled > 0 else 0.0

        gross_profit = sum(r.net_pnl for r in self._records if r.status == ContractStatus.WON.value and r.net_pnl > 0)
        gross_loss = sum(abs(r.net_pnl) for r in self._records if r.status == ContractStatus.LOST.value and r.net_pnl < 0)
        net_pnl = gross_profit - gross_loss

        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        return AuditMetrics(
            total_records=total,
            executed_trades=executed,
            settled_trades=settled,
            rejected_by_math=rejected_math,
            rejected_by_risk=rejected_risk,
            wins=wins,
            losses=losses,
            win_rate=round(win_rate, 4),
            gross_profit_usd=round(gross_profit, 2),
            gross_loss_usd=round(gross_loss, 2),
            net_pnl_usd=round(net_pnl, 2),
            profit_factor=round(profit_factor, 2),
            ledger_integrity_verified=self.verify_integrity(),
        )

    def export_csv(self) -> str:
        """Exporta os registros do ledger em formato CSV padrão."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "record_id",
            "timestamp",
            "event_type",
            "symbol",
            "contract_type",
            "stake",
            "payout",
            "net_pnl",
            "status",
            "strategy_name",
            "contract_id",
            "proposal_id",
            "reason",
            "record_hash",
        ])

        for r in self._records:
            writer.writerow([
                r.record_id,
                r.timestamp,
                r.event_type,
                r.symbol,
                r.contract_type,
                r.stake,
                r.payout,
                r.net_pnl,
                r.status,
                r.strategy_name,
                r.contract_id or "",
                r.proposal_id or "",
                r.reason or "",
                r.record_hash,
            ])

        return output.getvalue()

    def export_json(self) -> str:
        """Exporta os registros do ledger em formato JSON formatado."""
        data = [r.model_dump() for r in self._records]
        return json.dumps(data, indent=2)
