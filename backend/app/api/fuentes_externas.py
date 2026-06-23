"""
API Router — Fuentes externas de datos
Endpoints para DANE, REPS, ANSV, SIVIGILA, SISAIRE, HERE, ENSO y Sismicidad.
"""
import asyncio
import os
from fastapi import APIRouter
from app.services import fuentes_externas as svc

router = APIRouter()


@router.get("/dane/{zona_id}")
async def get_dane(zona_id: str):
    return await svc.obtener_dane(zona_id)


@router.get("/reps/{zona_id}")
async def get_reps(zona_id: str):
    return await svc.obtener_reps(zona_id)


@router.get("/ansv/{zona_id}")
async def get_ansv(zona_id: str):
    return await svc.obtener_ansv(zona_id)


@router.get("/sivigila/{zona_id}")
async def get_sivigila(zona_id: str):
    return await svc.obtener_sivigila(zona_id)


@router.get("/sisaire/{zona_id}")
async def get_sisaire(zona_id: str):
    return await svc.obtener_sisaire(zona_id)


@router.get("/here/{zona_id}")
async def get_here(zona_id: str):
    return await svc.obtener_here(zona_id, os.getenv("HERE_API_KEY"))


@router.get("/tomtom/{zona_id}")
async def get_tomtom(zona_id: str):
    """TomTom Traffic — TOMTOM_API_KEY vive en Railway, ningún usuario la ve."""
    return await svc.obtener_tomtom(zona_id)


@router.get("/tomorrow/{zona_id}")
async def get_tomorrow(zona_id: str):
    """Tomorrow.io clima hiperlocal — TOMORROW_IO_API_KEY vive en Railway."""
    return await svc.obtener_tomorrow(zona_id)


@router.get("/sismicidad/{zona_id}")
async def get_sismicidad(zona_id: str):
    """Sismos recientes en radio 250 km (USGS FDSNWS)."""
    return await svc.obtener_sismicidad(zona_id)


@router.get("/enso")
async def get_enso():
    """Índice ONI actual (NOAA CPC) — fase El Niño / La Niña / Neutro."""
    return await svc.obtener_enso()


@router.get("/resumen/{zona_id}")
async def get_resumen_fuentes(zona_id: str):
    """Todas las fuentes en una sola llamada — para el panel del dashboard."""
    (dane, reps, ansv, sivigila, sisaire, sismicidad, enso, embalse) = await asyncio.gather(
        svc.obtener_dane(zona_id),
        svc.obtener_reps(zona_id),
        svc.obtener_ansv(zona_id),
        svc.obtener_sivigila(zona_id),
        svc.obtener_sisaire(zona_id),
        svc.obtener_sismicidad(zona_id),
        svc.obtener_enso(),
        svc.obtener_nivel_embalse_xm(zona_id),
    )
    here = await svc.obtener_here(zona_id, os.getenv("HERE_API_KEY"))

    todas = [dane, reps, ansv, sivigila, sisaire, sismicidad, enso, embalse, here]
    activas = sum(1 for f in todas if f.get("fuente_real"))

    return {
        "zona_id": zona_id,
        "resumen": {
            "fuentes_activas": activas,
            "fuentes_total": len(todas),
            "cobertura_pct": round(activas / len(todas) * 100),
        },
        "dane": dane,
        "reps": reps,
        "ansv": ansv,
        "sivigila": sivigila,
        "sisaire": sisaire,
        "sismicidad": sismicidad,
        "enso": enso,
        "embalse": embalse,
        "here": here,
    }
