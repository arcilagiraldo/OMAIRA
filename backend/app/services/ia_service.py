"""
Servicio Multi-Modelo IA
Soporta: Claude (Anthropic), OpenAI, Reglas locales (sin API), Simulación
Funciona con o sin API key — nunca falla.
"""
import json
import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, Optional, Any
from enum import Enum
from app.services.openmeteo_service import obtener_meteo_real, nombre_zona


class ModeloIA(str, Enum):
    CLAUDE   = "claude"
    OPENAI   = "openai"
    LOCAL    = "local"       # Reglas + lógica experta (gratuito, sin internet)
    SIMULADO = "simulado"    # Demo visual (siempre disponible)


MODELOS_INFO = {
    ModeloIA.CLAUDE: {
        "nombre": "Claude Sonnet (Anthropic)",
        "descripcion": "Análisis experto con contexto geográfico y razonamiento avanzado",
        "requiere_key": True,
        "proveedor": "Anthropic",
        "icono": "🟣",
        "endpoint": "https://api.anthropic.com/v1/messages",
    },
    ModeloIA.OPENAI: {
        "nombre": "GPT-4o (OpenAI)",
        "descripcion": "Análisis con modelo de lenguaje de OpenAI",
        "requiere_key": True,
        "proveedor": "OpenAI",
        "icono": "🟢",
        "endpoint": "https://api.openai.com/v1/chat/completions",
    },
    ModeloIA.LOCAL: {
        "nombre": "Motor local (reglas expertas)",
        "descripcion": "Sistema basado en lógica experta y umbrales calibrados para Antioquia. Gratuito, sin internet.",
        "requiere_key": False,
        "proveedor": "SIRGA local",
        "icono": "🔵",
    },
    ModeloIA.SIMULADO: {
        "nombre": "Simulación IA (demo)",
        "descripcion": "Análisis simulado para demostración. Siempre disponible.",
        "requiere_key": False,
        "proveedor": "SIRGA demo",
        "icono": "⚫",
    },
}


def _construir_prompt(datos_combinados: Dict) -> str:
    """Construye el prompt de análisis para modelos de lenguaje"""
    zona_id = datos_combinados.get("zona", "guatape")
    zona_nombre = datos_combinados.get("zona_nombre", nombre_zona(zona_id))
    irg = datos_combinados.get("irg", {})
    sensores = datos_combinados.get("sensores", {})
    predicciones = datos_combinados.get("predicciones", [])
    contexto = datos_combinados.get("contexto_local", {})
    alertas = datos_combinados.get("alertas_irg", [])
    externos = datos_combinados.get("datos_externos", {})

    pred_resumen = "\n".join([
        f"  - {p.get('tipo_riesgo','?')}: {p.get('nivel','?')} ({p.get('probabilidad',0)*100:.1f}%)"
        for p in predicciones[:5]
    ]) if predicciones else "  - No disponibles"

    alertas_resumen = "\n".join([
        f"  - [{a.get('nivel','?').upper()}] {a.get('tipo','?')}: {a.get('descripcion','')[:100]}"
        for a in alertas[:4]
    ]) if alertas else "  - Sin alertas activas"

    externos_txt = ""
    if externos:
        fuente_label = "Open-Meteo (real, sin API key)" if externos.get("fuente_real") else externos.get("fuente", "Open-Meteo")
        externos_txt = f"""
DATOS METEOROLÓGICOS EXTERNOS ({fuente_label}):
- Temperatura: {externos.get('temperatura_c', 'N/D')}°C
- Lluvia acumulada 24h: {externos.get('lluvia_24h_mm', externos.get('precipitacion_3h', 'N/D'))} mm
- Precipitación actual: {externos.get('precipitacion_actual_mm', 'N/D')} mm/h
- Humedad relativa: {externos.get('humedad_relativa', 'N/D')}%
- Velocidad viento: {externos.get('velocidad_viento_ms', externos.get('viento_ms', 'N/D'))} m/s
- Nubosidad: {externos.get('nubosidad_pct', 'N/D')}%
- Código clima WMO: {externos.get('codigo_clima', 'N/D')}"""

    return f"""Eres un experto en gestión del riesgo de desastres en Colombia, especializado en el Oriente Antioqueño.
Analiza la siguiente información en tiempo real del sistema SIRGA para el municipio de {zona_nombre}, Antioquia.

DATOS DE SENSORES EN TIEMPO REAL:
- Lluvia 24h: {sensores.get('lluvia24', 'N/D')} mm/h
- Nivel embalse El Peñol: {sensores.get('embalse', 'N/D')}%
- Temperatura: {sensores.get('temp', 'N/D')}°C
- Humedad suelo: {sensores.get('hum', 'N/D')}%
- Viento: {sensores.get('viento', 'N/D')} m/s
{externos_txt}

ÍNDICE DE RIESGO GLOBAL (IRG): {irg.get('irg', 0)*100:.1f}% — Nivel: {irg.get('nivel', 'N/D').replace('_', ' ').upper()}

TOP FACTORES DE RIESGO:
{chr(10).join([f"  - {v}: {c*100:.1f}%" for v, c in irg.get('top_factores', [])[:4]])}

PREDICCIONES ML POR TIPO:
{pred_resumen}

ALERTAS ACTIVAS:
{alertas_resumen}

CONTEXTO LOCAL {zona_nombre.upper()}:
- Hora actual: {contexto.get('hora', 'N/D')}:00
- Turismo: {contexto.get('turismo_nivel', 'N/D')} ({contexto.get('turismo_pct', 'N/D')}%)
- Movilidad vial: {contexto.get('movilidad_pct', 'N/D')}%

Proporciona un análisis estructurado con estos 4 componentes EXACTOS en formato JSON:
{{
  "diagnostico": "Párrafo de 2-3 oraciones explicando la situación actual del riesgo en lenguaje claro para autoridades no técnicas",
  "pronostico": "Párrafo de 2-3 oraciones sobre qué se espera en las próximas 6-12 horas basado en las tendencias",
  "explicacion_experta": "Explicación técnica de 3-4 oraciones sobre los mecanismos físicos que generan el riesgo actual (deslizamientos, inundaciones, etc.)",
  "recomendaciones": ["Acción 1 específica y ejecutable", "Acción 2", "Acción 3", "Acción 4", "Acción 5"]
}}
Responde SOLO con el JSON, sin texto adicional, sin markdown."""


