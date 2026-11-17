"""Fixtures globais do pytest para o backend."""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.modules.risk_manager.risk_rules import RiskManager


@pytest.fixture
def client():
    """Retorna um cliente de teste da API FastAPI."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def risk_manager():
    """Retorna uma nova instância isolada de RiskManager para testes."""
    return RiskManager(
        max_stake_usd=5.00,
        max_stake_percent=0.01,
        max_consecutive_losses=3,
        max_daily_loss_usd=25.00,
        ban_martingale=True,
        initial_balance_usd=1000.00,
        kill_switch_initially_active=False,
    )
