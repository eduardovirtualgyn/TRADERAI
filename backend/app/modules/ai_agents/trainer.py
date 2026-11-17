"""Orquestrador de treinamento, validação e inferência de modelos de Inteligência Artificial."""

from typing import Dict, List, Optional
import numpy as np

from backend.app.core.logging import logger
from backend.app.modules.ai_agents.agent_strategy import AIPredictiveStrategy
from backend.app.modules.ai_agents.features import (
    build_training_dataset,
    extract_features_single,
)
from backend.app.modules.ai_agents.models import (
    CalibratedRandomForestModel,
    CalibratedXGBoostModel,
)
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.strategy_lab.registry import StrategyRegistry


class AIAgentTrainer:
    """Gerenciador de ciclo de vida e retreinamento de modelos de IA."""

    def __init__(self, registry: Optional[StrategyRegistry] = None):
        self.rf_model = CalibratedRandomForestModel()
        self.xgb_model = CalibratedXGBoostModel()

        self.rf_strategy = AIPredictiveStrategy(
            strategy_id="ai_rf_v1",
            name="AI Random Forest Calibrated",
            model=self.rf_model,
            min_ticks_required=50,
        )
        self.xgb_strategy = AIPredictiveStrategy(
            strategy_id="ai_xgb_v1",
            name="AI XGBoost Calibrated",
            model=self.xgb_model,
            min_ticks_required=50,
        )

        # Registro automático no StrategyRegistry se fornecido
        if registry is not None:
            registry.register(self.rf_strategy)
            registry.register(self.xgb_strategy)

    def train_all(self, ticks: List[TickData], min_history: int = 30) -> dict:
        """Extrai features da série temporal e treina os modelos de IA."""
        X, y = build_training_dataset(ticks=ticks, min_history=min_history)

        if len(X) < 40:
            raise ValueError(
                f"Amostra insuficiente ({len(X)} observações geradas). "
                "Necessário ao menos 40 pares de features para treinamento com validação cruzada."
            )

        logger.info("Iniciando treinamento dos agentes de IA com %d amostras e %d features...", len(X), X.shape[1])

        rf_metrics = self.rf_model.train(X, y)
        xgb_metrics = self.xgb_model.train(X, y)

        return {
            "samples_trained": len(X),
            "features_count": X.shape[1],
            "models": {
                "random_forest": {
                    "accuracy": rf_metrics.accuracy,
                    "brier_score": rf_metrics.brier_score,
                    "is_calibrated": rf_metrics.is_calibrated,
                },
                "xgboost": {
                    "accuracy": xgb_metrics.accuracy,
                    "brier_score": xgb_metrics.brier_score,
                    "is_calibrated": xgb_metrics.is_calibrated,
                },
            },
        }

    def predict_next(self, ticks: List[TickData]) -> dict:
        """Gera inferência probabilística para o próximo tick nos modelos treinados."""
        if len(ticks) < 15:
            raise ValueError("Mínimo de 15 ticks necessários para inferência das features.")

        x_vec = extract_features_single(ticks)

        p_even_rf, p_odd_rf = self.rf_model.predict_probability(x_vec)
        p_even_xgb, p_odd_xgb = self.xgb_model.predict_probability(x_vec)

        return {
            "random_forest": {
                "p_even": round(p_even_rf, 4),
                "p_odd": round(p_odd_rf, 4),
                "is_trained": self.rf_model.is_trained,
            },
            "xgboost": {
                "p_even": round(p_even_xgb, 4),
                "p_odd": round(p_odd_xgb, 4),
                "is_trained": self.xgb_model.is_trained,
            },
        }

    def get_status(self) -> dict:
        """Retorna o estado de treinamento e métricas ativas dos modelos."""
        return {
            "random_forest": {
                "is_trained": self.rf_model.is_trained,
                "metrics": {
                    "accuracy": self.rf_model.metrics.accuracy,
                    "brier_score": self.rf_model.metrics.brier_score,
                    "is_calibrated": self.rf_model.metrics.is_calibrated,
                    "sample_count": self.rf_model.metrics.sample_count,
                } if self.rf_model.metrics else None,
            },
            "xgboost": {
                "is_trained": self.xgb_model.is_trained,
                "metrics": {
                    "accuracy": self.xgb_model.metrics.accuracy,
                    "brier_score": self.xgb_model.metrics.brier_score,
                    "is_calibrated": self.xgb_model.metrics.is_calibrated,
                    "sample_count": self.xgb_model.metrics.sample_count,
                } if self.xgb_model.metrics else None,
            },
        }
