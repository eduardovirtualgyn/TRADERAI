"""Modelos de dados e métricas de desempenho para o motor de Backtesting."""

from dataclasses import dataclass, field
from typing import List, Optional
from backend.app.modules.strategy_lab.base import SignalDirection


@dataclass(frozen=True)
class BacktestTrade:
    """Registro imutável de uma operação executada na simulação."""

    trade_id: int
    entry_tick_index: int
    exit_tick_index: int
    entry_epoch: int
    exit_epoch: int
    strategy_id: str
    direction: SignalDirection
    predicted_prob: float
    confidence_lower_bound: float
    stake: float
    payout: float
    exit_digit: int
    won: bool
    net_pnl: float
    balance_after: float
    rationale: str


@dataclass(frozen=True)
class BacktestMetrics:
    """Consolidado de métricas quantitativas de risco e retorno da simulação."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    initial_balance: float
    final_balance: float
    total_net_pnl: float
    profit_factor: float
    average_trade_pnl: float
    max_drawdown_usd: float
    max_drawdown_pct: float
    max_consecutive_losses: int
    max_consecutive_wins: int
    risk_blocks_count: int


@dataclass
class BacktestReport:
    """Relatório completo gerado ao final de um ciclo de backtesting."""

    strategy_id: str
    total_ticks_analyzed: int
    metrics: BacktestMetrics
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
