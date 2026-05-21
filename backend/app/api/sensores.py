"""API Router — Sensores en tiempo real"""
from fastapi import APIRouter
from datetime import datetime
import random

router = APIRouter()

@router.get("/{zona_id}")
async def get_sensores(zona_id: str):
    """Lecturas actuales de sensores para una zona"""
    return {
        "zona_id": zona_id,
        "timestamp": datetime.utcnow().isoformat(),
        "sensores": [
            {"id": f"S-{zona_id}-LLUVIA-01", "tipo": "pluviometro", "valor": round(random.uniform(0, 40), 1),
             "unidad": "mm/h", "fuente": "SIATA", "calidad": 0.98},
            {"id": f"S-{zona_id}-NIVEL-01", "tipo": "limnimetro", "valor": round(random.uniform(0.5, 4.5), 2),
             "unidad": "m", "fuente": "SIATA", "calidad": 0.95},
            {"id": f"S-{zona_id}-TEMP-01", "tipo": "termometro", "valor": round(random.uniform(14, 26), 1),
             "unidad": "°C", "fuente": "IDEAM", "calidad": 0.99},
            {"id": f"S-{zona_id}-HUM-01", "tipo": "humedad_suelo", "valor": round(random.uniform(30, 95), 1),
             "unidad": "%", "fuente": "SIATA", "calidad": 0.92},
            {"id": f"S-{zona_id}-EMB-01", "tipo": "nivel_embalse", "valor": round(random.uniform(60, 95), 1),
             "unidad": "%", "fuente": "EPM", "calidad": 1.0},
        ]
    }
