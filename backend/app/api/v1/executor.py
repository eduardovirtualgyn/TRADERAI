"""Rotas da API para o Executor de Contratos e Ciclo de Vida de Ordens."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.api.deps import get_contract_executor
from backend.app.modules.contract_executor.executor import ContractExecutor
from backend.app.modules.contract_executor.models import (
    ExecutionResult,
    OrderRequest,
)

router = APIRouter(prefix="/executor", tags=["Contract Executor"])


class PanicStopPayload(BaseModel):
    """Payload para acionamento do Botão de Pânico."""

    reason: str = Field(default="Parada emergencial via API", description="Motivo do acionamento")


class SettleContractPayload(BaseModel):
    """Payload para resolução/liquidação de um contrato ativo."""

    contract_id: str = Field(..., description="ID do contrato na Deriv")
    won: bool = Field(..., description="True se venceu, False se perdeu")
    exit_digit: Optional[int] = Field(default=None, description="Último dígito verificado no encerramento")


@router.post("/execute", summary="Executa uma ordem com validação matemática e de risco")
async def execute_contract(
    payload: OrderRequest,
    executor: ContractExecutor = Depends(get_contract_executor),
) -> ExecutionResult:
    """Submete ordem à Deriv após aprovação no portão de probabilidade, EV e risco."""
    return await executor.execute_order(payload)


@router.post("/panic-stop", summary="Botão de Pânico: interrompe operações e arma Kill Switch")
def trigger_panic_stop(
    payload: PanicStopPayload,
    executor: ContractExecutor = Depends(get_contract_executor),
) -> dict:
    """Bloqueia todas as ordens imediatamente e congela a operação."""
    return executor.panic_stop(reason=payload.reason)


@router.get("/active-contracts", summary="Lista os contratos ativos no momento")
def list_active_contracts(
    executor: ContractExecutor = Depends(get_contract_executor),
) -> List[dict]:
    """Retorna os contratos que estão em andamento na corretora."""
    return executor.get_active_contracts()


@router.get("/history", summary="Retorna o histórico das últimas execuções de ordens")
def get_execution_history(
    executor: ContractExecutor = Depends(get_contract_executor),
) -> List[ExecutionResult]:
    """Retorna o histórico de ordens submetidas, rejeitadas e liquidadas."""
    return executor.get_history()


@router.post("/settle", summary="Liquida um contrato e atualiza métricas da conta")
def settle_contract(
    payload: SettleContractPayload,
    executor: ContractExecutor = Depends(get_contract_executor),
) -> ExecutionResult:
    """Resolve um contrato ativo e alimenta o controle de risco e saldo."""
    try:
        return executor.settle_contract(
            contract_id=payload.contract_id,
            won=payload.won,
            exit_digit=payload.exit_digit,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
