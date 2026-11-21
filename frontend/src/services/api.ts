import {
  AuditMetrics,
  AuditRecord,
  AutoTraderConfig,
  AutoTraderStatus,
  DerivStatus,
  EnsemblePrediction,
  ExecutionResult,
  KellyRecommendation,
  RiskStatus,
  TickSummary,
} from "@/types";

// Sempre o proxy do Next. Ele anexa TRADER_API_TOKEN no servidor.
// O browser não recebe esse segredo e não fala com a porta do backend.
const API_BASE = "/api/backend";

export interface ApiStructuredError extends Error {
  error_type?: string;
  code?: string;
  detail?: string;
  http_status?: number;
  stage?: string;
}

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
  });

  if (!response.ok) {
    const errorBody = await response.text();
    let parsed: any = null;
    try {
      parsed = JSON.parse(errorBody);
    } catch {
      // Body is not JSON
    }

    if (parsed && parsed.detail && typeof parsed.detail === "object") {
      const err: ApiStructuredError = new Error(parsed.detail.message || "Erro na API");
      err.error_type = parsed.detail.error_type;
      err.code = parsed.detail.code;
      err.detail = parsed.detail.detail;
      err.http_status = parsed.detail.http_status || response.status;
      err.stage = parsed.detail.stage;
      throw err;
    }

    const fallbackErr: ApiStructuredError = new Error(
      parsed?.detail || `Erro na API (${response.status}): ${errorBody}`
    );
    fallbackErr.http_status = response.status;
    fallbackErr.code = "API_ERROR";
    throw fallbackErr;
  }

  return response.json();
}

export const api = {
  // Deriv
  getDerivStatus: () => fetchJson<DerivStatus>("/deriv/status"),
  connectDeriv: (token?: string, symbol?: string) =>
    fetchJson<{ success: boolean; state: string; is_authorized: boolean; loginid: string; balance: number }>(
      "/deriv/connect",
      {
        method: "POST",
        body: JSON.stringify({ token, symbol }),
      }
    ),
  disconnectDeriv: () =>
    fetchJson<{ success: boolean; state: string }>("/deriv/disconnect", {
      method: "POST",
    }),
  setDemoBalance: (balance: number) =>
    fetchJson<{ success: boolean; balance: number; message: string }>("/deriv/balance", {
      method: "POST",
      body: JSON.stringify({ balance }),
    }),

  // Risco
  getRiskStatus: () => fetchJson<RiskStatus>("/risk/status"),
  toggleKillSwitch: (active: boolean, reason?: string) =>
    fetchJson<{ success: boolean; kill_switch_active: boolean; reason: string | null }>(
      "/risk/kill-switch",
      {
        method: "POST",
        body: JSON.stringify({ active, reason: reason || "Ação manual no dashboard" }),
      }
    ),
  resetCircuitBreaker: () =>
    fetchJson<{ success: boolean; message: string }>("/risk/circuit-breaker/reset", {
      method: "POST",
    }),
  calculateKelly: (params: { win_probability: number; payout: number; fraction_factor?: number }) =>
    fetchJson<KellyRecommendation>("/risk/kelly", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  // Ticks
  getTickSummary: (symbol = "R_100") =>
    fetchJson<TickSummary>(`/ticks/summary?symbol=${symbol}`),

  // Ensemble
  getEnsembleStatus: (symbol = "R_100") =>
    fetchJson<EnsemblePrediction>(`/ensemble/predict?symbol=${symbol}`),

  // Executor
  executeOrder: (payload: {
    symbol: string;
    contract_type: string;
    stake: number;
    estimated_probability: number;
    wilson_lower_bound: number;
    strategy_name?: string;
  }) =>
    fetchJson<ExecutionResult>("/executor/execute", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  triggerPanicStop: (reason?: string) =>
    fetchJson<{ success: boolean; panic_triggered: boolean; message: string }>(
      "/executor/panic-stop",
      {
        method: "POST",
        body: JSON.stringify({ reason: reason || "Botão de Pânico acionado no frontend" }),
      }
    ),
  getActiveContracts: () => fetchJson<any[]>("/executor/active-contracts"),
  settleContract: (contract_id: string, won: boolean, exit_digit?: number) =>
    fetchJson<ExecutionResult>("/executor/settle", {
      method: "POST",
      body: JSON.stringify({ contract_id, won, exit_digit }),
    }),

  // Auditoria
  getAuditLogs: (limit = 50) => fetchJson<AuditRecord[]>(`/audit/logs?limit=${limit}`),
  getAuditMetrics: () => fetchJson<AuditMetrics>("/audit/metrics"),
  verifyLedger: () =>
    fetchJson<{ valid: boolean; total_records: number; last_hash: string; message: string }>(
      "/audit/verify"
    ),
  exportCsvUrl: () => `${API_BASE}/audit/export/csv`,
  exportJsonUrl: () => `${API_BASE}/audit/export/json`,

  // Auto-Trader
  getAutoTraderStatus: () => fetchJson<AutoTraderStatus>("/auto-trader/status"),
  toggleAutoTrader: (enabled: boolean) =>
    fetchJson<AutoTraderStatus>("/auto-trader/toggle", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  configureAutoTrader: (config: Partial<AutoTraderConfig>) =>
    fetchJson<AutoTraderStatus>("/auto-trader/configure", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  resetAutoTraderStats: () =>
    fetchJson<AutoTraderStatus>("/auto-trader/reset-stats", {
      method: "POST",
    }),
};
