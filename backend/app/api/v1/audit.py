"""Rotas da API para Auditoria, Livro-Razão e Verificação Criptográfica."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response
from backend.app.api.deps import get_audit_ledger
from backend.app.modules.audit_logger.ledger import AuditLedger
from backend.app.modules.audit_logger.models import AuditMetrics, AuditRecord

router = APIRouter(prefix="/audit", tags=["Audit & Ledger"])


@router.get("/logs", summary="Consulta os registros de auditoria com filtros opcionais")
def get_audit_logs(
    limit: int = 100,
    status_filter: Optional[str] = None,
    event_type: Optional[str] = None,
    ledger: AuditLedger = Depends(get_audit_ledger),
) -> List[AuditRecord]:
    """Retorna os registros encadeados mais recentes."""
    return ledger.get_records(
        limit=limit,
        status_filter=status_filter,
        event_type_filter=event_type,
    )


@router.get("/metrics", summary="Consulta as métricas analíticas e de conformidade do ledger")
def get_audit_metrics(
    ledger: AuditLedger = Depends(get_audit_ledger),
) -> AuditMetrics:
    """Calcula taxas de acerto, rejeições de risco/matemática e lucro líquido real."""
    return ledger.compute_metrics()


@router.get("/verify", summary="Executa verificação criptográfica estrita do livro-razão")
def verify_ledger_integrity(
    ledger: AuditLedger = Depends(get_audit_ledger),
) -> dict:
    """Recalcula e confere todos os hashes SHA-256 encadeados."""
    is_valid = ledger.verify_integrity()
    return {
        "valid": is_valid,
        "total_records": len(ledger._records),
        "last_hash": ledger.last_hash,
        "message": "Cadeia de auditoria 100% íntegra." if is_valid else "VIOLAÇÃO DE INTEGRIDADE DETECTADA!",
    }


@router.get("/export/csv", summary="Exporta o histórico de auditoria em formato CSV")
def export_csv(
    ledger: AuditLedger = Depends(get_audit_ledger),
) -> Response:
    """Gera arquivo CSV para download e auditoria externa."""
    csv_content = ledger.export_csv()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=odd_even_audit_ledger.csv"},
    )


@router.get("/export/json", summary="Exporta o histórico de auditoria em formato JSON")
def export_json(
    ledger: AuditLedger = Depends(get_audit_ledger),
) -> Response:
    """Gera arquivo JSON estruturado para compliance."""
    json_content = ledger.export_json()
    return Response(
        content=json_content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=odd_even_audit_ledger.json"},
    )
