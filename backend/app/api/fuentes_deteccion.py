"""
Detección automática de fuentes de datos externas.
Analiza una URL nueva, clasifica su contenido y gestiona el ciclo
pendiente → aprobada / rechazada SIN activar nada automáticamente.
"""
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Almacenamiento en memoria (primario; DB opcional como secundario) ──────────
_fuentes_pendientes: Dict[str, Dict] = {}


# ── Heurísticas de clasificación ─────────────────────────────────────────────
# Solo variables que integrarFuentesCustomEnSensores() realmente consume.
# Variables derivadas internamente (turismo, creciente, vendaval, etc.) NO están aquí.
HEURISTICAS: Dict[str, Dict] = {
    "lluvia": {
        "keywords": ["precipitation", "precip", "rain", "rainfall", "lluvia",
                     "pp_mm", "rain_mm", "precip_mm", "precipitation_mm",
                     "rainfall_mm", "lluvia_mm", "llovizna"],
        "descripcion": "Lluvia / precipitación (mm)",
    },
    "nivel_rio": {
        "keywords": ["nivel", "level", "stage", "altura", "water_level",
                     "caudal", "flow", "discharge", "cota", "gauge",
                     "nivel_rio", "nivel_m", "water_stage"],
        "descripcion": "Nivel río / caudal",
    },
    "temperatura": {
        "keywords": ["temperatura", "temp", "temperature", "air_temp",
                     "t_aire", "temp_c", "temp_f", "air_temperature",
                     "temperature_2m", "t2m"],
        "descripcion": "Temperatura del aire (°C)",
    },
    "viento": {
        "keywords": ["viento", "wind", "wind_speed", "windspeed",
                     "velocidad_viento", "wind_kmh", "wind_ms", "wspd",
                     "wind_speed_10m", "velocidad"],
        "descripcion": "Velocidad del viento (m/s)",
    },
    "calidad_aire": {
        "keywords": ["ica", "aqi", "pm25", "pm2_5", "pm10", "no2",
                     "co2", "ozone", "o3", "air_quality", "calidad_aire",
                     "contaminacion", "european_aqi", "us_aqi"],
        "descripcion": "Calidad del aire / ICA (AQI)",
    },
    "embalse": {
        "keywords": ["embalse", "reservoir", "level_pct", "volumen_util",
                     "nivel_pct", "nivel_embalse", "storage_pct", "llenado",
                     "VolumenUtilPorcentaje", "volumen_porcentaje"],
        "descripcion": "Nivel de embalse (%)",
    },
    "sismo": {
        "keywords": ["magnitude", "magnitud", "mag", "depth", "profundidad",
                     "epicenter", "epicentro", "richter", "mw", "ml",
                     "seismic", "sismos"],
        "descripcion": "Sismicidad (magnitud)",
    },
}


def _extraer_campos(obj, prof: int = 0, prefijo: str = "") -> List[str]:
    """Extrae nombres de campo de un JSON hasta profundidad 4, máx 25 keys/nivel."""
    if prof > 4 or not isinstance(obj, (dict, list)):
        return []
    campos = []
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:25]:
            campos.append(prefijo + k)
            campos.extend(_extraer_campos(v, prof + 1, prefijo + k + "."))
    elif isinstance(obj, list) and obj:
        campos.extend(_extraer_campos(obj[0], prof + 1, prefijo + "[0]."))
    return campos


