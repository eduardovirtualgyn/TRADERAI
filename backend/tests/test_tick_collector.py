"""Testes unitários para o coletor de ticks, buffer circular e analisador de streaks."""

import pytest
from backend.app.api.v1.ticks import get_ticks_summary
from backend.app.modules.deriv_client.client import DerivWebSocketClient
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.tick_collector.buffer import TickBuffer
from backend.app.modules.tick_collector.collector import TickCollector
from backend.app.modules.tick_collector.storage import InMemoryTickStorage
from backend.app.modules.tick_collector.streak_analyzer import (
    calculate_current_streak,
    calculate_window_distribution,
)


def _make_tick(epoch: int, quote: float, pip_size: int = 2, symbol: str = "R_100") -> TickData:
    """Helper para instanciar TickData em testes."""
    return TickData.from_api_payload({
        "epoch": epoch,
        "quote": quote,
        "pip_size": pip_size,
        "symbol": symbol,
    })


def test_tick_buffer_capacity_and_overflow():
    """Valida integridade do ring buffer e descarte do tick mais antigo ao saturar."""
    buf = TickBuffer(capacity=3)
    assert buf.is_empty is True
    assert len(buf) == 0

    # Inserção de 3 ticks
    buf.append(_make_tick(1, 100.02))  # last_digit=2 (Even)
    buf.append(_make_tick(2, 100.04))  # last_digit=4 (Even)
    buf.append(_make_tick(3, 100.07))  # last_digit=7 (Odd)

    assert len(buf) == 3
    assert buf.is_full is True
    assert buf.total_ingested == 3
    assert buf.get_last_digits(3) == [2, 4, 7]

    # Inserção do 4º tick (deve descartar o 1º tick de quote 100.02)
    buf.append(_make_tick(4, 100.09))  # last_digit=9 (Odd)

    assert len(buf) == 3
    assert buf.total_ingested == 4
    assert buf.get_last_digits(3) == [4, 7, 9]
    assert buf.get_parity_series(3) == [True, False, False]
    assert buf.get_latest().last_digit == 9


def test_tick_buffer_clear():
    """Testa limpeza do buffer."""
    buf = TickBuffer(capacity=5)
    buf.append(_make_tick(1, 10.1))
    buf.append(_make_tick(2, 10.2))
    assert len(buf) == 2

    buf.clear()
    assert len(buf) == 0
    assert buf.total_ingested == 0
    assert buf.get_latest() is None


def test_streak_calculation_patterns():
    """Valida detecção de sequências consecutivas (streaks) de paridade."""
    # Cenário 1: Vazio
    streak_empty = calculate_current_streak([])
    assert streak_empty.direction == "NONE"
    assert streak_empty.length == 0
    assert streak_empty.last_digit is None

    # Cenário 2: Sequência de 4 pares consecutivos [2, 4, 8, 0]
    ticks_even = [
        _make_tick(1, 10.02),
        _make_tick(2, 10.04),
        _make_tick(3, 10.08),
        _make_tick(4, 10.00),
    ]
    streak_even = calculate_current_streak(ticks_even)
    assert streak_even.direction == "EVEN"
    assert streak_even.length == 4
    assert streak_even.last_digit == 0

    # Cenário 3: Interrupção por 1 ímpar [..., 0, 7]
    ticks_interrupted = ticks_even + [_make_tick(5, 10.07)]
    streak_odd = calculate_current_streak(ticks_interrupted)
    assert streak_odd.direction == "ODD"
    assert streak_odd.length == 1
    assert streak_odd.last_digit == 7


def test_window_distribution():
    """Testa proporção e frequência de dígitos em janela delimitada."""
    ticks = [
        _make_tick(1, 10.00),  # 0 (Even)
        _make_tick(2, 10.01),  # 1 (Odd)
        _make_tick(3, 10.02),  # 2 (Even)
        _make_tick(4, 10.03),  # 3 (Odd)
        _make_tick(5, 10.04),  # 4 (Even)
        _make_tick(6, 10.06),  # 6 (Even)
    ]
    # Total de 6 ticks: 4 pares (0, 2, 4, 6), 2 ímpares (1, 3)
    dist = calculate_window_distribution(ticks, window_size=6)
    assert dist.actual_samples == 6
    assert dist.even_count == 4
    assert dist.odd_count == 2
    assert dist.even_ratio == round(4 / 6, 4)
    assert dist.odd_ratio == round(2 / 6, 4)
    assert dist.digit_counts[0] == 1
    assert dist.digit_counts[4] == 1
    assert dist.digit_counts[5] == 0


def test_tick_collector_batch_flushing():
    """Garante que a fila em lote acumula e descarrega ticks no storage ao atingir o batch_size."""
    storage = InMemoryTickStorage()
    collector = TickCollector(buffer_capacity=100, batch_size=3, storage=storage)

    # 2 ticks (abaixo do batch_size 3)
    collector.on_tick_received(_make_tick(1, 50.11))
    collector.on_tick_received(_make_tick(2, 50.12))
    assert storage.count() == 0  # Ainda não descarregou

    # 3º tick (atinge o batch_size -> flush automático)
    collector.on_tick_received(_make_tick(3, 50.13))
    assert storage.count() == 3

    # Mais 1 tick e flush manual
    collector.on_tick_received(_make_tick(4, 50.14))
    assert storage.count() == 3
    flushed = collector.flush_pending_batch()
    assert flushed == 1
    assert storage.count() == 4


def test_tick_collector_bind_with_deriv_client():
    """Valida o desacoplamento e a transmissão de ticks do DerivClient para o TickCollector."""
    client = DerivWebSocketClient()
    collector = TickCollector(buffer_capacity=50)
    collector.bind_client(client)

    # Simula disparo de tick pelo cliente
    import json
    tick_raw = json.dumps({
        "tick": {
            "epoch": 1700000099,
            "quote": 123.48,
            "pip_size": 2,
            "symbol": "R_100",
        }
    })
    client._handle_message(tick_raw)

    assert len(collector.buffer) == 1
    assert collector.buffer.get_latest().last_digit == 8
    assert collector.buffer.get_latest().is_even is True

    collector.unbind_client()


def test_get_ticks_summary_endpoint():
    """Valida retorno do endpoint REST de resumo dos ticks."""
    collector = TickCollector(buffer_capacity=50)
    collector.on_tick_received(_make_tick(1, 200.12))
    collector.on_tick_received(_make_tick(2, 200.14))

    summary = get_ticks_summary(collector=collector)
    assert summary["buffer_size"] == 2
    assert summary["latest_digit"] == 4
    assert summary["latest_is_even"] is True
    assert summary["current_streak"]["direction"] == "EVEN"
    assert summary["current_streak"]["length"] == 2
    assert "10" in summary["windows"]
