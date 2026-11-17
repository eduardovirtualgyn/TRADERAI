"""Analisador de sequências (streaks) e distribuições de paridade em janelas deslizantes."""

from dataclasses import dataclass
from typing import Dict, List, Optional
from backend.app.modules.deriv_client.models import TickData


@dataclass(frozen=True)
class StreakInfo:
    """Informações sobre a sequência consecutiva atual de dígitos."""

    direction: str  # "EVEN", "ODD" ou "NONE"
    length: int
    last_digit: Optional[int] = None


@dataclass(frozen=True)
class WindowDistribution:
    """Distribuição de frequência de paridade em uma janela amostral."""

    window_size: int
    actual_samples: int
    even_count: int
    odd_count: int
    even_ratio: float
    odd_ratio: float
    digit_counts: Dict[int, int]


def calculate_current_streak(ticks: List[TickData]) -> StreakInfo:
    """Calcula a sequência contínua atual de paridade a partir do final da lista."""
    if not ticks:
        return StreakInfo(direction="NONE", length=0, last_digit=None)

    last_tick = ticks[-1]
    streak_is_even = last_tick.is_even
    streak_direction = "EVEN" if streak_is_even else "ODD"
    length = 0

    # Percorre de trás para frente até a primeira divergência de paridade
    for tick in reversed(ticks):
        if tick.is_even == streak_is_even:
            length += 1
        else:
            break

    return StreakInfo(
        direction=streak_direction,
        length=length,
        last_digit=last_tick.last_digit,
    )


def calculate_window_distribution(ticks: List[TickData], window_size: int) -> WindowDistribution:
    """Calcula a distribuição empírica de dígitos e proporção Par/Ímpar em uma janela."""
    if window_size <= 0:
        raise ValueError("O tamanho da janela deve ser maior que zero.")

    sample = ticks[-window_size:] if len(ticks) >= window_size else ticks
    total = len(sample)

    digit_counts = {d: 0 for d in range(10)}
    even_count = 0
    odd_count = 0

    for t in sample:
        digit_counts[t.last_digit] += 1
        if t.is_even:
            even_count += 1
        else:
            odd_count += 1

    even_ratio = (even_count / total) if total > 0 else 0.0
    odd_ratio = (odd_count / total) if total > 0 else 0.0

    return WindowDistribution(
        window_size=window_size,
        actual_samples=total,
        even_count=even_count,
        odd_count=odd_count,
        even_ratio=round(even_ratio, 4),
        odd_ratio=round(odd_ratio, 4),
        digit_counts=digit_counts,
    )
