"""Testes unitários e de integração do Módulo 9: Executor de Contratos da Deriv."""

from unittest.mock import MagicMock
import pytest

from backend.app.modules.contract_executor.executor import ContractExecutor
from backend.app.modules.contract_executor.models import (
    ContractStatus,
    OrderRequest,
)
from backend.app.modules.deriv_client.models import ContractBuyResult, ProposalData
from backend.app.modules.risk_manager.risk_rules import RiskManager
from backend.app.api.v1.executor import (
    execute_contract,
    trigger_panic_stop,
    list_active_contracts,
    get_execution_history,
    settle_contract,
    PanicStopPayload,
    SettleContractPayload,
)


def run_coro(coro):
    """Executa uma corrotina assíncrona sem instanciar event loops de socket no sandbox."""
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value
    raise RuntimeError("A corrotina suspendeu esperando I/O não mockado.")


@pytest.fixture
def mock_deriv_client():
    """Cria um mock de DerivWebSocketClient com respostas oficiais configuradas."""
    client = MagicMock()
    client.is_authorized = True

    async def fake_get_proposal(*args, **kwargs):
        amt = kwargs.get("amount", args[2] if len(args) > 2 else 1.0)
        payout = float(amt) * 1.95
        return ProposalData(
            proposal_id="prop-test-12345",
            ask_price=float(amt),
            payout=payout,
            spot=1050.25,
            spot_time=1700000000,
            contract_type="DIGITEVEN",
            symbol="R_100",
            net_payout=payout - float(amt),
            payout_ratio=1.95,
        )

    client.get_proposal = MagicMock(side_effect=fake_get_proposal)

    # Mock de buy
    buy_result = ContractBuyResult(
        contract_id="987654321",
        transaction_id="1234567",
        buy_price=1.00,
        payout=1.95,
        balance_after=1099.00,
        shortcode="DIGITEVEN_R_100_1T",
        start_time=1700000000,
    )

    async def fake_buy(*args, **kwargs):
        return buy_result

    client.buy = MagicMock(side_effect=fake_buy)
    return client


@pytest.fixture
def executor(mock_deriv_client, risk_manager: RiskManager):
    """Instância do ContractExecutor com dependências mockadas."""
    return ContractExecutor(
        deriv_client=mock_deriv_client,
        risk_manager=risk_manager,
    )


def test_executor_successful_trade_pipeline(executor: ContractExecutor, mock_deriv_client):
    """Valida o ciclo completo de uma execução bem-sucedida e posterior vitória."""
    order_req = OrderRequest(
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.00,
        strategy_name="markov_edge",
        estimated_probability=0.58,
        wilson_lower_bound=0.53,  # > P_be (51.28%)
    )

    result = run_coro(executor.execute_order(order_req))
    assert result.success is True
    assert result.status == ContractStatus.BUY_SUBMITTED
    assert result.contract_id == "987654321"
    assert result.payout == 1.95
    assert len(executor.active_contracts) == 1

    # Chamadas de rede verificadas
    mock_deriv_client.get_proposal.assert_called_once()
    mock_deriv_client.buy.assert_called_once_with(
        proposal_id="prop-test-12345",
        price=1.00,
    )

    # Liquidação como Vencedor
    settled = executor.settle_contract(contract_id="987654321", won=True, exit_digit=4)
    assert settled.status == ContractStatus.WON
    assert settled.net_pnl == 0.95
    assert len(executor.active_contracts) == 0
    assert len(executor.history) == 1
    assert executor.risk_manager.balance_usd == 1000.95


def test_executor_settle_contract_loss(executor: ContractExecutor):
    """Valida o impacto no saldo e streak após liquidação como derrota."""
    order_req = OrderRequest(
        symbol="R_100",
        contract_type="DIGITODD",
        stake=1.00,
        strategy_name="runs_anomaly",
        estimated_probability=0.58,
        wilson_lower_bound=0.53,
    )

    run_coro(executor.execute_order(order_req))
    settled = executor.settle_contract(contract_id="987654321", won=False, exit_digit=6)
    assert settled.status == ContractStatus.LOST
    assert settled.net_pnl == -1.00
    assert executor.risk_manager.consecutive_losses == 1
    assert executor.risk_manager.balance_usd == 999.00


