"""API Router — Predicciones multihorizonte"""
# ╔══════════════════════════════════════════════════════════════════╗
# ║  ⚠️  ADVERTENCIA — ENDPOINT CON DATOS SIMULADOS  ⚠️              ║
# ║                                                                  ║
# ║  La función get_serie_temporal() (endpoint                       ║
# ║  GET /api/v1/prediccion/serie/{zona_id}) devuelve SIEMPRE        ║
# ║  72 puntos generados con random.uniform().                       ║
# ║                                                                  ║
# ║  NO hay ningún camino de datos reales implementado.              ║
# ║  NO hay flag fuente_real ni modo_degradado en la lógica          ║
# ║  interna — el endpoint respondía con datos inventados            ║
# ║  sin ninguna advertencia visible.                                ║
# ║                                                                  ║
# ║  Estado: HUÉRFANO — el frontend no lo consume (verificado        ║
# ║  Sesión 7, 2026-06-18). Si en el futuro se conecta a algún       ║
# ║  panel o gráfico, PRIMERO implementar una fuente real o al       ║
# ║  menos mantener el campo fuente_real: False en la respuesta.     ║
# ║                                                                  ║
# ║  Auditoría: docs/investigacion-dos-modelos-riesgo.md             ║
# ║  Hallazgo: Sección "Hallazgos adicionales", punto A              ║
# ╚══════════════════════════════════════════════════════════════════╝
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
    """Serie temporal de predicciones para gráficos — DATOS SIMULADOS, ver advertencia en cabecera del módulo."""
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
    return {
        "zona_id": zona_id,
        "serie": puntos,
        "fuente_real": False,
        "modo_degradado": True,
        "advertencia": "Datos simulados con random.uniform() — no representan predicciones reales. Ver cabecera del módulo prediccion.py.",
    }
