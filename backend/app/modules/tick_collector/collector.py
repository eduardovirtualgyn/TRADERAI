"""Orquestrador do coletor de ticks, buffer circular e fila de persistência."""

from typing import List, Optional
from backend.app.core.logging import logger
from backend.app.modules.deriv_client.client import DerivWebSocketClient
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.tick_collector.buffer import TickBuffer
from backend.app.modules.tick_collector.storage import (
    BaseTickStorage,
    InMemoryTickStorage,
)
from backend.app.modules.tick_collector.streak_analyzer import (
    calculate_current_streak,
    calculate_window_distribution,
)


class TickCollector:
    """Coletor central de ticks com buffer circular de alta velocidade e fila em lote."""

    def __init__(
        self,
        buffer_capacity: int = 5000,
        batch_size: int = 50,
        storage: Optional[BaseTickStorage] = None,
    ):
        self.buffer = TickBuffer(capacity=buffer_capacity)
        self.batch_size = batch_size
        self.storage = storage or InMemoryTickStorage()

        self._pending_batch: List[TickData] = []
        self._client: Optional[DerivWebSocketClient] = None

    def bind_client(self, client: DerivWebSocketClient) -> None:
        """Conecta o coletor ao cliente WebSocket da Deriv."""
        self._client = client
        client.register_tick_callback(self.on_tick_received)
        logger.info("TickCollector acoplado com sucesso ao DerivWebSocketClient.")

    def unbind_client(self) -> None:
        """Desconecta o coletor do cliente WebSocket."""
        if self._client:
            self._client.unregister_tick_callback(self.on_tick_received)
            self._client = None
            logger.info("TickCollector desvinculado do cliente Deriv.")

    def on_tick_received(self, tick: TickData) -> None:
        """Processa a chegada de cada novo tick em tempo real (O(1))."""
        # 1. Alimenta o ring buffer em memória
        self.buffer.append(tick)

        # 2. Enfileira para persistência em lote
        self._pending_batch.append(tick)
        if len(self._pending_batch) >= self.batch_size:
            self.flush_pending_batch()

    def flush_pending_batch(self) -> int:
        """Despeja os ticks pendentes no armazenamento configurado."""
        if not self._pending_batch:
            return 0

        batch_to_save = self._pending_batch
        self._pending_batch = []

        try:
            saved_count = self.storage.save_batch(batch_to_save)
            return saved_count
        except Exception as exc:
            logger.error("Erro ao salvar lote de ticks: %s", exc)
            return 0

    def get_summary_snapshot(self) -> dict:
        """Gera um snapshot analítico consolidado do estado recente de mercado."""
        all_ticks = self.buffer.get_last_n_ticks(1000)
        streak = calculate_current_streak(all_ticks)

        standard_windows = [10, 50, 100, 500]
        window_stats = {}
        for w in standard_windows:
            if len(all_ticks) >= 1:
                dist = calculate_window_distribution(all_ticks, w)
                window_stats[str(w)] = {
                    "samples": dist.actual_samples,
                    "even_ratio": dist.even_ratio,
                    "odd_ratio": dist.odd_ratio,
                    "even_count": dist.even_count,
                    "odd_count": dist.odd_count,
                }
            else:
                window_stats[str(w)] = {
                    "samples": 0,
                    "even_ratio": 0.0,
                    "odd_ratio": 0.0,
                    "even_count": 0,
                    "odd_count": 0,
                }

        latest_tick = self.buffer.get_latest()

        # Frequência de dígitos nos últimos 100 ticks (ou todos disponíveis)
        digit_frequencies = {str(d): 0 for d in range(10)}
        sample_ticks = all_ticks[-100:] if len(all_ticks) >= 100 else all_ticks
        for t in sample_ticks:
            key = str(t.last_digit)
            digit_frequencies[key] = digit_frequencies.get(key, 0) + 1

        dist_100 = window_stats.get("100", {
            "samples": len(sample_ticks),
            "even_ratio": 0.5,
            "odd_ratio": 0.5,
            "even_count": sum(1 for t in sample_ticks if t.is_even),
            "odd_count": sum(1 for t in sample_ticks if not t.is_even),
        })

        last_ticks_data = [
            {
                "quote": t.quote,
                "last_digit": t.last_digit,
                "is_even": t.is_even,
                "epoch": t.epoch,
            }
            for t in all_ticks[-20:]
        ]

        return {
            # Compatibilidade com Next.js Frontend
            "buffer_count": len(self.buffer),
            "capacity": self.buffer.capacity,
            "current_streak_parity": streak.direction,
            "current_streak_length": streak.length,
            "last_ticks": last_ticks_data,
            "distribution_100": dist_100,
            "digit_frequencies": digit_frequencies,

            # Campos existentes do backend para integridade
            "buffer_size": len(self.buffer),
            "buffer_capacity": self.buffer.capacity,
            "total_ingested": self.buffer.total_ingested,
            "latest_quote": latest_tick.quote if latest_tick else None,
            "latest_epoch": latest_tick.epoch if latest_tick else None,
            "latest_digit": latest_tick.last_digit if latest_tick else None,
            "latest_is_even": latest_tick.is_even if latest_tick else None,
            "current_streak": {
                "direction": streak.direction,
                "length": streak.length,
                "last_digit": streak.last_digit,
            },
            "recent_digits_20": self.buffer.get_last_digits(20),
            "windows": window_stats,
        }
