"""Testes de segurança e validação das configurações."""

import pytest
from backend.app.core.config import Settings
from backend.app.core.errors import TraderSecurityError


def test_default_settings_security():
    """Valida se as configurações padrão impõem conta DEMO e proíbem Martingale."""
    settings = Settings()
    assert settings.account_mode == "DEMO"
    assert settings.allow_real_account is False
    assert settings.risk_ban_martingale is True
    assert settings.risk_max_stake_usd == 5.00
    assert settings.risk_max_stake_percent == 0.05
    assert settings.deriv_simulator is False
    assert "/ws/real" not in settings.deriv_ws_url


def test_reject_real_account_mode():
    """Garante que qualquer tentativa de configurar ACCOUNT_MODE='REAL' levanta TraderSecurityError."""
    with pytest.raises(TraderSecurityError, match="EXCLUSIVAMENTE em modo 'DEMO'"):
        Settings(account_mode="REAL")


def test_reject_allow_real_account():
    """Garante que allow_real_account=True levanta TraderSecurityError."""
    with pytest.raises(TraderSecurityError, match="'allow_real_account' não pode ser True"):
        Settings(allow_real_account=True)


def test_reject_real_websocket_url():
    """DERIV_WS_URL apontando para /ws/real não pode nem subir."""
    with pytest.raises(TraderSecurityError, match="/ws/real"):
        Settings(deriv_ws_url="wss://api.derivws.com/trading/v1/options/ws/real")


def test_dotenv_file_is_applied_to_settings(tmp_path, monkeypatch):
    """Uvicorn não exporta o .env. O carregador do projeto precisa fazer isso."""
    from backend.app.core.config import get_settings, load_project_dotenv, load_settings_from_env

    env_file = tmp_path / ".env"
    env_file.write_text("DERIV_APP_ID=4242\nDERIV_SIMULATOR=false\n", encoding="utf-8")
    monkeypatch.delenv("DERIV_APP_ID", raising=False)
    load_project_dotenv(env_file, force=True)
    get_settings.cache_clear()
    try:
        settings = load_settings_from_env()
        assert settings.deriv_app_id == "4242"
        assert isinstance(settings.deriv_app_id, str)
    finally:
        monkeypatch.delenv("DERIV_APP_ID", raising=False)
        get_settings.cache_clear()


def test_alphanumeric_deriv_app_id_loads_as_text(monkeypatch):
    """O portal novo emite App ID alfanumérico. Isso não pode virar int()."""
    from backend.app.core.config import get_settings, load_settings_from_env

    monkeypatch.setenv("DERIV_APP_ID", "  'AppTest9Kx2nQ7'  ")
    get_settings.cache_clear()
    try:
        settings = load_settings_from_env()
        assert settings.deriv_app_id == "AppTest9Kx2nQ7"
        assert isinstance(settings.deriv_app_id, str)
    finally:
        get_settings.cache_clear()


def test_empty_deriv_app_id_does_not_crash(monkeypatch):
    from backend.app.core.config import get_settings, load_settings_from_env

    monkeypatch.setenv("DERIV_APP_ID", "")
    get_settings.cache_clear()
    try:
        settings = load_settings_from_env()
        assert settings.deriv_app_id == ""
    finally:
        get_settings.cache_clear()


def test_reject_unban_martingale():
    """Garante que desativar o banimento de Martingale é terminantemente proibido."""
    with pytest.raises(TraderSecurityError, match="Martingale não pode ser habilitado"):
        Settings(risk_ban_martingale=False)
