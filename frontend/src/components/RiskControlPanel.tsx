"use client";

import React, { useState } from "react";
import { KellyRecommendation, RiskStatus } from "@/types";
import { AlertTriangle, Calculator, Clock, Lock, ShieldCheck, Zap } from "lucide-react";
import { api } from "@/services/api";

interface RiskControlPanelProps {
  riskStatus: RiskStatus | null;
  onRefresh: () => void;
}

export const RiskControlPanel: React.FC<RiskControlPanelProps> = ({ riskStatus, onRefresh }) => {
  const [kellyProb, setKellyProb] = useState<number>(0.56);
  const [kellyPayout, setKellyPayout] = useState<number>(1.95);
  const [kellyFraction, setKellyFraction] = useState<number>(0.20);
  const [kellyResult, setKellyResult] = useState<KellyRecommendation | null>(null);
  const [loadingKelly, setLoadingKelly] = useState(false);

  const dailyDrawdown = riskStatus?.daily_drawdown_usd || 0.0;
  const maxDailyLoss = riskStatus?.max_daily_loss_usd || 25.0;
  const drawdownPercent = (dailyDrawdown / maxDailyLoss) * 100;

  const consecutiveLosses = riskStatus?.consecutive_losses || 0;
  const maxConsecutiveLosses = riskStatus?.max_consecutive_losses || 3;

  const circuitBreakerActive = riskStatus?.circuit_breaker_active || false;
  const circuitBreakerRemaining = riskStatus?.circuit_breaker_remaining_seconds || 0;

  const handleCalculateKelly = async () => {
    setLoadingKelly(true);
    try {
      const res = await api.calculateKelly({
        win_probability: kellyProb,
        payout: kellyPayout,
        fraction_factor: kellyFraction,
      });
      setKellyResult(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingKelly(false);
    }
  };

  const handleResetCircuitBreaker = async () => {
    try {
      await api.resetCircuitBreaker();
      onRefresh();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 shadow-xl">
      <div className="flex items-center justify-between gap-3 mb-5 border-b border-dark-700 pb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-emerald-400" />
          <h2 className="text-sm font-bold tracking-wide uppercase font-mono text-gray-200">
            Gerenciamento de Risco & Salvaguardas
          </h2>
        </div>
        <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-bold">
          ANTI-MARTINGALE ATIVO
        </span>
      </div>

      {/* Grid of Risk Monitors */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {/* Daily Drawdown */}
        <div className="bg-dark-900/60 p-3.5 rounded-lg border border-dark-700">
          <div className="flex justify-between items-center text-xs font-mono text-gray-400 mb-1.5">
            <span>DRAWDOWN DIÁRIO:</span>
            <span className="font-bold text-white">
              ${dailyDrawdown.toFixed(2)} / ${maxDailyLoss.toFixed(2)}
            </span>
          </div>
          <div className="w-full bg-dark-700 h-2 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                drawdownPercent > 75 ? "bg-red-500" : drawdownPercent > 50 ? "bg-amber-500" : "bg-emerald-500"
              }`}
              style={{ width: `${Math.min(100, Math.max(0, drawdownPercent))}%` }}
            />
          </div>
          <p className="text-[10px] text-gray-500 font-mono mt-1.5">
            {drawdownPercent.toFixed(1)}% do limite. O contador zera na virada UTC
            {riskStatus?.drawdown_utc_date ? ` (${riskStatus.drawdown_utc_date})` : ""}.
          </p>
        </div>

        {/* Consecutive Losses */}
        <div className="bg-dark-900/60 p-3.5 rounded-lg border border-dark-700">
          <div className="flex justify-between items-center text-xs font-mono text-gray-400 mb-2">
            <span>PERDAS SEGUIDAS:</span>
            <span className="font-bold text-white">
              {consecutiveLosses} / {maxConsecutiveLosses}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {Array.from({ length: maxConsecutiveLosses }, (_, i) => {
              const lost = i < consecutiveLosses;
              return (
                <div
                  key={i}
                  className={`flex-1 h-3 rounded transition-all ${
                    lost ? "bg-red-500 shadow-sm shadow-red-500/50" : "bg-dark-700"
                  }`}
                />
              );
            })}
          </div>
          <p className="text-[10px] text-gray-500 font-mono mt-1.5">
            Dispara Kill Switch ao atingir {maxConsecutiveLosses} derrotas. Desarmar zera a sequência e o drawdown do dia.
          </p>
        </div>

        {/* Circuit Breaker Status */}
        <div className="bg-dark-900/60 p-3.5 rounded-lg border border-dark-700">
          <div className="flex justify-between items-center text-xs font-mono text-gray-400 mb-1.5">
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-cyan-400" />
              CIRCUIT BREAKER:
            </span>
            <span className={`font-bold ${circuitBreakerActive ? "text-amber-400" : "text-emerald-400"}`}>
              {circuitBreakerActive ? `${circuitBreakerRemaining}s RESTANTES` : "DESARMADO"}
            </span>
          </div>
          {circuitBreakerActive ? (
            <div className="flex items-center justify-between gap-2 mt-1">
              <span className="text-[10px] text-amber-300 font-mono truncate">
                {riskStatus?.circuit_breaker_reason || "Resfriamento ativo"}
              </span>
              <button
                onClick={handleResetCircuitBreaker}
                className="px-2 py-0.5 text-[10px] font-mono font-bold bg-dark-700 hover:bg-dark-600 border border-dark-500 rounded text-cyan-400"
              >
                Reset
              </button>
            </div>
          ) : (
            <p className="text-[10px] text-gray-500 font-mono mt-1.5">
              Pausa de 30s ativada se houver sequência de 2 derrotas
            </p>
          )}
        </div>

        {/* VaR & Stake Limits */}
        <div className="bg-dark-900/60 p-3.5 rounded-lg border border-dark-700">
          <div className="flex justify-between items-center text-xs font-mono text-gray-400 mb-1">
            <span>VaR HISTÓRICO (95%):</span>
            <span className="font-bold text-cyan-300">
              US$ {riskStatus?.historical_var_95_usd?.toFixed(2) || "0.00"}
            </span>
          </div>
          <div className="flex justify-between items-center text-xs font-mono text-gray-400 mb-1">
            <span>TETO POR TRADE:</span>
            <span className="font-bold text-white">US$ {riskStatus?.max_stake_usd?.toFixed(2) || "5.00"}</span>
          </div>
          <p className="text-[10px] text-gray-500 font-mono">
            Trava máxima: 1% da banca ou US$ 5.00 por ordem
          </p>
        </div>
      </div>

      {/* Fractional Kelly Calculator Box */}
      <div className="bg-dark-900/80 p-4 rounded-lg border border-dark-700">
        <div className="flex items-center gap-2 text-xs font-mono font-bold text-cyan-400 mb-3">
          <Calculator className="w-4 h-4" />
          <span>CALCULADORA DO CRITÉRIO DE KELLY FRACIONÁRIO CONSERVADOR</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
          <div>
            <label className="text-[11px] font-mono text-gray-400 block mb-1">PROBABILIDADE P(Win):</label>
            <input
              type="number"
              step="0.01"
              min="0.50"
              max="0.99"
              value={kellyProb}
              onChange={(e) => setKellyProb(parseFloat(e.target.value) || 0.5)}
              className="w-full bg-dark-800 border border-dark-600 rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div>
            <label className="text-[11px] font-mono text-gray-400 block mb-1">PAYOUT TOTAL (USD):</label>
            <input
              type="number"
              step="0.01"
              value={kellyPayout}
              onChange={(e) => setKellyPayout(parseFloat(e.target.value) || 1.95)}
              className="w-full bg-dark-800 border border-dark-600 rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div>
            <label className="text-[11px] font-mono text-gray-400 block mb-1">FRAÇÃO DE KELLY:</label>
            <select
              value={kellyFraction}
              onChange={(e) => setKellyFraction(parseFloat(e.target.value))}
              className="w-full bg-dark-800 border border-dark-600 rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-cyan-500"
            >
              <option value={0.10}>10% (Ultra Conservador)</option>
              <option value={0.15}>15% (Conservador Recomendado)</option>
              <option value={0.20}>20% (Padrão Quant)</option>
              <option value={0.25}>25% (Teto Regulamentar)</option>
            </select>
          </div>

          <div>
            <button
              onClick={handleCalculateKelly}
              disabled={loadingKelly}
              className="w-full py-1.5 px-3 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-mono text-xs font-bold transition-colors"
            >
              {loadingKelly ? "Calculando..." : "Dimensionar Stake"}
            </button>
          </div>
        </div>

        {kellyResult && (
          <div className="mt-3 pt-3 border-t border-dark-700 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
            <div className="flex items-center gap-3">
              <span className="text-gray-400">
                Full Kelly f*: <strong className="text-white">{(kellyResult.full_kelly_f * 100).toFixed(2)}%</strong>
              </span>
              <span className="text-gray-400">
                Kelly Fracionário: <strong className="text-cyan-300">{(kellyResult.fractional_f * 100).toFixed(2)}%</strong>
              </span>
              <span className="text-gray-400">
                Edge (EV/Stake): <strong className="text-emerald-400">{(kellyResult.edge * 100).toFixed(2)}%</strong>
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-gray-300">Stake Sugerido:</span>
              <span className="px-2.5 py-1 rounded bg-dark-800 border border-cyan-500/50 font-bold text-cyan-300">
                US$ {kellyResult.recommended_stake.toFixed(2)}
              </span>
              {!kellyResult.approved && (
                <span className="text-red-400 text-[11px] font-bold">({kellyResult.reason})</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
