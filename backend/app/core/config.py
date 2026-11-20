"""Módulo de configurações e gerenciamento de variáveis de ambiente.

Aplica a salvaguarda estrita de operação exclusiva em conta DEMO.
"""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from backend.app.core.errors import TraderSecurityError


def load_project_dotenv(path: Optional[Path] = None, *, force: bool = False) -> None:
    """Carrega o `.env` da raiz. O uvicorn não faz isso sozinho.

    Durante o pytest o carregamento automático fica desligado para um token
    real presente no `.env` local não vazar para a suíte. `force=True` lê um
    arquivo explícito.
    """
    # pytest já está carregado na coleta, antes de PYTEST_CURRENT_TEST existir.
    if not force and ("pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST")):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if path is not None:
        load_dotenv(path, override=False)
        return
    root = Path(__file__).resolve().parents[3]
    load_dotenv(root / ".env", override=False)
    load_dotenv(override=False)


class Settings(BaseModel):
    """Configurações da aplicação validadas pelo Pydantic."""

    # Segurança e Conta (DEMO ONLY)
    app_name: str = Field(default="ODD_EVEN_AI_TRADER", description="Nome da aplicação")
    app_env: str = Field(default="development", description="Ambiente de execução")
    trader_api_token: Optional[str] = Field(
        default=None,
        description="Segredo do operador. Obrigatório em produção. Não é o token da Deriv.",
    )
    cors_allow_origins: str = Field(
        default="",
        description="Origens CORS separadas por vírgula. `*` é ignorado.",
    )
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
        description="WebSocket de mercado. A negociação PAT usa o URL demo devolvido pelo OTP.",
    )
    deriv_rest_base_url: str = Field(
        default="https://api.derivws.com",
        description="Base REST da Options API (contas e OTP). Sem barra no final.",
    )
    deriv_simulator: bool = Field(
        default=False,
        description="Simulador local opt-in. Nunca é fallback de falha de autenticação.",
    )
    deriv_app_id: str = Field(
        default="",
        description="App ID do aplicativo que emitiu o PAT. Pode ser alfanumérico.",
    )
    deriv_demo_token: Optional[str] = Field(
        default=None,
        description="Token de autorização da conta DEMO (VRTC)",
    )
    deriv_default_symbol: str = Field(
        default="R_100",
        description="Símbolo sintético padrão (ex: Volatility 100 Index)",
    )
    deriv_demo_initial_balance: float = Field(
        default=100.00,
        description="Saldo inicial do simulador opt-in. Na conta demo o saldo vem da Deriv.",
    )
    auto_trader_stake: float = Field(
        default=1.0,
        description="Stake padrão do Auto-Trader em USD",
    )

    # Parâmetros de Gestão de Risco
    risk_max_stake_usd: float = Field(
        default=5.00,
        description="Teto máximo em USD por operação",
    )
    risk_max_stake_percent: float = Field(
        default=0.05,
        description="Teto proporcional por operação (padrão 5% para um stake de US$ 1 caber numa demo pequena)",
    )
    risk_min_operable_stake_usd: float = Field(
        default=1.0,
        description="Piso operável: o teto percentual não pode cair abaixo deste valor se a banca cobrir",
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

    @field_validator("deriv_app_id", mode="before")
    @classmethod
    def validate_deriv_app_id(cls, v: object) -> str:
        return normalize_app_id(v)

    @field_validator("deriv_ws_url")
    @classmethod
    def validate_deriv_ws_url(cls, v: str) -> str:
        if "/ws/real" in v.lower():
            raise TraderSecurityError(
                "VIOLAÇÃO DE SEGURANÇA: DERIV_WS_URL não pode apontar para o canal de conta REAL (/ws/real)."
            )
        return v

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


def normalize_app_id(value: Optional[object]) -> str:
    """App ID da Deriv como texto. O portal novo emite IDs alfanuméricos.

    Remove espaços e aspas que o compose ou um `.env` às vezes incluem no valor.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1].strip()
    return text.strip().strip("'\"")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


def load_settings_from_env() -> Settings:
    """Carrega as configurações a partir das variáveis de ambiente e do `.env`."""
    load_project_dotenv()
    account_mode = os.getenv("ACCOUNT_MODE", "DEMO")
    allow_real = _env_flag("ALLOW_REAL_ACCOUNT", False)

    raw_kwargs = {
        "app_name": os.getenv("APP_NAME", "ODD_EVEN_AI_TRADER"),
        "app_env": os.getenv("APP_ENV", "development"),
        "trader_api_token": os.getenv("TRADER_API_TOKEN"),
        "cors_allow_origins": os.getenv("CORS_ALLOW_ORIGINS", ""),
        "account_mode": account_mode,
        "allow_real_account": allow_real,
        "deriv_ws_url": os.getenv(
            "DERIV_WS_URL",
            "wss://api.derivws.com/trading/v1/options/ws/public",
        ),
        "deriv_rest_base_url": os.getenv("DERIV_REST_BASE_URL", "https://api.derivws.com"),
        "deriv_app_id": normalize_app_id(os.getenv("DERIV_APP_ID", "")),
        "deriv_demo_token": os.getenv("DERIV_DEMO_TOKEN"),
        "deriv_default_symbol": os.getenv("DERIV_DEFAULT_SYMBOL", "R_100"),
        "deriv_simulator": _env_flag("DERIV_SIMULATOR", False),
        "auto_trader_stake": float(os.getenv("AUTO_TRADER_STAKE", "1.0")),
        "risk_max_stake_usd": float(os.getenv("RISK_MAX_STAKE_USD", "5.00")),
        "risk_max_stake_percent": float(os.getenv("RISK_MAX_STAKE_PERCENT", "0.05")),
        "risk_min_operable_stake_usd": float(os.getenv("RISK_MIN_OPERABLE_STAKE_USD", "1.00")),
        "risk_max_consecutive_losses": int(os.getenv("RISK_MAX_CONSECUTIVE_LOSSES", "3")),
        "risk_max_daily_loss_usd": float(os.getenv("RISK_MAX_DAILY_LOSS_USD", "25.00")),
        "risk_kill_switch_active": _env_flag("RISK_KILL_SWITCH_ACTIVE", False),
        "risk_ban_martingale": _env_flag("RISK_BAN_MARTINGALE", True),
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
