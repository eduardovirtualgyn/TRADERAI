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
    """Exceção base para falhas de comunicação ou protocolo com a Deriv API."""

    def __init__(
        self,
        message: str,
        error_type: str = "Erro na Deriv API",
        code: str = "DERIV_API_ERROR",
        detail: str = "",
        http_status: int = 502,
        stage: str = "UNKNOWN",
    ):
        super().__init__(message)
        self.error_type = error_type
        self.code = code
        self.detail = detail or message
        self.http_status = http_status
        self.stage = stage

    def to_dict(self) -> dict:
        """Serializa o erro em payload estruturado para a API."""
        return {
            "success": False,
            "error_type": self.error_type,
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "http_status": self.http_status,
            "stage": self.stage,
        }


class DerivConnectionError(DerivApiError):
    """Falha de conectividade (DNS, TLS, Timeout, Handshake 520, WebSocket rejeitado)."""

    def __init__(
        self,
        message: str = "Não foi possível estabelecer conexão com a Deriv API.",
        detail: str = "Handshake WebSocket rejeitado pelo gateway.",
        code: str = "WS_CONNECTION_FAILED",
        http_status: int = 520,
    ):
        super().__init__(
            message=message,
            error_type="Falha de conectividade",
            code=code,
            detail=detail,
            http_status=http_status,
            stage="CONNECTIVITY / HANDSHAKE",
        )


class DerivAuthError(DerivApiError):
    """Falha de autenticação (Token inválido, expirado, revogado ou conta incompatível)."""

    def __init__(
        self,
        message: str = "Falha de autenticação na Deriv API.",
        detail: str = "Token de API inválido, expirado ou não autorizado.",
        code: str = "AUTH_FAILED",
        http_status: int = 401,
    ):
        super().__init__(
            message=message,
            error_type="Falha de autenticação",
            code=code,
            detail=detail,
            http_status=http_status,
            stage="AUTHORIZATION",
        )


class DerivConfigError(DerivApiError):
    """Falha de configuração (App ID ausente, endpoint inválido, parâmetros ausentes)."""

    def __init__(
        self,
        message: str = "Configuração da Deriv API inválida ou incompleta.",
        detail: str = "Parâmetros obrigatórios ausentes ou incorretos.",
        code: str = "CONFIG_ERROR",
        http_status: int = 400,
    ):
        super().__init__(
            message=message,
            error_type="Falha de configuração",
            code=code,
            detail=detail,
            http_status=http_status,
            stage="CONFIGURATION",
        )


class DerivOperationalError(DerivApiError):
    """Erro operacional em runtime (rate limit, mercado fechado, subscrição indisponível)."""

    def __init__(
        self,
        message: str = "Erro operacional na sessão da Deriv API.",
        detail: str = "Operação rejeitada pelo servidor da Deriv.",
        code: str = "OPERATIONAL_ERROR",
        http_status: int = 503,
    ):
        super().__init__(
            message=message,
            error_type="Erro operacional",
            code=code,
            detail=detail,
            http_status=http_status,
            stage="OPERATIONAL",
        )
