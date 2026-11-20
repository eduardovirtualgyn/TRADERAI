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
from backend.app.core.errors import (
    DerivApiError,
    DerivAuthError,
    DerivConfigError,
    DerivConnectionError,
    DerivOperationalError,
    TraderSecurityError,
)
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
    is_connected = client.is_connected

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
        "is_simulated": client.is_simulated,
        "session_mode": client.session_mode,
        "trading_channel": client.trading_channel,
        "last_error": client.last_error,
        "app_id": client.app_id,
        "ws_url": client.redacted_endpoint,
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
    """Inicia a sessão WebSocket com a Deriv em conta virtual DEMO com tratamento estruturado de erros."""
    token_to_use = payload.token or client.demo_token or settings.deriv_demo_token
    if not token_to_use or token_to_use == "seu_token_demo_aqui":
        err_cfg = DerivConfigError(
            message="Token de autorização não fornecido.",
            detail="Token DEMO não fornecido e não configurado no ambiente (.env).",
            code="MISSING_TOKEN",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_cfg.to_dict(),
        )

    client.demo_token = token_to_use
    target_symbol = payload.symbol or settings.deriv_default_symbol
    is_pat = str(token_to_use).startswith("pat_")

    # Token legado precisa do handshake v3 antes do authorize.
    # PAT autentica por REST e abre ele mesmo o WebSocket /ws/demo?otp=...
    if not is_pat and not client.is_connected:
        try:
            await client.connect()
        except DerivConnectionError as conn_err:
            logger.error("Falha de conectividade WebSocket com Deriv: %s", conn_err.detail)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=conn_err.to_dict(),
            ) from conn_err
        except Exception as exc:
            logger.error("Erro inesperado no handshake WebSocket com Deriv: %s", exc)
            fallback_err = DerivConnectionError(
                message="Não foi possível estabelecer conexão com a Deriv API.",
                detail=f"Falha de conexão com a Deriv: {exc}",
                code="WS_CONNECTION_FAILED",
                http_status=520,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=fallback_err.to_dict(),
            ) from exc

    # Autenticação da Conta DEMO (antes de assinar ticks: a sessão de trade é o socket demo)
    try:
        auth_info = await client.authorize(token=token_to_use)
    except TraderSecurityError as sec_err:
        logger.critical("🚨 Salvaguarda de segurança violada: %s", sec_err)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error_type": "Violação de Segurança",
                "code": "SECURITY_REAL_ACCOUNT_BLOCKED",
                "message": "Operação bloqueada por salvaguarda de segurança.",
                "detail": str(sec_err),
                "http_status": 403,
                "stage": "AUTHORIZATION",
            },
        ) from sec_err
    except DerivAuthError as auth_err:
        logger.warning("Falha na autenticação do token: %s", auth_err.detail)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_err.to_dict(),
        ) from auth_err
    except Exception as exc:
        logger.error("Erro inesperado na autorização: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error_type": "Falha de autenticação",
                "code": "AUTH_UNKNOWN_ERROR",
                "message": "Falha ao validar credenciais da conta na Deriv.",
                "detail": str(exc),
                "http_status": 401,
                "stage": "AUTHORIZATION",
            },
        ) from exc

    if client.is_simulated:
        logger.warning(
            "Sessão SIMULADOR opt-in. Ticks da Deriv não serão assinados e nenhuma ordem sai da máquina."
        )
    else:
        try:
            await client.subscribe_ticks(target_symbol)
        except Exception as exc:
            client.last_error = f"Autenticado, mas falha ao assinar ticks de {target_symbol}: {exc}"
            logger.error(client.last_error)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "success": False,
                    "error_type": "Erro operacional",
                    "code": "SUBSCRIBE_FAILED",
                    "message": f"Falha ao assinar ticks de {target_symbol}.",
                    "detail": str(exc),
                    "http_status": 502,
                    "stage": "MARKET_DATA",
                },
            ) from exc

    if auth_info and auth_info.balance > 0:
        risk_manager.balance_usd = auth_info.balance

    logger.info(
        "Autorização concluída. Modo: %s | Conta: %s | Canal: %s | Saldo: US$ %.2f",
        client.session_mode,
        auth_info.loginid,
        client.trading_channel,
        auth_info.balance,
    )

    return {
        "success": True,
        "state": client.state.value,
        "is_authorized": client.is_authorized,
        "is_simulated": client.is_simulated,
        "session_mode": client.session_mode,
        "trading_channel": client.trading_channel,
        "last_error": client.last_error,
        "loginid": auth_info.loginid,
        "balance": auth_info.balance,
        "currency": auth_info.currency,
        "subscribed_symbol": None if client.is_simulated else target_symbol,
    }


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


class SetBalancePayload(BaseModel):
    balance: float = Field(default=100.0, gt=0, le=100000.0, description="Novo saldo DEMO em USD")


@router.post("/balance", summary="Define o saldo da conta DEMO manualmente")
def set_demo_balance(
    payload: SetBalancePayload,
    client: DerivWebSocketClient = Depends(get_deriv_client),
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> dict:
    """Atualiza o saldo do simulador opt-in. Conta demo recusa este atalho."""
    try:
        new_bal = client.set_balance(payload.balance)
    except DerivOperationalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.to_dict()) from exc
    risk_manager.balance_usd = new_bal
    logger.info("Saldo DEMO atualizado manualmente para US$ %.2f", new_bal)
    return {
        "success": True,
        "balance": new_bal,
        "message": f"Saldo DEMO atualizado para US$ {new_bal:.2f}",
    }
