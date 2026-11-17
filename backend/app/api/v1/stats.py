"""Rotas da API para testes estatísticos e avaliação de probabilidade."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.api.deps import get_statistical_evaluator, get_tick_collector
from backend.app.modules.statistical_engine.evaluator import (
    StatisticalAssessment,
    StatisticalEvaluator,
)
from backend.app.modules.tick_collector.collector import TickCollector

router = APIRouter(prefix="/stats", tags=["Statistical Engine"])


class CustomEvaluationPayload(BaseModel):
    """Payload para testar uma série arbitrária de dígitos."""

    digits: List[int] = Field(..., min_length=1, description="Lista de inteiros entre 0 e 9")
    stake: Optional[float] = Field(default=1.0, gt=0, description="Stake de teste em USD")
    payout: Optional[float] = Field(default=1.95, gt=0, description="Payout oficial em USD")


def _assessment_to_dict(assessment: StatisticalAssessment) -> dict:
    return {
        "sample_size": assessment.sample_size,
        "is_trade_recommended": assessment.is_trade_recommended,
        "recommended_direction": assessment.recommended_direction,
        "break_even_prob": assessment.break_even_prob,
        "rationale": assessment.rationale,
        "conditional_probabilities": {
            "even": assessment.conditional_p_even,
            "odd": assessment.conditional_p_odd,
            "state_sample_size": assessment.state_sample_size,
            "wilson_lower_even": assessment.wilson_lower_even,
            "wilson_lower_odd": assessment.wilson_lower_odd,
        },
        "expected_value": {
            "net_ev_ratio_even": assessment.net_ev_ratio_even,
            "net_ev_ratio_odd": assessment.net_ev_ratio_odd,
        },
        "randomness_tests": {
            "chi_square": {
                "statistic": assessment.chi2.statistic,
                "p_value": assessment.chi2.p_value,
                "is_uniform": assessment.chi2.is_uniform,
            },
            "runs_test": {
                "runs_count": assessment.runs_test.runs_count,
                "z_score": assessment.runs_test.z_score,
                "p_value": assessment.runs_test.p_value,
                "is_independent": assessment.runs_test.is_independent,
            },
            "shannon_entropy": {
                "entropy_bits": assessment.entropy.entropy_bits,
                "max_entropy_bits": assessment.entropy.max_entropy_bits,
                "entropy_ratio": assessment.entropy.entropy_ratio,
                "is_high_entropy": assessment.entropy.is_high_entropy,
            },
        },
    }


@router.get("/evaluation", summary="Avaliação estatística completa dos ticks atuais no buffer")
def evaluate_current_buffer(
    stake: float = 1.0,
    payout: float = 1.95,
    collector: TickCollector = Depends(get_tick_collector),
    evaluator: StatisticalEvaluator = Depends(get_statistical_evaluator),
) -> dict:
    """Executa Qui-Quadrado, Runs Test, Entropia, Markov e cálculo de Net EV nos ticks em memória."""
    ticks = collector.buffer.get_last_n_ticks(1000)
    assessment = evaluator.evaluate_ticks(ticks=ticks, stake=stake, payout=payout)
    return _assessment_to_dict(assessment)


@router.post("/custom-test", summary="Submete uma série personalizada de dígitos para análise estatística")
def evaluate_custom_series(
    payload: CustomEvaluationPayload,
    evaluator: StatisticalEvaluator = Depends(get_statistical_evaluator),
) -> dict:
    """Permite testar qualquer sequência manual de dígitos sem depender do feed ao vivo."""
    for d in payload.digits:
        if not (0 <= d <= 9):
            raise HTTPException(
                status_code=400,
                detail=f"Dígito inválido detectado: {d}. Todos os valores devem estar no intervalo [0, 9].",
            )

    assessment = evaluator.evaluate_series(
        digits=payload.digits,
        stake=payload.stake,
        payout=payload.payout,
    )
    return _assessment_to_dict(assessment)
