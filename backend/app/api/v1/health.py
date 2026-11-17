"""Rotas de verificação de integridade (Health Check)."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from backend.app.api.deps import get_risk_manager
from backend.app.core.config import Settings, get_settings
from backend.app.modules.risk_manager.risk_rules import RiskManager

router = APIRouter(prefix="/health", tags=["Health & Status"])


@router.get("", summary="Verificação de integridade do sistema")
def health_check(
    settings: Settings = Depends(get_settings),
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> dict:
    """Retorna o estado operacional e as garantias ativas de segurança."""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "account_mode": settings.account_mode,
        "security_locks": {
            "demo_only": True,
            "real_account_blocked": not settings.allow_real_account,
            "martingale_banned": settings.risk_ban_martingale,
        },
        "risk_status": {
            "kill_switch_active": risk_manager.kill_switch_active,
            "kill_switch_reason": risk_manager.kill_switch_reason,
            "consecutive_losses": risk_manager.consecutive_losses,
            "daily_drawdown_usd": risk_manager.daily_drawdown_usd,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
