"""Ponto de entrada da aplicação FastAPI do ODD/EVEN AI TRADER."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.api.v1.router import api_v1_router
from backend.app.core.config import get_settings
from backend.app.core.errors import (
    AntiMartingaleViolationError,
    KillSwitchActiveError,
    NegativeEVError,
    RiskLimitExceededError,
    TraderSecurityError,
)
from backend.app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerencia ciclo de vida do servidor FastAPI e validações pré-start."""
    settings = get_settings()

    logger.info("==================================================================")
    logger.info("🚀 INICIALIZANDO ODD/EVEN AI TRADER")
    logger.info("🔒 MODO OPERACIONAL: %s (CONTA DEMO)", settings.account_mode)
    logger.info("🛡️ SALVAGUARDA: CONTA REAL BLOQUEADA? %s", not settings.allow_real_account)
    logger.info("⛔ BANIMENTO DE MARTINGALE ATIVO: %s", settings.risk_ban_martingale)
    logger.info("📊 EXPECTATIVA LÍQUIDA MÍNIMA EXIGIDA: +%.1f%%", settings.min_net_ev_ratio * 100)
    logger.info("==================================================================")

    # Verificação redundante de integridade de segurança
    if settings.account_mode != "DEMO" or settings.allow_real_account:
        logger.critical("🚨 FALHA CRÍTICA DE SEGURANÇA: Tentativa de iniciar em modo não-DEMO.")
        raise TraderSecurityError("Operação bloqueada: apenas o modo DEMO é permitido.")

    # Conexão automática em segundo plano com a Deriv API (não-bloqueante)
    connect_task = None
    demo_token = settings.deriv_demo_token
    missing_token = not demo_token or demo_token == "seu_token_demo_aqui"
    if settings.deriv_simulator and missing_token:
        from backend.app.api.deps import get_auto_trader, get_deriv_client, get_risk_manager, get_tick_collector

        client = get_deriv_client()
        client.enable_explicit_simulator(settings.deriv_demo_initial_balance)
        if client.auth_info is not None:
            get_risk_manager().balance_usd = client.auth_info.balance
        _ = get_tick_collector()
        _ = get_auto_trader()
        logger.warning(
            "DERIV_SIMULATOR=true sem token: simulador opt-in ligado (loginid=SIMULATOR). "
            "Nenhuma ordem será enviada à Deriv e o painel não deve ser lido como conta demo."
        )
    elif missing_token:
        from backend.app.api.deps import get_deriv_client
        from backend.app.modules.deriv_client.models import DerivConnectionState

        client = get_deriv_client()
        client.state = DerivConnectionState.ERROR
        client.session_mode = "error"
        client.last_error = (
            "DERIV_DEMO_TOKEN ausente. O robô não conecta e não entra em simulador. "
            "Gere um PAT de conta demo com escopo trade, ou ligue DERIV_SIMULATOR=true para o modo local."
        )
        logger.error(client.last_error)
    if demo_token and demo_token != "seu_token_demo_aqui":
        import asyncio
        from backend.app.api.deps import (
            get_auto_trader,
            get_deriv_client,
            get_risk_manager,
            get_tick_collector,
        )

        async def auto_connect_deriv():
            max_attempts = 3
            base_delay = 2.0
            client = get_deriv_client()
            _ = get_tick_collector()  # Realiza o bind de callbacks
            _ = get_auto_trader()  # Inicializa o motor autônomo com callback de ticks

            for attempt in range(1, max_attempts + 1):
                try:
                    await asyncio.sleep(0.5 if attempt == 1 else base_delay * (2 ** (attempt - 2)))
                    logger.info("Tentativa %d/%d de auto-conexão com a Deriv...", attempt, max_attempts)
                    auth_info = await client.authorize()
                    await client.subscribe_ticks(settings.deriv_default_symbol)
                    risk_mgr = get_risk_manager()
                    if auth_info.balance > 0:
                        risk_mgr.balance_usd = auth_info.balance
                    logger.info(
                        "✅ Deriv WebSocket conectado e autenticado com sucesso em DEMO (%s)! Saldo: US$ %.2f",
                        auth_info.loginid,
                        auth_info.balance,
                    )
                    return
                except Exception as exc:
                    logger.warning("Falha na tentativa %d/%d de auto-conexão: %s", attempt, max_attempts, exc)

            logger.info("Auto-conexão em segundo plano pausada após %d tentativas. Painel pronto para conexão manual.", max_attempts)

        connect_task = asyncio.create_task(auto_connect_deriv())

    yield

    if connect_task and not connect_task.done():
        connect_task.cancel()

    from backend.app.api.deps import get_deriv_client
    client = get_deriv_client()
    if client.is_connected:
        await client.disconnect()

    logger.info("🛑 FINALIZANDO ODD/EVEN AI TRADER COM SEGURANÇA.")


def create_app() -> FastAPI:
    """Cria e configura a instância FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title="ODD/EVEN AI TRADER — API Quantitativa",
        description=(
            "Plataforma de negociação algorítmica para contratos Even/Odd na Deriv. "
            "Operação restrita a conta DEMO, sem estratégias de Martingale e condicionada "
            "a Expectativa Matemática Líquida Positiva (Net EV > 0)."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # Middleware CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Handlers Globais para Exceções do Domínio de Risco e Segurança
    @app.exception_handler(TraderSecurityError)
    async def security_error_handler(request: Request, exc: TraderSecurityError):
        logger.error("Violação de segurança detectada: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "SECURITY_VIOLATION", "message": exc.message},
        )

    @app.exception_handler(AntiMartingaleViolationError)
    async def anti_martingale_error_handler(request: Request, exc: AntiMartingaleViolationError):
        logger.warning("Bloqueio Anti-Martingale: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "ANTI_MARTINGALE_BLOCKED", "message": exc.message},
        )

    @app.exception_handler(KillSwitchActiveError)
    async def kill_switch_error_handler(request: Request, exc: KillSwitchActiveError):
        logger.warning("Tentativa de ação com Kill Switch ativo: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_423_LOCKED,
            content={"error": "KILL_SWITCH_ACTIVE", "message": exc.message},
        )

    @app.exception_handler(NegativeEVError)
    async def negative_ev_error_handler(request: Request, exc: NegativeEVError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "NEGATIVE_EV_REJECTED", "message": exc.message},
        )

    @app.exception_handler(RiskLimitExceededError)
    async def risk_limit_error_handler(request: Request, exc: RiskLimitExceededError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "RISK_LIMIT_EXCEEDED", "message": exc.message},
        )

    # Rotas
    app.include_router(api_v1_router)

    @app.get("/", tags=["Root"])
    def root():
        return {
            "name": "ODD/EVEN AI TRADER",
            "status": "online",
            "mode": settings.account_mode,
            "docs_url": "/docs",
        }

    return app


app = create_app()
