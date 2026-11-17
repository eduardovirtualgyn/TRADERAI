"""Testes unitários e de integração das rotas de Health Check e API de Risco."""

from backend.app.api.v1.health import health_check
from backend.app.api.v1.risk import (
    KillSwitchPayload,
    RiskEvaluationPayload,
    evaluate_risk,
    get_risk_status,
    toggle_kill_switch,
)
from backend.app.core.config import Settings
from backend.app.main import app
from backend.app.modules.risk_manager.risk_rules import RiskManager


def test_root_endpoint_metadata():
    """Valida metadata da rota raiz."""
    route_paths = [getattr(r, "path", None) for r in app.routes if hasattr(r, "path")]
    assert "/" in route_paths
    assert "/docs" in route_paths
    assert "/openapi.json" in route_paths


def test_health_check_endpoint_guarantees(risk_manager: RiskManager):
    """Garante que o health check expõe status operacional e garantias de segurança."""
    settings = Settings()
    data = health_check(settings=settings, risk_manager=risk_manager)

    assert data["status"] == "healthy"
    assert data["app_name"] == "ODD_EVEN_AI_TRADER"
    assert data["account_mode"] == "DEMO"
    assert data["security_locks"]["demo_only"] is True
    assert data["security_locks"]["real_account_blocked"] is True
    assert data["security_locks"]["martingale_banned"] is True
    assert data["risk_status"]["kill_switch_active"] is False


def test_risk_status_and_kill_switch_actions(risk_manager: RiskManager):
    """Testa consulta de status e desarme/acionamento do Kill Switch."""
    # 1. Consulta inicial
    status_data = get_risk_status(risk_manager=risk_manager)
    assert status_data["ban_martingale"] is True
    assert status_data["kill_switch_active"] is False
    assert status_data["balance_usd"] == 1000.00

    # 2. Ativação manual do Kill Switch
    arm_res = toggle_kill_switch(
        payload=KillSwitchPayload(active=True, reason="Teste de interrupção manual"),
        risk_manager=risk_manager,
    )
    assert arm_res["success"] is True
    assert arm_res["kill_switch_active"] is True
    assert "Teste de interrupção manual" in arm_res["reason"]

    # 3. Avaliação de trade com Kill Switch ativo deve recusar
    eval_blocked = evaluate_risk(
        payload=RiskEvaluationPayload(stake=1.00, net_ev_ratio=0.05),
        risk_manager=risk_manager,
    )
    assert eval_blocked["approved"] is False
    assert "Kill Switch ATIVO" in eval_blocked["reason"]

    # 4. Desarme manual do Kill Switch
    disarm_res = toggle_kill_switch(
        payload=KillSwitchPayload(active=False, reason="Retomada das operações"),
        risk_manager=risk_manager,
    )
    assert disarm_res["success"] is True
    assert disarm_res["kill_switch_active"] is False

    # 5. Avaliação de trade agora deve ser aprovada
    eval_ok = evaluate_risk(
        payload=RiskEvaluationPayload(stake=1.00, net_ev_ratio=0.05),
        risk_manager=risk_manager,
    )
    assert eval_ok["approved"] is True
    assert eval_ok["reason"] is None


def test_deriv_status_endpoint():
    """Valida retorno do endpoint de monitoramento da Deriv."""
    from backend.app.api.v1.deriv import get_deriv_status
    from backend.app.modules.deriv_client.client import DerivWebSocketClient

    client = DerivWebSocketClient(ws_url="wss://ws.derivws.com/websockets/v3", app_id=1089)
    status_payload = get_deriv_status(settings=Settings(), client=client)

    assert status_payload["connection_state"] == "DISCONNECTED"
    assert status_payload["is_authorized"] is False
    assert status_payload["app_id"] == 1089
    assert status_payload["default_symbol"] == "R_100"
