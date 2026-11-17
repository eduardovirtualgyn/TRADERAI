"use client";

import React, { useState } from "react";
import { AuditMetrics, AuditRecord } from "@/types";
import { CheckCircle2, Download, FileJson, FileSpreadsheet, History, ShieldCheck, XCircle } from "lucide-react";
import { api } from "@/services/api";

interface AuditLedgerTableProps {
  records: AuditRecord[];
  metrics: AuditMetrics | null;
  onRefresh: () => void;
}

export const AuditLedgerTable: React.FC<AuditLedgerTableProps> = ({ records, metrics, onRefresh }) => {
  const [filterType, setFilterType] = useState<string>("ALL");

  const filteredRecords = records.filter((r) => {
    if (filterType === "ALL") return true;
    if (filterType === "SETTLED") return r.status === "WON" || r.status === "LOST";
    if (filterType === "REJECTED") return r.status.includes("REJECTED");
    return true;
  });

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 shadow-xl">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5 border-b border-dark-700 pb-3">
        <div className="flex items-center gap-2">
          <History className="w-5 h-5 text-indigo-400" />
          <h2 className="text-sm font-bold tracking-wide uppercase font-mono text-gray-200">
            Livro-Razão Criptográfico & Auditoria Contábil
          </h2>
        </div>

        {/* Action Controls & Exports */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Integrity Badge */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono font-bold border ${
              metrics?.ledger_integrity_verified
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-rose-500/10 border-rose-500/30 text-rose-400"
            }`}
          >
            {metrics?.ledger_integrity_verified ? (
              <>
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>SHA-256 ÍNTEGRO</span>
              </>
            ) : (
              <>
                <XCircle className="w-3.5 h-3.5" />
                <span>CADEIA ADULTERADA</span>
              </>
            )}
          </div>

          {/* Export CSV */}
          <a
            href={api.exportCsvUrl()}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-dark-700 hover:bg-dark-600 border border-dark-600 text-xs font-mono text-gray-200 transition-colors"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
            <span>CSV</span>
          </a>

          {/* Export JSON */}
          <a
            href={api.exportJsonUrl()}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-dark-700 hover:bg-dark-600 border border-dark-600 text-xs font-mono text-gray-200 transition-colors"
          >
            <FileJson className="w-3.5 h-3.5 text-cyan-400" />
            <span>JSON</span>
          </a>
        </div>
      </div>

      {/* Metrics Banner */}
      {metrics && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-5">
          <div className="bg-dark-900/60 p-2.5 rounded-lg border border-dark-700 text-xs font-mono">
            <span className="text-gray-400 text-[10px] block">TOTAL REGISTROS</span>
            <strong className="text-base text-white">{metrics.total_records}</strong>
          </div>

          <div className="bg-dark-900/60 p-2.5 rounded-lg border border-dark-700 text-xs font-mono">
            <span className="text-gray-400 text-[10px] block">TRADES LIQUIDADOS</span>
            <strong className="text-base text-cyan-300">{metrics.settled_trades}</strong>
          </div>

          <div className="bg-dark-900/60 p-2.5 rounded-lg border border-dark-700 text-xs font-mono">
            <span className="text-gray-400 text-[10px] block">TAXA DE ACERTO</span>
            <strong className="text-base text-emerald-400">{(metrics.win_rate * 100).toFixed(1)}%</strong>
          </div>

          <div className="bg-dark-900/60 p-2.5 rounded-lg border border-dark-700 text-xs font-mono">
            <span className="text-gray-400 text-[10px] block">PROFIT FACTOR</span>
            <strong className="text-base text-white">{metrics.profit_factor.toFixed(2)}</strong>
          </div>

          <div className="bg-dark-900/60 p-2.5 rounded-lg border border-dark-700 text-xs font-mono">
            <span className="text-gray-400 text-[10px] block">VETOS RISCO/MATH</span>
            <strong className="text-base text-amber-400">
              {metrics.rejected_by_risk + metrics.rejected_by_math}
            </strong>
          </div>

          <div className="bg-dark-900/60 p-2.5 rounded-lg border border-dark-700 text-xs font-mono">
            <span className="text-gray-400 text-[10px] block">PnL LÍQUIDO ACUMULADO</span>
            <strong
              className={`text-base ${
                metrics.net_pnl_usd >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {metrics.net_pnl_usd >= 0 ? "+" : ""}${metrics.net_pnl_usd.toFixed(2)}
            </strong>
          </div>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 mb-3 text-xs font-mono">
        <span className="text-gray-400">Filtrar:</span>
        <button
          onClick={() => setFilterType("ALL")}
          className={`px-2.5 py-0.5 rounded ${
            filterType === "ALL" ? "bg-indigo-600 text-white font-bold" : "text-gray-400 hover:text-white"
          }`}
        >
          Todos
        </button>
        <button
          onClick={() => setFilterType("SETTLED")}
          className={`px-2.5 py-0.5 rounded ${
            filterType === "SETTLED" ? "bg-indigo-600 text-white font-bold" : "text-gray-400 hover:text-white"
          }`}
        >
          Liquidados (Win/Loss)
        </button>
        <button
          onClick={() => setFilterType("REJECTED")}
          className={`px-2.5 py-0.5 rounded ${
            filterType === "REJECTED" ? "bg-indigo-600 text-white font-bold" : "text-gray-400 hover:text-white"
          }`}
        >
          Vetos (Rejeitados)
        </button>
      </div>

      {/* Ledger Table */}
      <div className="overflow-x-auto rounded-lg border border-dark-700">
        <table className="w-full text-xs font-mono">
          <thead className="bg-dark-900 text-gray-400 text-left border-b border-dark-700">
            <tr>
              <th className="py-2.5 px-3">Seq ID</th>
              <th className="py-2.5 px-3">Evento</th>
              <th className="py-2.5 px-3">Símbolo</th>
              <th className="py-2.5 px-3">Contrato</th>
              <th className="py-2.5 px-3">Stake</th>
              <th className="py-2.5 px-3">PnL Líquido</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3">Assinatura SHA-256</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dark-700 bg-dark-900/60">
            {filteredRecords.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-6 text-center text-gray-500">
                  Nenhum registro de auditoria encontrado.
                </td>
              </tr>
            ) : (
              filteredRecords.map((r) => {
                const isWin = r.status === "WON";
                const isLoss = r.status === "LOST";
                const isRejected = r.status.includes("REJECTED");

                return (
                  <tr key={r.record_id} className="hover:bg-dark-800 transition-colors">
                    <td className="py-2.5 px-3 font-bold text-gray-300">{r.record_id}</td>
                    <td className="py-2.5 px-3 text-indigo-300 font-semibold">{r.event_type}</td>
                    <td className="py-2.5 px-3 text-white">{r.symbol}</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          r.contract_type === "DIGITEVEN"
                            ? "bg-cyan-500/20 text-cyan-300"
                            : r.contract_type === "DIGITODD"
                            ? "bg-orange-500/20 text-orange-300"
                            : "bg-dark-700 text-gray-400"
                        }`}
                      >
                        {r.contract_type}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-white">
                      {r.stake > 0 ? `$${r.stake.toFixed(2)}` : "-"}
                    </td>
                    <td
                      className={`py-2.5 px-3 font-bold ${
                        r.net_pnl > 0 ? "text-emerald-400" : r.net_pnl < 0 ? "text-rose-400" : "text-gray-400"
                      }`}
                    >
                      {r.net_pnl !== 0 ? `${r.net_pnl > 0 ? "+" : ""}$${r.net_pnl.toFixed(2)}` : "-"}
                    </td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          isWin
                            ? "bg-emerald-500/20 text-emerald-400"
                            : isLoss
                            ? "bg-rose-500/20 text-rose-400"
                            : isRejected
                            ? "bg-amber-500/20 text-amber-400"
                            : "bg-dark-700 text-cyan-300"
                        }`}
                      >
                        {r.status}
                      </span>
                      {r.reason && <p className="text-[10px] text-gray-400 mt-0.5 max-w-xs truncate">{r.reason}</p>}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[10px] text-gray-500" title={r.record_hash}>
                      {r.record_hash.slice(0, 10)}...{r.record_hash.slice(-8)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
