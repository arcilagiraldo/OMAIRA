"""
Servicio de Cálculo de Riesgo Ambiental
Implementa: RIESGO_TOTAL = (H × E × V) × F_clima
"""
import math
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from app.models.schemas import (
    NivelRiesgo, TipoRiesgo, HorizontePrediccion,
    RiesgoComponentes, PrediccionRiesgo, AlertaRiesgo
)
from app.services.openmeteo_service import obtener_meteo_real
from app.services.database import guardar_predicciones as _db_guardar_predicciones

# ---------------------------------------------------------------------------
# Datos simulados de sensores (reemplazar con integración real SIATA/EPM)
# ---------------------------------------------------------------------------

DATOS_BASE_ZONAS = {
    "guatape": {
        "municipio": "Guatapé",
        "lat": 6.2336, "lon": -75.1567,
        "altitud_m": 1890,
        "pendiente_media_grados": 22,
        "cobertura_vegetal": 0.65,
        "densidad_poblacion": 12,  # hab/km²
        "infraestructura_riesgo": 0.4,
    },
    "medellin": {
        "municipio": "Medellín",
        "lat": 6.2442, "lon": -75.5812,
        "altitud_m": 1495,
        "pendiente_media_grados": 18,
        "cobertura_vegetal": 0.3,
        "densidad_poblacion": 4800,
        "infraestructura_riesgo": 0.7,
    },
    "rionegro": {
        "municipio": "Rionegro",
        "lat": 6.1546, "lon": -75.3769,
        "altitud_m": 2150,
        "pendiente_media_grados": 12,
        "cobertura_vegetal": 0.55,
        "densidad_poblacion": 95,
        "infraestructura_riesgo": 0.5,
    }
}


def _simular_datos_meteorologicos(zona_id: str) -> Dict:
    """
    Simula datos meteorológicos en tiempo real.
    En producción: consultar API IDEAM y sensores SIATA.
    """
    lluvia_24h = random.uniform(0, 120)
    return {
        "lluvia_24h_mm": lluvia_24h,
        "lluvia_72h_mm": lluvia_24h * random.uniform(1.5, 3.5),
        "humedad_suelo": min(1.0, lluvia_24h / 100),
        "temperatura_c": random.uniform(12, 28),
        "nivel_embalse_pct": random.uniform(50, 95),
        "velocidad_viento_ms": random.uniform(0, 15),
        "presion_hpa": random.uniform(870, 890),
    }


def _calcular_factor_enso() -> float:
    """
    Factor climático ENSO (El Niño / La Niña).
    En producción: consultar índice ONI de NOAA.
    Retorna: >1.0 = lluvioso (La Niña), <1.0 = seco (El Niño), ~1.0 = neutral
    """
    # Simulado — en producción consultar ONI NOAA
    oni_actual = 0.4  # Ligeramente Niño
    if oni_actual > 0.5:
        return 0.85  # El Niño → más seco → menos deslizamientos, más incendios
    elif oni_actual < -0.5:
        return 1.35  # La Niña → más lluvia → más inundaciones y deslizamientos
    return 1.0


def _calcular_amenaza(
    tipo: TipoRiesgo,
    zona: Dict,
    meteo: Dict,
    horizonte: HorizontePrediccion
) -> float:
    """
    Calcula componente H (Amenaza) combinando física + ML.
    Retorna valor entre 0 y 1.
    """
    factor_tiempo = {"1h": 0.7, "6h": 0.85, "24h": 1.0, "72h": 1.15}[horizonte.value]

    if tipo == TipoRiesgo.DESLIZAMIENTO:
        pendiente_norm = min(1.0, zona["pendiente_media_grados"] / 45)
        lluvia_norm = min(1.0, meteo["lluvia_24h_mm"] / 100)
        cobertura_inv = 1 - zona["cobertura_vegetal"]
        h = (0.4 * pendiente_norm + 0.4 * lluvia_norm + 0.2 * cobertura_inv)

    elif tipo == TipoRiesgo.INUNDACION:
        lluvia_norm = min(1.0, meteo["lluvia_72h_mm"] / 200)
        nivel_norm = meteo["nivel_embalse_pct"] / 100
        h = (0.5 * lluvia_norm + 0.3 * nivel_norm + 0.2 * meteo["humedad_suelo"])

    elif tipo == TipoRiesgo.TORMENTA:
        viento_norm = min(1.0, meteo["velocidad_viento_ms"] / 20)
        presion_norm = max(0, (890 - meteo["presion_hpa"]) / 30)
        h = (0.6 * presion_norm + 0.4 * viento_norm)

    elif tipo == TipoRiesgo.INCENDIO:
        humedad_inv = 1 - meteo["humedad_suelo"]
        viento_norm = min(1.0, meteo["velocidad_viento_ms"] / 20)
        lluvia_inv = max(0, 1 - meteo["lluvia_24h_mm"] / 20)
        h = (0.4 * humedad_inv + 0.3 * viento_norm + 0.3 * lluvia_inv)

    elif tipo == TipoRiesgo.SEQUIA:
        lluvia_inv = max(0, 1 - meteo["lluvia_72h_mm"] / 50)
        humedad_inv = 1 - meteo["humedad_suelo"]
        h = (0.6 * lluvia_inv + 0.4 * humedad_inv)

    else:
        h = 0.3

    return min(1.0, max(0.0, h * factor_tiempo))


