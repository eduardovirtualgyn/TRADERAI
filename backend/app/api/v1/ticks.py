"""Rotas da API para consulta de ticks, buffers e estatísticas rápidas."""

from fastapi import APIRouter, Depends
from backend.app.api.deps import get_tick_collector
from backend.app.modules.tick_collector.collector import TickCollector

router = APIRouter(prefix="/ticks", tags=["Ticks & Feed"])


@router.get("/summary", summary="Consulta o resumo estatístico dos últimos ticks coletados")
def get_ticks_summary(
    collector: TickCollector = Depends(get_tick_collector),
) -> dict:
    """Retorna o snapshot do buffer de ticks, streaks recentes e distribuições amostrais."""
    return collector.get_summary_snapshot()
