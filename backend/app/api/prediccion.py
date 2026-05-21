"""API Router — Predicciones multihorizonte"""
from fastapi import APIRouter
from app.services.riesgo_service import calcular_riesgo_zona
from app.models.schemas import HorizontePrediccion, TipoRiesgo
from typing import Optional

router = APIRouter()

@router.get("/{zona_id}")
async def get_prediccion(
    zona_id: str,
    horizonte: HorizontePrediccion = HorizontePrediccion.H24,
    tipo: Optional[TipoRiesgo] = None,
):
    return await calcular_riesgo_zona(zona_id, tipo_riesgo=tipo, horizonte=horizonte)

@router.get("/serie/{zona_id}")
async def get_serie_temporal(zona_id: str):
    """Serie temporal de predicciones para gráficos"""
    import random
    from datetime import datetime, timedelta
    puntos = []
    base = datetime.utcnow()
    for i in range(72):
        puntos.append({
            "timestamp": (base + timedelta(hours=i)).isoformat(),
            "deslizamiento": round(random.uniform(0.05, 0.75), 3),
            "inundacion": round(random.uniform(0.02, 0.60), 3),
            "incendio": round(random.uniform(0.01, 0.40), 3),
        })
    return {"zona_id": zona_id, "serie": puntos}