def _calcular_exposicion(zona: Dict) -> float:
    """Componente E (Exposición de elementos en riesgo)"""
    densidad_norm = min(1.0, zona["densidad_poblacion"] / 5000)
    infra = zona["infraestructura_riesgo"]
    return (0.6 * densidad_norm + 0.4 * infra)


def _calcular_vulnerabilidad(zona: Dict) -> float:
    """Componente V (Vulnerabilidad social y física)"""
    pendiente_norm = min(1.0, zona["pendiente_media_grados"] / 45)
    cobertura_inv = 1 - zona["cobertura_vegetal"]
    return (0.5 * pendiente_norm + 0.3 * cobertura_inv + 0.2 * zona["infraestructura_riesgo"])


def _nivel_desde_probabilidad(prob: float) -> NivelRiesgo:
    if prob < 0.1: return NivelRiesgo.MUY_BAJO
    if prob < 0.25: return NivelRiesgo.BAJO
    if prob < 0.45: return NivelRiesgo.MEDIO
    if prob < 0.65: return NivelRiesgo.ALTO
    if prob < 0.85: return NivelRiesgo.MUY_ALTO
    return NivelRiesgo.CRITICO


def _acciones_recomendadas(tipo: TipoRiesgo, nivel: NivelRiesgo) -> List[str]:
    """Genera recomendaciones contextuales según tipo y nivel de riesgo"""
    base = {
        TipoRiesgo.DESLIZAMIENTO: {
            NivelRiesgo.MEDIO: ["Monitorear taludes en zonas rurales", "Activar comités locales de emergencia"],
            NivelRiesgo.ALTO: ["Evacuar zonas de alta pendiente", "Cerrar vías vulnerables", "Alertar comunidades"],
            NivelRiesgo.MUY_ALTO: ["EVACUACIÓN INMEDIATA", "Activar PMU", "Solicitar apoyo UNGRD"],
            NivelRiesgo.CRITICO: ["EVACUACIÓN MASIVA", "Declarar calamidad pública", "Activar todos los protocolos"],
        },
        TipoRiesgo.INUNDACION: {
            NivelRiesgo.MEDIO: ["Monitorear nivel ríos y embalse", "Preparar kits de emergencia"],
            NivelRiesgo.ALTO: ["Alertar comunidades ribereñas", "Preparar albergues", "Restringir acceso a rondas"],
            NivelRiesgo.MUY_ALTO: ["Evacuar zonas de inundación", "Cortar servicios en zonas afectadas"],
            NivelRiesgo.CRITICO: ["EVACUACIÓN TOTAL ribera", "Activar apoyo EPM y Bomberos"],
        },
        TipoRiesgo.INCENDIO: {
            NivelRiesgo.MEDIO: ["Prohibir quemas", "Activar brigadas forestales"],
            NivelRiesgo.ALTO: ["Movilizar bomberos", "Restringir acceso a zonas boscosas"],
            NivelRiesgo.MUY_ALTO: ["Evacuar veredas aledañas", "Solicitar apoyo aéreo"],
            NivelRiesgo.CRITICO: ["EVACUACIÓN área forestal", "Activar protocolo CORNARE"],
        },
    }
    acciones = base.get(tipo, {}).get(nivel, [])
    if not acciones:
        acciones = ["Monitoreo preventivo activado", "Mantener canales de comunicación abiertos"]
    return acciones


