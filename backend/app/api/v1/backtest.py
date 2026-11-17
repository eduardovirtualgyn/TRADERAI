"""Rotas da API para execução de simulações e backtesting."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.deps import (
    get_statistical_evaluator,
    get_strategy_registry,
    get_tick_collector,
)
from backend.app.modules.backtesting.engine import BacktestEngine
from backend.app.modules.backtesting.models import BacktestReport
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalEvaluator
from backend.app.modules.strategy_lab.registry import StrategyRegistry
from backend.app.modules.tick_collector.collector import TickCollector

router = APIRouter(prefix="/backtest", tags=["Backtesting Engine"])


class BacktestRequest(BaseModel):
    """Payload de solicitação de execução de backtest."""

    strategy_id: str = Field(..., description="Identificador da estratégia (ex: markov_edge_v1)")
    ticks_source: str = Field(default="buffer", description="'buffer' para usar ticks em memória ou 'custom'")
    custom_digits: Optional[List[int]] = Field(default=None, description="Lista de dígitos para teste personalizado")
    initial_balance: float = Field(default=1000.0, gt=0, description="Saldo inicial da simulação em USD")
    stake: float = Field(default=1.0, gt=0, description="Valor do stake por trade em USD")
    payout_ratio: float = Field(default=1.95, gt=1.0, description="Multiplicador de payout da corretora")
    enable_risk_manager: bool = Field(default=True, description="Habilita salvaguardas e kill switch no backtest")


def _report_to_dict(report: BacktestReport) -> dict:
    m = report.metrics
    return {
        "strategy_id": report.strategy_id,
        "total_ticks_analyzed": report.total_ticks_analyzed,
        "metrics": {
            "total_trades": m.total_trades,
            "winning_trades": m.winning_trades,
            "losing_trades": m.losing_trades,
            "win_rate": m.win_rate,
            "initial_balance": m.initial_balance,
            "final_balance": m.final_balance,
            "total_net_pnl": m.total_net_pnl,
            "profit_factor": m.profit_factor,
            "average_trade_pnl": m.average_trade_pnl,
            "max_drawdown_usd": m.max_drawdown_usd,
            "max_drawdown_pct": m.max_drawdown_pct,
            "max_consecutive_losses": m.max_consecutive_losses,
            "max_consecutive_wins": m.max_consecutive_wins,
            "risk_blocks_count": m.risk_blocks_count,
        },
        "trades_count": len(report.trades),
        "recent_trades": [
            {
                "trade_id": t.trade_id,
                "direction": t.direction.value,
                "entry_tick": t.entry_tick_index,
                "exit_tick": t.exit_tick_index,
                "exit_digit": t.exit_digit,
                "won": t.won,
                "net_pnl": t.net_pnl,
                "balance_after": t.balance_after,
                "rationale": t.rationale,
            }
            for t in report.trades[-20:]  # Últimos 20 trades para resumo conciso
        ],
        "equity_curve_samples": report.equity_curve[:: max(1, len(report.equity_curve) // 50)],
    }


@router.post("/run", summary="Executa uma simulação walk-forward sem vazamento de dados")
def run_backtest(
    request: BacktestRequest,
    collector: TickCollector = Depends(get_tick_collector),
    registry: StrategyRegistry = Depends(get_strategy_registry),
    evaluator: StatisticalEvaluator = Depends(get_statistical_evaluator),
) -> dict:
    """Executa a simulação histórica estrita e retorna relatório com métricas quantitativas."""
    strategy = registry.get(request.strategy_id)
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail=f"Estratégia '{request.strategy_id}' não encontrada no laboratório.",
        )

    # Obtenção dos ticks para a simulação
    if request.ticks_source == "custom":
        if not request.custom_digits:
            raise HTTPException(
                status_code=400,
                detail="Quando 'ticks_source' for 'custom', o campo 'custom_digits' é obrigatório.",
            )
        ticks = [
            TickData.from_api_payload({
                "epoch": 1700000000 + i,
                "quote": 100.0 + (d / 100.0),
                "pip_size": 2,
                "symbol": "R_100",
            })
            for i, d in enumerate(request.custom_digits)
        ]
    else:
        ticks = collector.buffer.get_last_n_ticks(5000)

    if len(ticks) < strategy.min_ticks_required:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Série de ticks insuficiente ({len(ticks)} ticks disponíveis). "
                f"A estratégia requer no mínimo {strategy.min_ticks_required} ticks."
            ),
        )

    engine = BacktestEngine(
        initial_balance=request.initial_balance,
        default_stake=request.stake,
        default_payout_ratio=request.payout_ratio,
        duration_ticks=1,
        enable_risk_manager=request.enable_risk_manager,
    )

    report = engine.run(
        ticks=ticks,
        strategy=strategy,
        evaluator=evaluator,
        stake=request.stake,
        payout_ratio=request.payout_ratio,
    )

    return _report_to_dict(report)
