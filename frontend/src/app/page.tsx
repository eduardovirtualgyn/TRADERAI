"use client";

import React, { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { DigitStream } from "@/components/DigitStream";
import { RiskControlPanel } from "@/components/RiskControlPanel";
import { ModelEnsemblePanel } from "@/components/ModelEnsemblePanel";
import { ContractExecutionPanel } from "@/components/ContractExecutionPanel";
import { AuditLedgerTable } from "@/components/AuditLedgerTable";
import { api } from "@/services/api";
import {
  AuditMetrics,
  AuditRecord,
  DerivStatus,
  EnsemblePrediction,
  RiskStatus,
  TickSummary,
} from "@/types";

export default function DashboardPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>("R_100");
  const [derivStatus, setDerivStatus] = useState<DerivStatus | null>(null);
  const [riskStatus, setRiskStatus] = useState<RiskStatus | null>(null);
  const [tickSummary, setTickSummary] = useState<TickSummary | null>(null);
  const [ensemble, setEnsemble] = useState<EnsemblePrediction | null>(null);
  const [auditRecords, setAuditRecords] = useState<AuditRecord[]>([]);
  const [auditMetrics, setAuditMetrics] = useState<AuditMetrics | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Polling em tempo real a cada 2 segundos
  const refreshAll = async () => {
    try {
      const [derivRes, riskRes, tickRes, ensembleRes, auditRes, metricsRes] = await Promise.allSettled([
        api.getDerivStatus(),
        api.getRiskStatus(),
        api.getTickSummary(selectedSymbol),
        api.getEnsembleStatus(selectedSymbol),
        api.getAuditLogs(50),
        api.getAuditMetrics(),
      ]);

      if (derivRes.status === "fulfilled") setDerivStatus(derivRes.value);
      if (riskRes.status === "fulfilled") setRiskStatus(riskRes.value);
      if (tickRes.status === "fulfilled") setTickSummary(tickRes.value);
      if (ensembleRes.status === "fulfilled") setEnsemble(ensembleRes.value);
      if (auditRes.status === "fulfilled") setAuditRecords(auditRes.value);
      if (metricsRes.status === "fulfilled") setAuditMetrics(metricsRes.value);
    } catch (err) {
      console.error("Erro no polling do dashboard:", err);
    }
  };

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, 2000);
    return () => clearInterval(interval);
  }, [selectedSymbol]);

  const handlePanicStop = async () => {
    try {
      await api.triggerPanicStop("Parada de Emergência disparada via painel do operador");
      await refreshAll();
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleKillSwitch = async (active: boolean) => {
    try {
      await api.toggleKillSwitch(active, "Controle manual via Header");
      await refreshAll();
    } catch (err) {
      console.error(err);
    }
  };

  const handleConnectDeriv = async (token?: string) => {
    await api.connectDeriv(token, selectedSymbol);
    await refreshAll();
  };

  return (
    <div className="min-h-screen bg-dark-900 flex flex-col font-sans">
      {/* Persistent Navigation Header */}
      <Header
        derivStatus={derivStatus}
        riskStatus={riskStatus}
        onPanicStop={handlePanicStop}
        onToggleKillSwitch={handleToggleKillSwitch}
        onConnectDeriv={handleConnectDeriv}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 lg:p-8 space-y-6">
        {/* Row 1: Real-time Digits & High-Frequency Stream */}
        <DigitStream
          tickSummary={tickSummary}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={setSelectedSymbol}
        />

        {/* Row 2: Dual Grid: Risk Manager & AI Ensemble */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <RiskControlPanel
            riskStatus={riskStatus}
            onRefresh={refreshAll}
          />
          <ModelEnsemblePanel
            ensemble={ensemble}
            loading={isRefreshing}
          />
        </div>

        {/* Row 3: Atomic Order Execution Station */}
        <ContractExecutionPanel
          selectedSymbol={selectedSymbol}
          ensemble={ensemble}
          riskStatus={riskStatus}
          onTradeExecuted={refreshAll}
        />

        {/* Row 4: Immutable SHA-256 Audit Ledger */}
        <AuditLedgerTable
          records={auditRecords}
          metrics={auditMetrics}
          onRefresh={refreshAll}
        />
      </main>

      {/* Footer */}
      <footer className="border-t border-dark-700 bg-dark-800/60 py-4 px-6 text-center text-xs font-mono text-gray-500">
        ODD/EVEN AI TRADER &middot; Operando exclusivamente em ambiente DEMO &middot; Protocolo de Segurança Ativo &middot; Anti-Martingale Estrito &middot;
        Zero Data Leakage Guaranteed.
      </footer>
    </div>
  );
}