def _clasificar(campos: List[str], muestra: str) -> Tuple[str, str, float]:
    """
    Puntúa cada variable IRG contra los campos detectados.
    Retorna (variable, estado, confianza_0_1).

    Umbral:
      score_top >= 3 Y score_top >= 2 × score_segundo → RECONOCIDA
      score_top >= 1 pero criterio no cumplido          → AMBIGUA
      score_top == 0                                    → AMBIGUA sin variable

    El score mínimo de 3 exige al menos un match exacto (campo == keyword, +3 pts),
    evitando que menciones de palabras en texto libre activen una integración.
    El factor 2× evita clasificar como reconocida una API que mezcla variables.
    """
    muestra_l = muestra.lower()
    scores: Dict[str, int] = {}

    for var, cfg in HEURISTICAS.items():
        score = 0
        for kw in cfg["keywords"]:
            kw_l = kw.lower()
            # Match exacto en nombre de campo: +3
            if any(c.split(".")[-1].lower() == kw_l for c in campos):
                score += 3
            # Match parcial en nombre de campo: +2
            elif any(kw_l in c.lower() for c in campos):
                score += 2
            # Match en texto de muestra: +1
            elif kw_l in muestra_l:
                score += 1
        if score > 0:
            scores[var] = score

    if not scores:
        return ("", "ambigua", 0.0)

    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_var, top_score = ranking[0]
    segundo_score = ranking[1][1] if len(ranking) > 1 else 0

    if top_score >= 3 and top_score >= segundo_score * 2:
        confianza = min(1.0, top_score / 8.0)
        return (top_var, "reconocida", confianza)

    confianza = min(0.49, top_score / 8.0)
    return (top_var, "ambigua", confianza)


def _detectar_formato(content_type: str, body: str) -> Tuple[str, Optional[object]]:
    """Detecta formato y parsea si puede. Retorna (formato, datos_o_None)."""
    ct = content_type.lower()
    stripped = body.strip()

    if "json" in ct or stripped.startswith(("{", "[")):
        try:
            return ("json", json.loads(body))
        except Exception:
            return ("json_invalido", None)

    if "xml" in ct or stripped.startswith("<"):
        return ("xml", None)

    if "csv" in ct:
        lines = stripped.split("\n")
        if len(lines) > 1 and "," in lines[0]:
            return ("csv", lines[0].split(","))
        return ("csv", None)

    if "text" in ct:
        return ("texto_plano", None)

    return ("desconocido", None)


# ── Persistencia opcional en DB ───────────────────────────────────────────────

