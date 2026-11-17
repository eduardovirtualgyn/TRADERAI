"""Testes unitários e de integração do Módulo 10: Livro-Razão e Auditoria (AuditLedger)."""

import json
from unittest.mock import MagicMock
import pytest

from backend.app.modules.audit_logger.ledger import AuditLedger
from backend.app.modules.audit_logger.models import AuditRecord
from backend.app.modules.contract_executor.executor import ContractExecutor
from backend.app.modules.contract_executor.models import (
    ContractStatus,
    ExecutionResult,
    OrderRequest,
)
from backend.app.modules.deriv_client.models import ContractBuyResult, ProposalData
from backend.app.modules.risk_manager.risk_rules import RiskManager
from backend.app.api.v1.audit import (
    get_audit_logs,
    get_audit_metrics,
    verify_ledger_integrity,
    export_csv,
    export_json,
)


def run_coro(coro):
    """Helper para execução de corrotina em ambiente Windows restrito."""
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value
    raise RuntimeError("Corrotina suspendeu.")


def test_audit_ledger_record_and_hash_chain():
    """Valida encadeamento sequencial criptográfico com hashes SHA-256."""
    ledger = AuditLedger()
    assert ledger.last_hash == "0" * 64

    rec1 = ledger.record_event(
        event_type="TRADE_EXECUTION",
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.00,
        payout=1.95,
        status="BUY_SUBMITTED",
        strategy_name="markov_edge",
    )
    assert rec1.record_id == "REC-000001"
    assert rec1.prev_hash == "0" * 64
    assert len(rec1.record_hash) == 64
    assert ledger.last_hash == rec1.record_hash

    rec2 = ledger.record_event(
        event_type="SETTLEMENT_WIN",
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.00,
        payout=1.95,
        net_pnl=0.95,
        status="WON",
        strategy_name="markov_edge",
    )
    assert rec2.record_id == "REC-000002"
    assert rec2.prev_hash == rec1.record_hash
    assert ledger.last_hash == rec2.record_hash


def test_audit_ledger_integrity_verification():
    """Confirma que o ledger íntegro passa no teste criptográfico."""
    ledger = AuditLedger()
    for i in range(5):
        ledger.record_event(
            event_type="INFO",
            status=f"STEP_{i}",
            stake=float(i),
        )

    assert ledger.verify_integrity() is True


def test_audit_ledger_tampering_detection():
    """Garante que qualquer alteração maliciosa posterior invalida a cadeia."""
    ledger = AuditLedger()
    ledger.record_event(event_type="TRADE", status="WON", net_pnl=10.0)
    ledger.record_event(event_type="TRADE", status="LOST", net_pnl=-5.0)
    assert ledger.verify_integrity() is True

    # Tentativa de adulteração retroativa: alterar o PnL de um registro
    tampered_record = ledger._records[0]
    # Cria uma nova instância alterada na mesma posição
    adulterated = AuditRecord(
        record_id=tampered_record.record_id,
        timestamp=tampered_record.timestamp,
        event_type=tampered_record.event_type,
        symbol=tampered_record.symbol,
        contract_type=tampered_record.contract_type,
        stake=tampered_record.stake,
        payout=tampered_record.payout,
        net_pnl=999.0,  # Valor fraudulento alterado!
        status=tampered_record.status,
        strategy_name=tampered_record.strategy_name,
        prev_hash=tampered_record.prev_hash,
        record_hash=tampered_record.record_hash,  # Hash antigo que agora não bate mais
    )
    ledger._records[0] = adulterated

    # A verificação criptográfica DEVE detectar a fraude
    assert ledger.verify_integrity() is False


def test_audit_ledger_metrics_calculation():
    """Valida métricas agregadas de performance financeira e rejeições."""
    ledger = AuditLedger()

    # 1 rejeição por matemática
    ledger.record_event(event_type="ORDER_REJECTION", status=ContractStatus.REJECTED_BY_MATH.value)
    # 1 rejeição por risco
    ledger.record_event(event_type="ORDER_REJECTION", status=ContractStatus.REJECTED_BY_RISK.value)

    # 3 vitórias de $0.95
    for _ in range(3):
        ledger.record_event(
            event_type="SETTLEMENT_WIN",
            status=ContractStatus.WON.value,
            stake=1.00,
            payout=1.95,
            net_pnl=0.95,
        )

    # 1 derrota de -$1.00
    ledger.record_event(
        event_type="SETTLEMENT_LOSS",
        status=ContractStatus.LOST.value,
        stake=1.00,
        payout=1.95,
        net_pnl=-1.00,
    )

    metrics = ledger.compute_metrics()
    assert metrics.total_records == 6
    assert metrics.rejected_by_math == 1
    assert metrics.rejected_by_risk == 1
    assert metrics.wins == 3
    assert metrics.losses == 1
    assert metrics.settled_trades == 4
    assert metrics.win_rate == 0.75  # 3/4
    assert metrics.gross_profit_usd == 2.85  # 3 * 0.95
    assert metrics.gross_loss_usd == 1.00
    assert metrics.net_pnl_usd == 1.85
    assert metrics.profit_factor == 2.85
    assert metrics.ledger_integrity_verified is True


