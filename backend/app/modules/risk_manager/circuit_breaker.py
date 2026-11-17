"""Módulo de Circuit Breaker Temporal (Cooldown de Risco).

Implementa pausas obrigatórias para evitar tempestade de ordens (order spam),
revenge trading ou operação contínua durante picos anômalos de volatilidade e sequências de perdas.
"""

import time
from dataclasses import dataclass
from typing import Optional
from backend.app.core.logging import logger


@dataclass(frozen=True)
class CircuitBreakerStatus:
    """Snapshot do estado do Circuit Breaker."""

    active: bool
    remaining_seconds: float
    reason: Optional[str] = None
    triggered_at_timestamp: Optional[float] = None
    cooldown_duration_seconds: float = 0.0


class CircuitBreaker:
    """Controlador de resfriamento temporal obrigatório."""

    def __init__(self, default_cooldown_seconds: float = 60.0):
        self.default_cooldown_seconds = float(default_cooldown_seconds)
        self._cooldown_until: float = 0.0
        self._triggered_at: Optional[float] = None
        self._reason: Optional[str] = None

    def trigger(self, reason: str, duration_seconds: Optional[float] = None) -> None:
        """Aciona o resfriamento por um intervalo de tempo em segundos."""
        now = time.time()
        duration = float(duration_seconds) if duration_seconds is not None else self.default_cooldown_seconds
        self._cooldown_until = now + duration
        self._triggered_at = now
        self._reason = reason

        logger.warning(
            "⏳ CIRCUIT BREAKER ACIONADO: Pausa obrigatória de %.1fs. Motivo: %s",
            duration,
            reason,
        )

    def is_active(self) -> bool:
        """Informa se o Circuit Breaker está ativamente bloqueando novas operações."""
        return time.time() < self._cooldown_until

    def remaining_seconds(self) -> float:
        """Tempo restante de bloqueio em segundos."""
        rem = self._cooldown_until - time.time()
        return max(0.0, round(rem, 1))

    def reset(self) -> None:
        """Desarma o Circuit Breaker manualmente."""
        self._cooldown_until = 0.0
        self._triggered_at = None
        self._reason = None
        logger.info("✅ CIRCUIT BREAKER RESETADO MANUALMENTE.")

    def get_status(self) -> CircuitBreakerStatus:
        """Retorna o status detalhado atual."""
        active = self.is_active()
        remaining = self.remaining_seconds()
        return CircuitBreakerStatus(
            active=active,
            remaining_seconds=remaining,
            reason=self._reason if active else None,
            triggered_at_timestamp=self._triggered_at if active else None,
            cooldown_duration_seconds=self.default_cooldown_seconds,
        )
