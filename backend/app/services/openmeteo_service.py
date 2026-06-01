"""
Servicio Open-Meteo — clima real, gratuito, sin API key.
Único punto de acceso a datos meteorológicos en toda la app.
Cubre todos los municipios de Antioquia con resolución horaria.
"""
import math
import aiohttp
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# ── Caché en memoria: evita saturar la API ────────────────────────────────────
CACHE_TTL = 600  # 10 minutos
_cache: Dict[str, Tuple[float, Dict]] = {}

# ── Coordenadas y datos estáticos por zona ────────────────────────────────────
COORDS_ZONAS: Dict[str, Tuple[float, float]] = {
    "guatape":            (6.2336, -75.1567),
    "medellin":           (6.2442, -75.5812),
    "rionegro":           (6.1546, -75.3769),
    "santa_fe_antioquia": (6.5548, -75.8278),
    "caucasia":           (7.9882, -75.1975),
}

NOMBRES_ZONAS: Dict[str, str] = {
    "guatape":            "Guatapé",
    "medellin":           "Medellín",
    "rionegro":           "Rionegro",
    "santa_fe_antioquia": "Santa Fe de Antioquia",
    "caucasia":           "Caucasia",
}

# Promedios históricos para fallback (fuente: IDEAM normales climatológicas)
CLIMA_BASE: Dict[str, Dict] = {
    "guatape":            {"lluvia_anual_mm": 2800, "temp_media": 18.0, "viento_medio": 3.0, "presion_hpa": 808},
    "medellin":           {"lluvia_anual_mm": 1700, "temp_media": 22.0, "viento_medio": 2.5, "presion_hpa": 850},
    "rionegro":           {"lluvia_anual_mm": 2100, "temp_media": 17.0, "viento_medio": 3.5, "presion_hpa": 792},
    "santa_fe_antioquia": {"lluvia_anual_mm": 1400, "temp_media": 27.0, "viento_medio": 3.0, "presion_hpa": 952},
    "caucasia":           {"lluvia_anual_mm": 2200, "temp_media": 29.0, "viento_medio": 2.0, "presion_hpa": 1005},
}


