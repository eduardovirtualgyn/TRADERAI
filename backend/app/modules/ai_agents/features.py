"""Engenharia de atributos quantitativos (Feature Engineering) para modelos de IA."""

import math
from typing import List, Tuple
import numpy as np

from backend.app.modules.deriv_client.models import TickData


def calculate_entropy_slice(digits: List[int]) -> float:
    """Calcula a entropia de Shannon de uma fatia de dígitos."""
    total = len(digits)
    if total == 0:
        return 0.0
    counts = {}
    for d in digits:
        counts[d] = counts.get(d, 0) + 1
    entropy = 0.0
    for c in counts.values():
        p = c / total
        entropy -= p * math.log2(p)
    return entropy


def extract_features_at_index(ticks: List[TickData], idx: int) -> np.ndarray:
    """Extrai o vetor de features quantitativas disponível estritamente no índice idx.

    Garantia de Zero Data Leakage: Apenas ticks[0 : idx + 1] são consultados.
    """
    visible = ticks[: idx + 1]
    curr_tick = visible[-1]

    features = []

    # 1. Lags de Paridade (10 passos anteriores: 1 para Even, 0 para Odd)
    for lag in range(10):
        target_i = len(visible) - 1 - lag
        if target_i >= 0:
            features.append(1.0 if visible[target_i].is_even else 0.0)
        else:
            features.append(0.5)

    # 2. Lags de Dígito Exato (últimos 5 dígitos normalizados entre 0.0 e 0.9)
    for lag in range(5):
        target_i = len(visible) - 1 - lag
        if target_i >= 0:
            features.append(visible[target_i].last_digit / 10.0)
        else:
            features.append(0.5)

    # 3. Streak de Paridade Atual (assinado: +K para pares, -K para ímpares)
    curr_is_even = curr_tick.is_even
    streak_len = 0
    for t in reversed(visible):
        if t.is_even == curr_is_even:
            streak_len += 1
        else:
            break
    signed_streak = float(streak_len if curr_is_even else -streak_len)
    features.append(signed_streak)

    # 4. Proporção móvel de pares em janelas W in [5, 10, 20, 50]
    for w in [5, 10, 20, 50]:
        window_slice = visible[-w:]
        even_ratio = sum(1 for t in window_slice if t.is_even) / len(window_slice)
        features.append(float(even_ratio))

    # 5. Entropia da Informação nos últimos 20 ticks
    recent_digits = [t.last_digit for t in visible[-20:]]
    entropy_val = calculate_entropy_slice(recent_digits)
    features.append(float(entropy_val))

    # 6. Probabilidade condicional de 1ª ordem empírica no histórico visível
    prev_even_count = 0
    transition_same_count = 0
    for i in range(len(visible) - 1):
        if visible[i].is_even == curr_is_even:
            prev_even_count += 1
            if visible[i + 1].is_even == curr_is_even:
                transition_same_count += 1
    markov_est = (transition_same_count + 1.0) / (prev_even_count + 2.0)
    features.append(float(markov_est))

    return np.array(features, dtype=np.float32)


def extract_features_single(ticks: List[TickData]) -> np.ndarray:
    """Extrai o vetor de features mais recente para inferência em tempo real."""
    if not ticks:
        raise ValueError("A lista de ticks não pode estar vazia.")
    return extract_features_at_index(ticks, len(ticks) - 1)


def build_training_dataset(
    ticks: List[TickData],
    min_history: int = 50,
) -> Tuple[np.ndarray, np.ndarray]:
    """Constrói matrizes (X, y) para aprendizado supervisionado sem Look-Ahead Bias.

    X[i]: Features extraídas até o tick i.
    y[i]: 1 se o tick i + 1 for EVEN, 0 se for ODD.
    """
    n = len(ticks)
    if n < min_history + 2:
        return np.empty((0, 22), dtype=np.float32), np.empty((0,), dtype=np.int32)

    X_list = []
    y_list = []

    # Começamos a partir de min_history até n - 2 (pois o alvo y é o tick i + 1)
    for i in range(min_history, n - 1):
        x_vec = extract_features_at_index(ticks, i)
        target = 1 if ticks[i + 1].is_even else 0
        X_list.append(x_vec)
        y_list.append(target)

    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.int32)