async def calcular_riesgo_zona(
    zona_id: str,
    tipo_riesgo: Optional[TipoRiesgo] = None,
    horizonte: HorizontePrediccion = HorizontePrediccion.H24,
    fuentes_activas: Optional[List[str]] = None
) -> Dict:
    """
    Calcula el riesgo total para una zona.
    Implementa: RIESGO = (H × E × V) × F_clima
    """
    zona = DATOS_BASE_ZONAS.get(zona_id)
    modo_degradado = False

    if not zona:
        # Fallback: zona genérica de Antioquia
        zona = {
            "municipio": zona_id.title(),
            "lat": 6.5, "lon": -75.5,
            "altitud_m": 1500, "pendiente_media_grados": 20,
            "cobertura_vegetal": 0.5, "densidad_poblacion": 50,
            "infraestructura_riesgo": 0.4,
        }
        modo_degradado = True

    try:
        meteo = await obtener_meteo_real(zona_id, zona.get("lat"), zona.get("lon"))
    except Exception:
        meteo = _simular_datos_meteorologicos(zona_id)
        modo_degradado = True

    tipos = [tipo_riesgo] if tipo_riesgo else list(TipoRiesgo)
    predicciones = []
    f_clima = _calcular_factor_enso()
    e = _calcular_exposicion(zona)
    v = _calcular_vulnerabilidad(zona)

    for tipo in tipos:
        h = _calcular_amenaza(tipo, zona, meteo, horizonte)
        riesgo_raw = min(1.0, h * e * v * f_clima)

        # Incertidumbre proporcional al horizonte
        incert = {"1h": 0.05, "6h": 0.10, "24h": 0.18, "72h": 0.28}[horizonte.value]
        lower = max(0, riesgo_raw - incert)
        upper = min(1, riesgo_raw + incert)
        nivel = _nivel_desde_probabilidad(riesgo_raw)

        pred = PrediccionRiesgo(
            zona_id=zona_id,
            municipio=zona["municipio"],
            tipo_riesgo=tipo,
            horizonte=horizonte,
            nivel=nivel,
            probabilidad=round(riesgo_raw, 4),
            incertidumbre_lower=round(lower, 4),
            incertidumbre_upper=round(upper, 4),
            componentes=RiesgoComponentes(
                amenaza=round(h, 4),
                exposicion=round(e, 4),
                vulnerabilidad=round(v, 4),
                factor_clima=round(f_clima, 4),
                riesgo_total=round(riesgo_raw, 4)
            ),
            timestamp_prediccion=datetime.utcnow(),
            timestamp_horizonte=datetime.utcnow() + timedelta(
                hours={"1h": 1, "6h": 6, "24h": 24, "72h": 72}[horizonte.value]
            ),
            acciones_recomendadas=_acciones_recomendadas(tipo, nivel),
            fuentes_datos_activas=fuentes_activas or ["IDEAM", "SIATA"],
            modo_degradado=modo_degradado,
            metadata={
                "datos_meteo": meteo,
                "factor_enso": f_clima,
                "altitud_m": zona["altitud_m"],
                "lat": zona["lat"],
                "lon": zona["lon"],
            }
        )
        predicciones.append(pred.model_dump(mode="json"))

    resultado = {
        "zona_id": zona_id,
        "municipio": zona["municipio"],
        "lat": zona["lat"],
        "lon": zona["lon"],
        "timestamp": datetime.utcnow().isoformat(),
        "horizonte": horizonte.value,
        "modo_degradado": modo_degradado,
        "predicciones": predicciones,
        "resumen": {
            "nivel_maximo": max(p["nivel"] for p in predicciones),
            "riesgo_dominante": max(predicciones, key=lambda p: p["probabilidad"])["tipo_riesgo"],
            "probabilidad_maxima": max(p["probabilidad"] for p in predicciones),
        }
    }

    # Persistir en PostgreSQL de forma no bloqueante
    import asyncio
    asyncio.ensure_future(_db_guardar_predicciones(zona_id, predicciones))

    return resultado


async def generar_alertas(zona_id: str) -> List[Dict]:
    """Genera alertas automáticas según predicciones actuales"""
    resultado = await calcular_riesgo_zona(zona_id)
    alertas = []
    for pred in resultado["predicciones"]:
        nivel = pred["nivel"]
        if nivel in [NivelRiesgo.ALTO.value, NivelRiesgo.MUY_ALTO.value, NivelRiesgo.CRITICO.value]:
            alerta = AlertaRiesgo(
                alerta_id=f"ALT-{zona_id}-{pred['tipo_riesgo']}-{datetime.utcnow().strftime('%Y%m%d%H%M')}",
                tipo_riesgo=TipoRiesgo(pred["tipo_riesgo"]),
                nivel=NivelRiesgo(nivel),
                municipio=resultado["municipio"],
                descripcion=f"Riesgo {nivel.upper()} de {pred['tipo_riesgo']} detectado — probabilidad {pred['probabilidad']*100:.1f}%",
                acciones=pred["acciones_recomendadas"],
                timestamp=datetime.utcnow(),
                lat=resultado["lat"],
                lon=resultado["lon"],
            )
            alertas.append(alerta.model_dump(mode="json"))
    return alertas
