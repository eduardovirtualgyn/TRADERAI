"""Módulo de Dimensionamento de Posição via Critério de Kelly Fracionário Conservador.

O Critério de Kelly maximiza o crescimento logarítmico do capital no longo prazo.
Em trading quantitativo de alta frequência ou apostas binárias, o Kelly pleno (Full Kelly)
induz volatilidade extrema e risco de ruína devido ao erro de estimação amostral.

Portanto, este módulo adota estritamente o Kelly Fracionário (Fractional Kelly,
geralmente 10% a 25% de f*), com tetos absolutos e percentuais impostos pelo gerenciamento de risco.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class KellyRecommendation:
    """Resultado do cálculo de dimensionamento por Kelly Fracionário."""

    full_kelly_f: float
    fractional_f: float
    fraction_factor: float
    recommended_stake: float
    approved: bool
    edge: float
    reason: Optional[str] = None


def calculate_fractional_kelly(
    win_probability: float,
    payout: float,
    stake_ref: float = 1.0,
    balance: float = 1000.0,
    fraction_factor: float = 0.20,
    min_stake: float = 0.35,
    max_stake_usd: float = 5.0,
    max_stake_percent: float = 0.01,
) -> KellyRecommendation:
    """Calcula a fração e o valor ótimo de aposta usando Kelly Fracionário.

    Fórmula:
        b = (Payout - Stake) / Stake  (Razão de ganho líquido por unidade apostada)
        q = 1 - p
        f* = (p * b - q) / b = (p * (b + 1) - 1) / b

    Args:
        win_probability: Probabilidade estimada de vitória (0.0 a 1.0).
        payout: Payout bruto retornado pela proposta para stake_ref.
        stake_ref: Stake base usado na cotação de payout (default 1.0).
        balance: Saldo disponível da conta em USD.
        fraction_factor: Fração de amortecimento de Kelly (ex: 0.20 = 20% do Kelly).
        min_stake: Stake mínimo aceito pela Deriv (geralmente $0.35).
        max_stake_usd: Teto absoluto permitido pelas regras de risco.
        max_stake_percent: Teto relativo permitido sobre o saldo da conta.

    Returns:
        KellyRecommendation com os valores calculados e indicação de aprovação.
    """
    if balance <= 0:
        return KellyRecommendation(
            full_kelly_f=0.0,
            fractional_f=0.0,
            fraction_factor=fraction_factor,
            recommended_stake=0.0,
            approved=False,
            edge=0.0,
            reason="Saldo de conta insuficiente ou zerado.",
        )

    if stake_ref <= 0 or payout <= stake_ref:
        return KellyRecommendation(
            full_kelly_f=0.0,
            fractional_f=0.0,
            fraction_factor=fraction_factor,
            recommended_stake=0.0,
            approved=False,
            edge=0.0,
            reason="Payout menor ou igual ao stake de referência (sem ganho possível).",
        )

    # Razão de ganho líquido
    b = (payout - stake_ref) / stake_ref
    p = win_probability
    q = 1.0 - p

    # Expectativa matemática líquida bruta (edge)
    net_ev = (p * payout) - stake_ref
    edge = net_ev / stake_ref

    # Kelly Integral
    full_kelly_f = (p * b - q) / b

    if full_kelly_f <= 0 or edge <= 0:
        return KellyRecommendation(
            full_kelly_f=round(full_kelly_f, 4),
            fractional_f=0.0,
            fraction_factor=fraction_factor,
            recommended_stake=0.0,
            approved=False,
            edge=round(edge, 4),
            reason=f"Sem vantagem estatística positiva (EV/Stake = {edge:.2%}, Kelly={full_kelly_f:.2%}).",
        )

    # Kelly Fracionário Conservador
    clamped_fraction_factor = min(max(fraction_factor, 0.01), 0.25)
    fractional_f = full_kelly_f * clamped_fraction_factor

    # Dimensionamento em USD
    raw_stake = balance * fractional_f

    # Aplicação dos tetos regulamentares
    ceiling_by_percent = balance * max_stake_percent
    capped_stake = min(raw_stake, ceiling_by_percent, max_stake_usd)
    # Arredondamento para 2 casas decimais (centavos de dólar)
    recommended_stake = round(capped_stake, 2)

    if recommended_stake < min_stake:
        return KellyRecommendation(
            full_kelly_f=round(full_kelly_f, 4),
            fractional_f=round(fractional_f, 4),
            fraction_factor=clamped_fraction_factor,
            recommended_stake=0.0,
            approved=False,
            edge=round(edge, 4),
            reason=(
                f"Stake calculado (${recommended_stake:.2f}) é inferior ao mínimo "
                f"regulamentar de ${min_stake:.2f}."
            ),
        )

    return KellyRecommendation(
        full_kelly_f=round(full_kelly_f, 4),
        fractional_f=round(fractional_f, 4),
        fraction_factor=clamped_fraction_factor,
        recommended_stake=recommended_stake,
        approved=True,
        edge=round(edge, 4),
        reason=None,
    )
