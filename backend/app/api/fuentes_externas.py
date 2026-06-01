"""
API Router — Fuentes externas de datos
Endpoints para DANE, REPS, ANSV, SIVIGILA, SISAIRE y HERE.
"""
import os
from fastapi import APIRouter
from app.services import fuentes_externas as svc

router = APIRouter()


@router.get("/dane/{zona_id}")
async def get_dane(zona_id: str):
    """Indicadores sociodemográficos DANE: NBI, población, vulnerabilidad."""
    return await svc.obtener_dane(zona_id)


@router.get("/reps/{zona_id}")
async def get_reps(zona_id: str):
    """Prestadores de servicios de salud habilitados (REPS - MinSalud)."""
    return await svc.obtener_reps(zona_id)


@router.get("/ansv/{zona_id}")
async def get_ansv(zona_id: str):
    """Sectores críticos de siniestralidad vial (ANSV)."""
    return await svc.obtener_ansv(zona_id)


@router.get("/sivigila/{zona_id}")
async def get_sivigila(zona_id: str):
    """Eventos de vigilancia epidemiológica activos (SIVIGILA - INS)."""
    return await svc.obtener_sivigila(zona_id)


@router.get("/sisaire/{zona_id}")
async def get_sisaire(zona_id: str):
    """Índice de Calidad del Aire - ICA (SISAIRE - IDEAM)."""
    return await svc.obtener_sisaire(zona_id)


@router.get("/here/{zona_id}")
async def get_here(zona_id: str):
    """Tráfico y rutas de evacuación (HERE Technologies)."""
    api_key = os.getenv("HERE_API_KEY")
    return await svc.obtener_here(zona_id, api_key)


@router.get("/resumen/{zona_id}")
async def get_resumen_fuentes(zona_id: str):
    """
    Consolida todas las fuentes externas en una sola respuesta.
    Útil para el panel de estado de fuentes en el frontend.
    """
    import asyncio
    dane, reps, ansv, sivigila, sisaire = await asyncio.gather(
        svc.obtener_dane(zona_id),
        svc.obtener_reps(zona_id),
        svc.obtener_ansv(zona_id),
        svc.obtener_sivigila(zona_id),
        svc.obtener_sisaire(zona_id),
    )
    here = await svc.obtener_here(zona_id, os.getenv("HERE_API_KEY"))

    fuentes = [dane, reps, ansv, sivigila, sisaire, here]
    activas = sum(1 for f in fuentes if f.get("fuente_real"))
    total = len(fuentes)

    return {
        "zona_id": zona_id,
        "resumen": {
            "fuentes_activas": activas,
            "fuentes_total": total,
            "cobertura_pct": round(activas / total * 100),
        },
        "dane": dane,
        "reps": reps,
        "ansv": ansv,
        "sivigila": sivigila,
        "sisaire": sisaire,
        "here": here,
    }
