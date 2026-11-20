"""A API não pode ser gravada sem o token do operador."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import get_settings
from backend.app.core.errors import TraderSecurityError
from backend.app.core.operator_auth import (
    ensure_production_operator_token,
    parse_cors_origins,
    tokens_match,
)
from backend.app.main import app, create_app


OPERATOR = "test-operator-token"
AUTH = {"Authorization": f"Bearer {OPERATOR}"}


@pytest.fixture
def operator_token(monkeypatch):
    monkeypatch.setenv("TRADER_API_TOKEN", OPERATOR)
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def test_tokens_match_is_exact_and_ignores_lookalikes():
    assert tokens_match("mesmo-segredo", "mesmo-segredo") is True
    assert tokens_match("mesmo-segredo", "mesmo-segredo ") is False
    assert tokens_match("curto", "curto-porem-diferente") is False
    assert tokens_match("", "segredo") is False


def test_cors_allowlist_drops_wildcard():
    assert parse_cors_origins("https://bot.sslip.io, *, https://painel.exemplo") == [
        "https://bot.sslip.io",
        "https://painel.exemplo",
    ]
    assert parse_cors_origins("*") == []
    assert parse_cors_origins("") == []


def test_production_refuses_to_start_without_operator_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("TRADER_API_TOKEN", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(TraderSecurityError, match="TRADER_API_TOKEN"):
            with TestClient(app):
                pass
    finally:
        get_settings.cache_clear()


def test_production_refuses_placeholder_operator_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TRADER_API_TOKEN", "seu_token_de_operador")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        with pytest.raises(TraderSecurityError, match="TRADER_API_TOKEN"):
            ensure_production_operator_token(settings)
    finally:
        get_settings.cache_clear()


def test_unauthenticated_mutation_and_status_are_rejected(operator_token):
    client = TestClient(create_app())

    denied = [
        ("get", "/api/v1/auto-trader/status", None),
        ("get", "/api/v1/deriv/status", None),
        ("get", "/api/v1/risk/status", None),
        ("post", "/api/v1/auto-trader/toggle", {"enabled": True}),
        ("post", "/api/v1/risk/kill-switch", {"active": True, "reason": "teste"}),
        ("post", "/api/v1/deriv/connect", {"symbol": "R_100"}),
        ("post", "/api/v1/deriv/disconnect", {}),
        ("post", "/api/v1/executor/panic-stop", {"reason": "teste"}),
    ]
    for method, path, body in denied:
        kwargs = {"headers": {"Authorization": "Bearer errado"}}
        if body is not None and method != "get":
            kwargs["json"] = body
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, path
        assert response.json()["detail"]["code"] == "OPERATOR_UNAUTHORIZED"

    missing = client.post("/api/v1/auto-trader/toggle", json={"enabled": False})
    assert missing.status_code == 401

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"


def test_authenticated_mutation_succeeds(operator_token):
    client = TestClient(create_app())

    status = client.get("/api/v1/auto-trader/status", headers=AUTH)
    assert status.status_code == 200

    toggled = client.post("/api/v1/auto-trader/toggle", json={"enabled": True}, headers=AUTH)
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is True

    armed = client.post(
        "/api/v1/risk/kill-switch",
        json={"active": True, "reason": "teste do operador"},
        headers=AUTH,
    )
    assert armed.status_code == 200
    assert armed.json()["kill_switch_active"] is True

    disarmed = client.post(
        "/api/v1/risk/kill-switch",
        json={"active": False, "reason": "retomada"},
        headers=AUTH,
    )
    assert disarmed.status_code == 200
    assert disarmed.json()["kill_switch_active"] is False

    # Passou da trava do operador. Sem PAT da Deriv a conexão é recusada à parte.
    connect = client.post("/api/v1/deriv/connect", json={"symbol": "R_100"}, headers=AUTH)
    assert connect.status_code != 401


def test_compose_keeps_backend_off_the_host_and_points_the_proxy_at_the_service():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    route = (root / "frontend/src/server/backendProxy.ts").read_text(encoding="utf-8")

    assert "8001:8000" not in compose
    assert "BACKEND_INTERNAL_URL=http://backend:8000/api/v1" in compose
    assert "TRADER_API_TOKEN=${TRADER_API_TOKEN:-}" in compose
    assert "http://backend:8000/api/v1" in route
    assert 'const API_BASE = "/api/backend"' in (root / "frontend/src/services/api.ts").read_text(encoding="utf-8")