async def _db_guardar(fuente: Dict) -> None:
    try:
        from app.services.database import _pool
        if not _pool:
            return
        async with _pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO fuentes_detectadas
                   (id, url, nombre_sugerido, estado, formato_detectado,
                    variable_sugerida, confianza, campos_detectados, muestra_cruda,
                    motivo_rechazo, fecha_deteccion)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                   ON CONFLICT (id) DO UPDATE
                   SET estado=$4, variable_sugerida=$6, motivo_rechazo=$10,
                       aprobada_por=EXCLUDED.aprobada_por, fecha_decision=EXCLUDED.fecha_decision""",
                fuente["id"], fuente["url"], fuente.get("nombre_sugerido"),
                fuente["estado"], fuente.get("formato_detectado"),
                fuente.get("variable_sugerida"), fuente.get("confianza"),
                json.dumps(fuente.get("campos_detectados", [])),
                fuente.get("muestra_cruda", "")[:500],
                fuente.get("motivo_rechazo"),
                datetime.now(timezone.utc),
            )
    except Exception as e:
        logger.debug(f"_db_guardar fuentes_detectadas: {e}")


async def _db_actualizar_estado(fuente_id: str, estado: str,
                                 aprobada_por: Optional[str] = None,
                                 motivo: Optional[str] = None) -> None:
    try:
        from app.services.database import _pool
        if not _pool:
            return
        async with _pool.acquire() as conn:
            await conn.execute(
                """UPDATE fuentes_detectadas
                   SET estado=$2, aprobada_por=$3, motivo_rechazo=$4, fecha_decision=NOW()
                   WHERE id=$1""",
                fuente_id, estado, aprobada_por, motivo,
            )
    except Exception as e:
        logger.debug(f"_db_actualizar_estado: {e}")


# ── Modelos de request ─────────────────────────────────────────────────────────

class AnalizarRequest(BaseModel):
    url: str
    nombre_sugerido: Optional[str] = None


class AprobarRequest(BaseModel):
    variable_irg_confirmada: Optional[str] = None
    zonas_cobertura: Optional[List[str]] = None
    aprobada_por: Optional[str] = None


class RechazarRequest(BaseModel):
    motivo: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/analizar")
async def analizar_fuente_nueva(req: AnalizarRequest):
    """
    Prueba una URL, analiza su contenido y retorna clasificación SIN activarla.
    Nunca toca el IRG — el resultado queda pendiente de aprobación manual.
    """
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL debe comenzar con http:// o https://")

    fuente_id = f"fd_{int(time.time() * 1000)}"

    # 1. Llamada real con timeout 10s
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Accept": "application/json, text/plain, */*"})
        body = resp.text
        content_type = resp.headers.get("content-type", "")
        http_ok = resp.status_code < 400
    except Exception as e:
        fuente = {
            "id": fuente_id,
            "url": url,
            "nombre_sugerido": req.nombre_sugerido,
            "estado": "rechazada_sin_respuesta",
            "formato_detectado": None,
            "variable_sugerida": None,
            "confianza": 0.0,
            "campos_detectados": [],
            "muestra_cruda": "",
            "motivo_rechazo": f"Sin respuesta: {str(e)[:200]}",
            "fecha_deteccion": datetime.now(timezone.utc).isoformat(),
        }
        _fuentes_pendientes[fuente_id] = fuente
        await _db_guardar(fuente)
        return fuente

    if not http_ok:
        fuente = {
            "id": fuente_id,
            "url": url,
            "nombre_sugerido": req.nombre_sugerido,
            "estado": "rechazada_sin_respuesta",
            "formato_detectado": None,
            "variable_sugerida": None,
            "confianza": 0.0,
            "campos_detectados": [],
            "muestra_cruda": body[:200],
            "motivo_rechazo": f"HTTP {resp.status_code}",
            "fecha_deteccion": datetime.now(timezone.utc).isoformat(),
        }
        _fuentes_pendientes[fuente_id] = fuente
        await _db_guardar(fuente)
        return fuente

    # 2. Detectar formato y parsear
    formato, datos = _detectar_formato(content_type, body)
    muestra_cruda = body[:400]

    # 3. Extraer campos y clasificar
    campos: List[str] = []
    if formato == "json" and isinstance(datos, (dict, list)):
        campos = _extraer_campos(datos)
    elif formato == "csv" and isinstance(datos, list):
        campos = datos  # headers CSV

    variable, clasificacion, confianza = _clasificar(campos, muestra_cruda)

    # 4. Determinar estado final
    if clasificacion == "reconocida":
        estado = "pendiente_aprobacion"
        motivo = None
    else:
        estado = "rechazada_ambigua"
        if not variable:
            motivo = f"No se detectaron campos compatibles con ninguna variable IRG. Formato: {formato}. Campos encontrados: {', '.join(campos[:8]) or 'ninguno'}."
        else:
            motivo = f"Coincidencias débiles o múltiples variables posibles (top: '{variable}', confianza {confianza:.0%}). Se requiere selección manual."

    fuente = {
        "id": fuente_id,
        "url": url,
        "nombre_sugerido": req.nombre_sugerido,
        "estado": estado,
        "formato_detectado": formato,
        "variable_sugerida": variable or None,
        "confianza": round(confianza, 3),
        "campos_detectados": campos[:30],
        "muestra_cruda": muestra_cruda,
        "motivo_rechazo": motivo,
        "fecha_deteccion": datetime.now(timezone.utc).isoformat(),
    }
    if clasificacion == "reconocida" and variable:
        from app.services.pendientes_verificacion import verificar_si_resuelve_pendiente
        pendiente = verificar_si_resuelve_pendiente(variable)
        if pendiente:
            fuente["resuelve_pendientes"] = pendiente["tipos_afectados"]
            fuente["nota_pendiente"] = (
                f"Esta fuente, si se aprueba, podria resolver la limitacion "
                f"documentada para: {', '.join(pendiente['tipos_afectados'])}. "
                f"Motivo actual: {pendiente['motivo']}"
            )
    _fuentes_pendientes[fuente_id] = fuente
    await _db_guardar(fuente)

    logger.info(f"Fuente analizada: {url} → {estado} / {variable} ({confianza:.0%})")
    return fuente


@router.get("/pendientes")
async def listar_pendientes():
    """Lista todas las fuentes en estado pendiente_aprobacion."""
    pendientes = [f for f in _fuentes_pendientes.values()
                  if f["estado"] == "pendiente_aprobacion"]
    return {"total": len(pendientes), "fuentes": pendientes}


@router.get("/todas")
async def listar_todas():
    """Lista todas las fuentes detectadas (todos los estados)."""
    fuentes = sorted(_fuentes_pendientes.values(),
                     key=lambda f: f.get("fecha_deteccion", ""), reverse=True)
    return {"total": len(fuentes), "fuentes": fuentes}


@router.post("/{fuente_id}/aprobar")
async def aprobar_fuente(fuente_id: str, req: AprobarRequest = AprobarRequest()):
    """
    Aprueba una fuente pendiente o ambigua.
    Si la fuente era ambigua, variable_irg_confirmada es obligatoria.
    El sistema NO activa nada — devuelve los datos para que el frontend
    los guarde en localStorage con activa=true.
    """
    fuente = _fuentes_pendientes.get(fuente_id)
    if not fuente:
        raise HTTPException(404, f"Fuente {fuente_id} no encontrada")

    if fuente["estado"] not in ("pendiente_aprobacion", "rechazada_ambigua"):
        raise HTTPException(409, f"Fuente ya está en estado '{fuente['estado']}'")

    # Para fuentes ambiguas, la variable confirmada es obligatoria
    if fuente["estado"] == "rechazada_ambigua" and not req.variable_irg_confirmada:
        raise HTTPException(422, "variable_irg_confirmada es obligatoria para fuentes ambiguas")

    variable_final = req.variable_irg_confirmada or fuente.get("variable_sugerida")
    if variable_final and variable_final not in HEURISTICAS:
        raise HTTPException(422, f"Variable '{variable_final}' no es una variable IRG válida. "
                                 f"Válidas: {list(HEURISTICAS.keys())}")

    fuente["estado"] = "aprobada"
    fuente["variable_sugerida"] = variable_final
    fuente["aprobada_por"] = req.aprobada_por
    fuente["fecha_decision"] = datetime.now(timezone.utc).isoformat()
    _fuentes_pendientes[fuente_id] = fuente

    await _db_actualizar_estado(fuente_id, "aprobada", req.aprobada_por)
    logger.info(f"Fuente aprobada: {fuente['url']} → variable={variable_final}")

    return {
        "ok": True,
        "fuente_id": fuente_id,
        "variable_irg": variable_final,
        "mensaje": f"Fuente aprobada. Variable IRG: '{variable_final}'. "
                   f"Actívala en localStorage con activa=true para que entre al ciclo.",
        "fuente": fuente,
    }


@router.post("/{fuente_id}/rechazar")
async def rechazar_fuente(fuente_id: str, req: RechazarRequest = RechazarRequest()):
    """Rechaza definitivamente una fuente. No entra al IRG."""
    fuente = _fuentes_pendientes.get(fuente_id)
    if not fuente:
        raise HTTPException(404, f"Fuente {fuente_id} no encontrada")

    if fuente["estado"] == "aprobada":
        raise HTTPException(409, "No se puede rechazar una fuente ya aprobada")

    fuente["estado"] = "rechazada_manual"
    fuente["motivo_rechazo"] = req.motivo or "Rechazada manualmente"
    fuente["fecha_decision"] = datetime.now(timezone.utc).isoformat()
    _fuentes_pendientes[fuente_id] = fuente

    await _db_actualizar_estado(fuente_id, "rechazada_manual", motivo=req.motivo)
    logger.info(f"Fuente rechazada: {fuente['url']}")
    return {"ok": True, "fuente_id": fuente_id}
