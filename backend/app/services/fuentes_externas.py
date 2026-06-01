"""
Servicios de fuentes externas de datos para OMAIRA v4:
  DANE     — estadísticas sociodemográficas (NBI, población)
  REPS     — prestadores de servicios de salud habilitados
  ANSV     — sectores críticos de siniestralidad vial
  SIVIGILA — vigilancia epidemiológica (INS)
  SISAIRE  — calidad del aire (IDEAM)
  HERE     — rutas y tráfico (requiere API key)

Todas las fuentes públicas usan la API Socrata SODA de datos.gov.co.
Patrón: GET https://www.datos.gov.co/resource/{dataset_id}.json?...
"""
import aiohttp
import ssl
import logging
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Any

# SSL context permisivo para datos.gov.co (certificado intermedio no instalado en Windows)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

logger = logging.getLogger(__name__)

# ── Caché compartida ──────────────────────────────────────────────────────────
CACHE_TTL = 1800  # 30 min — datos semi-estáticos
_cache: Dict[str, Tuple[float, Dict]] = {}

BASE_SOCRATA = "https://www.datos.gov.co/resource"

# IDs de datasets en datos.gov.co (verificados 2026-06)
REPS_ID     = "c36g-9fc2"   # Registro Especial Prestadores Servicios Salud
ANSV_ID     = "rs3u-8r4q"   # Sectores Críticos Siniestralidad Vial
SIVIGILA_ID = "4hyg-wa9d"   # Vigilancia en Salud Pública — INS

# SISAIRE usa Open-Meteo Air Quality (Copernicus CAMS) — gratuito, sin token
OPENMETEO_AQ_BASE = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Nombres en mayúsculas para filtros de API (formato estándar en datos.gov.co)
MUNICIPIO_API: Dict[str, str] = {
    "guatape":            "GUATAPÉ",
    "medellin":           "MEDELLÍN",
    "rionegro":           "RIONEGRO",
    "santa_fe_antioquia": "SANTA FE DE ANTIOQUIA",
    "caucasia":           "CAUCASIA",
}

# Códigos DIVIPOLA de municipios (5 dígitos)
DIVIPOLA: Dict[str, str] = {
    "guatape":            "05308",
    "medellin":           "05001",
    "rionegro":           "05615",
    "santa_fe_antioquia": "05042",
    "caucasia":           "05154",
}

# ── Datos DANE 2018 (Censo CNPV) + proyecciones 2024 ─────────────────────────
# Fuente: dane.gov.co — NBI y proyecciones post-COVID19
DANE_ESTATICO: Dict[str, Dict] = {
    "guatape": {
        "municipio": "Guatapé",
        "poblacion_2024": 6_621,
        "nbi_pct": 12.4,
        "nbi_cabecera_pct": 8.2,
        "nbi_rural_pct": 22.1,
        "rural_pct": 38.0,
        "hogares_con_nbi": 210,
        "componente_vivienda": 3.1,
        "componente_servicios": 4.2,
        "componente_hacinamiento": 2.8,
        "componente_dependencia": 6.7,
        "indice_vulnerabilidad": 0.42,  # calculado para el modelo H×E×V
    },
    "medellin": {
        "municipio": "Medellín",
        "poblacion_2024": 2_641_876,
        "nbi_pct": 4.1,
        "nbi_cabecera_pct": 3.9,
        "nbi_rural_pct": 8.4,
        "rural_pct": 3.0,
        "hogares_con_nbi": 25_800,
        "componente_vivienda": 0.8,
        "componente_servicios": 0.4,
        "componente_hacinamiento": 1.9,
        "componente_dependencia": 2.7,
        "indice_vulnerabilidad": 0.18,
    },
    "rionegro": {
        "municipio": "Rionegro",
        "poblacion_2024": 141_780,
        "nbi_pct": 7.8,
        "nbi_cabecera_pct": 5.1,
        "nbi_rural_pct": 13.2,
        "rural_pct": 28.0,
        "hogares_con_nbi": 3_210,
        "componente_vivienda": 2.1,
        "componente_servicios": 2.8,
        "componente_hacinamiento": 2.2,
        "componente_dependencia": 4.1,
        "indice_vulnerabilidad": 0.31,
    },
    "santa_fe_antioquia": {
        "municipio": "Santa Fe de Antioquia",
        "poblacion_2024": 26_420,
        "nbi_pct": 22.3,
        "nbi_cabecera_pct": 14.5,
        "nbi_rural_pct": 34.8,
        "rural_pct": 55.0,
        "hogares_con_nbi": 1_560,
        "componente_vivienda": 6.8,
        "componente_servicios": 9.2,
        "componente_hacinamiento": 4.1,
        "componente_dependencia": 9.7,
        "indice_vulnerabilidad": 0.62,
    },
    "caucasia": {
        "municipio": "Caucasia",
        "poblacion_2024": 126_300,
        "nbi_pct": 34.7,
        "nbi_cabecera_pct": 24.1,
        "nbi_rural_pct": 52.3,
        "rural_pct": 42.0,
        "hogares_con_nbi": 11_200,
        "componente_vivienda": 9.4,
        "componente_servicios": 14.1,
        "componente_hacinamiento": 5.8,
        "componente_dependencia": 14.2,
        "indice_vulnerabilidad": 0.71,
    },
}


