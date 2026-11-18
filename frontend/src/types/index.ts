/** Tipos TypeScript espelhando os modelos FastAPI e Deriv API **/

export interface DerivStatus {
  state: "DISCONNECTED" | "CONNECTING" | "CONNECTED" | "AUTHORIZED" | "ERROR";
  is_connected: boolean;
  is_authorized: boolean;
  active_symbols: string[];
  account_info: {
    loginid: string;
    balance: number;
    currency: string;
    is_virtual: boolean;
  } | null;
}

export interface RiskStatus {
  balance_usd: number;
  daily_drawdown_usd: number;
  max_daily_loss_usd: number;
  consecutive_losses: number;
  max_consecutive_losses: number;
  max_stake_usd: number;
  max_stake_percent: number;
  ban_martingale: boolean;
  kill_switch_active: boolean;
  kill_switch_reason: string | null;
  circuit_breaker_active: boolean;
  circuit_breaker_remaining_seconds: number;
  circuit_breaker_reason: string | null;
  last_stake_usd: number | null;
  last_trade_won: boolean | null;
  total_trades_recorded: number;
  win_rate: number;
  historical_var_95_usd: number;
}

export interface KellyRecommendation {
  full_kelly_f: number;
  fractional_f: number;
  fraction_factor: number;
  recommended_stake: number;
  approved: boolean;
  edge: number;
  reason: string | null;
}

export interface TickSummary {
  buffer_count: number;
  capacity: number;
  current_streak_parity: "EVEN" | "ODD" | "NONE";
  current_streak_length: number;
  last_ticks: Array<{
    quote: number;
    last_digit: number;
    is_even: boolean;
    epoch: number;
  }>;
  distribution_100: {
    even_count: number;
    odd_count: number;
    even_ratio: number;
    odd_ratio: number;
  };
  digit_frequencies: Record<string, number>;
}

export interface EnsemblePrediction {
  consensus_direction: "DIGITEVEN" | "DIGITODD" | "NO_CONSENSUS";
  consensus_probability: number;
  even_probability: number;
  odd_probability: number;
  spread: number;
  is_discordant: boolean;
  wilson_lower_bound: number;
  break_even_probability: number;
  has_mathematical_edge: boolean;
  model_weights: Record<string, number>;
  individual_predictions: Array<{
    model_name: string;
    p_even: number;
    p_odd: number;
    brier_score: number;
    weight: number;
  }>;
}

export interface ExecutionResult {
  success: boolean;
  status:
    | "PENDING_PROPOSAL"
    | "PROPOSAL_RECEIVED"
    | "REJECTED_BY_MATH"
    | "REJECTED_BY_RISK"
    | "BUY_SUBMITTED"
    | "OPEN"
    | "WON"
    | "LOST"
    | "ERROR";
  symbol: string;
  contract_type: string;
  stake: number;
  payout: number;
  net_pnl: number;
  contract_id: string | null;
  proposal_id: string | null;
  strategy_name: string;
  rejection_reason: string | null;
  execution_timestamp: number;
  completion_timestamp: number | null;
}

export interface AuditMetrics {
  total_records: number;
  executed_trades: number;
  settled_trades: number;
  rejected_by_math: number;
  rejected_by_risk: number;
  wins: number;
  losses: number;
  win_rate: number;
  gross_profit_usd: number;
  gross_loss_usd: number;
  net_pnl_usd: number;
  profit_factor: number;
  ledger_integrity_verified: boolean;
}

export interface AuditRecord {
  record_id: string;
  timestamp: number;
  event_type: string;
  symbol: string;
  contract_type: string;
  stake: number;
  payout: number;
  net_pnl: number;
  status: string;
  strategy_name: string;
  reason: string | null;
  contract_id: string | null;
  proposal_id: string | null;
  prev_hash: string;
  record_hash: string;
}

export interface AutoTraderConfig {
  enabled: boolean;
  symbol: string;
  stake: number;
  min_probability: number;
  min_wilson_lower_bound: number;
  cooldown_seconds: number;
}

export interface AutoTraderStatus {
  enabled: boolean;
  state: "STOPPED" | "SEARCHING_EDGE" | "EXECUTING" | "COOLDOWN" | "PAUSED_BY_RISK";
  symbol: string;
  stake: number;
  min_probability: number;
  cooldown_seconds: number;
  last_decision: string;
  last_action_timestamp: number | null;
  total_trades: number;
  won_trades: number;
  lost_trades: number;
  session_pnl: number;
  active_contract_id: string | null;
}
