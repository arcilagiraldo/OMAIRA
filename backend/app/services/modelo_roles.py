"""
ROLES DE LOS TRES MODELOS DE RIESGO EN OMAIRA
══════════════════════════════════════════════

OMAIRA tiene 3 implementaciones del marco H×E×V coexistiendo.
No son redundantes — tienen propósitos distintos y complementarios.

MODELO 1 — calcIRGConPesos() [frontend/index.html]
  Propósito: IRG operacional en tiempo real para el dashboard principal
  Fortalezas: más variables (20+), pesos dinámicos ENSO, IDF DAGRAN,
              fuentes externas en vivo, calibrado con sistema Credibilidad
  Limitación: vive en el navegador — no disponible para alertas server-side
  Thresholds: irg<0.20→muy_bajo / <0.35→bajo / <0.55→medio / <0.72→alto
  Fuente BSS: única fuente original del sistema de Credibilidad (hasta Sesión 10)

MODELO 2 — irg_service.py [backend]
  Propósito: IRG server-side para endpoints /api/v1/irg/* y chatbot IA
  Fortalezas: disponible sin navegador, integrable con servicios externos
  Limitación: variables fijas, índice global (no desagrega por tipo de riesgo)
  Thresholds: idénticos al Modelo 1 (irg<0.20→muy_bajo / <0.35→bajo / <0.55→medio...)
  Estado BSS: conectado al sistema de Credibilidad desde Sesión 10
  Nota: devuelve un único valor irg ∈ [0,1] — no predicciones por tipo de riesgo

MODELO 3 — riesgo_service.py [backend]
  Propósito: alertas automáticas, predicciones por tipo específico de riesgo
  Fortalezas: desagrega por tipo (deslizamiento/inundación/incendio/tormenta/sequía),
              alimenta el sistema de alertas SIRGA y el chatbot de predicción
  Limitación: 5 tipos de riesgo solamente, no tiene datos ENSO ni DAGRAN
  Thresholds: prob<0.10→muy_bajo / <0.25→bajo / <0.45→medio / <0.65→alto
  Estado BSS: conectado al sistema de Credibilidad desde Sesión 10

DECISIÓN ARQUITECTURAL (2026-06-18):
  Mantener los 3 modelos con roles documentados (Opción 2).
  El sistema de Credibilidad mide los 3 en paralelo desde la Sesión 10.
  Cuando haya ≥500 outcomes por modelo con evidencia estadística confiable,
  la notificación automática indicará si conviene unificar en el modelo
  con mejor BSS. Ver: docs/investigacion-dos-modelos-riesgo.md

CAMPO modelo: EN RESPUESTAS JSON
  Todos los endpoints que retornan nivel o probabilidad incluyen:
    "modelo": "<MODELO_*>",
    "modelo_descripcion": "<descripción del rol>"
  Esto permite a cualquier consumidor de la API saber cuál modelo habla
  en cada respuesta — resuelve la ambigüedad documentada en Sesión 5.
"""

MODELO_FRONTEND      = "calcIRGConPesos_v6"
MODELO_IRG_BACKEND   = "irg_service_v6"
MODELO_RIESGO_BACKEND = "riesgo_service_v6"

DESCRIPCION_MODELOS = {
    MODELO_FRONTEND: "IRG operacional frontend — 20+ variables, pesos dinámicos ENSO/DAGRAN",
    MODELO_IRG_BACKEND: "IRG server-side global — índice único para chatbot y alertas IA",
    MODELO_RIESGO_BACKEND: "H×E×V por tipo de riesgo — alertas automáticas server-side",
}