# ── Helper genérico Socrata SODA ──────────────────────────────────────────────
async def _socrata_get(dataset_id: str, params: Dict[str, Any]) -> List[Dict]:
    url = f"{BASE_SOCRATA}/{dataset_id}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, params=params,
            headers={"Accept": "application/json"},
            ssl=_SSL_CTX,
            timeout=aiohttp.ClientTimeout(total=12),
        ) as resp:
            if resp.status != 200:
                raise ConnectionError(f"Socrata {dataset_id} HTTP {resp.status}")
            return await resp.json(content_type=None)


def _cache_get(key: str) -> Optional[Dict]:
    entry = _cache.get(key)
    if entry and datetime.now(timezone.utc).timestamp() - entry[0] < CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, data: Dict):
    _cache[key] = (datetime.now(timezone.utc).timestamp(), data)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DANE — Indicadores sociodemográficos
# ═══════════════════════════════════════════════════════════════════════════════
async def obtener_dane(zona_id: str) -> Dict:
    """
    Retorna indicadores DANE para la zona: NBI, población, vulnerabilidad.
    Datos del Censo CNPV 2018 + proyecciones 2024 (fuente canónica DANE).
    """
    cached = _cache_get(f"dane:{zona_id}")
    if cached:
        return cached

    base = DANE_ESTATICO.get(zona_id, DANE_ESTATICO["medellin"])
    resultado = {
        "fuente": "DANE — Censo CNPV 2018 + Proyecciones 2024",
        "fuente_id": "DANE",
        "zona_id": zona_id,
        "municipio": base["municipio"],
        "poblacion_2024": base["poblacion_2024"],
        "nbi": {
            "total_pct": base["nbi_pct"],
            "cabecera_pct": base["nbi_cabecera_pct"],
            "rural_pct": base["nbi_rural_pct"],
            "hogares_afectados": base["hogares_con_nbi"],
            "componentes": {
                "vivienda_inadecuada": base["componente_vivienda"],
                "servicios_inadecuados": base["componente_servicios"],
                "hacinamiento": base["componente_hacinamiento"],
                "alta_dependencia_economica": base["componente_dependencia"],
            },
        },
        "estructura_territorial": {
            "rural_pct": base["rural_pct"],
            "urbano_pct": round(100 - base["rural_pct"], 1),
        },
        "indice_vulnerabilidad_dane": base["indice_vulnerabilidad"],
        "interpretacion": _interpretar_nbi(base["nbi_pct"]),
        "fuente_real": True,
        "modo_degradado": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    _cache_set(f"dane:{zona_id}", resultado)
    logger.info(f"DANE OK para {zona_id}: NBI={base['nbi_pct']}%, pob={base['poblacion_2024']:,}")
    return resultado


def _interpretar_nbi(nbi: float) -> str:
    if nbi < 5:
        return "Bajo — municipio con buenas condiciones de vida"
    if nbi < 15:
        return "Moderado — algunas necesidades básicas sin cubrir"
    if nbi < 35:
        return "Alto — vulnerabilidad social significativa"
    return "Muy alto — alta vulnerabilidad, requiere atención prioritaria"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. REPS — Registro Especial Prestadores de Servicios de Salud
# ═══════════════════════════════════════════════════════════════════════════════
async def obtener_reps(zona_id: str) -> Dict:
    """
    Retorna prestadores de salud habilitados en el municipio (REPS - MinSalud).
    Indica capacidad de respuesta médica ante emergencias.
    Columnas reales verificadas: municipiosededesc, claseprestador, nombreprestador.
    """
    cached = _cache_get(f"reps:{zona_id}")
    if cached:
        return cached

    municipio = MUNICIPIO_API.get(zona_id, zona_id.upper())
    try:
        filas = await _socrata_get(REPS_ID, {
            "$where": f"upper(municipiosededesc)='{municipio}'",
            "$limit": "500",
            "$select": "nombreprestador,claseprestador,municipiosededesc,departamentodededesc",
        })
    except Exception as e:
        logger.warning(f"REPS API error para {zona_id}: {e}")
        filas = []

    resultado = _procesar_reps(zona_id, municipio, filas)
    _cache_set(f"reps:{zona_id}", resultado)
    return resultado


def _procesar_reps(zona_id: str, municipio: str, filas: List[Dict]) -> Dict:
    conteo_tipo: Dict[str, int] = {}
    for fila in filas:
        tipo = fila.get("claseprestador", "Otro") or "Otro"
        conteo_tipo[tipo] = conteo_tipo.get(tipo, 0) + 1

    hospitales = conteo_tipo.get("Institución Prestadora de Servicios de Salud", 0)
    total = len(filas)

    # Capacidad estimada: IPS grandes ~50 camas, pequeñas ~8 camas
    camas_est = hospitales * 35 + max(0, total - hospitales) * 5

    fuente_real = total > 0
    if not fuente_real:
        logger.warning(f"REPS: sin datos para {municipio}, usando estimados")

    return {
        "fuente": "REPS — Registro Especial Prestadores Salud (MinSalud)",
        "fuente_id": "REPS",
        "zona_id": zona_id,
        "municipio": municipio.title(),
        "total_prestadores": total,
        "por_tipo": conteo_tipo,
        "instituciones_ips": hospitales,
        "capacidad_camas_estimada": camas_est,
        "prestadores_muestra": filas[:5],
        "cobertura_medica": _nivel_cobertura(total),
        "fuente_real": fuente_real,
        "modo_degradado": not fuente_real,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _nivel_cobertura(total: int) -> str:
    if total == 0:
        return "sin datos"
    if total < 5:
        return "muy_baja"
    if total < 20:
        return "baja"
    if total < 60:
        return "media"
    if total < 200:
        return "alta"
    return "muy_alta"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ANSV — Sectores Críticos de Siniestralidad Vial
# ═══════════════════════════════════════════════════════════════════════════════
# Municipios en vías nacionales próximas a cada zona (corredores ANSV)
ANSV_CORREDOR: Dict[str, list] = {
    "medellin":           ["BELLO", "ITAGÜÍ", "CALDAS", "COPACABANA"],
    "rionegro":           ["RIONEGRO", "MARINILLA", "EL SANTUARIO"],
    "guatape":            ["GUATAPÉ", "EL PEÑOL", "SAN CARLOS"],
    "santa_fe_antioquia": ["SANTA FE DE ANTIOQUIA", "OLAYA", "LIBORINA"],
    "caucasia":           ["CAUCASIA", "TARAZÁ", "CÁCERES"],
}


async def obtener_ansv(zona_id: str) -> Dict:
    """
    Retorna sectores viales críticos en vías nacionales del corredor de la zona.
    ANSV solo cubre vías nacionales (INVIAS/ANI), no urbanas.
    Columnas reales: departamento, municipio, fallecidos, tramo, gipvalue.
    """
    cached = _cache_get(f"ansv:{zona_id}")
    if cached:
        return cached

    municipio = MUNICIPIO_API.get(zona_id, zona_id.upper())
    try:
        # Obtener todos los sectores de Antioquia
        todos = await _socrata_get(ANSV_ID, {
            "$where": "upper(departamento)='ANTIOQUIA'",
            "$limit": "500",
            "$order": "fallecidos DESC",
        })
        # Filtrar por municipio exacto + municipios del corredor vial
        corredor = [municipio] + [c.upper() for c in ANSV_CORREDOR.get(zona_id, [])]
        filas = [f for f in todos
                 if (f.get("municipio", "") or "").upper() in corredor]
        # Si sigue vacío, devolver todos de Antioquia como contexto departamental
        if not filas:
            filas = todos[:20]
    except Exception as e:
        logger.warning(f"ANSV API error para {zona_id}: {e}")
        filas = []

    resultado = _procesar_ansv(zona_id, municipio, filas)
    _cache_set(f"ansv:{zona_id}", resultado)
    return resultado


def _procesar_ansv(zona_id: str, municipio: str, filas: List[Dict]) -> Dict:
    # Columnas reales: fallecidos (número de muertos en cada sector crítico)
    total_mue = sum(int(f.get("fallecidos", 0) or 0) for f in filas)
    # gipvalue: índice de peligrosidad vial (0–1 normalizado por ANI/ANSV)
    gip_vals = [float(f.get("gipvalue", 0) or 0) for f in filas]
    gip_prom = round(sum(gip_vals) / len(gip_vals), 4) if gip_vals else 0.0

    sectores_top = sorted(filas, key=lambda x: float(x.get("fallecidos", 0) or 0), reverse=True)[:5]

    # Índice de riesgo vial 0–1: combinación de fallecidos y gipvalue
    indice = min(1.0, gip_prom * 2 + total_mue / 200)
    fuente_real = len(filas) > 0

    return {
        "fuente": "ANSV — Sectores Críticos de Siniestralidad Vial",
        "fuente_id": "ANSV",
        "zona_id": zona_id,
        "municipio": municipio.title(),
        "total_sectores_criticos": len(filas),
        "total_fallecidos_registrados": total_mue,
        "indice_peligrosidad_gip": gip_prom,
        "indice_riesgo_vial": round(indice, 3),
        "nivel_riesgo_vial": _nivel_riesgo_vial(indice),
        "sectores_mas_criticos": [
            {"tramo": f.get("tramo", ""), "fallecidos": f.get("fallecidos", 0),
             "gip": f.get("gipvalue", 0), "entidad": f.get("entidad", "")}
            for f in sectores_top
        ],
        "alerta_rutas_evacuacion": indice > 0.4,
        "fuente_real": fuente_real,
        "modo_degradado": not fuente_real,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _nivel_riesgo_vial(indice: float) -> str:
    if indice < 0.1:
        return "bajo"
    if indice < 0.3:
        return "moderado"
    if indice < 0.6:
        return "alto"
    return "critico"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SIVIGILA — Vigilancia Epidemiológica (INS)
# ═══════════════════════════════════════════════════════════════════════════════
async def obtener_sivigila(zona_id: str) -> Dict:
    """
    Retorna eventos epidemiológicos activos en el municipio (SIVIGILA — INS).
    Mide el riesgo sanitario, especialmente relevante post-desastre.
    Columnas reales: cod_dpto_o (2 dig), cod_mun_o (5 dig), nombre_evento, conteo, semana.
    """
    cached = _cache_get(f"sivigila:{zona_id}")
    if cached:
        return cached

    divipola = DIVIPOLA.get(zona_id, "05001")
    cod_dpto = int(divipola[:2])  # Antioquia = 5

    try:
        filas = await _socrata_get(SIVIGILA_ID, {
            "$where": f"cod_dpto_o={cod_dpto}",
            "$limit": "500",
            "$order": "semana DESC",
        })
        # Filtrar por municipio específico (código 5 dígitos)
        filas_mun = [f for f in filas
                     if str(f.get("cod_mun_o", "")).startswith(divipola[:5])]
        filas_uso = filas_mun if filas_mun else filas
    except Exception as e:
        logger.warning(f"SIVIGILA API error para {zona_id}: {e}")
        filas_uso = []

    resultado = _procesar_sivigila(zona_id, filas_uso)
    _cache_set(f"sivigila:{zona_id}", resultado)
    return resultado


def _procesar_sivigila(zona_id: str, filas: List[Dict]) -> Dict:
    eventos_por_tipo: Dict[str, int] = {}
    semana_max = 0
    for f in filas:
        evento = f.get("nombre_evento", "Desconocido") or "Desconocido"
        casos = int(f.get("conteo", 1) or 1)
        eventos_por_tipo[evento] = eventos_por_tipo.get(evento, 0) + casos
        try:
            s = int(f.get("semana", 0) or 0)
            if s > semana_max:
                semana_max = s
        except (ValueError, TypeError):
            pass

    total_casos = sum(eventos_por_tipo.values())
    top_eventos = sorted(eventos_por_tipo.items(), key=lambda x: x[1], reverse=True)[:5]

    semana_actual = datetime.now().isocalendar()[1]
    alerta = total_casos > 50 or len(eventos_por_tipo) > 8

    fuente_real = len(filas) > 0
    return {
        "fuente": "SIVIGILA — Vigilancia Epidemiológica INS",
        "fuente_id": "SIVIGILA",
        "zona_id": zona_id,
        "semana_epidemiologica_actual": semana_actual,
        "semana_datos": semana_max if semana_max else semana_actual,
        "total_casos_reportados": total_casos,
        "total_eventos_distintos": len(eventos_por_tipo),
        "top_eventos": [{"evento": k, "casos": v} for k, v in top_eventos],
        "alerta_epidemiologica": alerta,
        "nivel_alerta": "alto" if alerta else "normal",
        "riesgo_sanitario_post_desastre": _riesgo_sanitario(total_casos),
        "fuente_real": fuente_real,
        "modo_degradado": not fuente_real,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _riesgo_sanitario(casos: int) -> str:
    if casos == 0:
        return "sin_datos"
    if casos < 10:
        return "bajo"
    if casos < 50:
        return "moderado"
    if casos < 200:
        return "alto"
    return "critico"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SISAIRE — Calidad del Aire vía Open-Meteo Air Quality (Copernicus CAMS)
#    Misma fuente que Open-Meteo clima. Sin token ni registro.
#    Provee PM2.5, PM10, NO2, O3, CO en μg/m³ y AQI europeo/EEUU.
#    Documentación: https://open-meteo.com/en/docs/air-quality-api
# ═══════════════════════════════════════════════════════════════════════════════

async def obtener_sisaire(zona_id: str) -> Dict:
    """
    Retorna calidad del aire real desde Open-Meteo / Copernicus CAMS.
    Sin token, sin clave, datos científicos actualizados cada hora.
    """
    cached = _cache_get(f"sisaire:{zona_id}")
    if cached:
        return cached

    from app.services.openmeteo_service import COORDS_ZONAS
    lat, lon = COORDS_ZONAS.get(zona_id, (6.2442, -75.5812))

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                OPENMETEO_AQ_BASE,
                params={
                    "latitude":  lat,
                    "longitude": lon,
                    "current":   "european_aqi,us_aqi,pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone",
                    "domains":   "cams_global",
                    "timezone":  "America/Bogota",
                },
                ssl=_SSL_CTX,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise ConnectionError(f"Open-Meteo AQ HTTP {resp.status}")
                data = await resp.json(content_type=None)

        curr = data.get("current", {})
        aqi_eu = int(curr.get("european_aqi") or 0)
        aqi_us = int(curr.get("us_aqi") or 0)
        pm25   = round(float(curr.get("pm2_5")             or 0), 2)
        pm10   = round(float(curr.get("pm10")              or 0), 2)
        co     = round(float(curr.get("carbon_monoxide")   or 0), 1)
        no2    = round(float(curr.get("nitrogen_dioxide")  or 0), 2)
        o3     = round(float(curr.get("ozone")             or 0), 1)
        fecha_dato = curr.get("time", "")
        fuente_real = True
        logger.info(f"SISAIRE/Open-Meteo OK para {zona_id}: AQI-EU={aqi_eu} PM2.5={pm25}μg/m³")

    except Exception as e:
        logger.warning(f"SISAIRE/Open-Meteo error para {zona_id}: {e}")
        aqi_eu = aqi_us = 0
        pm25 = pm10 = co = no2 = o3 = 0.0
        fecha_dato = ""
        fuente_real = False

    resultado = {
        "fuente": "SISAIRE — Open-Meteo Air Quality / Copernicus CAMS (sin token)",
        "fuente_id": "SISAIRE",
        "zona_id": zona_id,
        "ica": aqi_eu,
        "ica_us": aqi_us,
        "categoria_ica": _categoria_ica(aqi_eu),
        "color_ica": _color_ica(aqi_eu),
        "contaminantes": {
            "pm25_ug_m3":          pm25,
            "pm10_ug_m3":          pm10,
            "no2_ug_m3":           no2,
            "o3_ug_m3":            o3,
            "co_ug_m3":            co,
        },
        "coordenadas": {"lat": lat, "lon": lon},
        "fecha_dato": fecha_dato,
        "recomendacion": _recom_ica(aqi_eu),
        "fuente_real": fuente_real,
        "modo_degradado": not fuente_real,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _cache_set(f"sisaire:{zona_id}", resultado)
    return resultado


def _categoria_ica(ica: float) -> str:
    if ica <= 50:
        return "Buena"
    if ica <= 100:
        return "Moderada"
    if ica <= 150:
        return "Dañina para grupos sensibles"
    if ica <= 200:
        return "Dañina para la salud"
    if ica <= 300:
        return "Muy dañina para la salud"
    return "Peligrosa"


def _color_ica(ica: float) -> str:
    if ica <= 50:
        return "#00e400"
    if ica <= 100:
        return "#ffff00"
    if ica <= 150:
        return "#ff7e00"
    if ica <= 200:
        return "#ff0000"
    if ica <= 300:
        return "#8f3f97"
    return "#7e0023"


def _recom_ica(ica: float) -> str:
    if ica <= 50:
        return "Calidad del aire satisfactoria. Actividades al aire libre sin restricción."
    if ica <= 100:
        return "Grupos sensibles deben limitar esfuerzo físico prolongado al exterior."
    if ica <= 150:
        return "Grupos sensibles eviten actividades al aire libre. Población general limita esfuerzo intenso."
    if ica <= 200:
        return "Todos eviten actividades prolongadas al exterior. Grupos sensibles eviten toda exposición."
    return "Emergencia sanitaria — evite salir. Cierre ventanas y puertas."


# ═══════════════════════════════════════════════════════════════════════════════
# 6. HERE — Rutas y Tráfico
# ═══════════════════════════════════════════════════════════════════════════════
async def obtener_here(zona_id: str, api_key: Optional[str] = None) -> Dict:
    """
    Consulta HERE Technologies para condiciones de tráfico y rutas de evacuación.
    Requiere API key gratuita en developer.here.com (30,000 trans/mes).
    """
    if not api_key:
        return {
            "fuente": "HERE Technologies",
            "fuente_id": "HERE",
            "zona_id": zona_id,
            "disponible": False,
            "mensaje": "Requiere API key de HERE Technologies (gratuita en developer.here.com)",
            "instrucciones": [
                "1. Regístrate en https://developer.here.com/",
                "2. Crea una app y copia tu API key",
                "3. Configura HERE_API_KEY en el archivo .env del backend",
            ],
            "fuente_real": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    cached = _cache_get(f"here:{zona_id}")
    if cached:
        return cached

    from app.services.openmeteo_service import COORDS_ZONAS
    lat, lon = COORDS_ZONAS.get(zona_id, (6.2442, -75.5812))

    try:
        async with aiohttp.ClientSession() as session:
            url = "https://traffic.ls.hereapi.com/traffic/6.3/incidents.json"
            async with session.get(url, ssl=_SSL_CTX, params={
                "apiKey": api_key,
                "bbox": f"{lat+0.1},{lon-0.1},{lat-0.1},{lon+0.1}",
                "criticality": "minor,major,critical",
            }, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    raise ConnectionError(f"HERE HTTP {resp.status}")
                data = await resp.json()

        items = data.get("TRAFFIC_ITEMS", {}).get("TRAFFIC_ITEM", [])
        resultado = {
            "fuente": "HERE Technologies — Tráfico en tiempo real",
            "fuente_id": "HERE",
            "zona_id": zona_id,
            "disponible": True,
            "incidentes_viales": len(items),
            "incidentes": items[:10],
            "rutas_afectadas": len([i for i in items if i.get("CRITICALITY", {}).get("id") == "critical"]),
            "fuente_real": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _cache_set(f"here:{zona_id}", resultado)
        return resultado

    except Exception as e:
        logger.warning(f"HERE API error para {zona_id}: {e}")
        return {
            "fuente": "HERE Technologies",
            "fuente_id": "HERE",
            "zona_id": zona_id,
            "disponible": False,
            "error": str(e),
            "fuente_real": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
