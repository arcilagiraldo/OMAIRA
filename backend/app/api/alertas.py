"""
API Router — Alertas Automáticas
"""
from fastapi import APIRouter
from app.services.riesgo_service import generar_alertas

router = APIRouter()


@router.get("/{zona_id}")
async def get_alertas(zona_id: str):
    """Alertas activas para una zona"""
    alertas = await generar_alertas(zona_id)
    return {
        "zona_id": zona_id,
        "total_alertas": len(alertas),
        "alertas": alertas
    }


@router.get("/")
async def get_alertas_todas():
    """Todas las alertas activas en Antioquia"""
    zonas = ["guatape", "medellin", "rionegro"]
    todas = []
    for zona in zonas:
        alertas = await generar_alertas(zona)
        todas.extend(alertas)
    return {"total": len(todas), "alertas": todas}