async def obtener_meteo_real(
    zona_id: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Dict:
    """
    Retorna datos meteorológicos reales de Open-Meteo.
    - Cachea 10 min para no saturar la API gratuita.
    - Fallback silencioso a promedios históricos si no hay red.
    """
    lat = lat or COORDS_ZONAS.get(zona_id, (6.2336, -75.1567))[0]
    lon = lon or COORDS_ZONAS.get(zona_id, (6.2336, -75.1567))[1]

    cache_key = f"{lat:.4f},{lon:.4f}"
    ahora = datetime.now(timezone.utc).timestamp()

    cached = _cache.get(cache_key)
    if cached and ahora - cached[0] < CACHE_TTL:
        return cached[1]

    try:
        datos = await _fetch(lat, lon, zona_id)
        _cache[cache_key] = (ahora, datos)
        logger.info(f"Open-Meteo OK para {zona_id}: lluvia={datos['lluvia_24h_mm']}mm, T={datos['temperatura_c']}°C")
        return datos
    except Exception as e:
        logger.warning(f"Open-Meteo no disponible para {zona_id} ({type(e).__name__}) — usando promedios históricos")
        fallback = _fallback(zona_id, lat, lon)
        # Cache corto: reintentar en 1 min
        _cache[cache_key] = (ahora - CACHE_TTL + 60, fallback)
        return fallback


async def _fetch(lat: float, lon: float, zona_id: str) -> Dict:
    """Llama a la API Open-Meteo y procesa la respuesta."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,precipitation,"
        "wind_speed_10m,surface_pressure,weather_code,cloud_cover"
        "&hourly=precipitation,soil_moisture_0_to_1cm"
        "&past_days=3&forecast_days=4"
        "&timezone=America%2FBogota"
        "&wind_speed_unit=ms"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                raise ConnectionError(f"Open-Meteo HTTP {resp.status}")
            raw = await resp.json()

    curr = raw.get("current", {})
    hourly = raw.get("hourly", {})
    tiempos = hourly.get("time", [])

    # Localizar la hora actual en el array hourly
    hora_actual_str = curr.get("time", "")[:16]  # "2026-05-21T14:00"
    idx = next(
        (i for i, t in enumerate(tiempos) if t[:16] == hora_actual_str),
        len(tiempos) // 2,
    )

    precipitaciones = hourly.get("precipitation", [])
    humedad_suelo_raw = hourly.get("soil_moisture_0_to_1cm", [])

    # Lluvia acumulada pasada y pronóstico futuro
    lluvia_24h = _suma_segura(precipitaciones, max(0, idx - 24), idx)
    lluvia_72h = _suma_segura(precipitaciones, max(0, idx - 72), idx)
    n = len(precipitaciones)
    lluvia_24h_pron = _suma_segura(precipitaciones, idx, min(n, idx + 24))
    lluvia_72h_pron = _suma_segura(precipitaciones, idx, min(n, idx + 72))

    # Humedad de suelo: promedio de últimas 6h (0–0.5 m³/m³ → 0–1)
    hum_vals = [v for v in humedad_suelo_raw[max(0, idx - 6):idx + 1] if v is not None]
    if hum_vals:
        hum_suelo = min(1.0, (sum(hum_vals) / len(hum_vals)) / 0.5)
    else:
        hum_rel = curr.get("relative_humidity_2m") or 70
        hum_suelo = min(1.0, hum_rel / 100 * 0.75 + lluvia_24h / 200 * 0.25)

    viento_ms  = curr.get("wind_speed_10m") or 0.0
    presion    = curr.get("surface_pressure") or CLIMA_BASE.get(zona_id, {}).get("presion_hpa", 870)
    temp       = curr.get("temperature_2m") or CLIMA_BASE.get(zona_id, {}).get("temp_media", 18)
    precip_now = curr.get("precipitation") or 0.0

    return {
        # Campos usados por el modelo de riesgo (compatibles con riesgo_service.py)
        "lluvia_24h_mm":           round(max(0.0, lluvia_24h), 1),
        "lluvia_72h_mm":           round(max(0.0, lluvia_72h), 1),
        "humedad_suelo":           round(min(1.0, max(0.0, hum_suelo)), 3),
        "temperatura_c":           round(temp, 1),
        "velocidad_viento_ms":     round(viento_ms, 1),
        "presion_hpa":             round(presion, 1),
        "nivel_embalse_pct":       _estimar_embalse(zona_id, lluvia_24h, lluvia_72h),
        # Campos extra para dashboard e IA
        "humedad_relativa":        curr.get("relative_humidity_2m"),
        "precipitacion_actual_mm": round(precip_now, 1),
        "codigo_clima":            curr.get("weather_code"),
        "nubosidad_pct":           curr.get("cloud_cover"),
        "lluvia_24h_pronostico_mm": round(max(0.0, lluvia_24h_pron), 1),
        "lluvia_72h_pronostico_mm": round(max(0.0, lluvia_72h_pron), 1),
        "fuente":                  "Open-Meteo (real)",
        "fuente_real":             True,
        "lat":                     lat,
        "lon":                     lon,
        "timestamp":               curr.get("time", datetime.utcnow().isoformat()),
    }


def _suma_segura(lst: list, inicio: int, fin: int) -> float:
    """Suma un tramo de lista ignorando None."""
    if not lst:
        return 0.0
    return sum(v for v in lst[inicio:fin] if v is not None)


def _estimar_embalse(zona_id: str, lluvia_24h: float, lluvia_72h: float) -> float:
    """
    Estimación del nivel del embalse El Peñol a partir de lluvia acumulada.
    Solo aplica para Guatapé. Pendiente: conectar API EPM en producción.
    """
    if zona_id != "guatape":
        return 70.0
    hora = datetime.now().hour
    nivel_base     = 72.0
    efecto_lluvia  = min(14.0, lluvia_72h / 22)   # cada 22mm de lluvia → +1% nivel
    variacion_hora = 1.5 * math.sin(hora * math.pi / 12)  # ±1.5% ciclo diurno
    nivel = nivel_base + efecto_lluvia + variacion_hora
    return round(min(97.0, max(42.0, nivel)), 1)


def _fallback(zona_id: str, lat: float, lon: float) -> Dict:
    """Promedios históricos cuando Open-Meteo no responde."""
    base = CLIMA_BASE.get(zona_id, CLIMA_BASE["medellin"])
    # Lluvia promedio diaria (distribución uniforme como primer orden)
    lluvia_24h = round(base["lluvia_anual_mm"] / 365, 1)
    lluvia_72h = round(lluvia_24h * 2.8, 1)
    return {
        "lluvia_24h_mm":           lluvia_24h,
        "lluvia_72h_mm":           lluvia_72h,
        "humedad_suelo":           round(min(0.7, lluvia_24h / 80), 3),
        "temperatura_c":           base["temp_media"],
        "velocidad_viento_ms":     base["viento_medio"],
        "presion_hpa":             base["presion_hpa"],
        "nivel_embalse_pct":       _estimar_embalse(zona_id, lluvia_24h, lluvia_72h),
        "humedad_relativa":        72,
        "precipitacion_actual_mm": 0.0,
        "codigo_clima":            None,
        "nubosidad_pct":           50,
        "fuente":                  "promedios históricos (Open-Meteo no disponible)",
        "fuente_real":             False,
        "lat":                     lat,
        "lon":                     lon,
        "timestamp":               datetime.utcnow().isoformat(),
    }


def nombre_zona(zona_id: str) -> str:
    """Nombre legible de una zona (para prompts IA)."""
    return NOMBRES_ZONAS.get(zona_id, zona_id.replace("_", " ").title())
