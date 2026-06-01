"""
API Router — Configuración No-Técnica (Wizard)
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.models.schemas import ConfiguracionZona, WizardPaso, TipoRiesgo

router = APIRouter()

# Almacenamiento en memoria (en producción: PostgreSQL)
_configuraciones: Dict[str, ConfiguracionZona] = {}

# Municipios disponibles de Antioquia
MUNICIPIOS_ANTIOQUIA = [
    {"id": "guatape", "nombre": "Guatapé", "lat": 6.2336, "lon": -75.1567,
     "sensores_disponibles": ["SIATA", "EPM", "IDEAM"], "riesgos_principales": ["inundacion", "deslizamiento"]},
    {"id": "medellin", "nombre": "Medellín", "lat": 6.2442, "lon": -75.5812,
     "sensores_disponibles": ["SIATA", "IDEAM", "CORNARE"], "riesgos_principales": ["deslizamiento", "inundacion", "tormenta"]},
    {"id": "rionegro", "nombre": "Rionegro", "lat": 6.1546, "lon": -75.3769,
     "sensores_disponibles": ["SIATA", "IDEAM"], "riesgos_principales": ["deslizamiento", "incendio"]},
    {"id": "santa_fe_antioquia", "nombre": "Santa Fe de Antioquia", "lat": 6.5548, "lon": -75.8278,
     "sensores_disponibles": ["IDEAM"], "riesgos_principales": ["incendio", "sequia", "inundacion"]},
    {"id": "caucasia", "nombre": "Caucasia", "lat": 7.9882, "lon": -75.1975,
     "sensores_disponibles": ["IDEAM", "DAGRAN"], "riesgos_principales": ["inundacion", "sequia"]},
]

FUENTES_DISPONIBLES = [
    {"id": "IDEAM", "nombre": "IDEAM", "descripcion": "Clima y pronósticos del tiempo", "tipo": "meteorologia", "disponible": True},
    {"id": "SIATA", "nombre": "SIATA", "descripcion": "Sensores en tiempo real — lluvia, temperatura, nivel", "tipo": "sensores", "disponible": True},
    {"id": "EPM", "nombre": "EPM", "descripcion": "Nivel embalse El Peñol y datos hidrológicos", "tipo": "hidrologia", "disponible": True},
    {"id": "IGAC", "nombre": "IGAC", "descripcion": "Topografía, DEM y cartografía base", "tipo": "geoespacial", "disponible": True},
    {"id": "CORNARE", "nombre": "CORNARE", "descripcion": "Monitoreo ambiental regional", "tipo": "ambiental", "disponible": True},
    {"id": "DAGRAN", "nombre": "DAGRAN / UNGRD", "descripcion": "Histórico de desastres y vulnerabilidad", "tipo": "historico", "disponible": True},
    {"id": "COPERNICUS", "nombre": "Copernicus / Sentinel", "descripcion": "Imágenes satelitales SAR y ópticas", "tipo": "satelital", "disponible": True},
    # Fuentes externas integradas (datos.gov.co / APIs públicas)
    {"id": "DANE", "nombre": "DANE", "descripcion": "Indicadores sociodemográficos: NBI, población, vulnerabilidad (Censo 2018)", "tipo": "socioeconomico", "disponible": True, "endpoint": "/api/v1/fuentes/dane/{zona_id}"},
    {"id": "REPS", "nombre": "REPS — MinSalud", "descripcion": "Prestadores de servicios de salud habilitados por municipio", "tipo": "salud", "disponible": True, "endpoint": "/api/v1/fuentes/reps/{zona_id}"},
    {"id": "ANSV", "nombre": "ANSV — Siniestralidad Vial", "descripcion": "Sectores críticos de accidentalidad vial (rutas de evacuación)", "tipo": "vial", "disponible": True, "endpoint": "/api/v1/fuentes/ansv/{zona_id}"},
    {"id": "SIVIGILA", "nombre": "SIVIGILA — INS", "descripcion": "Vigilancia epidemiológica y eventos de salud pública", "tipo": "epidemiologico", "disponible": True, "endpoint": "/api/v1/fuentes/sivigila/{zona_id}"},
    {"id": "SISAIRE", "nombre": "SISAIRE — IDEAM", "descripcion": "Índice de Calidad del Aire (ICA) — estaciones Antioquia", "tipo": "ambiental", "disponible": True, "endpoint": "/api/v1/fuentes/sisaire/{zona_id}"},
    {"id": "HERE", "nombre": "HERE Technologies", "descripcion": "Tráfico en tiempo real y rutas de evacuación (requiere API key)", "tipo": "vial", "disponible": False, "endpoint": "/api/v1/fuentes/here/{zona_id}", "requiere_clave": True},
]


@router.get("/wizard/pasos")
async def get_wizard_pasos():
    """Retorna la secuencia de pasos del wizard de configuración"""
    return {
        "pasos": [
            WizardPaso(paso=1, titulo="Selecciona tu municipio",
                       descripcion="Elige el municipio o zona que deseas monitorear. El sistema detectará automáticamente los sensores disponibles."),
            WizardPaso(paso=2, titulo="Conecta fuentes de datos",
                       descripcion="Selecciona con un clic las fuentes que deseas integrar. Solo activa las que tienes acceso."),
            WizardPaso(paso=3, titulo="Elige los riesgos a monitorear",
                       descripcion="Selecciona qué tipos de riesgo son relevantes para tu zona. El sistema recomienda los más importantes según la geografía."),
            WizardPaso(paso=4, titulo="Nivel de detalle",
                       descripcion="Elige el nivel de detalle. Mayor detalle = más precisión pero requiere más recursos."),
            WizardPaso(paso=5, titulo="Generar sistema",
                       descripcion="El sistema se configura automáticamente con los parámetros óptimos para tu zona."),
        ]
    }


@router.get("/wizard/municipios")
async def get_municipios():
    """Lista de municipios disponibles con auto-detección de sensores"""
    return {"municipios": MUNICIPIOS_ANTIOQUIA}


@router.get("/wizard/autodetectar/{municipio_id}")
async def autodetectar_configuracion(municipio_id: str):
    """
    Auto-detección inteligente: dado un municipio, retorna
    la configuración recomendada automáticamente.
    """
    municipio = next((m for m in MUNICIPIOS_ANTIOQUIA if m["id"] == municipio_id), None)
    if not municipio:
        raise HTTPException(status_code=404, detail=f"Municipio '{municipio_id}' no encontrado")

    fuentes_recomendadas = [f for f in FUENTES_DISPONIBLES
                            if f["id"] in municipio["sensores_disponibles"]]
    riesgos_recomendados = municipio["riesgos_principales"]

    return {
        "municipio_id": municipio_id,
        "municipio_nombre": municipio["nombre"],
        "coordenadas": {"lat": municipio["lat"], "lon": municipio["lon"]},
        "fuentes_recomendadas": fuentes_recomendadas,
        "riesgos_recomendados": riesgos_recomendados,
        "nivel_detalle_recomendado": "medio",
        "resolucion_grid_m": 30,
        "intervalo_actualizacion_min": 15,
        "nota": "Configuración automática óptima para tu zona. Puedes personalizar cualquier parámetro.",
    }


@router.get("/fuentes")
async def get_fuentes_disponibles():
    """Lista de todas las fuentes de datos disponibles"""
    return {"fuentes": FUENTES_DISPONIBLES}


@router.post("/guardar")
async def guardar_configuracion(config: ConfiguracionZona):
    """Guarda y aplica la configuración de una zona"""
    config.calcular_config_automatica()
    _configuraciones[config.municipio.lower().replace(" ", "_")] = config
    return {
        "mensaje": f"Configuración guardada para {config.municipio}",
        "config_aplicada": config.model_dump(),
        "estado": "activo"
    }


@router.get("/estado/{zona_id}")
async def get_estado_sistema(zona_id: str):
    """Estado actual del sistema para una zona"""
    config = _configuraciones.get(zona_id)
    return {
        "zona_id": zona_id,
        "configurada": config is not None,
        "config": config.model_dump() if config else None,
        "fuentes_activas": config.fuentes_activas if config else ["IDEAM", "SIATA"],
        "modo": "normal",
        "ultimo_update": "2024-01-01T00:00:00Z"
    }