def _analisis_local(datos_combinados: Dict) -> Dict:
    """
    Motor de reglas expertas local — funciona sin internet ni API key.
    Calibrado para condiciones de Antioquia/Guatapé.
    """
    irg = datos_combinados.get("irg", {})
    sensores = datos_combinados.get("sensores", {})
    contexto = datos_combinados.get("contexto_local", {})
    alertas = datos_combinados.get("alertas_irg", [])

    irg_val = irg.get("irg", 0.2)
    nivel = irg.get("nivel", "bajo")
    lluvia = sensores.get("lluvia24", 0)
    embalse = sensores.get("embalse", 70)
    turismo_pct = contexto.get("turismo_pct", 30)
    hora = contexto.get("hora", 12)
    top = irg.get("top_factores", [])
    factor_principal = top[0][0].replace("_", " ") if top else "precipitación"

    # ── Diagnóstico basado en reglas ──────────────────────────────────────
    if irg_val > 0.72:
        diagnostico = (
            f"SITUACIÓN CRÍTICA: El IRG de {irg_val*100:.0f}% indica condiciones de riesgo extremo "
            f"en Guatapé. El factor dominante es {factor_principal} con lluvia de {lluvia:.0f} mm/h "
            f"y embalse al {embalse:.0f}%. Se requieren acciones inmediatas de protección civil."
        )
    elif irg_val > 0.55:
        diagnostico = (
            f"SITUACIÓN DE ALERTA: IRG en {irg_val*100:.0f}% — nivel {nivel.replace('_',' ')}. "
            f"Combinación de {factor_principal} y condiciones atmosféricas adversas elevan el riesgo. "
            f"El embalse al {embalse:.0f}% requiere monitoreo continuo de EPM."
        )
    elif irg_val > 0.35:
        diagnostico = (
            f"RIESGO MODERADO: IRG en {irg_val*100:.0f}%. Condiciones de {factor_principal} "
            f"están dentro de rangos manejables pero requieren atención. "
            f"Lluvia acumulada de {lluvia:.0f} mm/h en las últimas 24 horas."
        )
    else:
        diagnostico = (
            f"CONDICIONES NORMALES: IRG en {irg_val*100:.0f}% — sin alertas críticas activas. "
            f"Lluvia de {lluvia:.0f} mm/h dentro de rangos históricos normales para el Oriente Antioqueño. "
            f"Sistema en monitoreo estándar."
        )

    # ── Pronóstico ────────────────────────────────────────────────────────
    if hora < 12:
        fase_dia = "la tarde"
        tendencia = "Las lluvias convectivas típicas de la tarde podrían elevar el riesgo en 2-3 puntos."
    elif hora < 18:
        fase_dia = "la noche"
        tendencia = "Al disminuir la radiación solar, las precipitaciones tenderán a reducirse, mejorando condiciones."
    else:
        fase_dia = "mañana en la mañana"
        tendencia = "En horas nocturnas el riesgo de neblina vial aumenta con la caída de temperatura."

    if turismo_pct > 70:
        turismo_txt = f"Alta afluencia turística ({turismo_pct}%) complica las operaciones de emergencia."
    else:
        turismo_txt = f"Afluencia turística moderada ({turismo_pct}%) facilita el control de accesos."

    pronostico = (
        f"Para {fase_dia} se proyecta {tendencia} "
        f"{turismo_txt} "
        f"Se recomienda actualizar el IRG cada 30 minutos durante este período."
    )

    # ── Explicación experta ───────────────────────────────────────────────
    if lluvia > 60 and sensores.get("hum", 50) > 75:
        mec = (
            "La saturación del suelo supera el 75%, reduciendo la cohesión en materiales arcillosos de las laderas del Oriente Antioqueño. "
            "Bajo condiciones de lluvia superior a 60 mm/h, el factor de seguridad de taludes cae por debajo de 1.0 en pendientes mayores a 30°. "
            "El modelo físico-empírico del sistema calcula la estabilidad combinando la ecuación de Bishop simplificada con correlaciones históricas DAGRAN. "
            "El nivel del embalse añade presión hidrostática sobre los materiales de las márgenes."
        )
    else:
        mec = (
            "El sistema integra el modelo RIESGO=(H×E×V)×F_clima donde H es la amenaza calculada con física de taludes y modelos ML calibrados con datos DAGRAN. "
            "La exposición (E) combina densidad de turistas y flujos de movilidad, mientras la vulnerabilidad (V) refleja la pendiente del terreno y cobertura vegetal. "
            f"El factor ENSO ({datos_combinados.get('factor_enso', 1.04)}) ajusta el riesgo según la fase del ciclo climático (actualmente neutro). "
            "La incertidumbre se calcula mediante intervalos de confianza bootstrap del 90%."
        )

    explicacion_experta = mec

    # ── Recomendaciones ───────────────────────────────────────────────────
    recs = []
    if alertas:
        for a in alertas[:2]:
            if a.get("acciones"):
                recs.append(a["acciones"][0])

    base_recs = {
        "critico":  ["Activar PMU municipal de inmediato", "Evacuar zonas en ladera y ribereñas", "Cortar acceso a embalse y zonas de riesgo", "Notificar DAGRAN y UNGRD", "Activar albergues de emergencia"],
        "muy_alto": ["Alertar comunidades vulnerables via megáfono y SMS", "Posicionar maquinaria en puntos críticos", "Suspender actividades acuáticas en embalse", "Monitorear nivel quebradas cada 15min"],
        "alto":     ["Activar brigadas comunitarias de vigilancia", "Informar a turistas de condiciones de riesgo", "Verificar estado de vías secundarias", "Mantener canales de comunicación activos"],
        "medio":    ["Monitoreo preventivo de quebradas y taludes", "Revisar condición de vías de acceso", "Mantener equipos de respuesta en alerta amarilla"],
        "bajo":     ["Continuar monitoreo estándar", "Verificar funcionamiento de sensores SIATA", "Actualizar plan de contingencia municipal"],
        "muy_bajo": ["Sistema en operación normal", "Próxima revisión programada en 1 hora"],
    }

    recs_base = base_recs.get(nivel, base_recs["bajo"])
    for r in recs_base:
        if r not in recs:
            recs.append(r)

    return {
        "diagnostico": diagnostico,
        "pronostico": pronostico,
        "explicacion_experta": explicacion_experta,
        "recomendaciones": recs[:5],
        "modelo_usado": "Motor local de reglas expertas SIRGA",
        "timestamp": datetime.utcnow().isoformat(),
    }


