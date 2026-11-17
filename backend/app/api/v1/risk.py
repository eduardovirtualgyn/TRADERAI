"""Rotas da API para gerenciamento de risco, Kill Switch, Circuit Breaker e Kelly Fracionário."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from backend.app.api.deps import get_risk_manager
from backend.app.modules.risk_manager.risk_rules import RiskManager

router = APIRouter(prefix="/risk", tags=["Risk Management"])


class KillSwitchPayload(BaseModel):
    """Payload para ativação ou desarme manual do Kill Switch."""

    active: bool = Field(..., description="True para armar, False para desarmar")
    reason: str = Field(default="Comando manual via API", description="Justificativa da ação")


class CircuitBreakerTriggerPayload(BaseModel):
    """Payload para acionamento forçado do Circuit Breaker."""

    duration_seconds: float = Field(default=60.0, gt=0, le=3600, description="Duração da pausa em segundos")
    reason: str = Field(default="Pausa profilática manual", description="Motivo do resfriamento")


class KellyCalculationPayload(BaseModel):
    """Payload para consulta de dimensionamento de posição via Kelly Fracionário."""

    win_probability: float = Field(..., ge=0.0, le=1.0, description="Probabilidade estimada de vitória")
    payout: float = Field(..., gt=0.0, description="Payout total bruto em USD")
    stake_ref: float = Field(default=1.0, gt=0.0, description="Stake de referência")
    fraction_factor: float = Field(default=0.20, ge=0.01, le=0.25, description="Fração conservadora de Kelly")


class RiskEvaluationPayload(BaseModel):
    """Payload para testar a elegibilidade de uma proposta de trade."""

    stake: float = Field(..., gt=0, description="Valor do stake proposto em USD")
    net_ev_ratio: float = Field(..., description="Razão da expectativa matemática líquida")


@router.get("/status", summary="Consulta o snapshot completo de risco da conta")
def get_risk_status(
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> dict:
    """Retorna os limites atuais, saldo monitorado, Circuit Breaker, VaR e Kill Switch."""
    return risk_manager.get_status()


@router.post("/kill-switch", summary="Aciona ou desarma o Kill Switch")
def toggle_kill_switch(
    payload: KillSwitchPayload,
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> dict:
    """Permite interromper imediatamente qualquer envio de ordens ao mercado."""
    risk_manager.set_kill_switch(active=payload.active, reason=payload.reason)
    return {
        "success": True,
        "kill_switch_active": risk_manager.kill_switch_active,
        "reason": risk_manager.kill_switch_reason,
    }


@router.post("/circuit-breaker/trigger", summary="Aciona pausa de resfriamento (Circuit Breaker)")
def trigger_circuit_breaker(
    payload: CircuitBreakerTriggerPayload,
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> dict:
    """Impõe pausa forçada nas operações por N segundos."""
    risk_manager.circuit_breaker.trigger(
        reason=payload.reason,
        duration_seconds=payload.duration_seconds,
    )
    cb_status = risk_manager.circuit_breaker.get_status()
    return {
        "success": True,
        "circuit_breaker_active": cb_status.active,
        "remaining_seconds": cb_status.remaining_seconds,
        "reason": cb_status.reason,
    }


@router.post("/circuit-breaker/reset", summary="Reseta o Circuit Breaker manualmente")
def reset_circuit_breaker(
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> dict:
    """Cancela a pausa de resfriamento imediatamente."""
    risk_manager.circuit_breaker.reset()
    return {
        "success": True,
        "circuit_breaker_active": False,
        "message": "Circuit Breaker rearmado/liberado com sucesso.",
    }


@router.post("/kelly", summary="Calcula o dimensionamento fracionário de Kelly")
def calculate_kelly(
    payload: KellyCalculationPayload,
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> dict:
    """Calcula a fração ótima e stake sugerido em conformidade com as salvaguardas."""
    rec = risk_manager.calculate_kelly_stake(
        win_probability=payload.win_probability,
        payout=payload.payout,
        stake_ref=payload.stake_ref,
        fraction_factor=payload.fraction_factor,
    )
    return {
        "full_kelly_f": rec.full_kelly_f,
        "fractional_f": rec.fractional_f,
        "fraction_factor": rec.fraction_factor,
        "recommended_stake": rec.recommended_stake,
        "approved": rec.approved,
        "edge": rec.edge,
        "reason": rec.reason,
    }


@router.post("/evaluate", summary="Avalia se uma ordem proposta é permitida pelas regras de risco")
def evaluate_risk(
    payload: RiskEvaluationPayload,
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> dict:
    """Verifica todos os critérios de risco (teto de stake, drawdown, streak, anti-martingale)."""
    decision = risk_manager.evaluate_trade(
        stake=payload.stake,
        net_ev_ratio=payload.net_ev_ratio,
        raise_on_violation=False,
    )
    return {
        "approved": decision.approved,
        "reason": decision.reason,
        "stake": decision.stake,
        "consecutive_losses": decision.consecutive_losses,
        "daily_drawdown_usd": decision.daily_drawdown_usd,
        "kill_switch_active": decision.kill_switch_active,
        "circuit_breaker_active": decision.circuit_breaker_active,
    }
