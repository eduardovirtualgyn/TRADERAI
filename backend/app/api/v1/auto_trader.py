"""Rotas da API para controle e telemetria do Auto-Trader Autônomo."""

from fastapi import APIRouter, Depends
from backend.app.api.deps import get_auto_trader
from backend.app.modules.auto_trader.engine import AutoTraderEngine
from backend.app.modules.auto_trader.models import (
    AutoTraderConfig,
    AutoTraderStatusResponse,
    AutoTraderTogglePayload,
)

router = APIRouter(prefix="/auto-trader", tags=["Auto-Trader"])


@router.get("/status", summary="Retorna o status em tempo real do Auto-Trader")
def get_status(
    auto_trader: AutoTraderEngine = Depends(get_auto_trader),
) -> AutoTraderStatusResponse:
    """Consulta o estado da máquina de estados, métricas e última decisão."""
    return auto_trader.get_status()


@router.post("/toggle", summary="Ativa ou pausa a operação do Auto-Trader")
def toggle_auto_trader(
    payload: AutoTraderTogglePayload,
    auto_trader: AutoTraderEngine = Depends(get_auto_trader),
) -> AutoTraderStatusResponse:
    """Inicia ou interrompe a execução contínua e autônoma de ordens."""
    auto_trader.set_enabled(payload.enabled)
    return auto_trader.get_status()


@router.post("/configure", summary="Atualiza os parâmetros do Auto-Trader")
async def configure_auto_trader(
    config: AutoTraderConfig,
    auto_trader: AutoTraderEngine = Depends(get_auto_trader),
) -> AutoTraderStatusResponse:
    """Configura símbolo, stake por trade, probabilidade mínima e cooldown."""
    auto_trader.update_config(config)
    return auto_trader.get_status()