def test_audit_ledger_export_csv_and_json():
    """Valida formatos de exportação em CSV e JSON."""
    ledger = AuditLedger()
    ledger.record_event(
        event_type="SETTLEMENT_WIN",
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=2.00,
        payout=3.90,
        net_pnl=1.90,
        status="WON",
        strategy_name="ensemble",
        contract_id="112233",
    )

    # Teste CSV
    csv_str = ledger.export_csv()
    assert "record_id,timestamp,event_type" in csv_str
    assert "DIGITEVEN" in csv_str
    assert "112233" in csv_str

    # Teste JSON
    json_str = ledger.export_json()
    parsed = json.loads(json_str)
    assert len(parsed) == 1
    assert parsed[0]["contract_id"] == "112233"
    assert parsed[0]["net_pnl"] == 1.90


def test_audit_ledger_integration_with_contract_executor(risk_manager: RiskManager):
    """Garante que o executor alimenta automaticamente o ledger via callback."""
    ledger = AuditLedger()

    # Mock do DerivClient
    mock_client = MagicMock()
    mock_client.is_authorized = True

    async def fake_proposal(*args, **kwargs):
        return ProposalData(
            proposal_id="prop_aud_1",
            ask_price=1.00,
            payout=1.95,
            spot=100.0,
            spot_time=1700000000,
            contract_type="DIGITEVEN",
            symbol="R_100",
            net_payout=0.95,
            payout_ratio=1.95,
        )

    async def fake_buy(*args, **kwargs):
        return ContractBuyResult(
            contract_id="cid_aud_99",
            transaction_id="tx_1",
            buy_price=1.00,
            payout=1.95,
            balance_after=1050.0,
            shortcode="DIGITEVEN",
            start_time=1700000000,
        )

    mock_client.get_proposal = MagicMock(side_effect=fake_proposal)
    mock_client.buy = MagicMock(side_effect=fake_buy)

    executor = ContractExecutor(
        deriv_client=mock_client,
        risk_manager=risk_manager,
        audit_callback=ledger.record_execution_result,
    )

    order_req = OrderRequest(
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.00,
        strategy_name="test_audit",
        estimated_probability=0.58,
        wilson_lower_bound=0.53,
    )

    # 1. Executa compra -> deve registrar TRADE_EXECUTION no ledger
    run_coro(executor.execute_order(order_req))
    assert len(ledger._records) == 1
    assert ledger._records[0].event_type == "TRADE_EXECUTION"
    assert ledger._records[0].contract_id == "cid_aud_99"

    # 2. Liquida -> deve registrar SETTLEMENT_WIN no ledger
    executor.settle_contract(contract_id="cid_aud_99", won=True, exit_digit=2)
    assert len(ledger._records) == 2
    assert ledger._records[1].event_type == "SETTLEMENT_WIN"
    assert ledger._records[1].net_pnl == 0.95

    # 3. Integridade do ledger com eventos do executor
    assert ledger.verify_integrity() is True


def test_audit_api_endpoints():
    """Testa diretamente as funções dos endpoints REST de auditoria."""
    ledger = AuditLedger()
    ledger.record_event(event_type="SETTLEMENT_WIN", status="WON", net_pnl=1.00)

    # Logs
    logs = get_audit_logs(limit=10, ledger=ledger)
    assert len(logs) == 1

    # Metrics
    metrics = get_audit_metrics(ledger=ledger)
    assert metrics.wins == 1

    # Verify
    verify_res = verify_ledger_integrity(ledger=ledger)
    assert verify_res["valid"] is True

    # Export CSV
    csv_resp = export_csv(ledger=ledger)
    assert "record_id" in csv_resp.body.decode("utf-8")

    # Export JSON
    json_resp = export_json(ledger=ledger)
    assert "record_hash" in json_resp.body.decode("utf-8")
