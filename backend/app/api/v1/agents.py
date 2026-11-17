"""Rotas da API para gerenciamento, treinamento e predição dos Agentes de IA."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.deps import get_ai_trainer, get_tick_collector
from backend.app.modules.ai_agents.trainer import AIAgentTrainer
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.tick_collector.collector import TickCollector

router = APIRouter(prefix="/agents", tags=["AI Agents"])


class AITrainRequest(BaseModel):
    """Payload para acionamento de treinamento dos modelos supervisionados."""

    ticks_source: str = Field(default="buffer", description="'buffer' para usar ticks em memória ou 'custom'")
    custom_digits: Optional[List[int]] = Field(default=None, description="Lista opcional de dígitos para treino customizado")
    min_history: int = Field(default=30, ge=15, description="Passos mínimos de histórico para formação de features")


@router.get("/status", summary="Consulta o estado de calibração e métricas dos modelos de IA")
def get_ai_status(
    trainer: AIAgentTrainer = Depends(get_ai_trainer),
) -> dict:
    """Retorna se os modelos estão treinados, acurácia e Brier Score de validação."""
    return trainer.get_status()


@router.post("/train", summary="Executa o treinamento e calibração supervisionada dos modelos de IA")
def train_ai_agents(
    request: AITrainRequest,
    collector: TickCollector = Depends(get_tick_collector),
    trainer: AIAgentTrainer = Depends(get_ai_trainer),
) -> dict:
    """Extrai features, divide em treino/validação out-of-fold e calibra as probabilidades."""
    if request.ticks_source == "custom":
        if not request.custom_digits:
            raise HTTPException(
                status_code=400,
                detail="O campo 'custom_digits' é obrigatório quando 'ticks_source' for 'custom'.",
            )
        ticks = [
            TickData.from_api_payload({
                "epoch": 1700000000 + i,
                "quote": 100.0 + (d / 100.0),
                "pip_size": 2,
                "symbol": "R_100",
            })
            for i, d in enumerate(request.custom_digits)
        ]
    else:
        ticks = collector.buffer.get_last_n_ticks(5000)

    try:
        report = trainer.train_all(ticks=ticks, min_history=request.min_history)
        return {
            "success": True,
            "training_report": report,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/predict", summary="Gera a probabilidade calibrada para o próximo tick")
def predict_next_tick(
    collector: TickCollector = Depends(get_tick_collector),
    trainer: AIAgentTrainer = Depends(get_ai_trainer),
) -> dict:
    """Aplica os modelos treinados sobre os ticks recentes no buffer para estimar P(EVEN) e P(ODD)."""
    ticks = collector.buffer.get_last_n_ticks(100)
    try:
        predictions = trainer.predict_next(ticks=ticks)
        return predictions
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
