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


def test_reject_real_account_mode():
    """Garante que qualquer tentativa de configurar ACCOUNT_MODE='REAL' levanta TraderSecurityError."""
    with pytest.raises(TraderSecurityError, match="EXCLUSIVAMENTE em modo 'DEMO'"):
        Settings(account_mode="REAL")


def test_reject_allow_real_account():
    """Garante que allow_real_account=True levanta TraderSecurityError."""
    with pytest.raises(TraderSecurityError, match="'allow_real_account' não pode ser True"):
        Settings(allow_real_account=True)


def test_reject_unban_martingale():
    """Garante que desativar o banimento de Martingale é terminantemente proibido."""
    with pytest.raises(TraderSecurityError, match="Martingale não pode ser habilitado"):
        Settings(risk_ban_martingale=False)
