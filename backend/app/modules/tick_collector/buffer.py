"""Ring buffer em memória de alta performance para armazenamento de ticks.

Utiliza deque com capacidade máxima delimitada para garantir operações O(1) de inserção.
"""

from collections import deque
from typing import Deque, List, Optional
from backend.app.modules.deriv_client.models import TickData


class TickBuffer:
    """Buffer circular em memória para séries temporais de ticks."""

    def __init__(self, capacity: int = 5000):
        if capacity <= 0:
            raise ValueError("A capacidade do buffer deve ser estritamente positiva.")
        self.capacity = capacity
        self._buffer: Deque[TickData] = deque(maxlen=capacity)
        self._total_ingested: int = 0

    def append(self, tick: TickData) -> None:
        """Adiciona um novo tick ao buffer circular (O(1))."""
        self._buffer.append(tick)
        self._total_ingested += 1

    def append_batch(self, ticks: List[TickData]) -> None:
        """Adiciona múltiplos ticks em sequência."""
        for t in ticks:
            self.append(t)

    def __len__(self) -> int:
        """Retorna o número de ticks atualmente mantidos no buffer."""
        return len(self._buffer)

    @property
    def total_ingested(self) -> int:
        """Retorna a contagem acumulada total de ticks recebidos desde o início."""
        return self._total_ingested

    @property
    def is_empty(self) -> bool:
        """Indica se o buffer está vazio."""
        return len(self._buffer) == 0

    @property
    def is_full(self) -> bool:
        """Indica se o buffer atingiu sua capacidade máxima."""
        return len(self._buffer) >= self.capacity

    def get_latest(self) -> Optional[TickData]:
        """Retorna o tick mais recente inserido ou None se vazio."""
        if not self._buffer:
            return None
        return self._buffer[-1]

    def get_last_n_ticks(self, n: int) -> List[TickData]:
        """Retorna os últimos N ticks em ordem cronológica (mais antigo -> mais recente)."""
        if n <= 0:
            return []
        available = len(self._buffer)
        count = min(n, available)
        # Slicing a partir do final
        start_idx = available - count
        return [self._buffer[i] for i in range(start_idx, available)]

    def get_last_digits(self, n: int) -> List[int]:
        """Retorna apenas os últimos N dígitos inteiros observados."""
        ticks = self.get_last_n_ticks(n)
        return [t.last_digit for t in ticks]

    def get_parity_series(self, n: int) -> List[bool]:
        """Retorna a série de paridade dos últimos N dígitos (True = Even, False = Odd)."""
        ticks = self.get_last_n_ticks(n)
        return [t.is_even for t in ticks]

    def clear(self) -> None:
        """Limpa o buffer mantendo a capacidade configurada."""
        self._buffer.clear()
        self._total_ingested = 0