def test_executor_blocks_negative_ev_trade(executor: ContractExecutor, mock_deriv_client):
    """Rejeita categoricamente operação com probabilidade sem vantagem (P=50%)."""
    order_req = OrderRequest(
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.00,
        strategy_name="streak_persistence",
        estimated_probability=0.50,  # 0.50 * 1.95 - 1.0 = -0.025 (EV negativo)
        wilson_lower_bound=0.46,
    )

    result = run_coro(executor.execute_order(order_req))
    assert result.success is False
    assert result.status == ContractStatus.REJECTED_BY_MATH
    assert "Expectativa matemática líquida não positiva" in result.rejection_reason
    # Garantia de que a ordem NÃO foi submetida para compra
    mock_deriv_client.buy.assert_not_called()


def test_executor_blocks_insufficient_wilson_lower_bound(executor: ContractExecutor, mock_deriv_client):
    """Rejeita se o limite inferior do IC de Wilson não superar o ponto de equilíbrio."""
    # Break-even = 1.00 / 1.95 = 51.28%
    order_req = OrderRequest(
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.00,
        strategy_name="ensemble",
        estimated_probability=0.56,
        wilson_lower_bound=0.49,  # Inferior ao break-even de 51.28%
    )

    result = run_coro(executor.execute_order(order_req))
    assert result.success is False
    assert result.status == ContractStatus.REJECTED_BY_MATH
    assert "não supera a probabilidade de equilíbrio" in result.rejection_reason
    mock_deriv_client.buy.assert_not_called()


def test_executor_blocks_when_kill_switch_active(executor: ContractExecutor, mock_deriv_client):
    """Com Kill Switch ativado, nem sequer gasta consulta à API da Deriv."""
    executor.risk_manager.set_kill_switch(True, "Trava de segurança ativada")

    order_req = OrderRequest(
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.00,
        strategy_name="manual",
        estimated_probability=0.60,
        wilson_lower_bound=0.55,
    )

    result = run_coro(executor.execute_order(order_req))
    assert result.success is False
    assert result.status == ContractStatus.REJECTED_BY_RISK
    assert "Kill Switch ATIVO" in result.rejection_reason
    mock_deriv_client.get_proposal.assert_not_called()
    mock_deriv_client.buy.assert_not_called()


def test_executor_blocks_anti_martingale_escalation(executor: ContractExecutor):
    """Garante bloqueio de aumento de stake após uma perda."""
    # Simula derrota anterior de $1.00
    executor.risk_manager.record_trade_result(won=False, pnl_usd=-1.00, stake_used=1.00)

    # Tentativa de escalonar para $2.00 após derrota
    order_req = OrderRequest(
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=2.00,
        strategy_name="manual",
        estimated_probability=0.60,
        wilson_lower_bound=0.55,
    )

    result = run_coro(executor.execute_order(order_req))
    assert result.success is False
    assert result.status == ContractStatus.REJECTED_BY_RISK
    assert "VIOLAÇÃO ANTI-MARTINGALE" in result.rejection_reason


def test_panic_stop_mechanism(executor: ContractExecutor):
    """Testa acionamento do Botão de Pânico emergencial."""
    panic_res = executor.panic_stop("Alerta de operador")
    assert panic_res["success"] is True
    assert panic_res["panic_triggered"] is True
    assert executor.risk_manager.kill_switch_active is True
    assert executor.risk_manager.circuit_breaker.is_active() is True


def test_executor_api_routes(executor: ContractExecutor):
    """Testa diretamente as funções dos endpoints de API do executor."""
    # 1. Panic Stop
    panic_res = trigger_panic_stop(
        payload=PanicStopPayload(reason="Teste API Pânico"),
        executor=executor,
    )
    assert panic_res["panic_triggered"] is True

    # Libera kill switch para permitir outras rotas
    executor.risk_manager.set_kill_switch(False)
    executor.risk_manager.circuit_breaker.reset()

    # 2. Execução via rota
    order_req = OrderRequest(
        symbol="R_100",
        contract_type="DIGITEVEN",
        stake=1.00,
        strategy_name="api_test",
        estimated_probability=0.58,
        wilson_lower_bound=0.53,
    )
    res = run_coro(execute_contract(payload=order_req, executor=executor))
    assert res.success is True
    assert res.contract_id == "987654321"

    # 3. Lista ativos
    active = list_active_contracts(executor=executor)
    assert len(active) == 1
    assert active[0]["contract_id"] == "987654321"

    # 4. Liquidação
    settled = settle_contract(
        payload=SettleContractPayload(contract_id="987654321", won=True, exit_digit=8),
        executor=executor,
    )
    assert settled.status == ContractStatus.WON

    # 5. Histórico
    hist = get_execution_history(executor=executor)
    assert len(hist) == 1
