"""Rotas da API para monitoramento, conexão e autorização da Deriv API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.api.deps import (
    get_deriv_client,
    get_risk_manager,
    get_tick_collector,
)
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import TraderSecurityError
from backend.app.core.logging import logger
from backend.app.modules.deriv_client.client import DerivConnectionState, DerivWebSocketClient
from backend.app.modules.risk_manager.risk_rules import RiskManager
from backend.app.modules.tick_collector.collector import TickCollector

router = APIRouter(prefix="/deriv", tags=["Deriv WebSocket"])


class DerivConnectPayload(BaseModel):
    """Payload para disparar ou redefinir a conexão da Deriv."""

    token: Optional[str] = Field(default=None, description="Token da conta DEMO da Deriv")
    symbol: Optional[str] = Field(default="R_100", description="Símbolo para assinar ticks")


@router.get("/status", summary="Consulta o estado da conexão com a Deriv API")
def get_deriv_status(
    settings: Settings = Depends(get_settings),
    client: DerivWebSocketClient = Depends(get_deriv_client),
) -> dict:
    """Retorna o estado da conexão, símbolos vigentes e informações da conta DEMO."""
    auth_info = client.auth_info
    is_connected = client.state in (DerivConnectionState.CONNECTED, DerivConnectionState.AUTHORIZED)

    account_data = {
        "is_virtual": auth_info.is_virtual if auth_info else False,
        "loginid": auth_info.loginid if auth_info else None,
        "currency": auth_info.currency if auth_info else None,
        "balance": auth_info.balance if auth_info else 0.0,
    } if auth_info else None

    return {
        "state": client.state.value,
        "connection_state": client.state.value,
        "is_connected": is_connected,
        "is_authorized": client.is_authorized,
        "app_id": client.app_id,
        "ws_url": client.ws_url,
        "default_symbol": settings.deriv_default_symbol,
        "active_symbols": client._active_symbols,
        "account_info": account_data,
        "auth": account_data,
    }


@router.post("/connect", summary="Conecta, autentica na conta DEMO e assina ticks")
async def connect_deriv(
    payload: DerivConnectPayload = DerivConnectPayload(),
    settings: Settings = Depends(get_settings),
    client: DerivWebSocketClient = Depends(get_deriv_client),
    collector: TickCollector = Depends(get_tick_collector),
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> dict:
    """Inicia a sessão WebSocket com a Deriv em conta virtual DEMO."""
    token_to_use = payload.token or client.demo_token or settings.deriv_demo_token
    if not token_to_use or token_to_use == "seu_token_demo_aqui":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token DEMO não fornecido e não configurado no ambiente (.env).",
        )

    client.demo_token = token_to_use

    try:
        # 1. Conecta ao WebSocket se necessário
        if not client.is_connected:
            await client.connect()

        # 2. Autentica com validação de salvaguarda virtual
        auth_info = await client.authorize(token=token_to_use)

        # 3. Assina o feed de ticks
        target_symbol = payload.symbol or settings.deriv_default_symbol
        await client.subscribe_ticks(target_symbol)

        # 4. Atualiza o saldo inicial no RiskManager
        if auth_info.balance > 0:
            risk_manager.balance_usd = auth_info.balance

        logger.info(
            "✅ Conexão e autorização DEMO concluídas com sucesso. Conta: %s | Saldo: US$ %.2f",
            auth_info.loginid,
            auth_info.balance,
        )

        return {
            "success": True,
            "state": client.state.value,
            "is_authorized": True,
            "loginid": auth_info.loginid,
            "balance": auth_info.balance,
            "currency": auth_info.currency,
            "subscribed_symbol": target_symbol,
        }
    except TraderSecurityError as sec_err:
        logger.critical("🚨 Bloqueio de segurança na autorização: %s", sec_err)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(sec_err),
        ) from sec_err
    except Exception as exc:
        logger.error("Falha ao conectar com Deriv: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha de conexão com a Deriv API: {exc}",
        ) from exc


@router.post("/disconnect", summary="Desconecta a sessão da Deriv")
async def disconnect_deriv(
    client: DerivWebSocketClient = Depends(get_deriv_client),
) -> dict:
    """Encerra a conexão WebSocket com a Deriv."""
    await client.disconnect()
    return {
        "success": True,
        "state": client.state.value,
        "is_connected": False,
        "is_authorized": False,
    }
