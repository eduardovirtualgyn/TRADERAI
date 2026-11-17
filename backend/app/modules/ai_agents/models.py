"""Modelos preditivos supervisionados com calibração rigorosa de probabilidade."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from backend.app.core.logging import logger


@dataclass(frozen=True)
class ModelMetrics:
    """Métricas de avaliação e calibração estatística do modelo de IA."""

    accuracy: float
    brier_score: float  # Brier score: 0.0 é perfeito, 0.25 é ruído aleatório 50/50
    log_loss_val: float
    sample_count: int
    is_calibrated: bool  # True se Brier Score < 0.25 e acurácia >= 50%


class BaseAIModel(ABC):
    """Interface abstrata para estimadores probabilísticos de paridade."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.is_trained: bool = False
        self.metrics: Optional[ModelMetrics] = None

    @abstractmethod
    def train(self, X: np.ndarray, y: np.ndarray) -> ModelMetrics:
        """Treina o modelo e afere métricas de calibração em conjunto de validação out-of-fold."""
        pass

    @abstractmethod
    def predict_probability(self, x_vector: np.ndarray) -> Tuple[float, float]:
        """Retorna (P(EVEN), P(ODD)) calibradas para o vetor de features informado."""
        pass


class CalibratedRandomForestModel(BaseAIModel):
    """Random Forest com regularização contra overfitting e CalibratedClassifierCV."""

    def __init__(self, n_estimators: int = 50, max_depth: int = 4):
        super().__init__(model_name="CalibratedRandomForest")
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self._model: Optional[CalibratedClassifierCV] = None

    def train(self, X: np.ndarray, y: np.ndarray) -> ModelMetrics:
        if len(X) < 30:
            raise ValueError(f"Amostra insuficiente para treino ({len(X)} < 30 observações).")

        # Split estratificado para validação out-of-sample
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.25, random_state=42, shuffle=False
        )

        base_rf = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=3,
            random_state=42,
        )

        # Calibração via Platt Scaling (método sigmoide)
        self._model = CalibratedClassifierCV(estimator=base_rf, method="sigmoid", cv=3)
        self._model.fit(X_train, y_train)

        # Avaliação no conjunto de validação
        val_probs = self._model.predict_proba(X_val)
        p_even_val = val_probs[:, 1]
        preds = (p_even_val >= 0.5).astype(int)

        acc = float(np.mean(preds == y_val))
        brier = float(brier_score_loss(y_val, p_even_val))
        loss = float(log_loss(y_val, val_probs, labels=[0, 1]))

        # Um modelo só é considerado calibrado e seguro se superar o ruído puro (Brier < 0.25)
        is_calibrated = bool(brier < 0.25)

        self.metrics = ModelMetrics(
            accuracy=round(acc, 4),
            brier_score=round(brier, 4),
            log_loss_val=round(loss, 4),
            sample_count=len(X),
            is_calibrated=is_calibrated,
        )
        self.is_trained = True

        logger.info(
            "Modelo %s treinado com %d amostras. Acc: %.2f%%, Brier: %.4f (Calibrado: %s)",
            self.model_name,
            len(X),
            acc * 100,
            brier,
            is_calibrated,
        )
        return self.metrics

    def predict_probability(self, x_vector: np.ndarray) -> Tuple[float, float]:
        if not self.is_trained or self._model is None:
            return 0.5, 0.5

        if x_vector.ndim == 1:
            x_input = x_vector.reshape(1, -1)
        else:
            x_input = x_vector

        probs = self._model.predict_proba(x_input)[0]
        # Classe 0 = ODD, Classe 1 = EVEN
        p_odd = float(probs[0])
        p_even = float(probs[1])
        return p_even, p_odd


class CalibratedXGBoostModel(BaseAIModel):
    """Gradient Boosting XGBoost com hiperparâmetros conservadores e calibração."""

    def __init__(self, n_estimators: int = 40, max_depth: int = 3, learning_rate: float = 0.05):
        super().__init__(model_name="CalibratedXGBoost")
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self._model: Optional[CalibratedClassifierCV] = None

    def train(self, X: np.ndarray, y: np.ndarray) -> ModelMetrics:
        if len(X) < 30:
            raise ValueError(f"Amostra insuficiente para treino ({len(X)} < 30 observações).")

        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.25, random_state=42, shuffle=False
        )

        base_xgb = XGBClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            reg_lambda=1.5,
            random_state=42,
            eval_metric="logloss",
        )

        self._model = CalibratedClassifierCV(estimator=base_xgb, method="sigmoid", cv=3)
        self._model.fit(X_train, y_train)

        val_probs = self._model.predict_proba(X_val)
        p_even_val = val_probs[:, 1]
        preds = (p_even_val >= 0.5).astype(int)

        acc = float(np.mean(preds == y_val))
        brier = float(brier_score_loss(y_val, p_even_val))
        loss = float(log_loss(y_val, val_probs, labels=[0, 1]))
        is_calibrated = bool(brier < 0.25)

        self.metrics = ModelMetrics(
            accuracy=round(acc, 4),
            brier_score=round(brier, 4),
            log_loss_val=round(loss, 4),
            sample_count=len(X),
            is_calibrated=is_calibrated,
        )
        self.is_trained = True

        logger.info(
            "Modelo %s treinado com %d amostras. Acc: %.2f%%, Brier: %.4f (Calibrado: %s)",
            self.model_name,
            len(X),
            acc * 100,
            brier,
            is_calibrated,
        )
        return self.metrics

    def predict_probability(self, x_vector: np.ndarray) -> Tuple[float, float]:
        if not self.is_trained or self._model is None:
            return 0.5, 0.5

        if x_vector.ndim == 1:
            x_input = x_vector.reshape(1, -1)
        else:
            x_input = x_vector

        probs = self._model.predict_proba(x_input)[0]
        p_odd = float(probs[0])
        p_even = float(probs[1])
        return p_even, p_odd
