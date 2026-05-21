"""
Modelos de datos — Sistema Riesgo Antioquia
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


class NivelRiesgo(str, Enum):
    MUY_BAJO = "muy_bajo"
    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"
    MUY_ALTO = "muy_alto"
    CRITICO = "critico"


class TipoRiesgo(str, Enum):
    DESLIZAMIENTO = "deslizamiento"
    INUNDACION = "inundacion"
    TORMENTA = "tormenta"
    INCENDIO = "incendio"
    SEQUIA = "sequia"


class HorizontePrediccion(str, Enum):
    H1 = "1h"
    H6 = "6h"
    H24 = "24h"
    H72 = "72h"


class CoordenadaGeo(BaseModel):
    lat: float = Field(..., ge=-4.5, le=8.5, description="Latitud (Colombia)")
    lon: float = Field(..., ge=-77.0, le=-66.0, description="Longitud (Colombia)")


class SensorReading(BaseModel):
    sensor_id: str
    tipo: str
    valor: float
    unidad: str
    timestamp: datetime
    lat: float
    lon: float
    calidad: float = Field(default=1.0, ge=0.0, le=1.0, description="Calidad del dato 0-1")
    fuente: str = "SIATA"


class RiesgoComponentes(BaseModel):
    """Componentes del modelo RIESGO = (H × E × V) × F_clima"""
    amenaza: float = Field(..., ge=0, le=1, description="H — amenaza física y ML")
    exposicion: float = Field(..., ge=0, le=1, description="E — exposición de elementos")
    vulnerabilidad: float = Field(..., ge=0, le=1, description="V — vulnerabilidad social")
    factor_clima: float = Field(..., ge=0, le=2, description="F_clima — ENSO + anomalías")
    riesgo_total: float = Field(..., ge=0, le=1)


class PrediccionRiesgo(BaseModel):
    zona_id: str
    municipio: str
    tipo_riesgo: TipoRiesgo
    horizonte: HorizontePrediccion
    nivel: NivelRiesgo
    probabilidad: float = Field(..., ge=0, le=1)
    incertidumbre_lower: float
    incertidumbre_upper: float
    componentes: RiesgoComponentes
    timestamp_prediccion: datetime
    timestamp_horizonte: datetime
    acciones_recomendadas: List[str] = []
    fuentes_datos_activas: List[str] = []
    modo_degradado: bool = False
    metadata: Dict[str, Any] = {}


class AlertaRiesgo(BaseModel):
    alerta_id: str
    tipo_riesgo: TipoRiesgo
    nivel: NivelRiesgo
    municipio: str
    descripcion: str
    acciones: List[str]
    timestamp: datetime
    activa: bool = True
    lat: Optional[float] = None
    lon: Optional[float] = None


class ConfiguracionZona(BaseModel):
    """Configuración no-técnica del sistema para una zona"""
    municipio: str
    departamento: str = "Antioquia"
    coordenada_centro: CoordenadaGeo
    radio_km: float = Field(default=25.0, ge=1, le=200)

    # Fuentes de datos (checkboxes en la UI)
    fuentes_activas: List[str] = Field(
        default=["IDEAM", "SIATA"],
        description="Fuentes de datos habilitadas"
    )

    # Riesgos a monitorear
    riesgos_activos: List[TipoRiesgo] = Field(
        default=[TipoRiesgo.DESLIZAMIENTO, TipoRiesgo.INUNDACION],
        description="Tipos de riesgo habilitados"
    )

    # Nivel de detalle (bajo/medio/alto → resolucion grid)
    nivel_detalle: str = Field(
        default="medio",
        pattern="^(bajo|medio|alto)$"
    )

    # Configuración auto-derivada
    resolucion_grid_m: Optional[int] = None  # Se calcula automáticamente
    intervalo_actualizacion_min: Optional[int] = None  # Se calcula automáticamente

    def calcular_config_automatica(self):
        """Auto-configuración según nivel de detalle"""
        mapa = {
            "bajo": {"resolucion": 100, "intervalo": 60},
            "medio": {"resolucion": 30, "intervalo": 15},
            "alto": {"resolucion": 10, "intervalo": 5},
        }
        cfg = mapa[self.nivel_detalle]
        self.resolucion_grid_m = cfg["resolucion"]
        self.intervalo_actualizacion_min = cfg["intervalo"]
        return self


class WizardPaso(BaseModel):
    paso: int
    titulo: str
    descripcion: str
    completado: bool = False
    datos: Optional[Dict[str, Any]] = None


class EstadoSistema(BaseModel):
    activo: bool
    modo: str  # "normal" | "degradado" | "mantenimiento"
    fuentes_disponibles: List[str]
    fuentes_caidas: List[str]
    ultimo_update: datetime
    zonas_configuradas: int
    alertas_activas: int
