"""
Fuente unica de verdad sobre que variables IRG tienen limitaciones
de verificacion independiente documentadas.

Si el sistema de deteccion de fuentes (Sesion 3) clasifica una URL
nueva como una de estas variables, avisa que podria resolver el
pendiente -- sin necesidad de tocar ningun otro archivo cuando se
agregue una entrada nueva en el futuro.

Para agregar un pendiente nuevo:
    Anadir una entrada a PENDIENTES_VERIFICACION.
    La clave es la variable IRG de HEURISTICAS que lo resolveria.
    El endpoint /analizar lo detecta automaticamente.
"""
from typing import Dict, List, Optional

PENDIENTES_VERIFICACION: Dict[str, Dict] = {
    "lluvia": {
        "tipos_afectados": ["lluvias_intensas"],
        "clase": "C",
        "motivo": (
            "Sin sensor fisico independiente (pluviometro) conectado. "
            "Open-Meteo es la unica fuente; el outcome mide consistencia "
            "interna del modelo, no precision contra observacion real."
        ),
        "fuente_ideal": "IDEAM SISMOI/DHIME o SIATA con convenio",
        "documentado_en": "docs/propuesta-7-tipos-circulares.md",
        "desde": "2026-06-25",
    },
    # inversion_termica NO tiene entrada aqui: es un concepto compuesto
    # (presion + visibilidad + temperatura), no una variable IRG simple
    # detectable por la heuristica actual de fuentes_deteccion.py.
    # Para beneficiarse de este sistema necesitaria heuristicas nuevas
    # para "presion" y "visibilidad" -- trabajo separado, no de esta sesion.
}


def verificar_si_resuelve_pendiente(variable_sugerida: str) -> Optional[Dict]:
    """Retorna el pendiente que resolveria la variable, o None si no hay ninguno."""
    return PENDIENTES_VERIFICACION.get(variable_sugerida)


def listar_pendientes() -> List[Dict]:
    """Lista todos los pendientes documentados con sus metadatos."""
    return [{"variable": k, **v} for k, v in PENDIENTES_VERIFICACION.items()]
