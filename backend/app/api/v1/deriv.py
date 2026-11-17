"""Rotas da API para monitoramento da integração com a Deriv."""

from fastapi import APIRouter, Depends
from backend.app.api.deps import get_deriv_client
from backend.app.core.config import Settings, get_settings
from backend.app.modules.deriv_client.client import DerivWebSocketClient

router = APIRouter(prefix="/deriv", tags=["Deriv WebSocket"])


@router.get("/status", summary="Consulta o estado da conexão com a Deriv API")
def get_deriv_status(
    settings: Settings = Depends(get_settings),
    client: DerivWebSocketClient = Depends(get_deriv_client),
) -> dict:
    """Retorna o estado da conexão, símbolos vigentes e informações da conta DEMO."""
    auth_info = client.auth_info
    return {
        "connection_state": client.state.value,
        "is_authorized": client.is_authorized,
        "app_id": client.app_id,
        "ws_url": client.ws_url,
        "default_symbol": settings.deriv_default_symbol,
        "auth": {
            "is_virtual": auth_info.is_virtual if auth_info else False,
            "loginid": auth_info.loginid if auth_info else None,
            "currency": auth_info.currency if auth_info else None,
            "balance": auth_info.balance if auth_info else None,
        } if auth_info else None,
    }
