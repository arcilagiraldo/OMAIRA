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
from app.services.riesgo_service import calcular_riesgo_zona
from app.services.openmeteo_service import obtener_meteo_real, COORDS_ZONAS
from app.models.schemas import NivelRiesgo
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

# Niveles que activan envío por WebSocket
_NIVELES_ALERTA = {NivelRiesgo.ALTO.value, NivelRiesgo.MUY_ALTO.value, NivelRiesgo.CRITICO.value}

# Umbral de lluvia reciente (mm/h) para distinguir creciente súbita de inundación gradual
_LLUVIA_INTENSA_MM = 20.0      # precursor directo: aguacero intenso → crecientes en minutos
_LLUVIA_CRECIENTE_MM = 15.0    # combinado con INUNDACION ALTO+ → creciente_quebradas

# ── Criterio de selección de eventos para WebSocket ──────────────────────────
# Un tipo de riesgo va por WebSocket SOLO SI el aviso instantáneo le da al
# operador una ventana real de tiempo para actuar ANTES de que el desastre ocurra.
#
# INCLUIDOS:
#   lluvia_intensa      → precursor directo: aguacero → deslizamiento/creciente en minutos
#   deslizamiento       → mayor mortalidad histórica en Antioquia (BanRep DTSer-317)
#   creciente_quebradas → puede arrasar viviendas en minutos tras lluvia intensa
#   inundacion          → similar a creciente pero con más margen; requiere aviso temprano
#   vendaval            → daño estructural súbito durante la tormenta misma
#
# DESCARTADOS (y por qué):
#   sismo_detectado     → cuando se detecta ya ocurrió; no hay ventana de evacuación
#   cambio_brusco_clima → genérico; reemplazado por los 5 tipos específicos de arriba
#   accidente_transito, congestion_vial, niebla_*, actividad_aerea
#                       → no amenazan vidas directamente ni requieren evacuación inmediata
#   incendio_forestal, sequia → propagación lenta; el ciclo normal de polling (15 min) es suficiente
# ─────────────────────────────────────────────────────────────────────────────


@app.websocket("/ws/riesgo/{zona_id}")
async def ws_riesgo_zona(
    websocket: WebSocket,
    zona_id: str,
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
):
    """
    WebSocket bajo demanda para cualquier municipio de los 123.
    Solo envía los 5 eventos con ventana real de acción antes del desastre.
    Datos de baja frecuencia (embalse XM/SIMEM, censo DANE, incendio, sequía)
    no se envían por este canal — siguen su ciclo de polling normal.

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

    # Coordenadas: las del frontend (MUNS) o fallback al dict backend
    coord_lat, coord_lon = (lat, lon) if (lat and lon) else COORDS_ZONAS.get(zona_id, (6.2336, -75.1567))

    try:
        # Trackea eventos activos por clave para enviar solo los que son nuevos
        eventos_activos: set = set()

        while True:
            resultado = await calcular_riesgo_zona(zona_id)
            preds = {p["tipo_riesgo"]: p for p in resultado["predicciones"]}
            meteo = resultado.get("metadata", {}).get("datos_meteo") or {}

            # Leer lluvia reciente desde Open-Meteo (no está en calcular_riesgo_zona)
            try:
                meteo_rt = await obtener_meteo_real(zona_id, lat=coord_lat, lon=coord_lon)
                lluvia_1h = meteo_rt.get("lluvia_mm_1h", 0) or 0
            except Exception:
                lluvia_1h = 0

            sig_eventos: set = set()
            envios = []

            # 1. lluvia_intensa — precursor directo: da minutos antes del deslizamiento/creciente
            if lluvia_1h >= _LLUVIA_INTENSA_MM:
                sig_eventos.add("lluvia_intensa")
                if "lluvia_intensa" not in eventos_activos:
                    envios.append({
                        "tipo": "lluvia_intensa",
                        "zona_id": zona_id,
                        "lluvia_mm_1h": round(lluvia_1h, 1),
                        "mensaje": f"Lluvia intensa: {lluvia_1h:.1f} mm/h — riesgo de deslizamiento y crecientes",
                    })

            # 2. deslizamiento — mayor mortalidad histórica Antioquia (BanRep DTSer-317)
            p_desl = preds.get("deslizamiento", {})
            if p_desl.get("nivel") in _NIVELES_ALERTA:
                clave = ("deslizamiento", p_desl["nivel"])
                sig_eventos.add(clave)
                if clave not in eventos_activos:
                    envios.append({
                        "tipo": "deslizamiento",
                        "zona_id": zona_id,
                        "nivel": p_desl["nivel"],
                        "probabilidad": p_desl.get("probabilidad"),
                        "mensaje": f"Riesgo {p_desl['nivel'].upper()} de deslizamiento — {p_desl.get('probabilidad', 0)*100:.1f}%",
                        "acciones": p_desl.get("acciones_recomendadas", []),
                    })

            # 3. creciente_quebradas — INUNDACION ALTO+ combinado con lluvia reciente intensa
            # El backend no tiene TipoRiesgo.CRECIENTE_QUEBRADAS; se detecta con el mismo
            # modelo H×E×V de INUNDACION cuando lluvia_mm_1h supera el umbral de creciente.
            p_inund = preds.get("inundacion", {})
            if p_inund.get("nivel") in _NIVELES_ALERTA and lluvia_1h >= _LLUVIA_CRECIENTE_MM:
                clave = ("creciente_quebradas", p_inund["nivel"])
                sig_eventos.add(clave)
                if clave not in eventos_activos:
                    envios.append({
                        "tipo": "creciente_quebradas",
                        "zona_id": zona_id,
                        "nivel": p_inund["nivel"],
                        "lluvia_mm_1h": round(lluvia_1h, 1),
                        "mensaje": f"Creciente súbita posible — {lluvia_1h:.1f} mm/h con riesgo {p_inund['nivel'].upper()} de inundación",
                        "acciones": p_inund.get("acciones_recomendadas", []),
                    })

            # 4. inundacion — lluvia acumulada (72h) → zonas bajas; más margen que creciente
            if p_inund.get("nivel") in _NIVELES_ALERTA:
                clave = ("inundacion", p_inund["nivel"])
                sig_eventos.add(clave)
                if clave not in eventos_activos:
                    envios.append({
                        "tipo": "inundacion",
                        "zona_id": zona_id,
                        "nivel": p_inund["nivel"],
                        "probabilidad": p_inund.get("probabilidad"),
                        "mensaje": f"Riesgo {p_inund['nivel'].upper()} de inundación — {p_inund.get('probabilidad', 0)*100:.1f}%",
                        "acciones": p_inund.get("acciones_recomendadas", []),
                    })

            # 5. vendaval — daño estructural súbito; usa TipoRiesgo.TORMENTA (viento + presión)
            p_torm = preds.get("tormenta", {})
            if p_torm.get("nivel") in _NIVELES_ALERTA:
                clave = ("vendaval", p_torm["nivel"])
                sig_eventos.add(clave)
                if clave not in eventos_activos:
                    envios.append({
                        "tipo": "vendaval",
                        "zona_id": zona_id,
                        "nivel": p_torm["nivel"],
                        "probabilidad": p_torm.get("probabilidad"),
                        "mensaje": f"Riesgo {p_torm['nivel'].upper()} de vendaval — {p_torm.get('probabilidad', 0)*100:.1f}%",
                        "acciones": p_torm.get("acciones_recomendadas", []),
                    })

            for evento in envios:
                await websocket.send_json(evento)
            eventos_activos = sig_eventos

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
