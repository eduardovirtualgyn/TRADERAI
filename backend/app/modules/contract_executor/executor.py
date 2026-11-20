"""Módulo 9: Executor de Contratos e Ciclo de Vida de Ordens da Deriv.

Implementa o fluxo transacional atômico de 3 etapas com verificações matemáticas,
salvaguardas de risco, mitigação de slippage e parada emergencial (Panic Button).
"""

import time
from typing import Callable, Dict, List, Optional

from backend.app.core.errors import (
    DerivApiError,
    TraderSecurityError,
)
from backend.app.core.logging import logger
from backend.app.modules.contract_executor.models import (
    ContractStatus,
    ExecutionResult,
    OrderRequest,
)
from backend.app.modules.deriv_client.client import DerivWebSocketClient
from backend.app.modules.risk_manager.risk_rules import RiskManager


class ContractExecutor:
    """Orquestrador transacional de execução de ordens com portão duplo de validação."""

    def __init__(
        self,
        deriv_client: DerivWebSocketClient,
        risk_manager: RiskManager,
        audit_callback: Optional[Callable[[ExecutionResult], None]] = None,
    ):
        self.deriv_client = deriv_client
        self.risk_manager = risk_manager
        self.audit_callback = audit_callback

        # Rastreamento de contratos em memória
        self.active_contracts: Dict[str, dict] = {}
        self.history: List[ExecutionResult] = []

    async def execute_order(self, request: OrderRequest) -> ExecutionResult:
        """Executa o pipeline transacional atômico de uma ordem."""
        logger.info(
            "Iniciando pipeline de execução: %s em %s (Stake: US$ %.2f, P_est: %.2f%%)",
            request.contract_type,
            request.symbol,
            request.stake,
            request.estimated_probability * 100,
        )

        # 0. Validação de Parâmetros
        if request.contract_type not in ("DIGITEVEN", "DIGITODD"):
            return self._record_failure(
                request=request,
                status=ContractStatus.ERROR,
                reason=f"Tipo de contrato não suportado: {request.contract_type}",
            )

        # 1. Pré-verificação de Salvaguardas Imediatas (Sem gastar chamada de rede)
        if self.risk_manager.kill_switch_active:
            return self._record_failure(
                request=request,
                status=ContractStatus.REJECTED_BY_RISK,
                reason=f"Kill Switch ATIVO: {self.risk_manager.kill_switch_reason or 'Operações suspensas'}",
            )

        if self.risk_manager.circuit_breaker.is_active():
            rem = self.risk_manager.circuit_breaker.remaining_seconds()
            return self._record_failure(
                request=request,
                status=ContractStatus.REJECTED_BY_RISK,
                reason=f"Circuit Breaker em andamento ({rem:.1f}s restantes).",
            )

        # 2. Etapa 1: Obtenção de Cotação Oficial no Livro da Deriv
        try:
            proposal = await self.deriv_client.get_proposal(
                symbol=request.symbol,
                contract_type=request.contract_type,
                amount=request.stake,
                duration=request.duration,
                duration_unit=request.duration_unit,
            )
        except Exception as exc:
            logger.error("Falha ao consultar proposta na Deriv API: %s", exc)
            return self._record_failure(
                request=request,
                status=ContractStatus.ERROR,
                reason=f"Falha ao obter cotação: {exc}",
            )

        # 3. Etapa 2: Verificação Matemática e Validação de Risco no Livro Real
        payout = proposal.payout
        if payout <= request.stake:
            return self._record_failure(
                request=request,
                status=ContractStatus.REJECTED_BY_MATH,
                reason=f"Payout inválido da corretora (${payout:.2f} <= stake ${request.stake:.2f}).",
                proposal_id=proposal.proposal_id,
                payout=payout,
            )

        p_be = request.stake / payout
        net_ev = (request.estimated_probability * payout) - request.stake
        net_ev_ratio = net_ev / request.stake

        # Portão A: Expectativa Líquida Positiva
        if net_ev <= 0.0:
            return self._record_failure(
                request=request,
                status=ContractStatus.REJECTED_BY_MATH,
                reason=f"Expectativa matemática líquida não positiva no livro real (EV_ratio={net_ev_ratio:.2%}).",
                proposal_id=proposal.proposal_id,
                payout=payout,
            )

        # Portão B: Limite de Confiança de Wilson superior ao Break-Even
        if request.wilson_lower_bound <= p_be:
            return self._record_failure(
                request=request,
                status=ContractStatus.REJECTED_BY_MATH,
                reason=(
                    f"Limite inferior de Wilson ({request.wilson_lower_bound:.2%}) "
                    f"não supera a probabilidade de equilíbrio ({p_be:.2%})."
                ),
                proposal_id=proposal.proposal_id,
                payout=payout,
            )

        # Portão C: Avaliação de Limites de Risco e Salvaguarda Anti-Martingale
        risk_decision = self.risk_manager.evaluate_trade(
            stake=request.stake,
            net_ev_ratio=net_ev_ratio,
            raise_on_violation=False,
        )

        if not risk_decision.approved:
            return self._record_failure(
                request=request,
                status=ContractStatus.REJECTED_BY_RISK,
                reason=risk_decision.reason or "Bloqueado pelo gerenciador de risco.",
                proposal_id=proposal.proposal_id,
                payout=payout,
            )

        # 4. Etapa 3: Execução Atômica de Compra
        try:
            buy_result = await self.deriv_client.buy(
                proposal_id=proposal.proposal_id,
                price=proposal.ask_price,
            )
        except Exception as exc:
            logger.error("Falha ao submeter ordem de compra à Deriv: %s", exc)
            return self._record_failure(
                request=request,
                status=ContractStatus.ERROR,
                reason=f"Erro de execução da ordem: {exc}",
                proposal_id=proposal.proposal_id,
                payout=payout,
            )

        # Sucesso na submissão
        contract_record = {
            "contract_id": buy_result.contract_id,
            "proposal_id": proposal.proposal_id,
            "symbol": request.symbol,
            "contract_type": request.contract_type,
            "stake": request.stake,
            "payout": payout,
            "strategy_name": request.strategy_name,
            "timestamp": time.time(),
        }
        self.active_contracts[buy_result.contract_id] = contract_record

        exec_res = ExecutionResult(
            success=True,
            status=ContractStatus.BUY_SUBMITTED,
            symbol=request.symbol,
            contract_type=request.contract_type,
            stake=request.stake,
            payout=payout,
            net_pnl=0.0,
            contract_id=buy_result.contract_id,
            proposal_id=proposal.proposal_id,
            strategy_name=request.strategy_name,
            execution_timestamp=contract_record["timestamp"],
        )

        logger.info(
            "✅ Ordem executada com sucesso! Contract ID: %s (Stake: US$ %.2f, Payout Potencial: US$ %.2f)",
            buy_result.contract_id,
            request.stake,
            payout,
        )

        if self.audit_callback:
            try:
                self.audit_callback(exec_res)
            except Exception as exc:
                logger.warning("Falha ao acionar callback de auditoria: %s", exc)

        return exec_res

    def settle_contract(
        self,
        contract_id: str | int,
        won: bool,
        exit_digit: Optional[int] = None,
    ) -> ExecutionResult:
        """Processa a finalização oficial do contrato e atualiza os contadores de risco."""
        cid = str(contract_id)
        contract = self.active_contracts.pop(cid, None)
        if not contract:
            raise KeyError(f"Contrato ativo ID {cid} não encontrado no executor.")

        stake = contract["stake"]
        payout = contract["payout"]
        pnl = (payout - stake) if won else (-stake)
        status = ContractStatus.WON if won else ContractStatus.LOST

        # 1. Atualiza métricas e limites de risco
        self.risk_manager.record_trade_result(won=won, pnl_usd=pnl, stake_used=stake)
        if hasattr(self.deriv_client, "update_balance"):
            try:
                self.deriv_client.update_balance(pnl, stake=stake, payout=payout, won=won)
            except TypeError:
                try:
                    self.deriv_client.update_balance(pnl)
                except Exception as bal_err:
                    logger.warning("Falha ao atualizar saldo no cliente Deriv: %s", bal_err)
            except Exception as bal_err:
                logger.warning("Falha ao atualizar saldo no cliente Deriv: %s", bal_err)

        settled_result = ExecutionResult(
            success=True,
            status=status,
            symbol=contract["symbol"],
            contract_type=contract["contract_type"],
            stake=stake,
            payout=payout,
            net_pnl=round(pnl, 2),
            contract_id=cid,
            proposal_id=contract.get("proposal_id"),
            strategy_name=contract.get("strategy_name", "manual"),
            execution_timestamp=contract.get("timestamp", time.time()),
            completion_timestamp=time.time(),
        )

        self.history.append(settled_result)
        logger.info(
            "🏁 Contrato %s liquidado: %s | PnL: US$ %.2f (Dígito final: %s)",
            cid,
            status.value,
            pnl,
            str(exit_digit) if exit_digit is not None else "N/A",
        )

        if self.audit_callback:
            try:
                self.audit_callback(settled_result)
            except Exception as exc:
                logger.warning("Falha ao registrar auditoria de liquidação: %s", exc)

        return settled_result

    def panic_stop(self, reason: str = "Parada de emergência (Panic Button)") -> dict:
        """Cancela atividades imediatas e aciona o Kill Switch incondicionalmente."""
        logger.critical("🚨 BOTÃO DE PÂNICO ACIONADO: %s", reason)
        self.risk_manager.set_kill_switch(active=True, reason=reason)
        self.risk_manager.circuit_breaker.trigger(reason=reason, duration_seconds=3600.0)
        aborted_count = len(self.active_contracts)
        return {
            "success": True,
            "panic_triggered": True,
            "kill_switch_active": self.risk_manager.kill_switch_active,
            "circuit_breaker_active": self.risk_manager.circuit_breaker.is_active(),
            "active_contracts_count": aborted_count,
            "message": f"Sistema paralisado com sucesso. {aborted_count} contratos monitorados.",
        }

    def get_active_contracts(self) -> List[dict]:
        """Retorna os contratos em andamento."""
        return list(self.active_contracts.values())

    def get_history(self) -> List[ExecutionResult]:
        """Retorna o histórico de execuções."""
        return list(self.history)

    def _record_failure(
        self,
        request: OrderRequest,
        status: ContractStatus,
        reason: str,
        proposal_id: Optional[str] = None,
        payout: float = 0.0,
    ) -> ExecutionResult:
        logger.warning(
            "Execução rejeitada/abortada [%s]: %s (Símbolo: %s, Tipo: %s)",
            status.value,
            reason,
            request.symbol,
            request.contract_type,
        )
        res = ExecutionResult(
            success=False,
            status=status,
            symbol=request.symbol,
            contract_type=request.contract_type,
            stake=request.stake,
            payout=payout,
            net_pnl=0.0,
            proposal_id=proposal_id,
            strategy_name=request.strategy_name,
            rejection_reason=reason,
        )
        self.history.append(res)
        if self.audit_callback:
            try:
                self.audit_callback(res)
            except Exception:
                pass
        return res
