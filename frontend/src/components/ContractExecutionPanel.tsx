"use client";

import React, { useState, useEffect } from "react";
import { AutoTraderStatus, EnsemblePrediction, RiskStatus } from "@/types";
import {
  Activity,
  Bot,
  Check,
  CheckCircle2,
  Clock,
  Cpu,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  TrendingUp,
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
  const [activeContracts, setActiveContracts] = useState<any[]>([]);
  const [isTogglingAuto, setIsTogglingAuto] = useState(false);
  const [isUnlocking, setIsUnlocking] = useState(false);
  const [autoStake, setAutoStake] = useState<number>(autoTrader?.stake || 1.0);
  const [autoMinProb, setAutoMinProb] = useState<number>(autoTrader?.min_probability || 0.55);
  const [showAutoSettings, setShowAutoSettings] = useState(false);

  // Sincroniza stake e probabilidade caso o autoTrader atualize via polling
  useEffect(() => {
    if (autoTrader) {
      setAutoStake(autoTrader.stake);
      setAutoMinProb(autoTrader.min_probability);
    }
  }, [autoTrader?.stake, autoTrader?.min_probability]);

  // Carrega contratos ativos em andamento no motor
  const loadActiveContracts = async () => {
    try {
      const contracts = await api.getActiveContracts();
      setActiveContracts(contracts || []);
    } catch (err) {
      console.error("Erro ao carregar contratos ativos:", err);
    }
  };

  useEffect(() => {
    loadActiveContracts();
    const interval = setInterval(loadActiveContracts, 2000);
    return () => clearInterval(interval);
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

  const handleUnlockRisk = async () => {
    setIsUnlocking(true);
    try {
      // 1. Desarma Kill Switch (zera contagem de perdas consecutivas e drawdown acumulado)
      await api.toggleKillSwitch(false, "Desbloqueio manual e reset de salvaguardas pelo operador");
      // 2. Reseta o Circuit Breaker temporal se estiver ativo
      await api.resetCircuitBreaker();
      // 3. Zera os contadores da sessão no robô
      await api.resetAutoTraderStats();
      // 4. Garante que o Auto-Trader esteja ativado
      await api.toggleAutoTrader(true);
      onTradeExecuted();
    } catch (err: any) {
      alert("Erro ao desbloquear risco: " + (err.message || err));
    } finally {
      setIsUnlocking(false);
    }
  };

  const handleSaveAutoConfig = async () => {
    try {
      await api.configureAutoTrader({
        symbol: selectedSymbol,
        stake: autoStake,
        min_probability: autoMinProb,
      });
      alert("Configurações do Auto-Trader salvas com sucesso!");
      setShowAutoSettings(false);
      onTradeExecuted();
    } catch (err: any) {
      alert("Erro ao salvar configuração: " + (err.message || err));
    }
  };

  const killSwitchActive = riskStatus?.kill_switch_active || false;
  const circuitBreakerActive = riskStatus?.circuit_breaker_active || false;
  const isBlocked = killSwitchActive || circuitBreakerActive;

  const isAutoEnabled = autoTrader?.enabled || false;
  const autoState = autoTrader?.state || "STOPPED";
  const totalTrades = autoTrader?.total_trades || 0;
  const wonTrades = autoTrader?.won_trades || 0;
  const lostTrades = autoTrader?.lost_trades || 0;
  const winRate = totalTrades > 0 ? ((wonTrades / totalTrades) * 100).toFixed(1) : "0.0";
  const sessionPnl = autoTrader?.session_pnl || 0.0;

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
                  <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                    OPERANDO 100% AUTÔNOMO
                  </span>
                ) : (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-dark-700 text-gray-400 border border-dark-600">
                    PAUSADO PELO OPERADOR
                  </span>
                )}
              </div>
              <p className="text-xs font-mono text-gray-400 mt-0.5">
                Execução 100% algorítmica direta na Deriv API via Ensemble Preditivo e Teoria da Informação. Negociação estritamente matemática e sem intervenção manual.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              onClick={() => setShowAutoSettings(!showAutoSettings)}
              className="p-2.5 rounded-lg border border-dark-600 bg-dark-900 text-gray-300 hover:text-cyan-400 hover:border-cyan-500 text-xs font-mono transition-all flex items-center gap-1.5"
              title="Ajustar parâmetros operacionais do robô"
            >
              <Sliders className="w-4 h-4 text-cyan-400" />
              <span>Parâmetros</span>
            </button>

            {isBlocked ? (
              <button
                onClick={handleUnlockRisk}
                disabled={isUnlocking}
                className="flex-1 sm:flex-none px-5 py-2.5 rounded-lg font-mono font-black text-xs uppercase tracking-wider flex items-center justify-center gap-2 transition-all shadow-lg bg-rose-600 hover:bg-rose-500 text-white animate-pulse border border-rose-400 cursor-pointer shadow-rose-950/40"
                title="Desarma o Kill Switch, zera derrotas consecutivas e reinicia o robô autônomo"
              >
                <ShieldAlert className="w-4 h-4 text-white" />
                <span>{isUnlocking ? "DESBLOQUEANDO..." : "DESBLOQUEAR RISCO & REATIVAR"}</span>
              </button>
            ) : (
              <button
                onClick={handleToggleAutoTrader}
                disabled={isTogglingAuto}
                className={`flex-1 sm:flex-none px-5 py-2.5 rounded-lg font-mono font-black text-xs uppercase tracking-wider flex items-center justify-center gap-2 transition-all shadow-lg ${
                  isAutoEnabled
                    ? "bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/50 hover:border-rose-400"
                    : "bg-emerald-500 hover:bg-emerald-400 text-dark-900 font-extrabold shadow-emerald-500/20 hover:shadow-emerald-500/40"
                }`}
              >
                {isTogglingAuto ? (
                  <span>ATUALIZANDO...</span>
                ) : isAutoEnabled ? (
                  <>
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
                    <span>PAUSAR ROBÔ</span>
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4 fill-current" />
                    <span>LIGAR AUTO-TRADER</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Modal/Accordion de Configurações do Auto-Trader */}
        {showAutoSettings && (
          <div className="mt-4 p-4 bg-dark-900 rounded-lg border border-cyan-500/30 text-xs font-mono grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-gray-400 block mb-1">STAKE AUTOMÁTICA (USD):</label>
              <input
                type="number"
                min="0.35"
                max="5.00"
                step="0.05"
                value={autoStake}
                onChange={(e) => setAutoStake(parseFloat(e.target.value) || 1.0)}
                className="w-full bg-dark-800 border border-dark-600 rounded px-3 py-1.5 text-white font-bold focus:border-cyan-400 focus:outline-none"
              />
              <span className="text-[10px] text-gray-500">Máx: $5.00 (Salvaguarda estrita Anti-Martingale)</span>
            </div>
            <div>
              <label className="text-gray-400 block mb-1">PROBABILIDADE MÍNIMA (%):</label>
              <input
                type="number"
                min="50"
                max="90"
                step="1"
                value={Math.round(autoMinProb * 100)}
                onChange={(e) => setAutoMinProb((parseFloat(e.target.value) || 55) / 100)}
                className="w-full bg-dark-800 border border-dark-600 rounded px-3 py-1.5 text-white font-bold focus:border-cyan-400 focus:outline-none"
              />
              <span className="text-[10px] text-gray-500">Recomendado: 55% a 65% (Break-even real Deriv: 52.1%)</span>
            </div>
            <div className="flex items-end">
              <button
                onClick={handleSaveAutoConfig}
                className="w-full py-2 bg-cyan-500 hover:bg-cyan-400 text-dark-900 font-bold rounded flex items-center justify-center gap-1 transition-all"
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
                <span className="text-cyan-400 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                  BUSCANDO EDGE
                </span>
              )}
              {autoState === "EXECUTING" && (
                <span className="text-emerald-400 flex items-center gap-1.5 animate-pulse font-black">
                  <Zap className="w-3.5 h-3.5 fill-current" />
                  EXECUTANDO ORDEM
                </span>
              )}
              {autoState === "COOLDOWN" && (
                <span className="text-amber-400 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  COOLDOWN ({autoTrader?.cooldown_seconds}s)
                </span>
              )}
              {autoState === "PAUSED_BY_RISK" && (
                <span className="text-rose-400 flex items-center gap-1">
                  <ShieldAlert className="w-3.5 h-3.5" />
                  BLOQUEADO POR RISCO
                </span>
              )}
              {autoState === "STOPPED" && (
                <span className="text-gray-500">ROBÔ PAUSADO</span>
              )}
            </div>
          </div>

          {/* Card 2: Trades do Robô */}
          <div className="bg-dark-900/80 border border-dark-700 p-3 rounded-lg">
            <span className="text-[10px] font-mono text-gray-400 block uppercase">TRADES DO ROBÔ:</span>
            <div className="font-mono font-bold text-xs mt-1 text-white">
              {totalTrades}{" "}
              <span className="text-[10px] font-normal text-gray-400">
                ({wonTrades}V - {lostTrades}D)
              </span>
              <span className="text-[10px] text-cyan-400 ml-1.5">
                [{winRate}% WR]
              </span>
            </div>
          </div>

          {/* Card 3: PnL da Sessão */}
          <div className="bg-dark-900/80 border border-dark-700 p-3 rounded-lg">
            <span className="text-[10px] font-mono text-gray-400 block uppercase">LUCRO SESSÃO (AUTO):</span>
            <div
              className={`font-mono font-bold text-xs mt-1 ${
                sessionPnl >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {sessionPnl >= 0 ? "+" : ""}
              US$ {sessionPnl.toFixed(2)}
            </div>
          </div>

          {/* Card 4: Salvaguardas */}
          <div className="bg-dark-900/80 border border-dark-700 p-3 rounded-lg">
            <span className="text-[10px] font-mono text-gray-400 block uppercase">SALVAGUARDAS:</span>
            <div className="font-mono font-bold text-[11px] mt-1 text-emerald-400 flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>ANTI-MARTINGALE</span>
            </div>
          </div>
        </div>

        {/* Ticker de Telemetria / Decisão Algorítmica em Tempo Real */}
        <div className="mt-3 p-2.5 bg-dark-950 rounded border border-dark-700 font-mono text-[11px] flex items-center justify-between gap-2 overflow-hidden">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-cyan-400 font-bold shrink-0">&gt; TELEMETRIA:</span>
            <span className={`truncate ${isBlocked ? "text-rose-400 font-bold" : "text-gray-300"}`}>
              {autoTrader?.last_decision || "Aguardando inicialização do feed..."}
            </span>
          </div>
          {isBlocked && (
            <button
              onClick={handleUnlockRisk}
              disabled={isUnlocking}
              className="shrink-0 px-2.5 py-1 bg-rose-500 hover:bg-rose-400 text-white font-bold rounded text-[10px] uppercase tracking-wider transition-all flex items-center gap-1 shadow cursor-pointer animate-pulse"
              title="Desarma o Kill Switch e zera a contagem de perdas"
            >
              <RefreshCw className={`w-3 h-3 ${isUnlocking ? "animate-spin" : ""}`} />
              <span>Desbloquear Risco</span>
            </button>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 📡 MONITOR DE ORDENS E CONTRATOS DO ROBÔ (100% AUTOMÁTICO)                */}
      {/* ========================================================================= */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 shadow-xl">
        <div className="flex items-center justify-between gap-3 mb-4 border-b border-dark-700 pb-3">
          <div className="flex items-center gap-2">
            <Cpu className="w-5 h-5 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wide uppercase font-mono text-gray-200">
              Monitor de Ordens do Auto-Trader ({activeContracts.length} Ativas)
            </h2>
          </div>
          <button
            onClick={loadActiveContracts}
            className="text-xs font-mono text-gray-400 hover:text-cyan-400 flex items-center gap-1 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Atualizar</span>
          </button>
        </div>

        {/* Monitor Table / Status */}
        {activeContracts.length === 0 ? (
          <div className="bg-dark-900/60 p-6 rounded-lg border border-dark-700 text-center font-mono">
            <div className="inline-flex items-center justify-center p-3 rounded-full bg-cyan-500/10 text-cyan-400 mb-2">
              <Activity className="w-5 h-5 animate-pulse" />
            </div>
            <p className="text-xs text-gray-300 font-semibold">
              Radar algorítmico ativo &middot; Nenhuma ordem em trânsito no momento
            </p>
            <p className="text-[11px] text-gray-500 mt-1 max-w-xl mx-auto">
              O robô analisa os dígitos a cada tick em segundo plano. Assim que o Ensemble comprovar desequilíbrio e vantagem estatística ($Net EV &gt; 0$), a ordem é disparada e liquidada automaticamente.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-dark-700">
            <table className="w-full text-xs font-mono">
              <thead className="bg-dark-900 text-gray-400 text-left border-b border-dark-700">
                <tr>
                  <th className="py-2.5 px-3">Contract ID</th>
                  <th className="py-2.5 px-3">Símbolo</th>
                  <th className="py-2.5 px-3">Contrato</th>
                  <th className="py-2.5 px-3">Stake</th>
                  <th className="py-2.5 px-3">Payout Potencial</th>
                  <th className="py-2.5 px-3 text-right">Status do Robô</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-700 bg-dark-900/60">
                {activeContracts.map((c) => (
                  <tr key={c.contract_id} className="hover:bg-dark-800 transition-colors">
                    <td className="py-2.5 px-3 text-cyan-400 font-bold">{c.contract_id}</td>
                    <td className="py-2.5 px-3 text-white">{c.symbol}</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          c.contract_type === "DIGITEVEN"
                            ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                            : "bg-orange-500/20 text-orange-300 border border-orange-500/40"
                        }`}
                      >
                        {c.contract_type === "DIGITEVEN" ? "PAR (EVEN)" : "ÍMPAR (ODD)"}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-white font-bold">${c.stake.toFixed(2)}</td>
                    <td className="py-2.5 px-3 text-emerald-400 font-bold">${c.payout.toFixed(2)}</td>
                    <td className="py-2.5 px-3 text-right">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30 animate-pulse">
                        <Activity className="w-3 h-3 animate-spin" />
                        AGUARDANDO DESFECHO DO TICK
                      </span>
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
