"""
Módulo IRG — Índice de Riesgo Global
Combina 20+ variables ponderadas para calcular un riesgo consolidado
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from datetime import datetime
import math


# ── Pesos de cada variable (deben sumar 1.0) ───────────────────────────────
PESOS_IRG = {
    # Meteorología (40%)
    "precipitacion":     0.10,
    "humedad_suelo":     0.08,
    "viento":            0.06,
    "granizo":           0.05,
    "vendaval":          0.05,
    "tormenta_electrica":0.04,
    "neblina_peligrosa": 0.02,
    # Hidrología (20%)
    "creciente_subita":  0.08,
    "nivel_embalse":     0.07,
    "saturacion_cuenca": 0.05,
    # Movilidad y exposición (20%)
    "turismo":           0.05,
    "movilidad":         0.04,
    "vias_problemas":    0.04,
    "puentes_riesgo":    0.03,
    "derrumbes_vias":    0.04,
    # Ambiente y aire (10%)
    "contaminacion_aire":0.03,
    "neblina_vial":      0.04,
    "restriccion_aerea": 0.03,
    # Contexto social (10%)
    "congestion_emergencia": 0.04,
    "densidad_exposicion":   0.06,
}

assert abs(sum(PESOS_IRG.values()) - 1.0) < 0.001, "Los pesos no suman 1.0"


@dataclass
class VariableRiesgo:
    nombre: str
    valor: float          # 0.0 – 1.0 normalizado
    valor_raw: float      # Valor en unidades reales
    unidad: str
    peso: float
    contribucion: float = 0.0
    icono: str = "⚠️"
    descripcion: str = ""


@dataclass
class ResultadoIRG:
    irg: float                          # 0.0 – 1.0
    nivel: str                          # bajo / medio / alto / critico
    variables: Dict[str, VariableRiesgo]
    top_factores: List[Tuple[str, float]]  # (nombre, contribución) ordenados
    alertas_irg: List[Dict]
    timestamp: datetime
    contexto_local: Dict
    modo_degradado: bool = False


def _nivel_irg(irg: float) -> str:
    if irg < 0.20: return "muy_bajo"
    if irg < 0.35: return "bajo"
    if irg < 0.55: return "medio"
    if irg < 0.72: return "alto"
    if irg < 0.88: return "muy_alto"
    return "critico"


def _turismo_por_hora(hora: int) -> float:
    """Simula el nivel de turismo en Guatapé según hora del día"""
    if 10 <= hora <= 18: return 0.85   # Alta temporada diurna
    if 7 <= hora < 10:   return 0.45   # Mañana moderado
    if 18 < hora <= 20:  return 0.35   # Tarde-noche bajando
    return 0.10                         # Nocturno


def _movilidad_por_turismo(turismo: float, hora: int) -> float:
    """Movilidad vehicular correlacionada con turismo y hora"""
    base = turismo * 0.8
    if 7 <= hora <= 9 or 17 <= hora <= 19:
        base = min(1.0, base * 1.3)  # Horas pico
    return base


def calcular_irg(
    datos_meteo: Dict,
    datos_sensores: Dict,
    hora: int = None,
    zona_id: str = "guatape",
    datos_ext: Dict = None,
) -> ResultadoIRG:
    """
    Calcula el Índice de Riesgo Global combinando todas las variables.
    
    Args:
        datos_meteo: dict con lluvia_24h_mm, humedad_suelo, velocidad_viento_ms,
                     nivel_embalse_pct, temperatura_c, presion_hpa
        datos_sensores: lecturas adicionales de sensores
        hora: hora del día (0-23), si None usa la hora actual
        zona_id: identificador de la zona
    """
    if hora is None:
        hora = datetime.now().hour

    lluvia   = datos_meteo.get("lluvia_24h_mm", 20)
    humedad  = datos_meteo.get("humedad_suelo", 0.5)
    viento   = datos_meteo.get("velocidad_viento_ms", 3)
    embalse  = datos_meteo.get("nivel_embalse_pct", 70) / 100
    presion  = datos_meteo.get("presion_hpa", 880)
    temp     = datos_meteo.get("temperatura_c", 18)

    # ── Normalizar variables (0-1) ────────────────────────────────────────
    turismo    = _turismo_por_hora(hora)
    movilidad  = _movilidad_por_turismo(turismo, hora)

    # Índice de tormenta eléctrica: baja presión + lluvia intensa
    tormenta_electrica = min(1.0, (lluvia / 80) * ((900 - presion) / 30 if presion < 900 else 0.3))

    # Vendaval: viento > 15 m/s es severo
    vendaval = min(1.0, max(0, (viento - 10) / 20))

    # Granizo: combinación de baja temperatura + inestabilidad atmosférica
    granizo = min(1.0, max(0, (15 - temp) / 15) * (lluvia / 60))

    # Neblina: humedad alta + temperatura baja + calma de viento
    neblina = min(1.0, humedad * max(0, 1 - viento / 8) * max(0, (20 - temp) / 15))

    # Creciente súbita: lluvia intensa + suelo saturado + embalse alto
    creciente = min(1.0, (lluvia / 100) * 0.4 + humedad * 0.3 + embalse * 0.3)

    # Saturación de cuencas
    saturacion_cuenca = min(1.0, humedad * 0.6 + embalse * 0.4)

    # Vías con problemas (correlacionado con lluvia y deslizamientos)
    vias_prob = min(1.0, (lluvia / 80) * 0.5 + humedad * 0.3 + 0.2 * (1 if lluvia > 60 else 0))

    # Puentes en riesgo (creciente + lluvia)
    puentes = min(1.0, creciente * 0.6 + (lluvia / 100) * 0.4)

    # Derrumbes en vías
    derrumbes = min(1.0, humedad * 0.4 + (lluvia / 80) * 0.4 + 0.2 * (1 if lluvia > 50 else 0))

    # Congestión por emergencia (turismo alto + vías con problema)
    congestion = min(1.0, turismo * 0.4 + vias_prob * 0.4 + movilidad * 0.2)

    # Contaminación del aire (calma + temperatura alta)
    contaminacion = min(1.0, max(0, 1 - viento / 10) * max(0, (temp - 15) / 15) * 0.5)

    # Neblina vial (diferente a peligrosa: más localizada)
    neblina_vial = min(1.0, neblina * 0.7 + humedad * 0.3)

    # Restricción aérea: viento fuerte + neblina + tormenta
    restriccion_aerea = min(1.0, (viento / 25) * 0.4 + neblina * 0.3 + tormenta_electrica * 0.3)

    # Densidad de exposición: turismo alto en zona de riesgo
    densidad_exp = min(1.0, turismo * 0.5 + movilidad * 0.5)

    # ── Integrar fuentes externas cuando están disponibles ───────────────
    # Cada fuente sobreescribe la estimación local con datos reales.
    # Para agregar una fuente futura: añadir su clave a datos_ext y mapearla aquí.
    fuentes_usadas = []
    if datos_ext:
        _s = datos_ext.get("sisaire") or {}
        _d = datos_ext.get("dane") or {}
        _a = datos_ext.get("ansv") or {}
        _r = datos_ext.get("reps") or {}
        _v = datos_ext.get("sivigila") or {}

        # SISAIRE → contaminacion_aire (AQI europeo real de Copernicus CAMS)
        aqi = _s.get("ica")
        if isinstance(aqi, (int, float)):
            contaminacion = min(1.0, aqi / 300)
            fuentes_usadas.append("SISAIRE")

        # DANE → densidad_exposicion (NBI real pondera vulnerabilidad social)
        nbi = (_d.get("nbi") or {}).get("total_pct")
        if isinstance(nbi, (int, float)):
            densidad_exp = min(1.0, turismo * 0.35 + movilidad * 0.30 + (nbi / 100) * 0.35)
            fuentes_usadas.append("DANE")

        # ANSV → vias_problemas / puentes / derrumbes (sectores reales de accidentalidad)
        sectores = _a.get("total_sectores_criticos")
        if isinstance(sectores, (int, float)) and sectores > 0:
            ansv_factor = min(1.0, sectores / 25)
            vias_prob  = min(1.0, vias_prob  * 0.65 + ansv_factor * 0.35)
            puentes    = min(1.0, puentes    * 0.70 + ansv_factor * 0.30)
            derrumbes  = min(1.0, derrumbes  * 0.70 + ansv_factor * 0.30)
            fuentes_usadas.append("ANSV")

        # REPS → congestion_emergencia (capacidad médica real de respuesta)
        cobertura = _r.get("cobertura_medica", "")
        _reps_map = {"ALTA": 0.15, "MEDIA_ALTA": 0.30, "MEDIA": 0.50, "BAJA": 0.70, "MUY_BAJA": 0.90}
        if cobertura in _reps_map:
            congestion = min(1.0, congestion * 0.65 + _reps_map[cobertura] * 0.35)
            fuentes_usadas.append("REPS")

        # SIVIGILA → congestion_emergencia (presión epidemiológica sobre el sistema)
        casos = _v.get("total_casos_reportados")
        if isinstance(casos, (int, float)) and casos > 0:
            sivigila_factor = min(1.0, casos / 3000)
            congestion = min(1.0, congestion * 0.85 + sivigila_factor * 0.15)
            if "REPS" not in fuentes_usadas:
                fuentes_usadas.append("SIVIGILA")

    # ── Mapa de variables ────────────────────────────────────────────────
    vars_mapa = {
        "precipitacion":      VariableRiesgo("Precipitación",      min(1, lluvia/100),  lluvia,    "mm/h", PESOS_IRG["precipitacion"],      icono="🌧️",  descripcion="Lluvia acumulada 24h"),
        "humedad_suelo":      VariableRiesgo("Humedad suelo",      humedad,              humedad*100,"%" ,  PESOS_IRG["humedad_suelo"],       icono="💧",  descripcion="Saturación del suelo"),
        "viento":             VariableRiesgo("Viento",             min(1, viento/25),   viento,    "m/s", PESOS_IRG["viento"],              icono="💨",  descripcion="Velocidad del viento"),
        "granizo":            VariableRiesgo("Granizo",            granizo,              granizo*100,"%",   PESOS_IRG["granizo"],             icono="🧊",  descripcion="Probabilidad de granizo"),
        "vendaval":           VariableRiesgo("Vendaval",           vendaval,             viento,    "m/s", PESOS_IRG["vendaval"],            icono="🌪️",  descripcion="Ráfagas severas"),
        "tormenta_electrica": VariableRiesgo("Tormenta eléctrica", tormenta_electrica,   tormenta_electrica*100,"%", PESOS_IRG["tormenta_electrica"], icono="⛈️", descripcion="Actividad eléctrica"),
        "neblina_peligrosa":  VariableRiesgo("Neblina peligrosa",  neblina,              neblina*100,"%",  PESOS_IRG["neblina_peligrosa"],   icono="🌫️",  descripcion="Visibilidad reducida"),
        "creciente_subita":   VariableRiesgo("Creciente súbita",   creciente,            creciente*100,"%",PESOS_IRG["creciente_subita"],    icono="🌊",  descripcion="Riesgo de crecida rápida"),
        "nivel_embalse":      VariableRiesgo("Nivel embalse",      embalse,              embalse*100,"%",  PESOS_IRG["nivel_embalse"],       icono="🏞️",  descripcion="Nivel El Peñol — EPM"),
        "saturacion_cuenca":  VariableRiesgo("Saturación cuenca",  saturacion_cuenca,    saturacion_cuenca*100,"%",PESOS_IRG["saturacion_cuenca"],icono="🌿",descripcion="Capacidad de absorción"),
        "turismo":            VariableRiesgo("Turismo",            turismo,              turismo*100,"%",  PESOS_IRG["turismo"],             icono="👥",  descripcion=f"Afluencia turística (hora {hora}:00)"),
        "movilidad":          VariableRiesgo("Movilidad vial",     movilidad,            movilidad*100,"%",PESOS_IRG["movilidad"],           icono="🚗",  descripcion="Tráfico vehicular activo"),
        "vias_problemas":     VariableRiesgo("Vías con problemas", vias_prob,            vias_prob*100,"%",PESOS_IRG["vias_problemas"],      icono="🚧",  descripcion="Vías afectadas por lluvia"),
        "puentes_riesgo":     VariableRiesgo("Puentes en riesgo",  puentes,              puentes*100,"%",  PESOS_IRG["puentes_riesgo"],      icono="🌉",  descripcion="Puentes sobre cauces"),
        "derrumbes_vias":     VariableRiesgo("Derrumbes en vías",  derrumbes,            derrumbes*100,"%",PESOS_IRG["derrumbes_vias"],      icono="🏔️",  descripcion="Material en calzada"),
        "contaminacion_aire": VariableRiesgo("Calidad del aire",   contaminacion,        contaminacion*100,"%",PESOS_IRG["contaminacion_aire"],icono="💨",descripcion="Índice de calidad ICA"),
        "neblina_vial":       VariableRiesgo("Neblina vial",       neblina_vial,         neblina_vial*100,"%",PESOS_IRG["neblina_vial"],     icono="🌫️",  descripcion="Visibilidad en vías"),
        "restriccion_aerea":  VariableRiesgo("Restricción aérea",  restriccion_aerea,    restriccion_aerea*100,"%",PESOS_IRG["restriccion_aerea"],icono="✈️",descripcion="Condiciones de vuelo"),
        "congestion_emergencia": VariableRiesgo("Congestión emergencia", congestion,      congestion*100,"%",PESOS_IRG["congestion_emergencia"],icono="🚨",descripcion="Bloqueos por incidentes"),
        "densidad_exposicion":VariableRiesgo("Personas expuestas", densidad_exp,         densidad_exp*100,"%",PESOS_IRG["densidad_exposicion"],icono="👤",descripcion="Concentración de población"),
    }

    # ── Calcular IRG ponderado ────────────────────────────────────────────
    irg_total = 0.0
    for key, var in vars_mapa.items():
        var.contribucion = var.valor * var.peso
        irg_total += var.contribucion

    irg_total = min(1.0, max(0.0, irg_total))
    nivel = _nivel_irg(irg_total)

    # ── Top factores de riesgo ────────────────────────────────────────────
    top_factores = sorted(
        [(k, v.contribucion) for k, v in vars_mapa.items()],
        key=lambda x: x[1], reverse=True
    )[:5]

    # ── Generar alertas IRG inteligentes ─────────────────────────────────
    alertas_irg = _generar_alertas_irg(vars_mapa, irg_total, nivel, hora)

    # ── Contexto local ────────────────────────────────────────────────────
    contexto = {
        "hora": hora,
        "turismo_nivel": "alto" if turismo > 0.7 else "medio" if turismo > 0.4 else "bajo",
        "turismo_pct": round(turismo * 100),
        "movilidad_pct": round(movilidad * 100),
        "zona": zona_id,
        "fuentes_externas_activas": fuentes_usadas if datos_ext else [],
    }

    return ResultadoIRG(
        irg=round(irg_total, 4),
        nivel=nivel,
        variables=vars_mapa,
        top_factores=top_factores,
        alertas_irg=alertas_irg,
        timestamp=datetime.utcnow(),
        contexto_local=contexto,
    )


def _generar_alertas_irg(
    vars_mapa: Dict[str, VariableRiesgo],
    irg: float,
    nivel: str,
    hora: int,
) -> List[Dict]:
    """Genera alertas combinadas cuando se detectan condiciones peligrosas"""
    alertas = []

    def alerta(tipo, nivel_al, desc, acciones, variables_trigger):
        alertas.append({
            "tipo": tipo, "nivel": nivel_al,
            "descripcion": desc, "acciones": acciones,
            "variables_trigger": variables_trigger,
        })

    v = vars_mapa

    # ── Reglas combinadas ─────────────────────────────────────────────────
    # Regla 1: Lluvia intensa + suelo saturado = alto riesgo de deslizamiento
    if v["precipitacion"].valor > 0.6 and v["humedad_suelo"].valor > 0.7:
        alerta("Deslizamiento inminente", "alto",
               f"Lluvia {v['precipitacion'].valor_raw:.0f} mm/h con suelo saturado al {v['humedad_suelo'].valor_raw:.0f}%. Condiciones críticas para movimientos en masa.",
               ["Suspender tránsito por vías de ladera", "Evacuar zonas de alta pendiente", "Activar comités locales de emergencia"],
               ["precipitacion", "humedad_suelo"])

    # Regla 2: Embalse alto + lluvia = inundación
    if v["nivel_embalse"].valor > 0.88 and v["precipitacion"].valor > 0.45:
        alerta("Riesgo inundación por embalse", "muy_alto",
               f"Embalse El Peñol al {v['nivel_embalse'].valor_raw:.0f}% con lluvia activa. Posibles vertimientos de emergencia EPM.",
               ["Alertar comunidades ribereñas", "Monitorear vertederos EPM", "Preparar rutas de evacuación", "Activar PMU"],
               ["nivel_embalse", "precipitacion", "creciente_subita"])

    # Regla 3: Alta afluencia turística + vías con problemas
    if v["turismo"].valor > 0.7 and v["vias_problemas"].valor > 0.5:
        alerta("Emergencia vial con turistas", "alto",
               f"Alta afluencia turística ({v['turismo'].valor_raw:.0f}%) con vías comprometidas. Riesgo de bloqueo de rutas de evacuación.",
               ["Activar control de tráfico en vía principal", "Informar turistas de rutas alternas", "Posicionar maquinaria en puntos críticos"],
               ["turismo", "vias_problemas", "congestion_emergencia"])

    # Regla 4: Tormenta eléctrica + turismo alto = riesgo en embalse
    if v["tormenta_electrica"].valor > 0.5 and v["turismo"].valor > 0.6:
        alerta("Tormenta con turistas en embalse", "alto",
               "Actividad eléctrica detectada con alta afluencia en el embalse. Riesgo para embarcaciones y visitantes.",
               ["Suspender actividades acuáticas", "Desalojar embarcaderos", "Cerrar acceso a Piedra del Peñol"],
               ["tormenta_electrica", "turismo"])

    # Regla 5: Neblina severa + movilidad alta
    if v["neblina_peligrosa"].valor > 0.55 and v["movilidad"].valor > 0.5:
        alerta("Neblina peligrosa en vías", "medio",
               f"Visibilidad reducida con tráfico activo. Riesgo de accidentes en vías de montaña.",
               ["Reducir velocidad máxima a 30 km/h", "Activar señalización de neblina", "Suspender transporte de carga nocturno"],
               ["neblina_peligrosa", "neblina_vial", "movilidad"])

    # Regla 6: Vendaval + restricción aérea
    if v["vendaval"].valor > 0.5:
        alerta("Vendaval activo", "alto",
               f"Vientos fuertes de {v['viento'].valor_raw:.1f} m/s. Riesgo de caída de árboles y estructuras.",
               ["Retirar mobiliario urbano", "Verificar estado de redes eléctricas", "Suspender vuelos en helipuerto"],
               ["vendaval", "restriccion_aerea"])

    # Regla 7: Creciente súbita (combinación múltiple)
    if v["creciente_subita"].valor > 0.6:
        alerta("Creciente súbita probable", "muy_alto",
               "Condiciones de lluvia intensa + suelo saturado + nivel alto del embalse. Alta probabilidad de creciente en las próximas 2 horas.",
               ["EVACUAR zonas ribereñas inmediatamente", "Cerrar puentes sobre quebradas", "Activar sirenas de alerta temprana"],
               ["creciente_subita", "precipitacion", "saturacion_cuenca", "nivel_embalse"])

    # Regla 8: IRG global crítico
    if irg > 0.72:
        alerta("⚠️ ALERTA MÁXIMA — IRG CRÍTICO", "critico",
               f"El Índice de Riesgo Global alcanzó {irg*100:.0f}%. Múltiples variables en niveles críticos simultáneamente.",
               ["ACTIVAR PLAN DE CONTINGENCIA MUNICIPAL", "Notificar DAGRAN y UNGRD", "Evacuación preventiva de zonas vulnerables", "Activar albergues de emergencia"],
               list(vars_mapa.keys()))

    # Ordenar por prioridad
    orden = {"critico": 0, "muy_alto": 1, "alto": 2, "medio": 3, "bajo": 4}
    alertas.sort(key=lambda a: orden.get(a["nivel"], 9))
    return alertas
