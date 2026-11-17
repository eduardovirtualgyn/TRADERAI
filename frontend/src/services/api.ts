import {
  AuditMetrics,
  AuditRecord,
  DerivStatus,
  EnsemblePrediction,
  ExecutionResult,
  KellyRecommendation,
  RiskStatus,
  TickSummary,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

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
    throw new Error(`Erro na API (${response.status}): ${errorBody}`);
  }

  return response.json();
}

export const api = {
  // Deriv
  getDerivStatus: () => fetchJson<DerivStatus>("/deriv/status"),

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
};
