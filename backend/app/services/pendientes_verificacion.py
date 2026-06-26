"""
Fuente única de verdad sobre qué variables IRG tienen limitaciones
de verificación independiente documentadas.

Si el sistema de detección de fuentes (Sesión 3) clasifica una URL
nueva como una de estas variables, avisa que podría resolver el
pendiente — sin necesidad de tocar ningún otro archivo cuando se
agregue una entrada nueva en el futuro.

Para agregar un pendiente nuevo:
    Añadir una entrada a PENDIENTES_VERIFICACION.
    La clave es la variable IRG de HEURISTICAS que lo resolvería.
    El endpoint /analizar lo detecta automáticamente.
"""
from typing import Dict, List, Optional

PENDIENTES_VERIFICACION: Dict[str, Dict] = {
    "lluvia": {
        "tipos_afectados": ["lluvias_intensas"],
        "clase": "C",
        "motivo": (
            "Sin sensor físico independiente (pluviómetro) conectado. "
            "Open-Meteo es la única fuente; el outcome mide consistencia "
            "interna del modelo, no precisión contra observación real."
        ),
        "fuente_ideal": "IDEAM SISMOI/DHIME (API pública) o SIATA con convenio",
        "documentado_en": "docs/propuesta-7-tipos-circulares.md",
        "desde": "2026-06-25",
    },
    # inversion_termica NO tiene entrada aquí: es un concepto compuesto
    # (presión + visibilidad + temperatura), no una variable IRG simple
    # detectable por la heurística actual de fuentes_deteccion.py.
    # Para beneficiarse de este sistema necesitaría heurísticas nuevas
    # para "presion" y "visibilidad" — trabajo separado, no de esta sesión.
}


def verificar_si_resuelve_pendiente(variable_sugerida: str) -> Optional[Dict]:
    """
    Dado que una fuente nueva fue clasificada como `variable_sugerida`
    (por el endpoint de detección — Sesión 3), retorna la info del
    pendiente que resolvería si se aprueba, o None si no hay ninguno.
    """
    return PENDIENTES_VERIFICACION.get(variable_sugerida)


def listar_pendientes() -> List[Dict]:
    """Lista todos los pendientes documentados con sus metadatos."""
    return [{"variable": k, **v} for k, v in PENDIENTES_VERIFICACION.items()]
