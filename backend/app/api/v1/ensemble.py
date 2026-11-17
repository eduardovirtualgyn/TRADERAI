"""Rotas da API para consulta do status e predições do Model Ensemble."""

from fastapi import APIRouter, Depends
from backend.app.api.deps import (
    get_model_ensemble,
    get_statistical_evaluator,
    get_tick_collector,
)
from backend.app.modules.model_ensemble.ensemble import ModelEnsemble
from backend.app.modules.statistical_engine.evaluator import StatisticalEvaluator
from backend.app.modules.tick_collector.collector import TickCollector

router = APIRouter(prefix="/ensemble", tags=["Model Ensemble"])


@router.get("/status", summary="Consulta a configuração e modelos participantes do Ensemble")
def get_ensemble_status(
    ensemble: ModelEnsemble = Depends(get_model_ensemble),
) -> dict:
    """Retorna os hiperparâmetros de consenso e os estimadores ativos no ensemble."""
    return {
        "max_allowed_discordance": ensemble.max_allowed_discordance,
        "ai_models_count": len(ensemble.ai_models),
        "ai_models": [m.model_name for m in ensemble.ai_models],
    }


@router.get("/predict", summary="Gera a probabilidade agregada de consenso para o próximo tick")
def predict_ensemble(
    collector: TickCollector = Depends(get_tick_collector),
    evaluator: StatisticalEvaluator = Depends(get_statistical_evaluator),
    ensemble: ModelEnsemble = Depends(get_model_ensemble),
) -> dict:
    """Executa a combinação ponderada por Brier Score inverso e aplica o filtro de discordância."""
    ticks = collector.buffer.get_last_n_ticks(1000)
    stats = evaluator.evaluate_ticks(ticks=ticks)
    prediction = ensemble.predict(ticks=ticks, stats=stats)

    return {
        "p_even": prediction.p_even,
        "p_odd": prediction.p_odd,
        "is_consensus_achieved": prediction.is_consensus_achieved,
        "discordance_spread": prediction.discordance_spread,
        "veto_reason": prediction.veto_reason,
        "individual_predictions": prediction.individual_predictions,
        "model_weights": prediction.weights,
    }
