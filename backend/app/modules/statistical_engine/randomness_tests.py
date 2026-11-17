"""Testes formais de aleatoriedade, aderência e independência serial.

Implementa Teste Qui-Quadrado de Uniformidade, Runs Test de Wald-Wolfowitz e Entropia de Shannon.
"""

import math
from dataclasses import dataclass
from typing import Dict, List
from scipy import stats


@dataclass(frozen=True)
class ChiSquareResult:
    """Resultado do Teste de Aderência Qui-Quadrado (Uniformidade dos dígitos 0..9)."""

    statistic: float
    p_value: float
    degrees_of_freedom: int
    is_uniform: bool  # True se p_value >= 0.05 (não rejeita H0 de uniformidade)
    observed_counts: Dict[int, int]
    expected_count_per_digit: float


@dataclass(frozen=True)
class RunsTestResult:
    """Resultado do Teste de Wald-Wolfowitz para independência serial da paridade."""

    runs_count: int
    even_count: int
    odd_count: int
    expected_runs: float
    variance_runs: float
    z_score: float
    p_value: float
    is_independent: bool  # True se p_value >= 0.05 (|z| < 1.96)


@dataclass(frozen=True)
class EntropyResult:
    """Resultado do cálculo da Entropia da Informação de Shannon."""

    entropy_bits: float
    max_entropy_bits: float
    entropy_ratio: float  # Proporção entre 0.0 e 1.0
    is_high_entropy: bool  # True se ratio >= 0.95


def chi_square_uniformity_test(digits: List[int]) -> ChiSquareResult:
    """Avalia se a distribuição dos 10 dígitos (0 a 9) adere a uma distribuição uniforme discreta.

    H0: Os dígitos são uniformemente distribuídos P(d) = 1/10.
    H1: A distribuição empírica apresenta viés ou assimetria significativa.
    """
    total = len(digits)
    counts = {d: 0 for d in range(10)}
    for d in digits:
        if 0 <= d <= 9:
            counts[d] += 1

    if total < 10:
        return ChiSquareResult(
            statistic=0.0,
            p_value=1.0,
            degrees_of_freedom=9,
            is_uniform=True,
            observed_counts=counts,
            expected_count_per_digit=0.0,
        )

    expected_per_digit = total / 10.0
    observed_list = [counts[d] for d in range(10)]
    expected_list = [expected_per_digit] * 10

    chi2_stat, p_val = stats.chisquare(f_obs=observed_list, f_exp=expected_list)

    # Não rejeita H0 ao nível de significância de 5% se p_val >= 0.05
    is_uniform = bool(p_val >= 0.05)

    return ChiSquareResult(
        statistic=round(float(chi2_stat), 4),
        p_value=round(float(p_val), 6),
        degrees_of_freedom=9,
        is_uniform=is_uniform,
        observed_counts=counts,
        expected_count_per_digit=round(expected_per_digit, 2),
    )


def wald_wolfowitz_runs_test(parity_series: List[bool]) -> RunsTestResult:
    """Aplica o teste de Wald-Wolfowitz para verificar se a alternância Par/Ímpar é independente.

    H0: A sequência de pares e ímpares é mutuamente independente (processo de Bernoulli).
    H1: Há aglomeração anormal (clustering) ou alternância excessiva (mean-reversion artificial).
    """
    n = len(parity_series)
    if n < 4:
        return RunsTestResult(
            runs_count=1 if n > 0 else 0,
            even_count=sum(1 for p in parity_series if p),
            odd_count=sum(1 for p in parity_series if not p),
            expected_runs=1.0,
            variance_runs=0.0,
            z_score=0.0,
            p_value=1.0,
            is_independent=True,
        )

    n1 = sum(1 for p in parity_series if p)      # Contagem de Even
    n2 = sum(1 for p in parity_series if not p)  # Contagem de Odd

    if n1 == 0 or n2 == 0:
        # Apenas um tipo de evento: ausência total de aleatoriedade
        return RunsTestResult(
            runs_count=1,
            even_count=n1,
            odd_count=n2,
            expected_runs=1.0,
            variance_runs=0.0,
            z_score=-99.9,
            p_value=0.0,
            is_independent=False,
        )

    # Contagem de runs (corridas contíguas de mesmo valor)
    runs = 1
    for i in range(1, n):
        if parity_series[i] != parity_series[i - 1]:
            runs += 1

    expected_runs = 1.0 + (2.0 * n1 * n2) / n
    var_numerator = (2.0 * n1 * n2) * ((2.0 * n1 * n2) - n)
    var_denominator = (n ** 2) * (n - 1)
    variance_runs = var_numerator / var_denominator if var_denominator > 0 else 0.0

    if variance_runs > 0:
        std_runs = math.sqrt(variance_runs)
        # Correção de continuidade
        diff = runs - expected_runs
        if diff > 0.5:
            z = (diff - 0.5) / std_runs
        elif diff < -0.5:
            z = (diff + 0.5) / std_runs
        else:
            z = 0.0
        # p-valor bicaudal da normal padrão
        p_val = float(2.0 * stats.norm.sf(abs(z)))
    else:
        z = 0.0
        p_val = 1.0

    is_independent = bool(p_val >= 0.05)

    return RunsTestResult(
        runs_count=runs,
        even_count=n1,
        odd_count=n2,
        expected_runs=round(expected_runs, 3),
        variance_runs=round(variance_runs, 4),
        z_score=round(z, 4),
        p_value=round(p_val, 6),
        is_independent=is_independent,
    )


def calculate_shannon_entropy(digits: List[int]) -> EntropyResult:
    """Calcula a Entropia da Informação de Shannon para a série discreta de dígitos [0..9].

    Entropia Máxima: log2(10) ≈ 3.321928 bits (quando todos os 10 dígitos são perfeitamente equiprováveis).
    """
    total = len(digits)
    max_entropy = math.log2(10.0)

    if total == 0:
        return EntropyResult(
            entropy_bits=0.0,
            max_entropy_bits=round(max_entropy, 4),
            entropy_ratio=0.0,
            is_high_entropy=False,
        )

    counts = {d: 0 for d in range(10)}
    for d in digits:
        if 0 <= d <= 9:
            counts[d] += 1

    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)

    ratio = entropy / max_entropy if max_entropy > 0 else 0.0

    return EntropyResult(
        entropy_bits=round(entropy, 4),
        max_entropy_bits=round(max_entropy, 4),
        entropy_ratio=round(ratio, 4),
        is_high_entropy=bool(ratio >= 0.95),
    )
