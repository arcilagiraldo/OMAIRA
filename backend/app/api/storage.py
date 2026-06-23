"""
API de almacenamiento online — reemplaza localStorage del frontend.
Persiste en PostgreSQL de Railway: IRG historial, preferencias, reportes, outcomes.
Todos los endpoints son opcionales: si la DB no está disponible, devuelven vacío/ok.
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional, List
from app.services.database import (
    guardar_irg_historial, get_irg_historial,
    guardar_preferencias, get_preferencias,
    guardar_reporte, get_reportes, get_reportes_confirmados,
    guardar_outcome, get_outcomes,
    get_api_zona,
    guardar_prediccion_compartida, get_predicciones_recientes,
)

router = APIRouter()


# ── IRG Historial ─────────────────────────────────────────────────────────────

class IRGEntry(BaseModel):
    email: str
    zona_id: str
    irg: float
    nivel: str
    fuentes: List[str] = []


@router.post("/irg")
async def post_irg(body: IRGEntry):
    await guardar_irg_historial(body.email, body.zona_id, body.irg, body.nivel, body.fuentes)
    return {"ok": True}


@router.get("/irg/{zona_id}")
async def get_irg(zona_id: str, email: str = Query(...), horas: int = Query(48)):
    data = await get_irg_historial(email, zona_id, min(horas, 720))
    return {"zona_id": zona_id, "historial": data, "n": len(data)}


# ── Preferencias usuario ──────────────────────────────────────────────────────

class Preferencias(BaseModel):
    email: str
    zona_activa: str = "guatape"
    horizonte: str = "24h"
    prefs: dict = {}


@router.get("/prefs")
async def get_prefs(email: str = Query(...)):
    data = await get_preferencias(email)
    return {"email": email, **data} if data else {"email": email, "zona_activa": "guatape", "horizonte": "24h", "prefs": {}}


@router.put("/prefs")
async def put_prefs(body: Preferencias):
    await guardar_preferencias(body.email, body.zona_activa, body.horizonte, body.prefs)
    return {"ok": True}


# ── Reportes ciudadanos ───────────────────────────────────────────────────────

class Reporte(BaseModel):
    zona_id: str
    tipo: str
    descripcion: Optional[str] = ""
    lat: float = 0.0
    lon: float = 0.0
    email: str = "anonimo"


@router.post("/reportes")
async def post_reporte(body: Reporte):
    rid = await guardar_reporte(body.zona_id, body.tipo, body.descripcion,
                                body.lat, body.lon, body.email)
    return {"ok": True, "id": rid}


@router.get("/reportes/{zona_id}")
async def get_reportes_zona(zona_id: str, horas: int = Query(48)):
    data = await get_reportes(zona_id, min(horas, 168))
    return {"zona_id": zona_id, "reportes": data, "n": len(data)}


@router.get("/api/{zona_id}")
async def get_api_endpoint(zona_id: str):
    """API hidrológico actual de la zona — fuente de verdad compartida entre clientes."""
    data = await get_api_zona(zona_id)
    return {"zona_id": zona_id, "api_valor": data["valor"] if data else 0.0,
            "ts": data["ts"] if data else None}


@router.get("/reportes/{zona_id}/confirmados")
async def get_reportes_confirmados_zona(zona_id: str,
                                        ventana_horas: int = Query(1),
                                        umbral: int = Query(3)):
    """
    Tipos de evento con ≥ umbral reportes de usuarios distintos en la
    ventana indicada. Usado por el WebSocket para disparar alertas a vecinos.
    """
    data = await get_reportes_confirmados(zona_id, min(ventana_horas, 6), max(umbral, 2))
    return {"zona_id": zona_id, "confirmados": data, "n": len(data)}


# ── Predicciones compartidas ──────────────────────────────────────────────────

class PrediccionPayload(BaseModel):
    zona_id: str
    tipo_riesgo: str
    modelo_id: str
    probabilidad: float
    dispositivo_hash: Optional[str] = None


@router.post("/predicciones")
async def post_prediccion(payload: PrediccionPayload):
    await guardar_prediccion_compartida(
        payload.zona_id, payload.tipo_riesgo, payload.modelo_id,
        payload.probabilidad, payload.dispositivo_hash,
    )
    return {"ok": True}


@router.get("/predicciones/{zona_id}/{tipo_riesgo}/recientes")
async def get_predicciones_zona(zona_id: str, tipo_riesgo: str,
                                ventana_minutos: int = Query(5)):
    data = await get_predicciones_recientes(zona_id, tipo_riesgo,
                                            min(int(ventana_minutos), 60))
    return {"zona_id": zona_id, "tipo_riesgo": tipo_riesgo,
            "predicciones": data, "n": len(data)}


# ── Outcomes credibilidad ─────────────────────────────────────────────────────

class Outcome(BaseModel):
    zona_id: str
    tipo_riesgo: str
    email: str
    ocurrio: int
    prob_predicha: float = 0.5


@router.post("/outcomes")
async def post_outcome(body: Outcome):
    await guardar_outcome(body.zona_id, body.tipo_riesgo, body.email,
                          body.ocurrio, body.prob_predicha)
    return {"ok": True}


@router.get("/outcomes/{zona_id}/{tipo_riesgo}")
async def get_outcomes_route(zona_id: str, tipo_riesgo: str):
    data = await get_outcomes(zona_id, tipo_riesgo)
    return {"zona_id": zona_id, "tipo_riesgo": tipo_riesgo, "outcomes": data, "n": len(data)}
