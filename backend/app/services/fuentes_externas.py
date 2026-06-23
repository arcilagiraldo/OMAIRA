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
import os
import aiohttp
import ssl
import logging
import time as _time
from datetime import datetime, timezone, timedelta
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

# ── Datos DANE 2024 — Proyecciones municipales + NBI CNPV 2018 ───────────────
# Fuente: dane.gov.co — Proyecciones de Población 2024 + NBI Censo 2018
# Última actualización: junio 2026
# poblacion_2024: proyección oficial DANE ajustada post-COVID para el municipio completo
#   (cabecera + centros poblados + rural disperso)
DANE_ESTATICO: Dict[str, Dict] = {
    # ── VALLE DE ABURRÁ ──────────────────────────────────────────────────────
    "medellin": {
        "municipio": "Medellín",
        "poblacion_2024": 2_526_795,   # DANE proyección 2024 (verificado por usuario)
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
    "bello": {
        "municipio": "Bello",
        "poblacion_2024": 614_263,
        "nbi_pct": 6.8,
        "nbi_cabecera_pct": 6.2,
        "nbi_rural_pct": 14.1,
        "rural_pct": 5.0,
        "hogares_con_nbi": 11_200,
        "componente_vivienda": 1.8,
        "componente_servicios": 1.1,
        "componente_hacinamiento": 2.9,
        "componente_dependencia": 3.4,
        "indice_vulnerabilidad": 0.24,
    },
    "itagui": {
        "municipio": "Itagüí",
        "poblacion_2024": 278_461,
        "nbi_pct": 3.9,
        "nbi_cabecera_pct": 3.8,
        "nbi_rural_pct": 7.2,
        "rural_pct": 2.0,
        "hogares_con_nbi": 3_120,
        "componente_vivienda": 0.9,
        "componente_servicios": 0.5,
        "componente_hacinamiento": 1.7,
        "componente_dependencia": 2.1,
        "indice_vulnerabilidad": 0.17,
    },
    "envigado": {
        "municipio": "Envigado",
        "poblacion_2024": 254_682,
        "nbi_pct": 2.7,
        "nbi_cabecera_pct": 2.5,
        "nbi_rural_pct": 5.8,
        "rural_pct": 7.0,
        "hogares_con_nbi": 1_840,
        "componente_vivienda": 0.5,
        "componente_servicios": 0.3,
        "componente_hacinamiento": 1.1,
        "componente_dependencia": 1.4,
        "indice_vulnerabilidad": 0.12,
    },
    "sabaneta": {
        "municipio": "Sabaneta",
        "poblacion_2024": 61_040,
        "nbi_pct": 2.8,
        "nbi_cabecera_pct": 2.6,
        "nbi_rural_pct": 5.1,
        "rural_pct": 4.0,
        "hogares_con_nbi": 480,
        "componente_vivienda": 0.6,
        "componente_servicios": 0.4,
        "componente_hacinamiento": 1.2,
        "componente_dependencia": 1.5,
        "indice_vulnerabilidad": 0.13,
    },
    "la_estrella": {
        "municipio": "La Estrella",
        "poblacion_2024": 70_124,
        "nbi_pct": 5.1,
        "nbi_cabecera_pct": 4.4,
        "nbi_rural_pct": 10.2,
        "rural_pct": 18.0,
        "hogares_con_nbi": 980,
        "componente_vivienda": 1.2,
        "componente_servicios": 0.9,
        "componente_hacinamiento": 2.0,
        "componente_dependencia": 2.4,
        "indice_vulnerabilidad": 0.21,
    },
    "copacabana": {
        "municipio": "Copacabana",
        "poblacion_2024": 97_175,
        "nbi_pct": 7.2,
        "nbi_cabecera_pct": 5.8,
        "nbi_rural_pct": 14.6,
        "rural_pct": 22.0,
        "hogares_con_nbi": 1_890,
        "componente_vivienda": 1.9,
        "componente_servicios": 1.6,
        "componente_hacinamiento": 2.4,
        "componente_dependencia": 3.1,
        "indice_vulnerabilidad": 0.26,
    },
    "girardota": {
        "municipio": "Girardota",
        "poblacion_2024": 57_779,
        "nbi_pct": 8.4,
        "nbi_cabecera_pct": 6.1,
        "nbi_rural_pct": 16.8,
        "rural_pct": 32.0,
        "hogares_con_nbi": 1_320,
        "componente_vivienda": 2.2,
        "componente_servicios": 2.1,
        "componente_hacinamiento": 2.7,
        "componente_dependencia": 3.8,
        "indice_vulnerabilidad": 0.29,
    },
    "caldas": {
        "municipio": "Caldas",
        "poblacion_2024": 80_266,
        "nbi_pct": 6.3,
        "nbi_cabecera_pct": 5.1,
        "nbi_rural_pct": 12.4,
        "rural_pct": 20.0,
        "hogares_con_nbi": 1_380,
        "componente_vivienda": 1.5,
        "componente_servicios": 1.2,
        "componente_hacinamiento": 2.3,
        "componente_dependencia": 2.9,
        "indice_vulnerabilidad": 0.23,
    },
    "barbosa": {
        "municipio": "Barbosa",
        "poblacion_2024": 57_249,
        "nbi_pct": 10.2,
        "nbi_cabecera_pct": 7.8,
        "nbi_rural_pct": 18.4,
        "rural_pct": 35.0,
        "hogares_con_nbi": 1_570,
        "componente_vivienda": 2.8,
        "componente_servicios": 2.5,
        "componente_hacinamiento": 3.1,
        "componente_dependencia": 4.2,
        "indice_vulnerabilidad": 0.34,
    },
    # ── ORIENTE ──────────────────────────────────────────────────────────────
    "guatape": {
        "municipio": "Guatapé",
        "poblacion_2024": 9_842,         # Proyección DANE 2024 — municipio completo
        "nbi_pct": 12.4,
        "nbi_cabecera_pct": 8.2,
        "nbi_rural_pct": 22.1,
        "rural_pct": 38.0,
        "hogares_con_nbi": 310,
        "componente_vivienda": 3.1,
        "componente_servicios": 4.2,
        "componente_hacinamiento": 2.8,
        "componente_dependencia": 6.7,
        "indice_vulnerabilidad": 0.42,
    },
    "el_penol": {
        "municipio": "El Peñol",
        "poblacion_2024": 16_956,
        "nbi_pct": 14.8,
        "nbi_cabecera_pct": 9.4,
        "nbi_rural_pct": 26.1,
        "rural_pct": 48.0,
        "hogares_con_nbi": 680,
        "componente_vivienda": 3.8,
        "componente_servicios": 5.6,
        "componente_hacinamiento": 3.4,
        "componente_dependencia": 7.2,
        "indice_vulnerabilidad": 0.47,
    },
    "rionegro": {
        "municipio": "Rionegro",
        "poblacion_2024": 151_872,       # Proyección DANE 2024 (verificado por usuario)
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
    "marinilla": {
        "municipio": "Marinilla",
        "poblacion_2024": 80_682,
        "nbi_pct": 9.1,
        "nbi_cabecera_pct": 6.4,
        "nbi_rural_pct": 16.8,
        "rural_pct": 30.0,
        "hogares_con_nbi": 1_980,
        "componente_vivienda": 2.4,
        "componente_servicios": 2.9,
        "componente_hacinamiento": 2.8,
        "componente_dependencia": 4.6,
        "indice_vulnerabilidad": 0.33,
    },
    "el_carmen": {
        "municipio": "El Carmen de Viboral",
        "poblacion_2024": 52_938,
        "nbi_pct": 13.6,
        "nbi_cabecera_pct": 8.9,
        "nbi_rural_pct": 22.4,
        "rural_pct": 45.0,
        "hogares_con_nbi": 1_870,
        "componente_vivienda": 3.6,
        "componente_servicios": 4.8,
        "componente_hacinamiento": 3.2,
        "componente_dependencia": 6.4,
        "indice_vulnerabilidad": 0.44,
    },
    "la_ceja": {
        "municipio": "La Ceja",
        "poblacion_2024": 59_699,
        "nbi_pct": 6.4,
        "nbi_cabecera_pct": 4.8,
        "nbi_rural_pct": 12.1,
        "rural_pct": 20.0,
        "hogares_con_nbi": 1_040,
        "componente_vivienda": 1.6,
        "componente_servicios": 1.8,
        "componente_hacinamiento": 2.1,
        "componente_dependencia": 3.3,
        "indice_vulnerabilidad": 0.25,
    },
    "guarne": {
        "municipio": "Guarne",
        "poblacion_2024": 66_158,
        "nbi_pct": 8.2,
        "nbi_cabecera_pct": 5.4,
        "nbi_rural_pct": 14.6,
        "rural_pct": 38.0,
        "hogares_con_nbi": 1_420,
        "componente_vivienda": 2.1,
        "componente_servicios": 2.4,
        "componente_hacinamiento": 2.5,
        "componente_dependencia": 4.0,
        "indice_vulnerabilidad": 0.30,
    },
    # ── NORTE ────────────────────────────────────────────────────────────────
    "santa_rosa": {
        "municipio": "Santa Rosa de Osos",
        "poblacion_2024": 48_124,
        "nbi_pct": 18.2,
        "nbi_cabecera_pct": 11.4,
        "nbi_rural_pct": 29.8,
        "rural_pct": 52.0,
        "hogares_con_nbi": 2_340,
        "componente_vivienda": 4.9,
        "componente_servicios": 6.8,
        "componente_hacinamiento": 4.1,
        "componente_dependencia": 8.2,
        "indice_vulnerabilidad": 0.52,
    },
    "yarumal": {
        "municipio": "Yarumal",
        "poblacion_2024": 42_018,
        "nbi_pct": 20.4,
        "nbi_cabecera_pct": 12.1,
        "nbi_rural_pct": 32.6,
        "rural_pct": 50.0,
        "hogares_con_nbi": 2_280,
        "componente_vivienda": 5.4,
        "componente_servicios": 7.2,
        "componente_hacinamiento": 4.6,
        "componente_dependencia": 9.1,
        "indice_vulnerabilidad": 0.55,
    },
    "ituango": {
        "municipio": "Ituango",
        "poblacion_2024": 29_650,
        "nbi_pct": 41.2,
        "nbi_cabecera_pct": 24.8,
        "nbi_rural_pct": 56.4,
        "rural_pct": 72.0,
        "hogares_con_nbi": 2_870,
        "componente_vivienda": 11.2,
        "componente_servicios": 15.8,
        "componente_hacinamiento": 7.4,
        "componente_dependencia": 16.1,
        "indice_vulnerabilidad": 0.74,
    },
    # ── BAJO CAUCA ──────────────────────────────────────────────────────────
    "caucasia": {
        "municipio": "Caucasia",
        "poblacion_2024": 93_843,        # Proyección DANE 2024 (verificado por usuario)
        "nbi_pct": 34.7,
        "nbi_cabecera_pct": 24.1,
        "nbi_rural_pct": 52.3,
        "rural_pct": 42.0,
        "hogares_con_nbi": 10_460,
        "componente_vivienda": 9.4,
        "componente_servicios": 14.1,
        "componente_hacinamiento": 5.8,
        "componente_dependencia": 14.2,
        "indice_vulnerabilidad": 0.71,
    },
    "el_bagre": {
        "municipio": "El Bagre",
        "poblacion_2024": 55_082,
        "nbi_pct": 44.8,
        "nbi_cabecera_pct": 31.2,
        "nbi_rural_pct": 62.4,
        "rural_pct": 48.0,
        "hogares_con_nbi": 5_890,
        "componente_vivienda": 12.4,
        "componente_servicios": 17.8,
        "componente_hacinamiento": 8.2,
        "componente_dependencia": 18.6,
        "indice_vulnerabilidad": 0.78,
    },
    # ── OCCIDENTE ────────────────────────────────────────────────────────────
    "santa_fe": {
        "municipio": "Santa Fe de Antioquia",
        "poblacion_2024": 23_598,        # Proyección DANE 2024
        "nbi_pct": 22.3,
        "nbi_cabecera_pct": 14.5,
        "nbi_rural_pct": 34.8,
        "rural_pct": 55.0,
        "hogares_con_nbi": 1_380,
        "componente_vivienda": 6.8,
        "componente_servicios": 9.2,
        "componente_hacinamiento": 4.1,
        "componente_dependencia": 9.7,
        "indice_vulnerabilidad": 0.62,
    },
    # ── URABÁ ────────────────────────────────────────────────────────────────
    "turbo": {
        "municipio": "Turbo",
        "poblacion_2024": 162_869,
        "nbi_pct": 52.4,
        "nbi_cabecera_pct": 38.6,
        "nbi_rural_pct": 68.2,
        "rural_pct": 58.0,
        "hogares_con_nbi": 18_420,
        "componente_vivienda": 14.8,
        "componente_servicios": 21.4,
        "componente_hacinamiento": 9.6,
        "componente_dependencia": 22.8,
        "indice_vulnerabilidad": 0.82,
    },
    "apartado": {
        "municipio": "Apartadó",
        "poblacion_2024": 127_506,
        "nbi_pct": 24.8,
        "nbi_cabecera_pct": 18.4,
        "nbi_rural_pct": 42.6,
        "rural_pct": 22.0,
        "hogares_con_nbi": 7_940,
        "componente_vivienda": 6.8,
        "componente_servicios": 9.2,
        "componente_hacinamiento": 5.4,
        "componente_dependencia": 10.8,
        "indice_vulnerabilidad": 0.64,
    },
    "chigorodo": {
        "municipio": "Chigorodó",
        "poblacion_2024": 71_843,
        "nbi_pct": 29.6,
        "nbi_cabecera_pct": 21.2,
        "nbi_rural_pct": 46.8,
        "rural_pct": 35.0,
        "hogares_con_nbi": 5_480,
        "componente_vivienda": 8.2,
        "componente_servicios": 11.6,
        "componente_hacinamiento": 6.4,
        "componente_dependencia": 13.2,
        "indice_vulnerabilidad": 0.68,
    },
    "carepa": {
        "municipio": "Carepa",
        "poblacion_2024": 47_617,
        "nbi_pct": 31.4,
        "nbi_cabecera_pct": 22.8,
        "nbi_rural_pct": 48.2,
        "rural_pct": 40.0,
        "hogares_con_nbi": 3_860,
        "componente_vivienda": 8.8,
        "componente_servicios": 12.4,
        "componente_hacinamiento": 6.8,
        "componente_dependencia": 14.1,
        "indice_vulnerabilidad": 0.70,
    },
    # ── SUROESTE ────────────────────────────────────────────────────────────
    "andes": {
        "municipio": "Andes",
        "poblacion_2024": 45_436,
        "nbi_pct": 21.6,
        "nbi_cabecera_pct": 13.2,
        "nbi_rural_pct": 34.8,
        "rural_pct": 58.0,
        "hogares_con_nbi": 2_640,
        "componente_vivienda": 5.8,
        "componente_servicios": 7.4,
        "componente_hacinamiento": 4.6,
        "componente_dependencia": 9.8,
        "indice_vulnerabilidad": 0.56,
    },
    "urrao": {
        "municipio": "Urrao",
        "poblacion_2024": 47_318,
        "nbi_pct": 32.8,
        "nbi_cabecera_pct": 18.6,
        "nbi_rural_pct": 52.4,
        "rural_pct": 68.0,
        "hogares_con_nbi": 3_840,
        "componente_vivienda": 9.2,
        "componente_servicios": 12.8,
        "componente_hacinamiento": 6.4,
        "componente_dependencia": 14.6,
        "indice_vulnerabilidad": 0.69,
    },
    # ── NORDESTE ────────────────────────────────────────────────────────────
    "segovia": {
        "municipio": "Segovia",
        "poblacion_2024": 40_218,
        "nbi_pct": 28.4,
        "nbi_cabecera_pct": 19.8,
        "nbi_rural_pct": 48.6,
        "rural_pct": 45.0,
        "hogares_con_nbi": 3_080,
        "componente_vivienda": 7.8,
        "componente_servicios": 11.2,
        "componente_hacinamiento": 5.8,
        "componente_dependencia": 12.4,
        "indice_vulnerabilidad": 0.67,
    },
    # Alias para compatibilidad
    "santa_fe_antioquia": {
        "municipio": "Santa Fe de Antioquia",
        "poblacion_2024": 23_598,
        "nbi_pct": 22.3,
        "nbi_cabecera_pct": 14.5,
        "nbi_rural_pct": 34.8,
        "rural_pct": 55.0,
        "hogares_con_nbi": 1_380,
        "componente_vivienda": 6.8,
        "componente_servicios": 9.2,
        "componente_hacinamiento": 4.1,
        "componente_dependencia": 9.7,
        "indice_vulnerabilidad": 0.62,
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
# Mapeo municipio_id → título exacto del artículo en Wikipedia Español
# Se usa para consultar Wikidata (que contiene datos estructurados DANE).
# Misma fuente que aparece en Google/búsquedas de internet.
MUNICIPIO_WIKIPEDIA: Dict[str, str] = {
    # Valle de Aburrá
    "medellin": "Medellín",
    "bello": "Bello (Antioquia)",
    "itagui": "Itagüí",
    "envigado": "Envigado",
    "sabaneta": "Sabaneta (Antioquia)",
    "la_estrella": "La Estrella (Antioquia)",
    "copacabana": "Copacabana (Antioquia)",
    "girardota": "Girardota",
    "caldas": "Caldas (Antioquia)",
    "barbosa": "Barbosa (Antioquia)",
    "amaga": "Amagá",
    # Oriente
    "guatape": "Guatapé (Antioquia)",
    "el_penol": "El Peñol (Antioquia)",
    "rionegro": "Rionegro (Antioquia)",
    "marinilla": "Marinilla",
    "el_carmen": "El Carmen de Viboral",
    "la_ceja": "La Ceja",
    "el_retiro": "El Retiro (Antioquia)",
    "san_vicente": "San Vicente Ferrer",
    "la_union": "La Unión (Antioquia)",
    "sonson": "Sonsón",
    "abejorral": "Abejorral",
    "santuario": "Santuario (Antioquia)",
    "cocorna": "Cocorná",
    "san_francisco": "San Francisco (Antioquia)",
    "san_luis": "San Luis (Antioquia)",
    "granada": "Granada (Antioquia)",
    "alejandria": "Alejandría (Antioquia)",
    "concepcion": "Concepción (Antioquia)",
    "argelia": "Argelia (Antioquia)",
    "guarne": "Guarne",
    "san_carlos": "San Carlos (Antioquia)",
    "narino_ant": "Nariño (Antioquia)",
    # Norte
    "santa_rosa": "Santa Rosa de Osos",
    "yarumal": "Yarumal",
    "don_matias": "Don Matías",
    "entrerrios": "Entrerríos",
    "ituango": "Ituango",
    "angostura": "Angostura (Antioquia)",
    "guadalupe": "Guadalupe (Antioquia)",
    "valdivia": "Valdivia (Antioquia)",
    "taraza": "Tarazá",
    "caceres": "Cáceres (Antioquia)",
    "zaragoza": "Zaragoza (Antioquia)",
    "anori": "Anorí",
    "campamento": "Campamento (Antioquia)",
    "belmira": "Belmira",
    "san_jose_mt": "San José de la Montaña",
    "san_andres_c": "San Andrés de Cuerquia",
    "san_andres_cuerquia": "San Andrés de Cuerquia",
    "toledo": "Toledo (Antioquia)",
    "gomez_plata": "Gómez Plata",
    "san_pedro_milagros": "San Pedro de los Milagros",
    # Nordeste
    "segovia": "Segovia (Antioquia)",
    "remedios": "Remedios (Antioquia)",
    "vegachi": "Vegachí",
    "yali": "Yalí",
    "yolombo": "Yolombó",
    "amalfi": "Amalfi (Antioquia)",
    "cisneros": "Cisneros (Antioquia)",
    "caracoli": "Caracolí",
    "maceo": "Maceo (Antioquia)",
    # Bajo Cauca
    "el_bagre": "El Bagre",
    "caucasia": "Caucasia (Antioquia)",
    "nechi": "Nechí",
    # Occidente
    "santa_fe": "Santa Fe de Antioquia",
    "santa_fe_antioquia": "Santa Fe de Antioquia",
    "sopetran": "Sopetrán",
    "olaya": "Olaya (Antioquia)",
    "liborina": "Liborina",
    "sabanalarga": "Sabanalarga (Antioquia)",
    "peque": "Peque (Antioquia)",
    "caicedo": "Caicedo (Antioquia)",
    "anza": "Anzá",
    "armenia_a": "Armenia (Antioquia)",
    "ebejico": "Ebéjico",
    "san_jeronimo": "San Jerónimo (Antioquia)",
    "heliconia": "Heliconia (Antioquia)",
    "angelopolis": "Angélpolis",
    "venecia": "Venecia (Antioquia)",
    "buritica": "Buriticá",
    "giraldo": "Giraldo (Antioquia)",
    "frontino": "Frontino",
    "abriaqui": "Abriaquí",
    # Suroeste
    "andes": "Andes (Antioquia)",
    "jerico": "Jericó (Antioquia)",
    "fredonia": "Fredonia (Antioquia)",
    "tarso": "Tarso (Antioquia)",
    "pueblorrico": "Pueblorrico",
    "ciudad_bolivar": "Ciudad Bolívar (Antioquia)",
    "betania": "Betania (Antioquia)",
    "concordia": "Concordia (Antioquia)",
    "betulia": "Betulia (Antioquia)",
    "salgar": "Salgar",
    "urrao": "Urrao",
    "jardin": "Jardín (Antioquia)",
    "la_pintada": "La Pintada (Antioquia)",
    "montebello": "Montebello (Antioquia)",
    "santa_barbara": "Santa Bárbara (Antioquia)",
    "tamesis": "Támesis",
    "valparaiso": "Valparaíso (Antioquia)",
    # Urabá
    "turbo": "Turbo (Colombia)",
    "apartado": "Apartadó",
    "carepa": "Carepa (Antioquia)",
    "chigorodo": "Chigorodó",
    "necocli": "Necoclí",
    "arboletes": "Arboletes",
    "san_juan_u": "San Juan de Urabá",
    "san_pedro_u": "San Pedro de Urabá",
    "dabeiba": "Dabeiba",
    "vigia_f": "Vigía del Fuerte",
    "vigia_fuerte": "Vigía del Fuerte",
    "murindo": "Murindó",
    # Magdalena Medio
    "yondo": "Yondó",
}


async def _fetch_poblacion_wikidata(wiki_titulo: str) -> Optional[int]:
    """
    Obtiene la población desde Wikidata usando el título del artículo de Wikipedia ES.
    Wikidata contiene datos estructurados de DANE — exactamente los mismos valores que
    aparecen en Google, Wikipedia y búsquedas de internet.

    Usa la claim P1082 (población) con calificador P585 (fecha/año).
    Retorna el valor más reciente o el marcado como 'preferred'.
    Cache: 24 horas (datos cambian anualmente con nueva proyección DANE).
    """
    cache_key = f"wikidata_pop:{wiki_titulo}"
    cached = _cache_get(cache_key)
    if cached:
        return cached.get("pop")

    try:
        # Obtener entidad Wikidata a partir del artículo de Wikipedia ES
        url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "sites": "eswiki",
            "titles": wiki_titulo,
            "format": "json",
            "props": "claims",
            "formatversion": "2",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=10),
                ssl=False,
                headers={"User-Agent": "OMAIRA/5.0 (sistema de gestión de riesgos Colombia)"}
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)

        entities = data.get("entities", [])
        if not entities:
            return None
        entity = entities[0] if isinstance(entities, list) else next(iter(entities.values()), {})
        if entity.get("id") == "-1" or "missing" in entity:
            return None

        # P1082 = población
        pop_claims = entity.get("claims", {}).get("P1082", [])
        if not pop_claims:
            return None

        best_pop: Optional[int] = None
        best_year: int = 0

        for claim in pop_claims:
            if claim.get("rank") == "deprecated":
                continue
            snak = claim.get("mainsnak", {})
            if snak.get("snaktype") != "value":
                continue
            val = snak.get("datavalue", {}).get("value", {})
            try:
                pop_val = int(str(val.get("amount", "0")).lstrip("+").split(".")[0])
            except (ValueError, AttributeError):
                continue
            if pop_val < 500:
                continue

            # Extraer año del calificador P585 (fecha de referencia)
            year = 0
            for q in claim.get("qualifiers", {}).get("P585", []):
                time_str = q.get("datavalue", {}).get("value", {}).get("time", "")
                if time_str and len(time_str) >= 5:
                    try:
                        year = int(time_str[1:5])
                    except ValueError:
                        pass

            # Preferido = usar directamente; sino, el más reciente
            if claim.get("rank") == "preferred":
                best_pop = pop_val
                best_year = year
                break
            if year > best_year or best_pop is None:
                best_pop = pop_val
                best_year = year

        if best_pop and best_pop > 0:
            _cache_set(cache_key, {"pop": best_pop, "year": best_year})
            logger.info(f"Wikidata pop OK '{wiki_titulo}': {best_pop:,} (año ref: {best_year})")
            return best_pop

    except Exception as e:
        logger.debug(f"Wikidata fetch error para '{wiki_titulo}': {e}")
    return None


async def obtener_dane(zona_id: str) -> Dict:
    """
    Retorna indicadores DANE para la zona: NBI, población, vulnerabilidad.
    Población: primero intenta Wikipedia (fuente DANE, misma que aparece en internet),
    si no disponible usa el valor estático del catálogo DANE_ESTATICO.
    NBI: siempre desde DANE_ESTATICO (Censo CNPV 2018, no cambia frecuente).
    """
    cached = _cache_get(f"dane:{zona_id}")
    if cached:
        return cached

    # NBI y datos estructurales — desde catálogo estático (Censo 2018)
    en_catalogo = zona_id in DANE_ESTATICO
    base = DANE_ESTATICO.get(zona_id) or DANE_ESTATICO.get("medellin")

    # Población — Wikidata primero (datos estructurados DANE = mismos que internet/Google)
    pop_real: Optional[int] = None
    pop_año: Optional[int] = None
    pop_fuente = "Catálogo DANE estático"
    pop_verificada = False

    wiki_nombre = MUNICIPIO_WIKIPEDIA.get(zona_id)
    if wiki_nombre:
        pop_wikidata = await _fetch_poblacion_wikidata(wiki_nombre)
        if pop_wikidata and pop_wikidata > 0:
            pop_real = pop_wikidata
            pop_fuente = "Wikidata / Proyección DANE (misma fuente que Google e internet)"
            pop_verificada = True

    # Fallback: catálogo estático (solo si Wikidata no responde)
    if pop_real is None and en_catalogo:
        pop_real = base["poblacion_2024"]
        pop_fuente = "Catálogo DANE estático — puede no coincidir con búsquedas actuales"

    resultado = {
        "fuente": "DANE — Censo CNPV 2018 + Proyecciones",
        "fuente_id": "DANE",
        "zona_id": zona_id,
        "municipio": base["municipio"],
        "poblacion_2024": pop_real,
        "poblacion_verificada": pop_verificada,
        "poblacion_fuente": pop_fuente,
        "nbi": {
            "total_pct": base["nbi_pct"] if en_catalogo else None,
            "cabecera_pct": base["nbi_cabecera_pct"] if en_catalogo else None,
            "rural_pct": base["nbi_rural_pct"] if en_catalogo else None,
            "hogares_afectados": base["hogares_con_nbi"] if en_catalogo else None,
            "componentes": {
                "vivienda_inadecuada": base["componente_vivienda"] if en_catalogo else None,
                "servicios_inadecuados": base["componente_servicios"] if en_catalogo else None,
                "hacinamiento": base["componente_hacinamiento"] if en_catalogo else None,
                "alta_dependencia_economica": base["componente_dependencia"] if en_catalogo else None,
            } if en_catalogo else {},
        },
        "estructura_territorial": {
            "rural_pct": base["rural_pct"] if en_catalogo else None,
            "urbano_pct": round(100 - base["rural_pct"], 1) if en_catalogo else None,
        },
        "indice_vulnerabilidad_dane": base["indice_vulnerabilidad"] if en_catalogo else None,
        "interpretacion": _interpretar_nbi(base["nbi_pct"]) if en_catalogo else "Sin datos NBI para este municipio",
        "fuente_real": en_catalogo,
        "modo_degradado": not en_catalogo,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    _cache_set(f"dane:{zona_id}", resultado)
    logger.info(f"DANE OK {zona_id}: NBI={'sí' if en_catalogo else 'no'}, pob={pop_real}")
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
        # Sin sectores para este municipio/corredor → lista vacía; no heredar datos de otras subregiones
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
        # Sin datos municipales propios → lista vacía; no heredar datos departamentales de otras subregiones
        filas_uso = filas_mun
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


# ── ENSO — Índice ONI real (NOAA CPC) ────────────────────────────────────────
async def obtener_enso() -> Dict:
    """Índice ONI de NOAA — fase actual de El Niño/La Niña. Caché 24 h."""
    cache_key = "enso_oni"
    ahora = _time.time()
    cached = _cache.get(cache_key)
    if cached and ahora - cached[0] < 86400:
        return cached[1]

    url = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=_SSL_CTX, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                texto = await resp.text()

        lineas = [l.strip() for l in texto.strip().splitlines()
                  if l.strip() and not l.strip().startswith("SEAS")]
        ultima = lineas[-1].split()
        # Formato NOAA: SEAS YR TOTAL ANOM — índice 3 es la anomalía ONI, no el índice 2 (TOTAL SST ~28°C)
        seas, yr, oni = ultima[0], int(ultima[1]), float(ultima[3])

        if oni > 0.5:
            fase = "El Niño"
            f_clima = max(0.70, 1.0 - (oni - 0.5) * 0.30)
            desc = "Condiciones más secas. Menor riesgo de inundaciones, mayor riesgo de incendios en Antioquia."
        elif oni < -0.5:
            fase = "La Niña"
            f_clima = min(1.55, 1.0 + (abs(oni) - 0.5) * 0.45)
            desc = "Condiciones más húmedas. Mayor riesgo de deslizamientos e inundaciones en Antioquia."
        else:
            fase = "Neutro"
            f_clima = 1.0
            desc = "Condiciones climáticas sin amplificación adicional de riesgos."

        resultado = {
            "fuente": "NOAA Climate Prediction Center — ONI",
            "fuente_id": "ENSO",
            "indice_oni": oni,
            "temporada": seas,
            "año": yr,
            "fase_enso": fase,
            "factor_clima": round(f_clima, 3),
            "descripcion": desc,
            "fuente_real": True,
            "modo_degradado": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _cache[cache_key] = (ahora, resultado)
        return resultado

    except Exception as e:
        logger.warning(f"ENSO NOAA no disponible: {e}")
        fallback = {
            "fuente": "Fallback — NOAA no disponible",
            "fuente_id": "ENSO",
            "indice_oni": 0.0,
            "fase_enso": "Neutro (estimado)",
            "factor_clima": 1.0,
            "descripcion": "Sin datos ENSO — factor climático neutro aplicado.",
            "fuente_real": False,
            "modo_degradado": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _cache[cache_key] = (ahora - 82800, fallback)  # reintentar en 1 h
        return fallback


# ── Sismicidad — USGS FDSNWS ─────────────────────────────────────────────────
_COORDS_SISMO: Dict[str, tuple] = {
    "guatape":            (6.2336, -75.1567),
    "medellin":           (6.2442, -75.5812),
    "rionegro":           (6.1546, -75.3769),
    "santa_fe_antioquia": (6.5548, -75.8278),
    "caucasia":           (7.9882, -75.1975),
}

async def obtener_sismicidad(zona_id: str) -> Dict:
    """Sismos recientes (USGS FDSNWS) en radio 250 km. Caché 30 min."""
    cache_key = f"sismicidad:{zona_id}"
    ahora = _time.time()
    cached = _cache.get(cache_key)
    if cached and ahora - cached[0] < 1800:
        return cached[1]

    lat, lon = _COORDS_SISMO.get(zona_id, (6.2442, -75.5812))
    inicio = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")

    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson", "latitude": lat, "longitude": lon,
        "maxradiuskm": 250, "minmagnitude": 3.0,
        "orderby": "time", "limit": 10, "starttime": inicio,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, ssl=_SSL_CTX,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)

        features = data.get("features", [])
        total = len(features)
        max_mag = 0.0
        sismos = []
        for f in features[:5]:
            p = f.get("properties", {})
            mag = p.get("mag") or 0.0
            if mag > max_mag:
                max_mag = mag
            t_ms = p.get("time", 0)
            dt = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).isoformat() if t_ms else ""
            sismos.append({"magnitud": round(mag, 1), "lugar": p.get("place", ""), "tiempo": dt})

        if max_mag >= 5.0:
            factor = min(1.0, (max_mag - 3.0) / 3.0)
        elif max_mag >= 4.0:
            factor = 0.35 + min(0.30, total / 20 * 0.30)
        else:
            factor = min(0.20, total * 0.03)

        nivel = "alto" if factor > 0.5 else "medio" if factor > 0.2 else "bajo"

        resultado = {
            "fuente": "USGS FDSNWS — National Earthquake Information Center",
            "fuente_id": "USGS",
            "zona_id": zona_id,
            "sismos_7_dias": total,
            "magnitud_maxima": round(max_mag, 1),
            "factor_sismico": round(factor, 3),
            "nivel_sismico": nivel,
            "sismos_recientes": sismos,
            "fuente_real": True,
            "modo_degradado": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _cache[cache_key] = (ahora, resultado)
        return resultado

    except Exception as e:
        logger.warning(f"Sismicidad USGS no disponible para {zona_id}: {e}")
        fallback = {
            "fuente": "Fallback — USGS no disponible",
            "fuente_id": "USGS",
            "zona_id": zona_id,
            "sismos_7_dias": 0,
            "magnitud_maxima": 0.0,
            "factor_sismico": 0.04,
            "nivel_sismico": "bajo",
            "sismos_recientes": [],
            "fuente_real": False,
            "modo_degradado": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _cache[cache_key] = (ahora - 1740, fallback)  # reintentar en 1 min
        return fallback


# ── Embalses — Nivel real vía API pública XM/SIMEM ───────────────────────────
# Fuente: https://www.simem.co/backend-files/api/PublicData?datasetid=843497
# Dataset: Reservas Hidráulicas del SIN — actualización diaria ~08h COT
_EMBALSE_XM: Dict[str, str] = {
    "guatape":    "PENOL",
    "el_penol":   "PENOL",
    "san_carlos": "PENOL",
    "alejandria": "PENOL",
    "ituango":    "ITUANGO",
}


async def obtener_nivel_embalse_xm(zona_id: str) -> Dict:
    """Nivel real del embalse vía API pública XM/SIMEM (sin API key). Caché 4 h."""
    codigo = _EMBALSE_XM.get(zona_id)
    if not codigo:
        return {
            "fuente_real": False,
            "modo_degradado": True,
            "zona_id": zona_id,
            "motivo": "sin embalse mapeado para este municipio",
        }

    cache_key = f"embalse_xm:{codigo}"
    ahora = _time.time()
    cached = _cache.get(cache_key)
    if cached and ahora - cached[0] < 14400:  # 4 h — datos son diarios
        return cached[1]

    fecha_hoy  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fecha_base = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
    url = (
        "https://www.simem.co/backend-files/api/PublicData"
        f"?datasetid=843497&startdate={fecha_base}&enddate={fecha_hoy}"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=_SSL_CTX,
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)

        if not data.get("success"):
            raise ValueError(f"SIMEM: {data.get('message', 'error desconocido')}")

        records = data.get("result", {}).get("records", [])
        propios = [r for r in records if r.get("CodigoEmbalse") == codigo]
        if not propios:
            raise ValueError(f"sin registros para embalse {codigo} en {fecha_base}–{fecha_hoy}")

        ultimo = sorted(propios, key=lambda r: r.get("Fecha", ""), reverse=True)[0]
        nivel_pct = round(float(ultimo["VolumenUtilPorcentaje"]) * 100, 1)

        resultado = {
            "fuente": "XM — SIMEM Reservas Hidráulicas (dataset 843497)",
            "fuente_id": "XM_EMBALSE",
            "zona_id": zona_id,
            "codigo_embalse": codigo,
            "fecha_dato": ultimo.get("Fecha"),
            "nivel_embalse_pct": nivel_pct,
            "fuente_real": True,
            "modo_degradado": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _cache[cache_key] = (ahora, resultado)
        return resultado

    except Exception as e:
        logger.warning(f"XM Embalse {codigo} no disponible para {zona_id}: {e}")
        fallback = {
            "fuente_real": False,
            "modo_degradado": True,
            "zona_id": zona_id,
            "codigo_embalse": codigo,
            "motivo": str(e)[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _cache[cache_key] = (ahora - 13200, fallback)  # reintentar en 1 h
        return fallback


# ═══════════════════════════════════════════════════════════════════════════════
# 7. TOMTOM — Tráfico en tiempo real (key en Railway, nunca en el frontend)
# ═══════════════════════════════════════════════════════════════════════════════
async def obtener_tomtom(zona_id: str) -> Dict:
    """
    Consulta TomTom Traffic API usando TOMTOM_API_KEY del entorno Railway.
    Ningún usuario necesita escribir ni ver la clave — el control es del desarrollador.
    """
    api_key = os.getenv("TOMTOM_API_KEY")
    if not api_key:
        return {
            "fuente": "TomTom Traffic",
            "fuente_id": "TOMTOM",
            "zona_id": zona_id,
            "fuente_real": False,
            "modo_degradado": True,
            "motivo": "TOMTOM_API_KEY no configurada en Railway",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    cache_key = f"tomtom:{zona_id}"
    ahora = _time.time()
    cached = _cache.get(cache_key)
    if cached and ahora - cached[0] < 300:  # 5 min — datos de tráfico cambian rápido
        return cached[1]

    from app.services.openmeteo_service import COORDS_ZONAS
    lat, lon = COORDS_ZONAS.get(zona_id, (6.2442, -75.5812))

    try:
        async with aiohttp.ClientSession() as session:
            flow_url = (
                f"https://api.tomtom.com/traffic/services/4/flowSegmentData"
                f"/absolute/10/json?point={lat},{lon}&key={api_key}"
            )
            async with session.get(flow_url, ssl=_SSL_CTX,
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    raise ConnectionError(f"TomTom flow HTTP {r.status}")
                flow_data = await r.json(content_type=None)

            delta = 0.5
            bbox = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
            inc_url = (
                f"https://api.tomtom.com/traffic/services/5/incidentDetails"
                f"?bbox={bbox}&fields={{incidents{{type,properties{{iconCategory,"
                f"magnitudeOfDelay,events{{description}},from,to,delay}}}}}}"
                f"&language=es-419&t=1111&categoryFilter=0,1,2,3,4,5,6,7,8,9,10,11"
                f"&timeValidityFilter=present&key={api_key}"
            )
            async with session.get(inc_url, ssl=_SSL_CTX,
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                inc_data = await r.json(content_type=None) if r.status == 200 else {}

        f = flow_data.get("flowSegmentData", {})
        inc = inc_data.get("incidents", [])
        velocidad = f.get("currentSpeed", 0)
        velocidad_libre = f.get("freeFlowSpeed", 0)
        congestion_pct = (
            round((1 - velocidad / velocidad_libre) * 100)
            if velocidad and velocidad_libre else 0
        )
        tt_actual = f.get("currentTravelTime", 0)
        tt_libre = f.get("freeFlowTravelTime", 0)
        if tt_actual and tt_libre:
            nivel_flujo = ("congestionado" if tt_actual > tt_libre * 1.5
                           else "lento" if tt_actual > tt_libre * 1.2 else "normal")
        else:
            nivel_flujo = "normal"

        resultado = {
            "fuente": "TomTom Traffic — tiempo real",
            "fuente_id": "TOMTOM",
            "zona_id": zona_id,
            "velocidad_actual": velocidad,
            "velocidad_libre": velocidad_libre,
            "congestion_pct": congestion_pct,
            "nivel_flujo": nivel_flujo,
            "num_incidentes": len(inc),
            "incidentes": [
                {
                    "tipo": i.get("properties", {}).get("iconCategory", "?"),
                    "descripcion": (i.get("properties", {}).get("events") or [{}])[0].get("description", "Incidente vial"),
                    "desde": i.get("properties", {}).get("from", ""),
                    "hasta": i.get("properties", {}).get("to", ""),
                    "demora_min": round((i.get("properties", {}).get("delay", 0) or 0) / 60),
                }
                for i in inc[:5]
            ],
            "fuente_real": True,
            "modo_degradado": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _cache[cache_key] = (ahora, resultado)
        return resultado

    except Exception as e:
        logger.warning(f"TomTom error para {zona_id}: {e}")
        return {
            "fuente": "TomTom Traffic",
            "fuente_id": "TOMTOM",
            "zona_id": zona_id,
            "fuente_real": False,
            "modo_degradado": True,
            "motivo": str(e)[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 8. TOMORROW.IO — Clima hiperlocal (key en Railway, nunca en el frontend)
# ═══════════════════════════════════════════════════════════════════════════════
async def obtener_tomorrow(zona_id: str) -> Dict:
    """
    Consulta Tomorrow.io usando TOMORROW_IO_API_KEY del entorno Railway.
    Ningún usuario necesita escribir ni ver la clave — el control es del desarrollador.
    """
    api_key = os.getenv("TOMORROW_IO_API_KEY")
    if not api_key:
        return {
            "fuente": "Tomorrow.io",
            "fuente_id": "TOMORROW_IO",
            "zona_id": zona_id,
            "fuente_real": False,
            "modo_degradado": True,
            "motivo": "TOMORROW_IO_API_KEY no configurada en Railway",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    cache_key = f"tomorrow:{zona_id}"
    ahora = _time.time()
    cached = _cache.get(cache_key)
    if cached and ahora - cached[0] < 900:  # 15 min
        return cached[1]

    from app.services.openmeteo_service import COORDS_ZONAS
    lat, lon = COORDS_ZONAS.get(zona_id, (6.2442, -75.5812))

    try:
        url = (
            f"https://api.tomorrow.io/v4/weather/realtime"
            f"?location={lat},{lon}&apikey={api_key}"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=_SSL_CTX,
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    raise ConnectionError(f"Tomorrow.io HTTP {r.status}")
                data = await r.json(content_type=None)

        values = data.get("data", {}).get("values", {})
        resultado = {
            "fuente": "Tomorrow.io — clima hiperlocal",
            "fuente_id": "TOMORROW_IO",
            "zona_id": zona_id,
            "uv_index": values.get("uvIndex"),
            "epa_index": values.get("epaIndex"),
            "precipitation_type": values.get("precipitationType"),
            "visibility": values.get("visibility"),
            "humidity": values.get("humidity"),
            "wind_speed": values.get("windSpeed"),
            "values_raw": values,
            "fuente_real": bool(values),
            "modo_degradado": not bool(values),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _cache[cache_key] = (ahora, resultado)
        logger.info(f"Tomorrow.io OK {zona_id}: UV={values.get('uvIndex')} ICA={values.get('epaIndex')}")
        return resultado

    except Exception as e:
        logger.warning(f"Tomorrow.io error para {zona_id}: {e}")
        return {
            "fuente": "Tomorrow.io",
            "fuente_id": "TOMORROW_IO",
            "zona_id": zona_id,
            "fuente_real": False,
            "modo_degradado": True,
            "motivo": str(e)[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
