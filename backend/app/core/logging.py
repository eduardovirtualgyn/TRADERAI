"""Configuração centralizada de logs para o ODD/EVEN AI TRADER."""

import logging
import sys


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configura o logger raiz com formatação uniforme e segura."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | [%(name)s:%(funcName)s:%(lineno)d] | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    logger = logging.getLogger("odd_even_trader")
    logger.setLevel(numeric_level)

    # Evita duplicação de handlers se a função for chamada mais de uma vez
    if not logger.handlers:
        logger.addHandler(handler)

    return logger


logger = setup_logging()
