"""Injeção de dependências para as rotas da API."""

from backend.app.core.config import Settings, get_settings
from backend.app.modules.ai_agents.trainer import AIAgentTrainer
from backend.app.modules.deriv_client.client import DerivWebSocketClient
from backend.app.modules.model_ensemble.ensemble import ModelEnsemble
from backend.app.modules.model_ensemble.ensemble_strategy import EnsembleStrategy
from backend.app.modules.risk_manager.risk_rules import RiskManager
from backend.app.modules.statistical_engine.evaluator import StatisticalEvaluator
from backend.app.modules.strategy_lab.registry import StrategyRegistry
from backend.app.modules.tick_collector.collector import TickCollector
from backend.app.modules.contract_executor.executor import ContractExecutor
from backend.app.modules.audit_logger.ledger import AuditLedger
from backend.app.modules.auto_trader.engine import AutoTraderEngine

_risk_manager_instance: RiskManager | None = None
_deriv_client_instance: DerivWebSocketClient | None = None
_tick_collector_instance: TickCollector | None = None
_statistical_evaluator_instance: StatisticalEvaluator | None = None
_strategy_registry_instance: StrategyRegistry | None = None
_ai_trainer_instance: AIAgentTrainer | None = None
_model_ensemble_instance: ModelEnsemble | None = None
_contract_executor_instance: ContractExecutor | None = None
_audit_ledger_instance: AuditLedger | None = None
_auto_trader_instance: AutoTraderEngine | None = None


def get_risk_manager() -> RiskManager:
    """Retorna a instância singleton em memória do RiskManager."""
    global _risk_manager_instance
    if _risk_manager_instance is None:
        settings = get_settings()
        _risk_manager_instance = RiskManager(
            max_stake_usd=settings.risk_max_stake_usd,
            max_stake_percent=settings.risk_max_stake_percent,
            max_consecutive_losses=settings.risk_max_consecutive_losses,
            max_daily_loss_usd=settings.risk_max_daily_loss_usd,
            ban_martingale=settings.risk_ban_martingale,
            kill_switch_initially_active=settings.risk_kill_switch_active,
        )
    return _risk_manager_instance


def get_deriv_client() -> DerivWebSocketClient:
    """Retorna a instância singleton em memória do DerivWebSocketClient."""
    global _deriv_client_instance
    if _deriv_client_instance is None:
        settings = get_settings()
        _deriv_client_instance = DerivWebSocketClient(
            ws_url=settings.deriv_ws_url,
            app_id=settings.deriv_app_id,
            demo_token=settings.deriv_demo_token,
        )
    return _deriv_client_instance


def get_tick_collector() -> TickCollector:
    """Retorna a instância singleton em memória do TickCollector."""
    global _tick_collector_instance
    if _tick_collector_instance is None:
        client = get_deriv_client()
        _tick_collector_instance = TickCollector()
        _tick_collector_instance.bind_client(client)
    return _tick_collector_instance


def get_statistical_evaluator() -> StatisticalEvaluator:
    """Retorna a instância singleton em memória do StatisticalEvaluator."""
    global _statistical_evaluator_instance
    if _statistical_evaluator_instance is None:
        settings = get_settings()
        _statistical_evaluator_instance = StatisticalEvaluator(
            min_sample_size=settings.min_tick_sample_size,
            confidence_level=settings.confidence_level,
        )
    return _statistical_evaluator_instance


def get_strategy_registry() -> StrategyRegistry:
    """Retorna a instância singleton em memória do StrategyRegistry com estratégias padrão."""
    global _strategy_registry_instance
    if _strategy_registry_instance is None:
        _strategy_registry_instance = StrategyRegistry(register_defaults=True)
    return _strategy_registry_instance


def get_ai_trainer() -> AIAgentTrainer:
    """Retorna a instância singleton do AIAgentTrainer integrada ao StrategyRegistry."""
    global _ai_trainer_instance
    if _ai_trainer_instance is None:
        registry = get_strategy_registry()
        _ai_trainer_instance = AIAgentTrainer(registry=registry)
    return _ai_trainer_instance


def get_model_ensemble() -> ModelEnsemble:
    """Retorna a instância singleton do ModelEnsemble integrada aos modelos de IA e ao StrategyRegistry."""
    global _model_ensemble_instance
    if _model_ensemble_instance is None:
        trainer = get_ai_trainer()
        registry = get_strategy_registry()
        _model_ensemble_instance = ModelEnsemble(
            max_allowed_discordance=0.15,
            ai_models=[trainer.rf_model, trainer.xgb_model],
        )
        ensemble_strat = EnsembleStrategy(ensemble=_model_ensemble_instance)
        registry.register(ensemble_strat)
    return _model_ensemble_instance


def get_audit_ledger() -> AuditLedger:
    """Retorna a instância singleton em memória do AuditLedger."""
    global _audit_ledger_instance
    if _audit_ledger_instance is None:
        _audit_ledger_instance = AuditLedger()
    return _audit_ledger_instance


def get_contract_executor() -> ContractExecutor:
    """Retorna a instância singleton do ContractExecutor integrada ao DerivClient e RiskManager."""
    global _contract_executor_instance
    if _contract_executor_instance is None:
        client = get_deriv_client()
        risk_mgr = get_risk_manager()
        ledger = get_audit_ledger()
        _contract_executor_instance = ContractExecutor(
            deriv_client=client,
            risk_manager=risk_mgr,
            audit_callback=ledger.record_execution_result,
        )
    return _contract_executor_instance


def get_auto_trader() -> AutoTraderEngine:
    """Retorna a instância singleton do AutoTraderEngine."""
    global _auto_trader_instance
    if _auto_trader_instance is None:
        client = get_deriv_client()
        collector = get_tick_collector()
        evaluator = get_statistical_evaluator()
        ensemble = get_model_ensemble()
        ensemble_strat = EnsembleStrategy(ensemble=ensemble)
        executor = get_contract_executor()
        risk_mgr = get_risk_manager()
        _auto_trader_instance = AutoTraderEngine(
            deriv_client=client,
            tick_collector=collector,
            evaluator=evaluator,
            ensemble_strategy=ensemble_strat,
            contract_executor=executor,
            risk_manager=risk_mgr,
        )
    return _auto_trader_instance
