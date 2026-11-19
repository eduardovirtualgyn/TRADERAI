"""Agregador de Ensemble com ponderação por Brier Score inverso e filtro de consenso."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np

from backend.app.core.logging import logger
from backend.app.modules.ai_agents.features import extract_features_single
from backend.app.modules.ai_agents.models import BaseAIModel
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.evaluator import StatisticalAssessment


@dataclass(frozen=True)
class EnsemblePrediction:
    """Resultado da agregação probabilística entre os múltiplos estimadores."""

    p_even: float
    p_odd: float
    individual_predictions: Dict[str, float]
    weights: Dict[str, float]
    discordance_spread: float
    is_consensus_achieved: bool
    veto_reason: Optional[str] = None


class ModelEnsemble:
    """Consolidador de probabilidades estatísticas e de IA com trava de discordância."""

    def __init__(
        self,
        max_allowed_discordance: float = 0.15,  # Diferença máxima aceitável entre previsões (15%)
        ai_models: Optional[List[BaseAIModel]] = None,
    ):
        self.max_allowed_discordance = max_allowed_discordance
        self.ai_models: List[BaseAIModel] = ai_models or []

    def add_ai_model(self, model: BaseAIModel) -> None:
        """Adiciona um modelo de IA ao ensemble."""
        if model not in self.ai_models:
            self.ai_models.append(model)

    def predict(
        self,
        ticks: List[TickData],
        stats: StatisticalAssessment,
    ) -> EnsemblePrediction:
        """Gera a predição agregada combinando o motor estatístico e os modelos de IA."""
        predictions_even: Dict[str, float] = {}
        brier_scores: Dict[str, float] = {}

        # 1. Estimador Estatístico: Cadeia de Markov de 2ª Ordem
        predictions_even["markov_order2"] = stats.conditional_p_even
        # Markov tem Brier Score basal de 0.25 (ruído padrão) diminuído do desvio empírico
        markov_brier = max(0.05, 0.25 - abs(stats.conditional_p_even - 0.50))
        brier_scores["markov_order2"] = markov_brier

        # 2. Estimador Estatístico: Alternância do Runs Test
        if stats.runs_test.is_independent or stats.runs_test.runs_count == 0:
            runs_p_even = 0.50
        else:
            # Se Z > 0 (alternância excessiva), probabilidade de alternar em relação ao último tick
            last_is_even = ticks[-1].is_even if ticks else True
            if stats.runs_test.z_score > 0:
                runs_p_even = 0.40 if last_is_even else 0.60
            else:
                runs_p_even = 0.60 if last_is_even else 0.40

        predictions_even["runs_test"] = runs_p_even
        runs_brier = max(0.10, 0.25 - (abs(stats.runs_test.z_score) * 0.02))
        brier_scores["runs_test"] = runs_brier

        # 3. Estimador de Assimetria e Frequência Recente (Janela de 25 ticks)
        if len(ticks) >= 15:
            recent_slice = ticks[-25:]
            recent_even_ratio = sum(1 for t in recent_slice if t.is_even) / float(len(recent_slice))
            predictions_even["recent_window"] = recent_even_ratio
            brier_scores["recent_window"] = max(0.08, 0.25 - abs(recent_even_ratio - 0.50))

        # 4. Estimador de Streaks de Paridade (Reversão à Média após sequência)
        if ticks:
            last_even = ticks[-1].is_even
            curr_streak = 0
            for t in reversed(ticks):
                if t.is_even == last_even:
                    curr_streak += 1
                else:
                    break
            if curr_streak >= 2:
                # Com streak >= 2, há forte pressão estatística de reversão à média
                p_revert = min(0.64, 0.50 + (curr_streak * 0.04))
                streak_p_even = (1.0 - p_revert) if last_even else p_revert
                predictions_even["streak_reversion"] = streak_p_even
                brier_scores["streak_reversion"] = max(0.06, 0.25 - (curr_streak * 0.03))

        # 5. Estimadores de Machine Learning (se treinados e calibrados)
        if self.ai_models and len(ticks) >= 15:
            try:
                x_vec = extract_features_single(ticks)
                for model in self.ai_models:
                    if model.is_trained and model.metrics and model.metrics.is_calibrated:
                        p_even_m, _ = model.predict_probability(x_vec)
                        predictions_even[model.model_name] = p_even_m
                        brier_scores[model.model_name] = max(0.01, model.metrics.brier_score)
            except Exception as exc:
                logger.error("Erro na extração de features para ensemble: %s", exc)

        # 4. Cálculo de Pesos por Inverso do Brier Score: w_i = 1 / Brier_i
        raw_weights = {k: 1.0 / brier_scores[k] for k in predictions_even.keys()}
        total_w = sum(raw_weights.values())
        normalized_weights = {k: round(v / total_w, 4) for k, v in raw_weights.items()}

        # 5. Média Ponderada
        p_even_ensemble = sum(predictions_even[k] * normalized_weights[k] for k in predictions_even.keys())
        p_odd_ensemble = 1.0 - p_even_ensemble

        # 6. Verificação de Discordância e Veto por Incerteza
        p_values = list(predictions_even.values())
        spread = max(p_values) - min(p_values) if p_values else 0.0

        if spread > self.max_allowed_discordance:
            veto_reason = (
                f"DIVERGÊNCIA EXCESSIVA: Spread entre estimadores ({spread:.2%}) "
                f"excede o teto permitido de {self.max_allowed_discordance:.2%}. Operação vetada por falta de consenso."
            )
            return EnsemblePrediction(
                p_even=round(p_even_ensemble, 4),
                p_odd=round(p_odd_ensemble, 4),
                individual_predictions={k: round(v, 4) for k, v in predictions_even.items()},
                weights=normalized_weights,
                discordance_spread=round(spread, 4),
                is_consensus_achieved=False,
                veto_reason=veto_reason,
            )

        return EnsemblePrediction(
            p_even=round(p_even_ensemble, 4),
            p_odd=round(p_odd_ensemble, 4),
            individual_predictions={k: round(v, 4) for k, v in predictions_even.items()},
            weights=normalized_weights,
            discordance_spread=round(spread, 4),
            is_consensus_achieved=True,
            veto_reason=None,
        )
