"""OMAIRA v6 — Backend FastAPI"""
import asyncio
import re
import json
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

from app.api import riesgo, alertas, sensores, prediccion, configuracion
from app.api.avanzado import router_irg, router_ia
from app.api.auth import router as router_auth
from app.api.fuentes_externas import router as router_fuentes
from app.api.monitor import router as router_monitor
from app.api.storage import router as router_storage
from app.api.proxy import router as router_proxy
from app.api.fuentes_deteccion import router as router_deteccion
from app.api.notificaciones import router as router_notificaciones
from app.services.websocket_manager import ConnectionManager
from app.services.riesgo_service import generar_alertas
from app.services.openmeteo_service import obtener_meteo_real, COORDS_ZONAS
from app.services.database import init_pool, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()   # intenta conectar a PostgreSQL (falla silenciosamente si no hay DB)
    yield
    await close_pool()


app = FastAPI(title="OMAIRA v6 API", version="6.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers REST ──────────────────────────────────────────────────────────────
app.include_router(riesgo.router,          prefix="/api/v1/riesgo")
app.include_router(alertas.router,         prefix="/api/v1/alertas")
app.include_router(sensores.router,        prefix="/api/v1/sensores")
app.include_router(prediccion.router,      prefix="/api/v1/prediccion")
app.include_router(router_irg,             prefix="/api/v1/irg")
app.include_router(router_ia,              prefix="/api/v1/ia")
app.include_router(configuracion.router,   prefix="/api/v1/config")
app.include_router(router_auth,            prefix="/api/v1/auth")
app.include_router(router_fuentes,         prefix="/api/v1/fuentes")
app.include_router(router_monitor,         prefix="/api/v1/monitor")
app.include_router(router_storage,         prefix="/api/v1/storage")
app.include_router(router_proxy,           prefix="/api/v1/proxy")
app.include_router(router_deteccion,       prefix="/api/v1/fuentes/deteccion")
app.include_router(router_notificaciones,  prefix="/api/v1/notificaciones")

# ── WebSocket ─────────────────────────────────────────────────────────────────
manager = ConnectionManager()

_ZONA_RE = re.compile(r'^[a-z0-9_]{2,50}$')

# Umbral de lluvia intensa para notificación inmediata (mm/h genérico Antioquia)
_LLUVIA_INTENSA_MM = 20.0


@app.websocket("/ws/riesgo/{zona_id}")
async def ws_riesgo_zona(
    websocket: WebSocket,
    zona_id: str,
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
):
    """
    WebSocket bajo demanda para cualquier municipio de los 123.
    Solo envía eventos de alta velocidad: alertas nuevas, lluvia intensa.
    Datos de baja velocidad (embalse XM/SIMEM, censo DANE) no se envían
    por este canal — siguen su ciclo de polling normal en el frontend.

    El frontend pasa lat/lon del municipio seleccionado (del array MUNS)
    como query params para que el backend pueda consultar Open-Meteo con
    las coordenadas correctas aunque la zona no esté en COORDS_ZONAS.
    """
    if not _ZONA_RE.match(zona_id):
        await websocket.close(code=4004, reason="zona_id inválido")
        return

    connected = await manager.connect(websocket, zona_id)
    if not connected:
        return

    # Coordenadas: las del frontend (MUNS) o fallback a las del dict backend
    coord_lat, coord_lon = (lat, lon) if (lat and lon) else COORDS_ZONAS.get(zona_id, (6.2336, -75.1567))

    try:
        # Trackea alertas activas por (tipo_riesgo, nivel) para detectar solo las nuevas
        alertas_activas: set = set()

        while True:
            # ── Alertas nuevas ────────────────────────────────────────────────
            alertas = await generar_alertas(zona_id)
            sig_activas = {(a["tipo_riesgo"], a["nivel"]) for a in alertas}
            nuevas = sig_activas - alertas_activas
            for a in alertas:
                if (a["tipo_riesgo"], a["nivel"]) in nuevas:
                    await websocket.send_json({
                        "tipo": "alerta_nueva",
                        "zona_id": zona_id,
                        "mensaje": a["descripcion"],
                        "alerta": a,
                    })
            alertas_activas = sig_activas

            # ── Lluvia intensa ────────────────────────────────────────────────
            try:
                meteo = await obtener_meteo_real(zona_id, lat=coord_lat, lon=coord_lon)
                lluvia = meteo.get("lluvia_mm_1h", 0) or 0
                if lluvia >= _LLUVIA_INTENSA_MM:
                    await websocket.send_json({
                        "tipo": "lluvia_intensa",
                        "zona_id": zona_id,
                        "lluvia_mm_1h": round(lluvia, 1),
                        "mensaje": f"Lluvia intensa: {lluvia:.1f} mm/h",
                    })
            except Exception:
                pass  # fallo de meteo no interrumpe el ciclo

            await asyncio.sleep(30)

    except WebSocketDisconnect:
        manager.disconnect(websocket, zona_id)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "sistema": "OMAIRA v4"}


@app.get("/")
def root():
    return {"status": "OMAIRA v4 Backend activo", "version": "4.1.0"}
