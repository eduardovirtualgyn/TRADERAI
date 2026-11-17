"use client";

import React, { useState } from "react";
import { EnsemblePrediction, ExecutionResult, RiskStatus } from "@/types";
import { ArrowUpRight, Check, Play, RefreshCw, Send, ShieldAlert, X } from "lucide-react";
import { api } from "@/services/api";

interface ContractExecutionPanelProps {
  selectedSymbol: string;
  ensemble: EnsemblePrediction | null;
  riskStatus: RiskStatus | null;
  onTradeExecuted: () => void;
}

export const ContractExecutionPanel: React.FC<ContractExecutionPanelProps> = ({
  selectedSymbol,
  ensemble,
  riskStatus,
  onTradeExecuted,
}) => {
  const [contractType, setContractType] = useState<"DIGITEVEN" | "DIGITODD">("DIGITEVEN");
  const [stake, setStake] = useState<number>(1.00);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastExecution, setLastExecution] = useState<ExecutionResult | null>(null);
  const [activeContracts, setActiveContracts] = useState<any[]>([]);

  // Sincroniza com o ensemble quando houver direção eleita
  React.useEffect(() => {
    if (ensemble?.consensus_direction === "DIGITEVEN" || ensemble?.consensus_direction === "DIGITODD") {
      setContractType(ensemble.consensus_direction);
    }
  }, [ensemble?.consensus_direction]);

  const loadActiveContracts = async () => {
    try {
      const contracts = await api.getActiveContracts();
      setActiveContracts(contracts);
    } catch (err) {
      console.error(err);
    }
  };

  React.useEffect(() => {
    loadActiveContracts();
  }, []);

  const handleExecute = async () => {
    setIsSubmitting(true);
    try {
      const pEst = contractType === "DIGITEVEN" ? (ensemble?.even_probability || 0.55) : (ensemble?.odd_probability || 0.55);
      const wilson = ensemble?.wilson_lower_bound || 0.52;

      const res = await api.executeOrder({
        symbol: selectedSymbol,
        contract_type: contractType,
        stake: stake,
        estimated_probability: pEst,
        wilson_lower_bound: wilson,
        strategy_name: "ai_ensemble",
      });

      setLastExecution(res);
      await loadActiveContracts();
      onTradeExecuted();
    } catch (err: any) {
      alert("Erro ao submeter ordem: " + (err.message || err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSettle = async (contractId: string, won: boolean) => {
    try {
      await api.settleContract(contractId, won, won ? (contractType === "DIGITEVEN" ? 4 : 5) : (contractType === "DIGITEVEN" ? 7 : 8));
      await loadActiveContracts();
      onTradeExecuted();
    } catch (err: any) {
      alert("Erro ao liquidar contrato: " + (err.message || err));
    }
  };

  const killSwitchActive = riskStatus?.kill_switch_active || false;
  const circuitBreakerActive = riskStatus?.circuit_breaker_active || false;
  const isBlocked = killSwitchActive || circuitBreakerActive;

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 shadow-xl">
      <div className="flex items-center justify-between gap-3 mb-5 border-b border-dark-700 pb-3">
        <div className="flex items-center gap-2">
          <Play className="w-5 h-5 text-cyan-400" />
          <h2 className="text-sm font-bold tracking-wide uppercase font-mono text-gray-200">
            Estação de Execução de Contratos (DEMO)
          </h2>
        </div>
        <button
          onClick={loadActiveContracts}
          className="text-xs font-mono text-gray-400 hover:text-cyan-400 flex items-center gap-1"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Atualizar Ordens</span>
        </button>
      </div>

      {/* Execution Form */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-5 items-end">
        {/* Symbol */}
        <div>
          <label className="text-[11px] font-mono text-gray-400 block mb-1">ÍNDICE SINTÉTICO:</label>
          <div className="px-3 py-2 bg-dark-900 border border-dark-600 rounded font-mono font-bold text-sm text-cyan-400">
            {selectedSymbol}
          </div>
        </div>

        {/* Contract Type Buttons */}
        <div>
          <label className="text-[11px] font-mono text-gray-400 block mb-1">TIPO DE CONTRATO:</label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setContractType("DIGITEVEN")}
              className={`py-2 px-2 text-xs font-mono font-bold rounded border transition-all ${
                contractType === "DIGITEVEN"
                  ? "bg-cyan-500/20 border-cyan-400 text-cyan-300 glow-even"
                  : "bg-dark-900 border-dark-600 text-gray-400 hover:text-gray-200"
              }`}
            >
              PAR (EVEN)
            </button>
            <button
              type="button"
              onClick={() => setContractType("DIGITODD")}
              className={`py-2 px-2 text-xs font-mono font-bold rounded border transition-all ${
                contractType === "DIGITODD"
                  ? "bg-orange-500/20 border-orange-400 text-orange-300 glow-odd"
                  : "bg-dark-900 border-dark-600 text-gray-400 hover:text-gray-200"
              }`}
            >
              ÍMPAR (ODD)
            </button>
          </div>
        </div>

        {/* Stake Input */}
        <div>
          <label className="text-[11px] font-mono text-gray-400 block mb-1">STAKE (USD - Máx: $5.00):</label>
          <input
            type="number"
            min="0.35"
            max="5.00"
            step="0.05"
            value={stake}
            onChange={(e) => setStake(parseFloat(e.target.value) || 1.0)}
            className="w-full bg-dark-900 border border-dark-600 rounded px-3 py-2 text-sm font-mono font-bold text-white focus:outline-none focus:border-cyan-500"
          />
        </div>

        {/* Action Button */}
        <div>
          <button
            onClick={handleExecute}
            disabled={isSubmitting || isBlocked}
            className={`w-full py-2.5 px-4 rounded font-mono font-bold text-xs uppercase tracking-wider flex items-center justify-center gap-2 transition-all shadow-md ${
              isBlocked
                ? "bg-dark-700 border border-dark-600 text-gray-500 cursor-not-allowed"
                : isSubmitting
                ? "bg-cyan-700 text-white animate-pulse"
                : "bg-cyan-500 hover:bg-cyan-400 text-dark-900 font-black glow-even"
            }`}
          >
            {isBlocked ? (
              <>
                <ShieldAlert className="w-4 h-4 text-rose-500" />
                <span>BLOQUEADO POR RISCO</span>
              </>
            ) : isSubmitting ? (
              <span>ENVIANDO ORDEM...</span>
            ) : (
              <>
                <Send className="w-4 h-4" />
                <span>EXECUTAR ORDEM</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Last Execution Feedback Banner */}
      {lastExecution && (
        <div
          className={`mb-5 p-3 rounded-lg border text-xs font-mono flex items-center justify-between ${
            lastExecution.success
              ? "bg-emerald-950/30 border-emerald-500/50 text-emerald-300"
              : "bg-rose-950/30 border-rose-500/50 text-rose-300"
          }`}
        >
          <div>
            <strong>Status: {lastExecution.status}</strong> &middot; {lastExecution.symbol} {lastExecution.contract_type} | Stake: ${lastExecution.stake.toFixed(2)}
            {lastExecution.contract_id && ` | Contract ID: ${lastExecution.contract_id}`}
            {lastExecution.rejection_reason && (
              <p className="text-[11px] text-rose-400 mt-0.5">&times; Rejeição: {lastExecution.rejection_reason}</p>
            )}
          </div>
          <button
            onClick={() => setLastExecution(null)}
            className="text-gray-400 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Active Contracts Table */}
      <div>
        <h3 className="text-xs font-mono font-bold text-gray-400 uppercase mb-2">
          CONTRATOS ABERTOS EM ANDAMENTO ({activeContracts.length}):
        </h3>
        {activeContracts.length === 0 ? (
          <div className="bg-dark-900/40 p-4 rounded-lg border border-dark-700 text-center text-xs font-mono text-gray-500">
            Nenhum contrato ativo no momento. Submeta uma nova ordem acima.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-dark-700">
            <table className="w-full text-xs font-mono">
              <thead className="bg-dark-900 text-gray-400 text-left border-b border-dark-700">
                <tr>
                  <th className="py-2 px-3">Contract ID</th>
                  <th className="py-2 px-3">Símbolo</th>
                  <th className="py-2 px-3">Contrato</th>
                  <th className="py-2 px-3">Stake</th>
                  <th className="py-2 px-3">Payout Potencial</th>
                  <th className="py-2 px-3 text-right">Ação (DEMO Settle)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-700 bg-dark-900/60">
                {activeContracts.map((c) => (
                  <tr key={c.contract_id} className="hover:bg-dark-800">
                    <td className="py-2 px-3 text-cyan-400 font-bold">{c.contract_id}</td>
                    <td className="py-2 px-3 text-white">{c.symbol}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          c.contract_type === "DIGITEVEN"
                            ? "bg-cyan-500/20 text-cyan-300"
                            : "bg-orange-500/20 text-orange-300"
                        }`}
                      >
                        {c.contract_type}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-white font-bold">${c.stake.toFixed(2)}</td>
                    <td className="py-2 px-3 text-emerald-400 font-bold">${c.payout.toFixed(2)}</td>
                    <td className="py-2 px-3 text-right space-x-2">
                      <button
                        onClick={() => handleSettle(c.contract_id, true)}
                        className="px-2 py-1 rounded bg-emerald-600/30 hover:bg-emerald-600 text-emerald-300 hover:text-white border border-emerald-500 text-[10px] font-bold"
                        title="Simular Vitória no fechamento"
                      >
                        Vitória (+PnL)
                      </button>
                      <button
                        onClick={() => handleSettle(c.contract_id, false)}
                        className="px-2 py-1 rounded bg-rose-600/30 hover:bg-rose-600 text-rose-300 hover:text-white border border-rose-500 text-[10px] font-bold"
                        title="Simular Derrota no fechamento"
                      >
                        Derrota (-Stake)
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
