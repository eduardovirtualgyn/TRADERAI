"""Roteador agregador da versão 1 da API."""

from fastapi import APIRouter
from backend.app.api.v1.agents import router as agents_router
from backend.app.api.v1.audit import router as audit_router
from backend.app.api.v1.auto_trader import router as auto_trader_router
from backend.app.api.v1.backtest import router as backtest_router
from backend.app.api.v1.deriv import router as deriv_router
from backend.app.api.v1.ensemble import router as ensemble_router
from backend.app.api.v1.executor import router as executor_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.risk import router as risk_router
from backend.app.api.v1.stats import router as stats_router
from backend.app.api.v1.strategies import router as strategies_router
from backend.app.api.v1.ticks import router as ticks_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(risk_router)
api_v1_router.include_router(deriv_router)
api_v1_router.include_router(ticks_router)
api_v1_router.include_router(stats_router)
api_v1_router.include_router(strategies_router)
api_v1_router.include_router(backtest_router)
api_v1_router.include_router(agents_router)
api_v1_router.include_router(ensemble_router)
api_v1_router.include_router(executor_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(auto_trader_router)
