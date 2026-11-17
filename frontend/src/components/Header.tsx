"use client";

import React, { useState } from "react";
import { DerivStatus, RiskStatus } from "@/types";
import { AlertOctagon, CheckCircle2, ShieldAlert, Wifi, WifiOff } from "lucide-react";

interface HeaderProps {
  derivStatus: DerivStatus | null;
  riskStatus: RiskStatus | null;
  onPanicStop: () => void;
  onToggleKillSwitch: (active: boolean) => void;
}

export const Header: React.FC<HeaderProps> = ({
  derivStatus,
  riskStatus,
  onPanicStop,
  onToggleKillSwitch,
}) => {
  const [confirmPanic, setConfirmPanic] = useState(false);

  const isConnected = derivStatus?.is_connected ?? false;
  const isAuthorized = derivStatus?.is_authorized ?? false;
  const balance = riskStatus?.balance_usd ?? derivStatus?.account_info?.balance ?? 1000.0;
  const killSwitchActive = riskStatus?.kill_switch_active ?? false;

  const handlePanicClick = () => {
    if (!confirmPanic) {
      setConfirmPanic(true);
      setTimeout(() => setConfirmPanic(false), 4000); // 4s timeout para confirmação
    } else {
      onPanicStop();
      setConfirmPanic(false);
    }
  };

  return (
    <header className="border-b border-dark-600 bg-dark-800/90 backdrop-blur-md sticky top-0 z-50 px-4 lg:px-8 py-3">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        {/* Brand & Mode */}
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-gradient-to-br from-cyan-500/20 to-orange-500/20 border border-dark-500">
            <span className="font-mono font-black text-transparent bg-clip-text bg-gradient-to-r from-even to-odd text-xl">
              OE
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-lg tracking-tight text-white font-mono">
                ODD/EVEN <span className="text-cyan-400">AI TRADER</span>
              </h1>
              <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 animate-pulse">
                DEMO ONLY
              </span>
            </div>
            <p className="text-xs text-gray-400 hidden sm:block">
              Algorithmic Digit Parity Engine &middot; Real-Time Risk Safeguards
            </p>
          </div>
        </div>

        {/* Real-time Status Badges */}
        <div className="flex items-center flex-wrap gap-3">
          {/* WebSocket Status */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-dark-600 text-xs font-mono">
            {isConnected ? (
              <Wifi className="w-4 h-4 text-emerald-400 animate-pulse" />
            ) : (
              <WifiOff className="w-4 h-4 text-rose-500" />
            )}
            <span className="text-gray-300">DERIV WS:</span>
            <span
              className={
                isAuthorized
                  ? "text-emerald-400 font-semibold"
                  : isConnected
                  ? "text-cyan-400"
                  : "text-rose-400"
              }
            >
              {isAuthorized ? "AUTHORIZED (DEMO)" : isConnected ? "CONNECTED" : "OFFLINE"}
            </span>
          </div>

          {/* Account Balance */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-dark-600 text-xs font-mono">
            <span className="text-gray-400">SALDO DEMO:</span>
            <span className="text-white font-bold text-sm">
              US$ {balance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>

          {/* Kill Switch Toggle */}
          <button
            onClick={() => onToggleKillSwitch(!killSwitchActive)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-bold font-mono transition-all ${
              killSwitchActive
                ? "bg-rose-500/20 border-rose-500 text-rose-400 glow-danger"
                : "bg-dark-700 border-dark-600 text-emerald-400 hover:border-dark-500"
            }`}
            title="Armar ou desarmar o Kill Switch preventivo"
          >
            {killSwitchActive ? (
              <>
                <ShieldAlert className="w-4 h-4" />
                <span>KILL SWITCH ATIVO</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>KILL SWITCH NORMAL</span>
              </>
            )}
          </button>

          {/* Panic Button */}
          <button
            onClick={handlePanicClick}
            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg font-mono text-xs font-black tracking-wider uppercase transition-all shadow-lg ${
              confirmPanic
                ? "bg-red-600 text-white animate-bounce ring-4 ring-red-500/50"
                : "bg-red-950/80 hover:bg-red-900 border border-red-700 text-red-300 hover:text-white"
            }`}
          >
            <AlertOctagon className="w-4 h-4 text-red-400" />
            <span>{confirmPanic ? "CONFIRMAR PÂNICO!" : "BOTÃO DE PÂNICO"}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
