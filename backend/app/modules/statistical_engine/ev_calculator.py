"""Motor de cálculo de Expectativa Matemática Líquida (Net EV) e Validação Estatística.

Garante que nenhuma operação seja aprovada sem vantagem matemática real comprovada.
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TradeExpectationResult:
    """Resultado imutável da análise matemática de uma proposta."""

    stake: float
    payout: float
    estimated_prob: float
    break_even_prob: float
    net_ev: float
    net_ev_ratio: float
    is_viable: bool
    rejection_reason: Optional[str] = None


def get_z_score(confidence: float = 0.95) -> float:
    """Retorna o valor z crítico da distribuição normal padrão para intervalos bilaterais."""
    # Mapeamento dos níveis de confiança usuais sem dependência obrigatória de scipy
    z_table = {
        0.90: 1.644853,
        0.95: 1.959964,
        0.98: 2.326348,
        0.99: 2.575829,
        0.999: 3.290527,
    }
    # Arredondamento para encontrar chave próxima
    closest = min(z_table.keys(), key=lambda k: abs(k - confidence))
    return z_table[closest]


def calculate_break_even_probability(stake: float, payout: float) -> float:
    """Calcula a probabilidade mínima de acerto para não haver prejuízo (Break-even).

    Fórmula: P_be = Stake / Payout
    Exemplo: Stake $10.00, Payout $19.50 -> P_be = 10 / 19.50 = 51.282%
    """
    if payout <= 0.0:
        raise ValueError("O payout deve ser estritamente positivo.")
    if stake <= 0.0:
        raise ValueError("O stake deve ser estritamente positivo.")
    if payout <= stake:
        raise ValueError(
            f"Payout ({payout}) deve ser superior ao stake ({stake}) para contratos de dígito."
        )

    return stake / payout


def calculate_net_expected_value(prob: float, stake: float, payout: float) -> float:
    """Calcula a expectativa matemática líquida absoluta em moeda (USD).

    Fórmula: EV = (Prob * Payout) - Stake
    """
    if not (0.0 <= prob <= 1.0):
        raise ValueError(f"Probabilidade inválida: {prob}. Deve estar entre 0.0 e 1.0.")
    if stake <= 0.0 or payout <= 0.0:
        raise ValueError("Stake e payout devem ser estritamente positivos.")

    return (prob * payout) - stake


def calculate_net_ev_ratio(prob: float, stake: float, payout: float) -> float:
    """Calcula a razão de retorno esperado por unidade de capital arriscado (ROI esperado).

    Fórmula: EV_ratio = EV / Stake = Prob * (Payout / Stake) - 1.0
    """
    ev = calculate_net_expected_value(prob=prob, stake=stake, payout=payout)
    return ev / stake


def calculate_wilson_lower_bound(
    successes: int,
    total: int,
    confidence: float = 0.95,
) -> float:
    """Calcula o limite inferior do Intervalo de Confiança de Wilson para proporções binomiais.

    Protege contra sobre-otimização em pequenas sequências de dígitos.
    """
    if total <= 0:
        return 0.0
    if successes < 0 or successes > total:
        raise ValueError(
            f"Número de sucessos ({successes}) inválido para o total ({total})."
        )

    z = get_z_score(confidence)
    p_hat = successes / total

    denominator = 1.0 + (z**2 / total)
    centre = p_hat + (z**2 / (2.0 * total))
    spread = z * math.sqrt((p_hat * (1.0 - p_hat) / total) + (z**2 / (4.0 * (total**2))))

    lower_bound = (centre - spread) / denominator
    return max(0.0, float(lower_bound))


def validate_trade_expectation(
    prob: float,
    stake: float,
    payout: float,
    min_ev_ratio: float = 0.0,
) -> TradeExpectationResult:
    """Aplica o filtro matemático rigoroso para autorizar ou recusar uma proposta de contrato.

    Regra: O trade só é viável se EV_ratio > min_ev_ratio e P > P_be.
    """
    try:
        p_be = calculate_break_even_probability(stake, payout)
        ev = calculate_net_expected_value(prob, stake, payout)
        ev_ratio = calculate_net_ev_ratio(prob, stake, payout)
    except ValueError as exc:
        return TradeExpectationResult(
            stake=stake,
            payout=payout,
            estimated_prob=prob,
            break_even_prob=0.0,
            net_ev=0.0,
            net_ev_ratio=0.0,
            is_viable=False,
            rejection_reason=f"Erro de validação nos parâmetros: {exc}",
        )

    # Verificação de Vantagem Matemática Real
    if ev <= 0.0:
        return TradeExpectationResult(
            stake=stake,
            payout=payout,
            estimated_prob=prob,
            break_even_prob=p_be,
            net_ev=ev,
            net_ev_ratio=ev_ratio,
            is_viable=False,
            rejection_reason=(
                f"Expectativa matemática não positiva (EV={ev:.4f} USD, EV_ratio={ev_ratio:.2%}). "
                f"Probabilidade estimada ({prob:.2%}) inferior ou igual ao break-even ({p_be:.2%})."
            ),
        )

    if ev_ratio < min_ev_ratio:
        return TradeExpectationResult(
            stake=stake,
            payout=payout,
            estimated_prob=prob,
            break_even_prob=p_be,
            net_ev=ev,
            net_ev_ratio=ev_ratio,
            is_viable=False,
            rejection_reason=(
                f"EV ratio ({ev_ratio:.2%}) abaixo da margem mínima requerida ({min_ev_ratio:.2%})."
            ),
        )

    return TradeExpectationResult(
        stake=stake,
        payout=payout,
        estimated_prob=prob,
        break_even_prob=p_be,
        net_ev=ev,
        net_ev_ratio=ev_ratio,
        is_viable=True,
        rejection_reason=None,
    )
