"""Rotas da API para gerenciamento do laboratório de estratégias e consulta de sinais."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.api.deps import (
    get_statistical_evaluator,
    get_strategy_registry,
    get_tick_collector,
)
from backend.app.modules.statistical_engine.evaluator import StatisticalEvaluator
from backend.app.modules.strategy_lab.registry import StrategyRegistry
from backend.app.modules.tick_collector.collector import TickCollector

router = APIRouter(prefix="/strategies", tags=["Strategy Lab"])


class StrategyTogglePayload(BaseModel):
    """Payload para habilitar ou desabilitar uma estratégia."""

    enabled: bool = Field(..., description="True para ativar, False para desativar")


@router.get("", summary="Lista todas as estratégias registradas no laboratório")
def list_strategies(
    registry: StrategyRegistry = Depends(get_strategy_registry),
) -> List[dict]:
    """Retorna o catálogo de estratégias, seus identificadores e parâmetros ativos."""
    return registry.list_strategies()


@router.post("/{strategy_id}/toggle", summary="Habilita ou desabilita uma estratégia específica")
def toggle_strategy(
    strategy_id: str,
    payload: StrategyTogglePayload,
    registry: StrategyRegistry = Depends(get_strategy_registry),
) -> dict:
    """Modifica o status de ativação da estratégia informada."""
    success = registry.toggle(strategy_id, enabled=payload.enabled)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Estratégia com id '{strategy_id}' não encontrada no registro.",
        )
    return {
        "success": True,
        "strategy_id": strategy_id,
        "enabled": payload.enabled,
    }


@router.get("/signals", summary="Avalia as estratégias ativas contra os ticks recentes e retorna sinais")
def get_active_signals(
    stake: float = 1.0,
    payout: float = 1.95,
    collector: TickCollector = Depends(get_tick_collector),
    evaluator: StatisticalEvaluator = Depends(get_statistical_evaluator),
    registry: StrategyRegistry = Depends(get_strategy_registry),
) -> dict:
    """Executa as estratégias ativas sobre os ticks em memória e retorna sinais aprovados."""
    ticks = collector.buffer.get_last_n_ticks(1000)
    stats = evaluator.evaluate_ticks(ticks=ticks, stake=stake, payout=payout)
    signals = registry.evaluate_all(ticks=ticks, stats=stats, stake=stake, payout=payout)

    return {
        "total_signals": len(signals),
        "signals": [
            {
                "strategy_id": s.strategy_id,
                "direction": s.direction.value,
                "estimated_prob": s.estimated_prob,
                "confidence_lower_bound": s.confidence_lower_bound,
                "break_even_prob": s.break_even_prob,
                "net_ev_ratio": s.net_ev_ratio,
                "stake": s.stake,
                "payout": s.payout,
                "timestamp": s.timestamp,
                "rationale": s.rationale,
            }
            for s in signals
        ],
    }
