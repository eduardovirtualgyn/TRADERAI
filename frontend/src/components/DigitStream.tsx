"use client";

import React from "react";
import { TickSummary } from "@/types";
import { Activity, Flame, Hash, Percent } from "lucide-react";

interface DigitStreamProps {
  tickSummary: TickSummary | null;
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
}

const POPULAR_SYMBOLS = ["R_100", "R_75", "R_50", "R_25", "R_10"];

export const DigitStream: React.FC<DigitStreamProps> = ({
  tickSummary,
  selectedSymbol,
  onSelectSymbol,
}) => {
  const lastTicks = tickSummary?.last_ticks || [];
  const streakParity = tickSummary?.current_streak_parity || "NONE";
  const streakLength = tickSummary?.current_streak_length || 0;
  const dist = tickSummary?.distribution_100 || { even_ratio: 0.5, odd_ratio: 0.5, even_count: 50, odd_count: 50 };
  const freqs = tickSummary?.digit_frequencies || {};

  // Encontra a frequência máxima para normalizar as barras
  const maxFreq = Math.max(...Object.values(freqs).concat(1));

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 shadow-xl">
      {/* Top Header & Symbol Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5 border-b border-dark-700 pb-3">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-cyan-400" />
          <h2 className="text-sm font-bold tracking-wide uppercase font-mono text-gray-200">
            Feed de Ticks &middot; Dígitos em Tempo Real
          </h2>
        </div>

        {/* Symbol Selector */}
        <div className="flex items-center gap-1.5 bg-dark-900 p-1 rounded-lg border border-dark-700">
          {POPULAR_SYMBOLS.map((sym) => (
            <button
              key={sym}
              onClick={() => onSelectSymbol(sym)}
              className={`px-2.5 py-1 text-xs font-mono font-bold rounded transition-colors ${
                selectedSymbol === sym
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                  : "text-gray-400 hover:text-gray-200 hover:bg-dark-800"
              }`}
            >
              {sym}
            </button>
          ))}
        </div>
      </div>

      {/* Live Digits Ribbon */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-mono text-gray-400 flex items-center gap-1.5">
            <Hash className="w-3.5 h-3.5 text-gray-400" />
            ÚLTIMOS 20 DÍGITOS RECEBIDOS (Mais recente à direita):
          </span>
          {streakLength > 1 && (
            <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-400 text-xs font-mono font-bold animate-pulse">
              <Flame className="w-3.5 h-3.5" />
              <span>
                STREAK: {streakLength}x {streakParity === "EVEN" ? "PAR (EVEN)" : "ÍMPAR (ODD)"}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 overflow-x-auto py-2 px-1">
          {lastTicks.length === 0 ? (
            <div className="text-xs font-mono text-gray-500 py-3">Aguardando feed de cotações da Deriv API...</div>
          ) : (
            lastTicks.slice(-20).map((tick, idx, arr) => {
              const isLast = idx === arr.length - 1;
              const isEven = tick.is_even;
              return (
                <div
                  key={tick.epoch + "-" + idx}
                  className={`flex flex-col items-center justify-center min-w-[38px] h-[52px] rounded-lg font-mono font-black border transition-all ${
                    isEven
                      ? "bg-cyan-950/40 border-cyan-500/50 text-cyan-300"
                      : "bg-orange-950/40 border-orange-500/50 text-orange-400"
                  } ${isLast ? (isEven ? "glow-even ring-2 ring-cyan-400" : "glow-odd ring-2 ring-orange-500") : ""}`}
                >
                  <span className="text-lg leading-none">{tick.last_digit}</span>
                  <span className="text-[9px] uppercase font-bold tracking-tighter opacity-80 mt-1">
                    {isEven ? "PAR" : "ÍMP"}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Statistics Grid: Distribution & Digit Frequencies */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-3 border-t border-dark-700">
        {/* Parity 100-Tick Distribution */}
        <div className="bg-dark-900/60 p-4 rounded-lg border border-dark-700">
          <div className="flex items-center justify-between text-xs font-mono mb-2">
            <span className="text-gray-300 font-bold flex items-center gap-1.5">
              <Percent className="w-3.5 h-3.5 text-cyan-400" />
              DISTRIBUIÇÃO (JANELA DE 100 TICKS)
            </span>
            <span className="text-gray-400">Total: {tickSummary?.buffer_count || 0} ticks</span>
          </div>

          <div className="space-y-3 mt-3">
            <div>
              <div className="flex justify-between text-xs font-mono mb-1">
                <span className="text-cyan-400 font-bold">PARES (EVEN):</span>
                <span className="text-white font-bold">
                  {(dist.even_ratio * 100).toFixed(1)}% ({dist.even_count})
                </span>
              </div>
              <div className="w-full bg-dark-700 h-2.5 rounded-full overflow-hidden">
                <div
                  className="bg-cyan-400 h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.max(0, dist.even_ratio * 100))}%` }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs font-mono mb-1">
                <span className="text-orange-400 font-bold">ÍMPARES (ODD):</span>
                <span className="text-white font-bold">
                  {(dist.odd_ratio * 100).toFixed(1)}% ({dist.odd_count})
                </span>
              </div>
              <div className="w-full bg-dark-700 h-2.5 rounded-full overflow-hidden">
                <div
                  className="bg-orange-500 h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.max(0, dist.odd_ratio * 100))}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Digit Frequencies 0 to 9 */}
        <div className="bg-dark-900/60 p-4 rounded-lg border border-dark-700">
          <div className="text-xs font-mono text-gray-300 font-bold mb-2">
            FREQUÊNCIA DE CADA DÍGITO (0 - 9)
          </div>
          <div className="grid grid-cols-10 gap-1.5 mt-3">
            {Array.from({ length: 10 }, (_, d) => {
              const count = freqs[d] || 0;
              const heightPercent = maxFreq > 0 ? (count / maxFreq) * 100 : 0;
              const isEvenDigit = d % 2 === 0;

              return (
                <div key={d} className="flex flex-col items-center">
                  <div className="w-full h-16 bg-dark-700/80 rounded-t flex items-end justify-center p-0.5">
                    <div
                      className={`w-full rounded-t transition-all duration-500 ${
                        isEvenDigit ? "bg-cyan-500/70" : "bg-orange-500/70"
                      }`}
                      style={{ height: `${Math.max(8, heightPercent)}%` }}
                      title={`Dígito ${d}: ${count} ocorrências`}
                    />
                  </div>
                  <div
                    className={`w-full text-center py-1 text-xs font-mono font-bold border-t ${
                      isEvenDigit ? "text-cyan-400 border-cyan-500/30" : "text-orange-400 border-orange-500/30"
                    }`}
                  >
                    {d}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
