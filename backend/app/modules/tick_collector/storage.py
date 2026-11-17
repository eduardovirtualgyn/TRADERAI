"""Adaptadores de persistência para armazenamento em lote de ticks."""

from abc import ABC, abstractmethod
from typing import List
from backend.app.core.logging import logger
from backend.app.modules.deriv_client.models import TickData


class BaseTickStorage(ABC):
    """Interface abstrata para persistência assíncrona de ticks."""

    @abstractmethod
    def save_batch(self, ticks: List[TickData]) -> int:
        """Persiste um lote de ticks e retorna a quantidade armazenada."""
        pass


class InMemoryTickStorage(BaseTickStorage):
    """Armazenador em memória para execução de testes e operação sem banco externo."""

    def __init__(self):
        self.stored_ticks: List[TickData] = []

    def save_batch(self, ticks: List[TickData]) -> int:
        self.stored_ticks.extend(ticks)
        logger.debug("Lote de %d ticks salvo em memória. Total acumulado: %d", len(ticks), len(self.stored_ticks))
        return len(ticks)

    def count(self) -> int:
        return len(self.stored_ticks)

    def clear(self) -> None:
        self.stored_ticks.clear()
