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

    direction = "NO_CONSENSUS"
    consensus_p = max(prediction.p_even, prediction.p_odd)
    if prediction.is_consensus_achieved and consensus_p >= 0.52:
        direction = "DIGITEVEN" if prediction.p_even > prediction.p_odd else "DIGITODD"

    break_even_p = 0.5128  # Payout padrão Deriv (1 / 1.95)
    wilson_lower = getattr(stats, "wilson_lower_bound", round(consensus_p - 0.02, 4))
    has_edge = bool(prediction.is_consensus_achieved and wilson_lower > break_even_p)

    return {
        "p_even": prediction.p_even,
        "p_odd": prediction.p_odd,
        "is_consensus_achieved": prediction.is_consensus_achieved,
        "discordance_spread": prediction.discordance_spread,
        "veto_reason": prediction.veto_reason,
        "individual_predictions": prediction.individual_predictions,
        "model_weights": prediction.weights,

        # Mapeamento estrito com os tipos do Frontend Next.js
        "consensus_direction": direction,
        "consensus_probability": consensus_p,
        "even_probability": prediction.p_even,
        "odd_probability": prediction.p_odd,
        "spread": prediction.discordance_spread,
        "is_discordant": not prediction.is_consensus_achieved,
        "wilson_lower_bound": wilson_lower,
        "break_even_probability": break_even_p,
        "has_mathematical_edge": has_edge,
    }
