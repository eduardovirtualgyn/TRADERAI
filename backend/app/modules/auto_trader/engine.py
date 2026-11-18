"""Motor de execução contínua e autônoma (Auto-Trader) para opções ODD/EVEN."""

import asyncio
import time
from typing import Optional

from backend.app.core.logging import logger
from backend.app.modules.auto_trader.models import AutoTraderConfig, AutoTraderStatusResponse
from backend.app.modules.contract_executor.executor import ContractExecutor
from backend.app.modules.contract_executor.models import OrderRequest
from backend.app.modules.deriv_client.client import DerivWebSocketClient
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.model_ensemble.ensemble_strategy import EnsembleStrategy
from backend.app.modules.risk_manager.risk_rules import RiskManager
from backend.app.modules.statistical_engine.evaluator import StatisticalEvaluator
from backend.app.modules.strategy_lab.base import SignalDirection
from backend.app.modules.tick_collector.collector import TickCollector


class AutoTraderEngine:
    """Motor de negociação 100% autônomo com portão de salvaguardas quantitativas."""

    def __init__(
        self,
        deriv_client: DerivWebSocketClient,
        tick_collector: TickCollector,
        evaluator: StatisticalEvaluator,
        ensemble_strategy: EnsembleStrategy,
        contract_executor: ContractExecutor,
        risk_manager: RiskManager,
        config: Optional[AutoTraderConfig] = None,
    ):
        self.deriv_client = deriv_client
        self.tick_collector = tick_collector
        self.evaluator = evaluator
        self.ensemble_strategy = ensemble_strategy
        self.executor = contract_executor
        self.risk_manager = risk_manager

        self.config = config or AutoTraderConfig()
        self.state = "STOPPED"
        self.last_decision = "Robô autônomo aguardando ativação."
        self.last_action_timestamp: Optional[float] = None
        self.active_contract_id: Optional[str] = None
        self.is_executing_trade: bool = False

        # Estatísticas da sessão
        self.total_trades: int = 0
        self.won_trades: int = 0
        self.lost_trades: int = 0
        self.session_pnl: float = 0.0

        # Vincula o callback de ticks
        self.deriv_client.register_tick_callback(self.on_tick_received)
        logger.info("AutoTraderEngine inicializado e vinculado ao stream de ticks.")

    def set_enabled(self, enabled: bool) -> None:
        """Ativa ou desativa o robô autônomo."""
        self.config.enabled = enabled
        if enabled:
            self.state = "SEARCHING_EDGE"
            self.last_decision = "Radar autônomo ativo. Monitorando ticks e calculando anomalias estatísticas..."
            logger.info("🟢 AUTO-TRADER ATIVADO. Monitorando símbolo: %s", self.config.symbol)
        else:
            self.state = "STOPPED"
            self.last_decision = "Robô autônomo pausado pelo operador."
            logger.info("🟡 AUTO-TRADER PAUSADO.")

    def update_config(self, config: AutoTraderConfig) -> None:
        """Atualiza os parâmetros de operação."""
        self.config = config
        logger.info("Configurações do Auto-Trader atualizadas: %s", config.model_dump())

    def get_status(self) -> AutoTraderStatusResponse:
        """Retorna o snapshot de telemetria do Auto-Trader."""
        return AutoTraderStatusResponse(
            enabled=self.config.enabled,
            state=self.state,
            symbol=self.config.symbol,
            stake=self.config.stake,
            min_probability=self.config.min_probability,
            cooldown_seconds=self.config.cooldown_seconds,
            last_decision=self.last_decision,
            last_action_timestamp=self.last_action_timestamp,
            total_trades=self.total_trades,
            won_trades=self.won_trades,
            lost_trades=self.lost_trades,
            session_pnl=round(self.session_pnl, 2),
            active_contract_id=self.active_contract_id,
        )

    def on_tick_received(self, tick: TickData) -> None:
        """Processa cada novo tick recebido da Deriv em tempo real."""
        # Se não estiver ligado, não consome processamento
        if not self.config.enabled:
            if self.state != "STOPPED":
                self.state = "STOPPED"
            return

        # Verifica se o símbolo do tick coincide com o configurado
        if tick.symbol != self.config.symbol:
            return

        # 1. Salvaguardas Críticas Imediatas
        if self.risk_manager.kill_switch_active:
            self.state = "PAUSED_BY_RISK"
            self.last_decision = (
                f"VETO: Kill Switch ativo ({self.risk_manager.kill_switch_reason or 'Operações suspensas'})"
            )
            return

        if self.risk_manager.circuit_breaker.is_active():
            rem = self.risk_manager.circuit_breaker.remaining_seconds()
            self.state = "PAUSED_BY_RISK"
            self.last_decision = (
                f"VETO: Circuit Breaker em andamento ({rem:.0f}s restantes após perdas consecutivas)"
            )
            return

        # 2. Verifica se já há uma ordem em processamento ou aguardando liquidação
        if self.is_executing_trade or self.active_contract_id is not None:
            self.state = "EXECUTING"
            return

        # 3. Cooldown de segurança entre operações
        now = time.time()
        if self.last_action_timestamp and (now - self.last_action_timestamp < self.config.cooldown_seconds):
            self.state = "COOLDOWN"
            return

        # 4. Amostra mínima no buffer
        ticks = self.tick_collector.buffer.get_last_n_ticks(1000)
        if len(ticks) < 50:
            self.state = "SEARCHING_EDGE"
            self.last_decision = f"Coletando amostra mínima ({len(ticks)}/50 ticks)..."
            return

        # 5. Avaliação Estatística e Veto de Passeio Aleatório
        stats = self.evaluator.evaluate_ticks(ticks=ticks)
        if stats.is_random_walk:
            self.state = "SEARCHING_EDGE"
            self.last_decision = "VETO MATEMÁTICO: Mercado em passeio aleatório uniforme (50/50, EV <= 0). Protegendo capital."
            return

        # 6. Avaliação da Estratégia Ensemble
        signal = self.ensemble_strategy.evaluate(
            ticks=ticks,
            stats=stats,
            stake=self.config.stake,
            payout=1.95,
        )

        if not signal:
            self.state = "SEARCHING_EDGE"
            p_max = max(stats.conditional_p_even, stats.conditional_p_odd)
            self.last_decision = (
                f"VETO: Sem borda matemática confirmada (P_max: {p_max:.1%}, Wilson Lower <= Break-even {stats.break_even_prob:.1%})"
            )
            return

        # Filtro de confiança mínima configurada
        if signal.estimated_probability < self.config.min_probability:
            self.state = "SEARCHING_EDGE"
            self.last_decision = (
                f"Probabilidade ({signal.estimated_probability:.1%}) abaixo do mínimo configurado ({self.config.min_probability:.1%})"
            )
            return

        if signal.confidence_lower_bound < self.config.min_wilson_lower_bound:
            self.state = "SEARCHING_EDGE"
            self.last_decision = (
                f"Wilson Lower ({signal.confidence_lower_bound:.1%}) abaixo do limiar ({self.config.min_wilson_lower_bound:.1%})"
            )
            return

        # 7. SINAL APROVADO! Dispara execução atômica em segundo plano
        self.is_executing_trade = True
        self.state = "EXECUTING"
        self.last_action_timestamp = now
        self.last_decision = (
            f"🎯 SINAL DETECTADO: {signal.direction.value} | P={signal.estimated_probability:.1%}, "
            f"Wilson={signal.confidence_lower_bound:.1%}. Disparando ordem autônoma..."
        )
        logger.info("🚀 [AUTO-TRADER] %s", self.last_decision)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._execute_and_settle(signal))
        except RuntimeError:
            asyncio.run(self._execute_and_settle(signal))

    async def _execute_and_settle(self, signal) -> None:
        """Executa a ordem na Deriv e acompanha a liquidação até o encerramento."""
        contract_type = "DIGITEVEN" if signal.direction == SignalDirection.EVEN else "DIGITODD"
        try:
            req = OrderRequest(
                symbol=self.config.symbol,
                contract_type=contract_type,
                stake=self.config.stake,
                duration=1,
                duration_unit="t",
                estimated_probability=signal.estimated_probability,
                wilson_lower_bound=signal.confidence_lower_bound,
                strategy_name="auto_trader_ai",
            )
            exec_res = await self.executor.execute_order(req)
            if not exec_res.success:
                self.last_decision = f"Falha na execução: {exec_res.rejection_reason}"
                logger.warning("❌ [AUTO-TRADER] Execução rejeitada: %s", exec_res.rejection_reason)
                self.is_executing_trade = False
                return

            cid = exec_res.contract_id
            self.active_contract_id = cid
            self.last_decision = (
                f"Ordem #{cid} enviada ({contract_type} US$ {self.config.stake:.2f}). Aguardando fechamento..."
            )
            logger.info("✅ [AUTO-TRADER] Ordem submetida com sucesso! Contract ID: %s", cid)

            # Aguarda liquidação na Deriv (opções de 1 tick fecham em 1-2 segundos)
            settled = await self._wait_settlement(cid, contract_type, timeout_seconds=12.0)
            if settled:
                self.total_trades += 1
                if settled.net_pnl > 0:
                    self.won_trades += 1
                    self.last_decision = f"🏆 VITÓRIA no contrato #{cid}! Lucro: +US$ {settled.net_pnl:.2f}"
                else:
                    self.lost_trades += 1
                    self.last_decision = f"📉 DERROTA no contrato #{cid}. PnL: -US$ {abs(settled.net_pnl):.2f}"
                self.session_pnl += settled.net_pnl
                logger.info("🏁 [AUTO-TRADER] %s | PnL Sessão: US$ %.2f", self.last_decision, self.session_pnl)

        except Exception as exc:
            logger.exception("Erro durante ciclo do Auto-Trader: %s", exc)
            self.last_decision = f"Erro no ciclo de execução: {exc}"
        finally:
            self.active_contract_id = None
            self.is_executing_trade = False
            self.last_action_timestamp = time.time()

    async def _wait_settlement(
        self,
        contract_id: str,
        contract_type: str,
        timeout_seconds: float = 12.0,
    ):
        """Acompanha o encerramento do contrato via Deriv API e liquida no Executor."""
        start = time.time()
        while time.time() - start < timeout_seconds:
            await asyncio.sleep(0.6)
            try:
                open_info = await self.deriv_client.get_open_contract(contract_id)
                if open_info:
                    status = open_info.get("status")
                    is_sold = open_info.get("is_sold") == 1
                    profit = float(open_info.get("profit", 0.0))
                    if is_sold or status in ("won", "lost"):
                        won = (status == "won") or (profit > 0)
                        exit_tick = open_info.get("exit_tick_display_value") or open_info.get("exit_tick")
                        exit_digit = int(str(exit_tick)[-1]) if exit_tick is not None else None
                        return self.executor.settle_contract(
                            contract_id=contract_id,
                            won=won,
                            exit_digit=exit_digit,
                        )
            except Exception as poll_err:
                logger.debug("Tentativa de consulta de contrato %s: %s", contract_id, poll_err)

        # Fallback de segurança (simulador ou rede): liquida usando o último tick do buffer
        logger.info("Liquidando contrato %s via verificação do último tick do buffer...", contract_id)
        latest_tick = self.tick_collector.buffer.get_latest()
        exit_digit = latest_tick.last_digit if latest_tick else 0
        won = (exit_digit % 2 == 0) if contract_type == "DIGITEVEN" else (exit_digit % 2 != 0)
        return self.executor.settle_contract(
            contract_id=contract_id,
            won=won,
            exit_digit=exit_digit,
        )
