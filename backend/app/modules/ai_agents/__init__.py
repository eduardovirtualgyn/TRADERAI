"""Módulo 6: Agentes de inteligência artificial e engenharia de atributos."""

from backend.app.modules.ai_agents.agent_strategy import AIPredictiveStrategy
from backend.app.modules.ai_agents.features import (
    build_training_dataset,
    extract_features_at_index,
    extract_features_single,
)
from backend.app.modules.ai_agents.models import (
    BaseAIModel,
    CalibratedRandomForestModel,
    CalibratedXGBoostModel,
    ModelMetrics,
)
from backend.app.modules.ai_agents.trainer import AIAgentTrainer

__all__ = [
    "AIPredictiveStrategy",
    "extract_features_at_index",
    "extract_features_single",
    "build_training_dataset",
    "BaseAIModel",
    "CalibratedRandomForestModel",
    "CalibratedXGBoostModel",
    "ModelMetrics",
    "AIAgentTrainer",
]
