"""Módulo de tratamento de exceções customizadas do ODD/EVEN AI TRADER."""


class TraderBaseError(Exception):
    """Exceção base para todos os erros da plataforma."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class TraderSecurityError(TraderBaseError):
    """Disparada quando uma regra de segurança mandatória é violada."""
    pass


class NegativeEVError(TraderBaseError):
    """Disparada quando uma proposta de operação possui expectativa matemática nula ou negativa."""
    pass


class AntiMartingaleViolationError(TraderBaseError):
    """Disparada quando qualquer tentativa de aumentar stake após derrota é detectada."""
    pass


class RiskLimitExceededError(TraderBaseError):
    """Disparada quando limites de perda diária, teto de exposição ou perdas consecutivas são excedidos."""
    pass


class KillSwitchActiveError(TraderBaseError):
    """Disparada quando ordens são submetidas enquanto o Kill Switch está armado."""
    pass


class DerivApiError(TraderBaseError):
    """Disparada em falhas de comunicação ou protocolo com a Deriv WebSocket API."""
    pass
