"""Autenticação do operador da API.

O token não é o PAT da Deriv. Ele só destranca o painel. A comparação é
em tempo constante e não usa o valor cru, para o tamanho do segredo não
vazar por exceção nem por tempo.
"""

import hashlib
import hmac
from typing import Optional

from backend.app.core.config import Settings
from backend.app.core.errors import TraderSecurityError

_PLACEHOLDERS = {
    "",
    "changeme",
    "change-me",
    "seu_token_aqui",
    "seu_token_de_operador",
}


def token_is_configured(value: Optional[str]) -> bool:
    cleaned = (value or "").strip()
    return cleaned.lower() not in _PLACEHOLDERS


def tokens_match(presented: str, expected: str) -> bool:
    """Compara dois segredos sem vazar tamanho nem conteúdo no tempo da resposta."""
    presented_digest = hashlib.sha256(presented.encode("utf-8")).digest()
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(presented_digest, expected_digest)


def ensure_production_operator_token(settings: Settings) -> None:
    """Em produção a API não sobe sem TRADER_API_TOKEN. Assim ela não fica aberta."""
    if settings.app_env.strip().lower() != "production":
        return
    if token_is_configured(settings.trader_api_token):
        return
    raise TraderSecurityError(
        "TRADER_API_TOKEN é obrigatório quando APP_ENV=production. "
        "Sem ele o backend não inicia, para a API não ficar publicamente gravável."
    )


def parse_cors_origins(raw: Optional[str]) -> list[str]:
    """Lista de origens. `*` é descartado: não combinamos curinga com credencial."""
    origins: list[str] = []
    for part in (raw or "").split(","):
        item = part.strip().rstrip("/")
        if not item or item == "*":
            continue
        origins.append(item)
    return origins
