"""Exige o token do operador nas rotas da API, menos o health check."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.app.core.config import get_settings
from backend.app.core.operator_auth import token_is_configured, tokens_match

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _presented_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return (request.headers.get("x-trader-token") or "").strip()


def _unauthorized(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "detail": {
                "success": False,
                "error_type": "Autenticação do operador",
                "code": code,
                "message": message,
                "detail": message,
                "http_status": 401,
                "stage": "OPERATOR_AUTH",
            }
        },
    )


class OperatorAuthMiddleware(BaseHTTPMiddleware):
    """Protege /api/v1. O health público não devolve saldo nem permite ordem."""

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        if not path.startswith("/api/"):
            return await call_next(request)
        if request.method.upper() == "GET" and path == "/api/v1/health":
            return await call_next(request)

        settings = get_settings()
        configured = token_is_configured(settings.trader_api_token)
        if not configured:
            if request.method.upper() in _MUTATING or settings.app_env.strip().lower() == "production":
                return _unauthorized(
                    "OPERATOR_AUTH_REQUIRED",
                    "Mutações desligadas: defina TRADER_API_TOKEN. "
                    "Em produção a API nem deveria ter subido sem esse segredo.",
                )
            return await call_next(request)

        expected = (settings.trader_api_token or "").strip()
        presented = _presented_token(request)
        if not presented or not tokens_match(presented, expected):
            return _unauthorized(
                "OPERATOR_UNAUTHORIZED",
                "Token de operador ausente ou inválido.",
            )
        return await call_next(request)
