"""
API Router — Riesgo Ambiental
"""
from fastapi import APIRouter, Query
from typing import Optional, List
from app.models.schemas import TipoRiesgo, HorizontePrediccion
from app.services.riesgo_service import calcular_riesgo_zona

router = APIRouter()


@router.get("/zona/{zona_id}")
async def get_riesgo_zona(
    zona_id: str,
    horizonte: HorizontePrediccion = HorizontePrediccion.H24,
    tipo: Optional[TipoRiesgo] = None,
):
    """Calcula riesgo actual para una zona específica"""
    return await calcular_riesgo_zona(zona_id, tipo_riesgo=tipo, horizonte=horizonte)


@router.get("/multihorizonte/{zona_id}")
async def get_riesgo_multihorizonte(zona_id: str):
    """Predicciones para todos los horizontes: 1h, 6h, 24h, 72h"""
    resultados = {}
    for h in HorizontePrediccion:
        resultados[h.value] = await calcular_riesgo_zona(zona_id, horizonte=h)
    return {"zona_id": zona_id, "horizontes": resultados}


@router.get("/mapa/{zona_id}")
async def get_mapa_riesgo(zona_id: str):
    """GeoJSON de riesgo para renderizar en mapa"""
    datos = await calcular_riesgo_zona(zona_id)
    features = []
    for pred in datos["predicciones"]:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [datos["lon"], datos["lat"]]
            },
            "properties": {
                "zona_id": zona_id,
                "municipio": datos["municipio"],
                "tipo_riesgo": pred["tipo_riesgo"],
                "nivel": pred["nivel"],
                "probabilidad": pred["probabilidad"],
                "color": _color_por_nivel(pred["nivel"]),
            }
        })
    return {"type": "FeatureCollection", "features": features}


def _color_por_nivel(nivel: str) -> str:
    colores = {
        "muy_bajo": "#22c55e",
        "bajo": "#84cc16",
        "medio": "#eab308",
        "alto": "#f97316",
        "muy_alto": "#ef4444",
        "critico": "#7f1d1d",
    }
    return colores.get(nivel, "#6b7280")
