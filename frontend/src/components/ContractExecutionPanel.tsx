"use client";

import React, { useState } from "react";
import { AutoTraderStatus, EnsemblePrediction, ExecutionResult, RiskStatus } from "@/types";
import {
  Activity,
  Bot,
  Check,
  Cpu,
  Play,
  RefreshCw,
  Send,
  ShieldAlert,
  Sliders,
  TrendingUp,
  X,
  Zap,
} from "lucide-react";
import { api } from "@/services/api";

interface ContractExecutionPanelProps {
  selectedSymbol: string;
  ensemble: EnsemblePrediction | null;
  riskStatus: RiskStatus | null;
  autoTrader?: AutoTraderStatus | null;
  onTradeExecuted: () => void;
}

export const ContractExecutionPanel: React.FC<ContractExecutionPanelProps> = ({
  selectedSymbol,
  ensemble,
  riskStatus,
  autoTrader,
  onTradeExecuted,
}) => {
  const [contractType, setContractType] = useState<"DIGITEVEN" | "DIGITODD">("DIGITEVEN");
  const [stake, setStake] = useState<number>(1.00);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastExecution, setLastExecution] = useState<ExecutionResult | null>(null);
  const [activeContracts, setActiveContracts] = useState<any[]>([]);

  // Configurações do Auto-Trader
  const [isTogglingAuto, setIsTogglingAuto] = useState(false);
  const [autoStake, setAutoStake] = useState<number>(autoTrader?.stake || 1.0);
  const [autoMinProb, setAutoMinProb] = useState<number>(autoTrader?.min_probability || 0.52);
  const [showAutoSettings, setShowAutoSettings] = useState(false);

  // Sincroniza stake e prob caso o autoTrader atualize
  React.useEffect(() => {
    if (autoTrader) {
      setAutoStake(autoTrader.stake);
      setAutoMinProb(autoTrader.min_probability);
    }
  }, [autoTrader?.stake, autoTrader?.min_probability]);

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

  const handleToggleAutoTrader = async () => {
    setIsTogglingAuto(true);
    try {
      const nextState = !autoTrader?.enabled;
      await api.toggleAutoTrader(nextState);
      onTradeExecuted();
    } catch (err: any) {
      alert("Erro ao alternar Auto-Trader: " + (err.message || err));
    } finally {
      setIsTogglingAuto(false);
    }
  };

  const handleSaveAutoConfig = async () => {
    try {
      await api.configureAutoTrader({
        symbol: selectedSymbol,
        stake: autoStake,
        min_probability: autoMinProb,
      });
      alert("Configurações do Auto-Trader atualizadas com sucesso!");
      setShowAutoSettings(false);
      onTradeExecuted();
    } catch (err: any) {
      alert("Erro ao salvar configuração: " + (err.message || err));
    }
  };

  const handleExecute = async () => {
    setIsSubmitting(true);
    try {
      const currentProb = contractType === "DIGITEVEN" ? (ensemble?.even_probability || 0.55) : (ensemble?.odd_probability || 0.55);
      const pEst = Math.max(0.55, currentProb);
      const wilson = Math.max(0.52, ensemble?.wilson_lower_bound || 0.52);

      const res = await api.executeOrder({
        symbol: selectedSymbol,
        contract_type: contractType,
        stake: stake,
        estimated_probability: pEst,
        wilson_lower_bound: wilson,
        strategy_name: "manual_operator",
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

  const isAutoEnabled = autoTrader?.enabled || false;
  const autoState = autoTrader?.state || "STOPPED";

  return (
    <div className="space-y-6">
      {/* ========================================================================= */}
      {/* 🤖 PAINEL DO ROBÔ DE NEGOCIAÇÃO 100% AUTÔNOMO (AUTO-TRADER)               */}
      {/* ========================================================================= */}
      <div
        className={`border rounded-xl p-5 shadow-2xl transition-all duration-300 ${
          isAutoEnabled
            ? "bg-gradient-to-r from-dark-800 via-dark-800 to-emerald-950/20 border-emerald-500/60 shadow-emerald-950/20"
            : "bg-dark-800 border-dark-600"
        }`}
      >
        {/* Header do Auto-Trader */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-dark-700">
          <div className="flex items-center gap-3">
            <div
              className={`p-2.5 rounded-lg border ${
                isAutoEnabled
                  ? "bg-emerald-500/20 border-emerald-400 text-emerald-400 animate-pulse"
                  : "bg-dark-900 border-dark-700 text-gray-400"
              }`}
            >
              <Bot className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-black font-mono tracking-wide text-white">
                  ROBÔ 100% AUTÔNOMO (AUTO-TRADER)
                </h2>
                {isAutoEnabled ? (
                  <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                    OPERANDO
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-dark-700 text-gray-400 border border-dark-600">
                    PAUSADO
                  </span>
                )}
              </div>
              <p className="text-xs font-mono text-gray-400 mt-0.5">
                Executa sozinho na Deriv quando o Ensemble comprova borda matemática ($Net EV &gt; 0$).
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              onClick={() => setShowAutoSettings(!showAutoSettings)}
              className="p-2.5 rounded-lg border border-dark-600 bg-dark-900 text-gray-400 hover:text-cyan-400 hover:border-cyan-500 text-xs font-mono transition-all flex items-center gap-1"
              title="Ajustar parâmetros do robô"
            >
              <Sliders className="w-4 h-4" />
              <span className="hidden md:inline">Parâmetros</span>
            </button>

            <button
              onClick={handleToggleAutoTrader}
              disabled={isTogglingAuto || isBlocked}
              className={`flex-1 sm:flex-none px-5 py-2.5 rounded-lg font-mono font-black text-xs uppercase tracking-wider flex items-center justify-center gap-2 transition-all shadow-lg ${
                isBlocked
                  ? "bg-dark-700 border border-dark-600 text-gray-500 cursor-not-allowed"
                  : isAutoEnabled
                  ? "bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/50 hover:border-rose-400"
                  : "bg-emerald-500 hover:bg-emerald-400 text-dark-900 font-extrabold shadow-emerald-500/20 hover:shadow-emerald-500/40"
              }`}
            >
              {isTogglingAuto ? (
                <span>ATUALIZANDO...</span>
              ) : isBlocked ? (
                <>
                  <ShieldAlert className="w-4 h-4 text-rose-500" />
                  <span>BLOQUEADO POR RISCO</span>
                </>
              ) : isAutoEnabled ? (
                <>
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
                  <span>DESATIVAR ROBÔ</span>
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4 fill-current" />
                  <span>LIGAR AUTO-TRADER</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Modal/Accordion de Configurações do Auto-Trader */}
        {showAutoSettings && (
          <div className="mt-4 p-4 bg-dark-900 rounded-lg border border-dark-700 text-xs font-mono grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-gray-400 block mb-1">STAKE AUTOMÁTICA (USD):</label>
              <input
                type="number"
                min="0.35"
                max="5.00"
                step="0.05"
                value={autoStake}
                onChange={(e) => setAutoStake(parseFloat(e.target.value) || 1.0)}
                className="w-full bg-dark-800 border border-dark-600 rounded px-3 py-1.5 text-white font-bold"
              />
              <span className="text-[10px] text-gray-500">Máx: $5.00 (Salvaguarda estrita)</span>
            </div>
            <div>
              <label className="text-gray-400 block mb-1">PROBABILIDADE MÍNIMA (%):</label>
              <input
                type="number"
                min="50"
                max="90"
                step="1"
                value={Math.round(autoMinProb * 100)}
                onChange={(e) => setAutoMinProb((parseFloat(e.target.value) || 52) / 100)}
                className="w-full bg-dark-800 border border-dark-600 rounded px-3 py-1.5 text-white font-bold"
              />
              <span className="text-[10px] text-gray-500">Mínimo sugerido: 52% (Break-even: 51.3%)</span>
            </div>
            <div className="flex items-end">
              <button
                onClick={handleSaveAutoConfig}
                className="w-full py-2 bg-cyan-500 hover:bg-cyan-400 text-dark-900 font-bold rounded flex items-center justify-center gap-1"
              >
                <Check className="w-4 h-4" />
                <span>Salvar Configuração</span>
              </button>
            </div>
          </div>
        )}

        {/* Telemetria e Indicadores em Tempo Real */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
          {/* Card 1: Estado da Máquina */}
          <div className="bg-dark-900/80 border border-dark-700 p-3 rounded-lg">
            <span className="text-[10px] font-mono text-gray-400 block uppercase">ESTADO DO RADAR:</span>
            <div className="font-mono font-bold text-xs mt-1 flex items-center gap-1.5">
              {autoState === "SEARCHING_EDGE" && (
                <span className="text-cyan-400 flex items-center gap-1">
                  <Activity className="w-3.5 h-3.5 animate-spin" />
                  BUSCANDO EDGE
                </span>
              )}
              {autoState === "EXECUTING" && (
                <span className="text-emerald-400 flex items-center gap-1 animate-pulse font-black">
                  <Zap className="w-3.5 h-3.5" />
                  EXECUTANDO
                </span>
              )}
              {autoState === "COOLDOWN" && (
                <span className="text-amber-400">COOLDOWN ({autoTrader?.cooldown_seconds}s)</span>
              )}
              {autoState === "PAUSED_BY_RISK" && (
                <span className="text-rose-400">BLOQUEADO POR RISCO</span>
              )}
              {autoState === "STOPPED" && (
                <span className="text-gray-500">MODO MANUAL</span>
              )}
            </div>
          </div>

          {/* Card 2: Trades do Robô */}
          <div className="bg-dark-900/80 border border-dark-700 p-3 rounded-lg">
            <span className="text-[10px] font-mono text-gray-400 block uppercase">TRADES DO ROBÔ:</span>
            <div className="font-mono font-bold text-xs mt-1 text-white">
              {autoTrader?.total_trades || 0}{" "}
              <span className="text-[10px] font-normal text-gray-400">
                ({autoTrader?.won_trades || 0}V - {autoTrader?.lost_trades || 0}D)
              </span>
            </div>
          </div>

          {/* Card 3: PnL da Sessão */}
          <div className="bg-dark-900/80 border border-dark-700 p-3 rounded-lg">
            <span className="text-[10px] font-mono text-gray-400 block uppercase">LUCRO SESSÃO (AUTO):</span>
            <div
              className={`font-mono font-bold text-xs mt-1 ${
                (autoTrader?.session_pnl || 0) >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {(autoTrader?.session_pnl || 0) >= 0 ? "+" : ""}
              US$ {(autoTrader?.session_pnl || 0).toFixed(2)}
            </div>
          </div>

          {/* Card 4: Salvaguardas */}
          <div className="bg-dark-900/80 border border-dark-700 p-3 rounded-lg">
            <span className="text-[10px] font-mono text-gray-400 block uppercase">SALVAGUARDAS:</span>
            <div className="font-mono font-bold text-[11px] mt-1 text-emerald-400 flex items-center gap-1">
              <Check className="w-3.5 h-3.5" />
              <span>ANTI-MARTINGALE</span>
            </div>
          </div>
        </div>

        {/* Ticker de Telemetria / Última Decisão Matemática */}
        <div className="mt-3 p-2.5 bg-dark-950 rounded border border-dark-700 font-mono text-[11px] flex items-center gap-2 overflow-hidden">
          <span className="text-cyan-400 font-bold shrink-0">&gt; TELEMETRIA:</span>
          <span className="text-gray-300 truncate">
            {autoTrader?.last_decision || "Aguardando inicialização do feed..."}
          </span>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 🛠️ ESTAÇÃO DE EXECUÇÃO MANUAL (ASSISTIDA POR IA)                           */}
      {/* ========================================================================= */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 shadow-xl">
        <div className="flex items-center justify-between gap-3 mb-5 border-b border-dark-700 pb-3">
          <div className="flex items-center gap-2">
            <Play className="w-5 h-5 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wide uppercase font-mono text-gray-200">
              Execução Manual Assistida (DEMO)
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
              Nenhum contrato ativo no momento. O robô autônomo executa e liquida em tempo real automaticamente.
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
    </div>
  );
};