async def _analizar_con_claude(datos_combinados: Dict, api_key: str) -> Dict:
    """Llama a la API de Claude para análisis experto"""
    prompt = _construir_prompt(datos_combinados)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-3-haiku-20240307",  # Haiku: más rápido y económico para análisis RT
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                raise ValueError(f"Claude API error: {resp.status}")
            data = await resp.json()
            texto = data["content"][0]["text"]
            resultado = json.loads(texto)
            resultado["modelo_usado"] = "Claude 3 Haiku (Anthropic)"
            resultado["timestamp"] = datetime.utcnow().isoformat()
            return resultado


async def _analizar_con_openai(datos_combinados: Dict, api_key: str) -> Dict:
    """Llama a la API de OpenAI para análisis experto"""
    prompt = _construir_prompt(datos_combinados)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "gpt-4o-mini",
        "max_tokens": 1000,
        "messages": [
            {"role": "system", "content": "Eres un experto en gestión del riesgo de desastres en Colombia. Responde siempre con JSON válido."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                raise ValueError(f"OpenAI API error: {resp.status}")
            data = await resp.json()
            texto = data["choices"][0]["message"]["content"]
            resultado = json.loads(texto)
            resultado["modelo_usado"] = "GPT-4o mini (OpenAI)"
            resultado["timestamp"] = datetime.utcnow().isoformat()
            return resultado


async def analizar_con_ia(
    datos_combinados: Dict,
    modelo: ModeloIA = ModeloIA.LOCAL,
    api_key: Optional[str] = None,
    lat: float = 6.2336,
    lon: float = -75.1567,
) -> Dict:
    """
    Punto de entrada principal. Selecciona el modelo y ejecuta el análisis.
    Enriquece los sensores con datos reales de Open-Meteo antes del análisis.
    Siempre tiene fallback al motor local — nunca falla.
    """
    zona_id = datos_combinados.get("zona", "guatape")

    # Obtener datos reales de Open-Meteo (usa el servicio unificado con caché)
    meteo_real: Dict = {}
    if modelo != ModeloIA.SIMULADO:
        try:
            meteo_real = await obtener_meteo_real(zona_id, lat, lon)
        except Exception:
            meteo_real = {}

    # Sobrescribir sensores simulados con valores reales donde estén disponibles
    sensores_orig = datos_combinados.get("sensores", {})
    sensores_enriquecidos = {
        "lluvia24": meteo_real.get("lluvia_24h_mm",       sensores_orig.get("lluvia24", 0)),
        "temp":     meteo_real.get("temperatura_c",        sensores_orig.get("temp", 19)),
        "hum":      meteo_real.get("humedad_relativa",     sensores_orig.get("hum", 65)),
        "viento":   meteo_real.get("velocidad_viento_ms",  sensores_orig.get("viento", 3)),
        "embalse":  meteo_real.get("nivel_embalse_pct",    sensores_orig.get("embalse", 72)),
    }

    datos_completos = {
        **datos_combinados,
        "sensores":      sensores_enriquecidos,
        "zona_nombre":   nombre_zona(zona_id),
        "datos_externos": meteo_real,
    }

    resultado = None
    error_msg = None

    try:
        if modelo == ModeloIA.CLAUDE and api_key:
            resultado = await _analizar_con_claude(datos_completos, api_key)
        elif modelo == ModeloIA.OPENAI and api_key:
            resultado = await _analizar_con_openai(datos_completos, api_key)
        elif modelo == ModeloIA.LOCAL:
            resultado = _analisis_local(datos_completos)
        else:
            # Simulado o sin API key
            resultado = _analisis_local(datos_completos)
            resultado["modelo_usado"] = "Motor local (API key no configurada)"

    except Exception as e:
        error_msg = str(e)
        # FALLBACK: nunca falla, siempre retorna análisis local
        resultado = _analisis_local(datos_completos)
        resultado["modelo_usado"] = f"Motor local (fallback — error: {type(e).__name__})"
        resultado["fallback_activado"] = True

    resultado["datos_externos_disponibles"] = bool(meteo_real)
    resultado["datos_externos"] = meteo_real
    resultado["modelo_solicitado"] = modelo.value
    resultado["error"] = error_msg
    resultado["irg_pct"] = round(datos_combinados.get("irg", {}).get("irg", 0) * 100, 1)

    return resultado
