"use client";

import React, { useState } from "react";
import { DerivStatus, RiskStatus } from "@/types";
import { AlertOctagon, CheckCircle2, KeyRound, PlayCircle, ShieldAlert, Wifi, WifiOff } from "lucide-react";

interface HeaderProps {
  derivStatus: DerivStatus | null;
  riskStatus: RiskStatus | null;
  onPanicStop: () => void;
  onToggleKillSwitch: (active: boolean) => void;
  onConnectDeriv?: (token?: string) => Promise<void>;
}

export const Header: React.FC<HeaderProps> = ({
  derivStatus,
  riskStatus,
  onPanicStop,
  onToggleKillSwitch,
  onConnectDeriv,
}) => {
  const [confirmPanic, setConfirmPanic] = useState(false);
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [inputToken, setInputToken] = useState("");
  const [isConnecting, setIsConnecting] = useState(false);

  const isConnected = derivStatus?.is_connected ?? false;
  const isAuthorized = derivStatus?.is_authorized ?? false;
  const balance = riskStatus?.balance_usd ?? derivStatus?.account_info?.balance ?? 1000.0;
  const killSwitchActive = riskStatus?.kill_switch_active ?? false;

  const handlePanicClick = () => {
    if (!confirmPanic) {
      setConfirmPanic(true);
      setTimeout(() => setConfirmPanic(false), 4000);
    } else {
      onPanicStop();
      setConfirmPanic(false);
    }
  };

  const handleConnectClick = async () => {
    if (!onConnectDeriv) return;
    setIsConnecting(true);
    try {
      await onConnectDeriv();
    } catch (err: any) {
      setShowTokenModal(true);
    } finally {
      setIsConnecting(false);
    }
  };

  const handleManualTokenSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!onConnectDeriv || !inputToken.trim()) return;
    setIsConnecting(true);
    try {
      await onConnectDeriv(inputToken.trim());
      setShowTokenModal(false);
    } catch (err: any) {
      alert("Falha na autenticação: " + (err.message || err));
    } finally {
      setIsConnecting(false);
    }
  };

  return (
    <>
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
                    : "text-rose-400 font-semibold"
                }
              >
                {isAuthorized ? "AUTHORIZED (DEMO)" : isConnected ? "CONNECTED" : "OFFLINE"}
              </span>

              {/* Botão Conectar / Reconectar */}
              {!isAuthorized && onConnectDeriv && (
                <button
                  onClick={handleConnectClick}
                  disabled={isConnecting}
                  className="ml-1.5 px-2 py-0.5 rounded bg-cyan-600/30 hover:bg-cyan-600 text-cyan-300 hover:text-white border border-cyan-500/50 text-[10px] font-bold transition-all"
                >
                  {isConnecting ? "Conectando..." : "Conectar Agora"}
                </button>
              )}
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

      {/* Modal para Inserir Token DEMO se necessário */}
      {showTokenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-dark-800 border border-dark-600 rounded-xl max-w-md w-full p-6 shadow-2xl">
            <div className="flex items-center gap-2 text-cyan-400 mb-2">
              <KeyRound className="w-5 h-5" />
              <h3 className="font-bold font-mono text-sm uppercase">Conectar Conta DEMO da Deriv</h3>
            </div>
            <p className="text-xs text-gray-400 font-mono mb-4">
              Insira o API Token da sua conta virtual (VRTC...) para autorizar o WebSocket e receber ticks em tempo real:
            </p>
            <form onSubmit={handleManualTokenSubmit} className="space-y-4">
              <input
                type="password"
                placeholder="Cole seu token aqui (ex: pat_...)"
                value={inputToken}
                onChange={(e) => setInputToken(e.target.value)}
                className="w-full bg-dark-900 border border-dark-600 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-cyan-500"
                autoFocus
              />
              <div className="flex justify-end gap-2 text-xs font-mono">
                <button
                  type="button"
                  onClick={() => setShowTokenModal(false)}
                  className="px-3 py-1.5 rounded bg-dark-700 hover:bg-dark-600 text-gray-300"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={isConnecting}
                  className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold flex items-center gap-1.5"
                >
                  <PlayCircle className="w-4 h-4" />
                  <span>{isConnecting ? "Autenticando..." : "Conectar"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
