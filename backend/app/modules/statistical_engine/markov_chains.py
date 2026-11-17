"""Cadeias de Markov de 1ª e 2ª ordem para modelagem de transições de paridade.

Permite estimar probabilidades condicionais P(S_t | S_{t-1}) e P(S_t | S_{t-1}, S_{t-2}).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class MarkovFirstOrder:
    """Matriz de transição de 1ª ordem para estados de paridade (EVEN / ODD)."""

    total_transitions: int
    p_even_given_even: float  # P(E_t | E_{t-1})
    p_odd_given_even: float   # P(O_t | E_{t-1})
    p_even_given_odd: float   # P(E_t | O_{t-1})
    p_odd_given_odd: float    # P(O_t | O_{t-1})
    count_even_even: int
    count_even_odd: int
    count_odd_even: int
    count_odd_odd: int


@dataclass(frozen=True)
class MarkovSecondOrder:
    """Matriz de transição de 2ª ordem (estados de 2 passos anteriores: EE, EO, OE, OO)."""

    total_transitions: int
    probabilities: Dict[str, Dict[str, float]]  # ex: {"EE": {"EVEN": 0.51, "ODD": 0.49}}
    counts: Dict[str, Dict[str, int]]


def calculate_first_order_markov(
    parity_series: List[bool],
    laplace_smoothing: float = 1.0,
) -> MarkovFirstOrder:
    """Calcula a matriz de transição de 1ª ordem com suavização opcional de Laplace.

    parity_series: lista de booleanos (True = Even, False = Odd).
    """
    if len(parity_series) < 2:
        return MarkovFirstOrder(
            total_transitions=0,
            p_even_given_even=0.5,
            p_odd_given_even=0.5,
            p_even_given_odd=0.5,
            p_odd_given_odd=0.5,
            count_even_even=0,
            count_even_odd=0,
            count_odd_even=0,
            count_odd_odd=0,
        )

    c_ee = 0
    c_eo = 0
    c_oe = 0
    c_oo = 0

    for i in range(len(parity_series) - 1):
        prev_even = parity_series[i]
        curr_even = parity_series[i + 1]

        if prev_even and curr_even:
            c_ee += 1
        elif prev_even and not curr_even:
            c_eo += 1
        elif not prev_even and curr_even:
            c_oe += 1
        else:
            c_oo += 1

    total = c_ee + c_eo + c_oe + c_oo
    alpha = max(0.0, laplace_smoothing)

    # Denominadores com suavização de Laplace
    denom_even = (c_ee + c_eo) + (2.0 * alpha)
    denom_odd = (c_oe + c_oo) + (2.0 * alpha)

    p_ee = (c_ee + alpha) / denom_even if denom_even > 0 else 0.5
    p_eo = (c_eo + alpha) / denom_even if denom_even > 0 else 0.5
    p_oe = (c_oe + alpha) / denom_odd if denom_odd > 0 else 0.5
    p_oo = (c_oo + alpha) / denom_odd if denom_odd > 0 else 0.5

    return MarkovFirstOrder(
        total_transitions=total,
        p_even_given_even=round(p_ee, 4),
        p_odd_given_even=round(p_eo, 4),
        p_even_given_odd=round(p_oe, 4),
        p_odd_given_odd=round(p_oo, 4),
        count_even_even=c_ee,
        count_even_odd=c_eo,
        count_odd_even=c_oe,
        count_odd_odd=c_oo,
    )


def calculate_second_order_markov(
    parity_series: List[bool],
    laplace_smoothing: float = 1.0,
) -> MarkovSecondOrder:
    """Calcula as probabilidades condicionais a partir dos últimos 2 estados: P(S_t | S_{t-2}, S_{t-1})."""
    states = ["EE", "EO", "OE", "OO"]
    counts = {s: {"EVEN": 0, "ODD": 0} for s in states}

    if len(parity_series) < 3:
        probs = {s: {"EVEN": 0.5, "ODD": 0.5} for s in states}
        return MarkovSecondOrder(total_transitions=0, probabilities=probs, counts=counts)

    total = 0
    for i in range(len(parity_series) - 2):
        s1 = "E" if parity_series[i] else "O"
        s2 = "E" if parity_series[i + 1] else "O"
        s_curr = "EVEN" if parity_series[i + 2] else "ODD"

        history_key = f"{s1}{s2}"
        counts[history_key][s_curr] += 1
        total += 1

    alpha = max(0.0, laplace_smoothing)
    probs = {}

    for s in states:
        c_even = counts[s]["EVEN"]
        c_odd = counts[s]["ODD"]
        denom = (c_even + c_odd) + (2.0 * alpha)

        p_even = (c_even + alpha) / denom if denom > 0 else 0.5
        p_odd = (c_odd + alpha) / denom if denom > 0 else 0.5

        probs[s] = {
            "EVEN": round(p_even, 4),
            "ODD": round(p_odd, 4),
        }

    return MarkovSecondOrder(total_transitions=total, probabilities=probs, counts=counts)


def get_conditional_probabilities(
    parity_series: List[bool],
    markov_order: int = 2,
    laplace_smoothing: float = 1.0,
) -> Tuple[float, float, int]:
    """Retorna (P(EVEN | histórico), P(ODD | histórico), sample_size_for_state)."""
    if len(parity_series) < markov_order:
        return 0.5, 0.5, 0

    if markov_order == 2 and len(parity_series) >= 2:
        m2 = calculate_second_order_markov(parity_series, laplace_smoothing=laplace_smoothing)
        s1 = "E" if parity_series[-2] else "O"
        s2 = "E" if parity_series[-1] else "O"
        key = f"{s1}{s2}"
        p_even = m2.probabilities[key]["EVEN"]
        p_odd = m2.probabilities[key]["ODD"]
        n_samples = m2.counts[key]["EVEN"] + m2.counts[key]["ODD"]
        return p_even, p_odd, n_samples
    else:
        m1 = calculate_first_order_markov(parity_series, laplace_smoothing=laplace_smoothing)
        last_is_even = parity_series[-1]
        if last_is_even:
            p_even = m1.p_even_given_even
            p_odd = m1.p_odd_given_even
            n_samples = m1.count_even_even + m1.count_even_odd
        else:
            p_even = m1.p_even_given_odd
            p_odd = m1.p_odd_given_odd
            n_samples = m1.count_odd_even + m1.count_odd_odd
        return p_even, p_odd, n_samples
