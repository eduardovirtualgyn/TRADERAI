"""Motor de simulação sequencial (Walk-Forward) estrito sem vazamento de dados.

Garante que na avaliação do instante t nenhuma informação de t + 1 seja acessível.
"""

import math
from typing import List, Optional

from backend.app.modules.backtesting.models import (
    BacktestMetrics,
    BacktestReport,
    BacktestTrade,
)
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.risk_manager.risk_rules import RiskManager
from backend.app.modules.statistical_engine.evaluator import StatisticalEvaluator
from backend.app.modules.strategy_lab.base import BaseStrategy, SignalDirection


class BacktestEngine:
    """Simulador walk-forward tick-a-tick com modelagem de execução da Deriv."""

    def __init__(
        self,
        initial_balance: float = 1000.0,
        default_stake: float = 1.0,
        default_payout_ratio: float = 1.95,
        duration_ticks: int = 1,
        enable_risk_manager: bool = True,
    ):
        self.initial_balance = float(initial_balance)
        self.default_stake = float(default_stake)
        self.default_payout_ratio = float(default_payout_ratio)
        self.duration_ticks = int(duration_ticks)
        self.enable_risk_manager = bool(enable_risk_manager)

    def run(
        self,
        ticks: List[TickData],
        strategy: BaseStrategy,
        evaluator: Optional[StatisticalEvaluator] = None,
        stake: Optional[float] = None,
        payout_ratio: Optional[float] = None,
    ) -> BacktestReport:
        """Executa a simulação linear estrita sem Look-Ahead Bias."""
        active_stake = float(stake or self.default_stake)
        active_payout_ratio = float(payout_ratio or self.default_payout_ratio)
        active_payout = active_stake * active_payout_ratio

        active_evaluator = evaluator or StatisticalEvaluator(
            min_sample_size=strategy.min_ticks_required,
            default_stake=active_stake,
            default_payout=active_payout,
        )

        current_balance = self.initial_balance
        equity_curve = [current_balance]
        trades: List[BacktestTrade] = []
        risk_blocks_count = 0

        # Gerenciador de risco isolado para o backtest
        risk_mgr: Optional[RiskManager] = None
        if self.enable_risk_manager:
            risk_mgr = RiskManager(
                max_stake_usd=active_stake * 5.0,
                max_stake_percent=0.05,
                max_consecutive_losses=3,
                max_daily_loss_usd=active_stake * 20.0,
                ban_martingale=True,
                initial_balance_usd=self.initial_balance,
            )

        n_ticks = len(ticks)
        start_index = max(strategy.min_ticks_required, active_evaluator.min_sample_size)
        trade_id = 0

        t = start_index
        while t < n_ticks:
            # PROTOCOLO ZERO DATA LEAKAGE: Apenas ticks estritamente até t são visíveis!
            visible_ticks = ticks[: t + 1]

            # 1. Inferência estatística no momento t
            stats = active_evaluator.evaluate_ticks(
                ticks=visible_ticks,
                stake=active_stake,
                payout=active_payout,
            )

            # 2. Avaliação de estratégia no momento t
            signal = strategy.evaluate(
                ticks=visible_ticks,
                stats=stats,
                stake=active_stake,
                payout=active_payout,
            )

            if signal is not None:
                # 3. Portão de Risco
                if risk_mgr:
                    risk_decision = risk_mgr.evaluate_trade(
                        stake=signal.stake,
                        net_ev_ratio=signal.net_ev_ratio,
                        raise_on_violation=False,
                    )
                    if not risk_decision.approved:
                        risk_blocks_count += 1
                        t += 1
                        continue

                # 4. Resolução da Ordem no instante futuro t + duration_ticks
                exit_index = t + self.duration_ticks
                if exit_index >= n_ticks:
                    # Fim dos dados históricos antes da resolução do contrato
                    break

                exit_tick = ticks[exit_index]
                exit_digit = exit_tick.last_digit

                # Verificação de vitória ou derrota
                if signal.direction == SignalDirection.EVEN:
                    won = exit_tick.is_even
                else:
                    won = not exit_tick.is_even

                # Cálculo de PnL financeiro real da Deriv
                if won:
                    pnl = signal.payout - signal.stake  # Lucro líquido positivo
                else:
                    pnl = -signal.stake                # Perda do stake

                current_balance += pnl
                equity_curve.append(round(current_balance, 2))

                trade_id += 1
                trades.append(
                    BacktestTrade(
                        trade_id=trade_id,
                        entry_tick_index=t,
                        exit_tick_index=exit_index,
                        entry_epoch=visible_ticks[-1].epoch,
                        exit_epoch=exit_tick.epoch,
                        strategy_id=strategy.strategy_id,
                        direction=signal.direction,
                        predicted_prob=signal.estimated_prob,
                        confidence_lower_bound=signal.confidence_lower_bound,
                        stake=signal.stake,
                        payout=signal.payout,
                        exit_digit=exit_digit,
                        won=won,
                        net_pnl=round(pnl, 2),
                        balance_after=round(current_balance, 2),
                        rationale=signal.rationale,
                    )
                )

                if risk_mgr:
                    risk_mgr.record_trade_result(won=won, pnl_usd=pnl, stake_used=signal.stake)

                # Avança o tempo até a expiração do contrato
                t = exit_index
            else:
                t += 1

        # Consolidação analítica das métricas de desempenho
        metrics = self._calculate_metrics(
            trades=trades,
            initial_balance=self.initial_balance,
            final_balance=current_balance,
            equity_curve=equity_curve,
            risk_blocks_count=risk_blocks_count,
        )

        return BacktestReport(
            strategy_id=strategy.strategy_id,
            total_ticks_analyzed=n_ticks,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
        )

    def _calculate_metrics(
        self,
        trades: List[BacktestTrade],
        initial_balance: float,
        final_balance: float,
        equity_curve: List[float],
        risk_blocks_count: int,
    ) -> BacktestMetrics:
        """Calcula o conjunto formal de métricas estatísticas e financeiras."""
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.won)
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0

        total_net_pnl = final_balance - initial_balance
        avg_trade_pnl = (total_net_pnl / total_trades) if total_trades > 0 else 0.0

        total_win_usd = sum(t.net_pnl for t in trades if t.won)
        total_loss_usd = sum(abs(t.net_pnl) for t in trades if not t.won)

        if total_loss_usd > 0:
            profit_factor = total_win_usd / total_loss_usd
        elif total_win_usd > 0:
            profit_factor = 999.0
        else:
            profit_factor = 0.0

        # Cálculo de Max Drawdown em USD e Percentual sobre o pico de equity
        peak = initial_balance
        max_dd_usd = 0.0
        max_dd_pct = 0.0

        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd_usd = peak - eq
            dd_pct = (dd_usd / peak) if peak > 0 else 0.0
            if dd_usd > max_dd_usd:
                max_dd_usd = dd_usd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        # Contagem de maiores streaks consecutivos de vitórias e derrotas
        max_cons_wins = 0
        max_cons_losses = 0
        curr_wins = 0
        curr_losses = 0

        for t in trades:
            if t.won:
                curr_wins += 1
                curr_losses = 0
                if curr_wins > max_cons_wins:
                    max_cons_wins = curr_wins
            else:
                curr_losses += 1
                curr_wins = 0
                if curr_losses > max_cons_losses:
                    max_cons_losses = curr_losses

        return BacktestMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=round(win_rate, 4),
            initial_balance=round(initial_balance, 2),
            final_balance=round(final_balance, 2),
            total_net_pnl=round(total_net_pnl, 2),
            profit_factor=round(profit_factor, 2),
            average_trade_pnl=round(avg_trade_pnl, 2),
            max_drawdown_usd=round(max_dd_usd, 2),
            max_drawdown_pct=round(max_dd_pct, 4),
            max_consecutive_losses=max_cons_losses,
            max_consecutive_wins=max_cons_wins,
            risk_blocks_count=risk_blocks_count,
        )
