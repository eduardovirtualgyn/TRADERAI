"use client";

import React from "react";
import { EnsemblePrediction } from "@/types";
import { BrainCircuit, CheckCircle2, Cpu, Scale, XCircle } from "lucide-react";

interface ModelEnsemblePanelProps {
  ensemble: EnsemblePrediction | null;
  loading: boolean;
}

export const ModelEnsemblePanel: React.FC<ModelEnsemblePanelProps> = ({ ensemble, loading }) => {
  const pEven = ensemble?.even_probability || 0.50;
  const pOdd = ensemble?.odd_probability || 0.50;
  const direction = ensemble?.consensus_direction || "NO_CONSENSUS";
  const spread = ensemble?.spread || 0.0;
  const isDiscordant = ensemble?.is_discordant || false;
  const wilsonLower = ensemble?.wilson_lower_bound || 0.49;
  const breakEven = ensemble?.break_even_probability || 0.5128;
  const hasEdge = ensemble?.has_mathematical_edge || false;

  const isApproved = hasEdge && !isDiscordant && direction !== "NO_CONSENSUS";

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 shadow-xl">
      <div className="flex items-center justify-between gap-3 mb-5 border-b border-dark-700 pb-3">
        <div className="flex items-center gap-2">
          <BrainCircuit className="w-5 h-5 text-indigo-400" />
          <h2 className="text-sm font-bold tracking-wide uppercase font-mono text-gray-200">
            Ensemble de Modelos & Validação Matemática
          </h2>
        </div>

        {/* Verdict Badge */}
        <div className="flex items-center gap-2">
          {isApproved ? (
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-400 font-mono text-xs font-bold">
              <CheckCircle2 className="w-4 h-4" />
              <span>SINAL AUTORIZADO (EV &gt; 0)</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-500/15 border border-rose-500/40 text-rose-400 font-mono text-xs font-bold">
              <XCircle className="w-4 h-4" />
              <span>VETO MATEMÁTICO (PASSEIO ALEATÓRIO)</span>
            </div>
          )}
        </div>
      </div>

      {/* Main Probabilities Comparison */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
        {/* P(EVEN) Card */}
        <div
          className={`p-4 rounded-lg border transition-all ${
            direction === "DIGITEVEN"
              ? "bg-cyan-950/30 border-cyan-500 glow-even"
              : "bg-dark-900/60 border-dark-700"
          }`}
        >
          <div className="flex justify-between items-center text-xs font-mono text-gray-400 mb-1">
            <span className="font-bold text-cyan-400">PROBABILIDADE PAR (EVEN):</span>
            {direction === "DIGITEVEN" && (
              <span className="px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 text-[10px] font-bold">
                DIREÇÃO ELEITA
              </span>
            )}
          </div>
          <div className="text-3xl font-black font-mono text-white tracking-tight my-1">
            {(pEven * 100).toFixed(1)}%
          </div>
          <p className="text-[11px] text-gray-400 font-mono">
            Calibrado com Platt Scaling sigmoide
          </p>
        </div>

        {/* P(ODD) Card */}
        <div
          className={`p-4 rounded-lg border transition-all ${
            direction === "DIGITODD"
              ? "bg-orange-950/30 border-orange-500 glow-odd"
              : "bg-dark-900/60 border-dark-700"
          }`}
        >
          <div className="flex justify-between items-center text-xs font-mono text-gray-400 mb-1">
            <span className="font-bold text-orange-400">PROBABILIDADE ÍMPAR (ODD):</span>
            {direction === "DIGITODD" && (
              <span className="px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300 text-[10px] font-bold">
                DIREÇÃO ELEITA
              </span>
            )}
          </div>
          <div className="text-3xl font-black font-mono text-white tracking-tight my-1">
            {(pOdd * 100).toFixed(1)}%
          </div>
          <p className="text-[11px] text-gray-400 font-mono">
            Ponderado pelo inverso do Brier Score
          </p>
        </div>

        {/* Statistical Proof & Wilson Bound */}
        <div className="bg-dark-900/60 p-4 rounded-lg border border-dark-700 flex flex-col justify-between">
          <div className="text-xs font-mono text-gray-400 mb-1 flex items-center justify-between">
            <span className="flex items-center gap-1 text-gray-300 font-bold">
              <Scale className="w-3.5 h-3.5 text-indigo-400" />
              INTERVALO DE WILSON (95% CI):
            </span>
          </div>
          <div>
            <div className="flex justify-between text-xs font-mono my-1">
              <span className="text-gray-400">Limite Inferior (CI_lower):</span>
              <span className={`font-bold ${wilsonLower > breakEven ? "text-emerald-400" : "text-rose-400"}`}>
                {(wilsonLower * 100).toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between text-xs font-mono mb-2">
              <span className="text-gray-400">Break-even do Payout:</span>
              <span className="font-bold text-white">{(breakEven * 100).toFixed(2)}%</span>
            </div>
          </div>
          <div className="text-[10px] font-mono text-gray-400 bg-dark-800 p-1.5 rounded border border-dark-700">
            {wilsonLower > breakEven ? (
              <span className="text-emerald-400 font-semibold">
                &check; CI_lower &gt; Break-even: Vantagem com significância estatística.
              </span>
            ) : (
              <span className="text-rose-400 font-semibold">
                &times; CI_lower &le; Break-even: Rejeitado por incerteza amostral.
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Model Weights & Divergence Veto Info */}
      <div className="bg-dark-900/80 p-3.5 rounded-lg border border-dark-700 text-xs font-mono flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <span className="text-gray-400 flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-cyan-400" />
            Modelos Ativos:
          </span>
          <span className="text-gray-300">
            Random Forest: <strong className="text-cyan-400">w={(ensemble?.model_weights?.random_forest || 0.5).toFixed(2)}</strong>
          </span>
          <span className="text-gray-300">
            XGBoost: <strong className="text-orange-400">w={(ensemble?.model_weights?.xgboost || 0.5).toFixed(2)}</strong>
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-gray-400">Spread entre Modelos:</span>
          <span className={`font-bold ${spread > 0.15 ? "text-red-400" : "text-emerald-400"}`}>
            {(spread * 100).toFixed(1)}% {spread > 0.15 ? "(VETO POR DIVERGÊNCIA)" : "(CONSENSO OK)"}
          </span>
        </div>
      </div>
    </div>
  );
};
