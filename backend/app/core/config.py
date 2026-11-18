"""Módulo de configurações e gerenciamento de variáveis de ambiente.

Aplica a salvaguarda estrita de operação exclusiva em conta DEMO.
"""

import os
from functools import lru_cache
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from backend.app.core.errors import TraderSecurityError


class Settings(BaseModel):
    """Configurações da aplicação validadas pelo Pydantic."""

    # Segurança e Conta (DEMO ONLY)
    app_name: str = Field(default="ODD_EVEN_AI_TRADER", description="Nome da aplicação")
    app_env: str = Field(default="development", description="Ambiente de execução")
    account_mode: str = Field(
        default="DEMO",
        description="Modo da conta. OBRIGATÓRIO: 'DEMO'. Conta real terminantemente proibida.",
    )
    allow_real_account: bool = Field(
        default=False,
        description="Flag de bloqueio de conta real. NUNCA deve ser True.",
    )

    # Deriv WebSocket API (Novo endpoint oficial Options API / Public Data)
    deriv_ws_url: str = Field(
        default="wss://api.derivws.com/trading/v1/options/ws/public",
        description="Endpoint oficial da Deriv WebSocket API (Options / Public Data)",
    )
    deriv_app_id: int = Field(
        default=1089,
        description="App ID registrado na Deriv (1089 para testes)",
    )
    deriv_demo_token: Optional[str] = Field(
        default=None,
        description="Token de autorização da conta DEMO (VRTC)",
    )
    deriv_default_symbol: str = Field(
        default="R_100",
        description="Símbolo sintético padrão (ex: Volatility 100 Index)",
    )

    # Parâmetros de Gestão de Risco
    risk_max_stake_usd: float = Field(
        default=5.00,
        description="Teto máximo em USD por operação",
    )
    risk_max_stake_percent: float = Field(
        default=0.01,
        description="Teto máximo proporcional por operação (1% da banca)",
    )
    risk_max_consecutive_losses: int = Field(
        default=3,
        description="Limite de derrotas em sequência antes da pausa preventiva",
    )
    risk_max_daily_loss_usd: float = Field(
        default=25.00,
        description="Drawdown máximo acumulado no dia em USD",
    )
    risk_kill_switch_active: bool = Field(
        default=False,
        description="Estado inicial do Kill Switch",
    )
    risk_ban_martingale: bool = Field(
        default=True,
        description="Proibição de Martingale (imutável)",
    )

    # Parâmetros Quantitativos
    min_acceptable_payout_ratio: float = Field(
        default=1.90,
        description="Multiplicador mínimo de payout (ex: 1.90 = $19.00 de retorno para $10.00 de stake)",
    )
    min_net_ev_ratio: float = Field(
        default=0.01,
        description="Expectativa matemática líquida mínima (+1%)",
    )
    confidence_level: float = Field(
        default=0.95,
        description="Nível de confiança estatística (Wilson score)",
    )
    min_tick_sample_size: int = Field(
        default=500,
        description="Amostra mínima para inferência quantitativa",
    )

    # Persistência
    database_url: str = Field(
        default="postgresql://deriv_user:deriv_pass@localhost:5432/deriv_trader",
        description="URL de conexão PostgreSQL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="URL de conexão Redis",
    )

    @field_validator("account_mode")
    @classmethod
    def validate_account_mode(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if cleaned != "DEMO":
            raise TraderSecurityError(
                f"VIOLAÇÃO DE SEGURANÇA: Modo de conta '{cleaned}' não permitido. "
                "O sistema opera EXCLUSIVAMENTE em modo 'DEMO'."
            )
        return cleaned

    @field_validator("allow_real_account")
    @classmethod
    def validate_allow_real_account(cls, v: bool) -> bool:
        if v is True:
            raise TraderSecurityError(
                "VIOLAÇÃO DE SEGURANÇA: 'allow_real_account' não pode ser True. "
                "A ativação de conta real é terminantemente proibida nesta fase."
            )
        return v

    @field_validator("risk_ban_martingale")
    @classmethod
    def validate_ban_martingale(cls, v: bool) -> bool:
        if v is not True:
            raise TraderSecurityError(
                "VIOLAÇÃO DE SEGURANÇA: Martingale não pode ser habilitado no ODD/EVEN AI TRADER."
            )
        return v


def load_settings_from_env() -> Settings:
    """Carrega as configurações a partir das variáveis de ambiente."""
    account_mode = os.getenv("ACCOUNT_MODE", "DEMO")
    allow_real = os.getenv("ALLOW_REAL_ACCOUNT", "False").lower() in ("true", "1", "yes")

    raw_kwargs = {
        "app_name": os.getenv("APP_NAME", "ODD_EVEN_AI_TRADER"),
        "app_env": os.getenv("APP_ENV", "development"),
        "account_mode": account_mode,
        "allow_real_account": allow_real,
        "deriv_ws_url": os.getenv("DERIV_WS_URL", "wss://ws.derivws.com/websockets/v3"),
        "deriv_app_id": int(os.getenv("DERIV_APP_ID", "1089")),
        "deriv_demo_token": os.getenv("DERIV_DEMO_TOKEN"),
        "deriv_default_symbol": os.getenv("DERIV_DEFAULT_SYMBOL", "R_100"),
        "risk_max_stake_usd": float(os.getenv("RISK_MAX_STAKE_USD", "5.00")),
        "risk_max_stake_percent": float(os.getenv("RISK_MAX_STAKE_PERCENT", "0.01")),
        "risk_max_consecutive_losses": int(os.getenv("RISK_MAX_CONSECUTIVE_LOSSES", "3")),
        "risk_max_daily_loss_usd": float(os.getenv("RISK_MAX_DAILY_LOSS_USD", "25.00")),
        "risk_kill_switch_active": os.getenv("RISK_KILL_SWITCH_ACTIVE", "False").lower() in ("true", "1", "yes"),
        "risk_ban_martingale": os.getenv("RISK_BAN_MARTINGALE", "True").lower() not in ("false", "0", "no"),
        "min_acceptable_payout_ratio": float(os.getenv("MIN_ACCEPTABLE_PAYOUT_RATIO", "1.90")),
        "min_net_ev_ratio": float(os.getenv("MIN_NET_EV_RATIO", "0.01")),
        "confidence_level": float(os.getenv("CONFIDENCE_LEVEL", "0.95")),
        "min_tick_sample_size": int(os.getenv("MIN_TICK_SAMPLE_SIZE", "500")),
        "database_url": os.getenv("DATABASE_URL", "postgresql://deriv_user:deriv_pass@localhost:5432/deriv_trader"),
        "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    }

    return Settings(**raw_kwargs)


@lru_cache()
def get_settings() -> Settings:
    """Retorna uma instância singleton em cache das configurações."""
    return load_settings_from_env()
