"""
API Router — Notificaciones por email al operador via Resend

Envía emails automáticos cuando el sistema de Credibilidad detecta
evidencia suficiente para recomendar unificación de modelos, o cuando
ocurre un rollback automático por pérdida de outcomes.

Requiere variables de entorno en Railway:
  RESEND_API_KEY  — clave de API de resend.com (gratis hasta 3000 emails/mes)
  OPERADOR_EMAIL  — destinatario (ej: arcilagiraldo@gmail.com)
  RESEND_FROM     — remitente verificado en Resend (opcional, default: onboarding@resend.dev)

Si RESEND_API_KEY no está configurada: retorna ok:true con modo:simulado.
Los emails nunca bloquean el flujo principal — fire-and-forget desde frontend.
"""
import os
import httpx
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

OPERADOR_EMAIL_DEFAULT = "criaderolasluciernagas@gmail.com"
RESEND_API_URL = "https://api.resend.com/emails"


class EmailPayload(BaseModel):
    tipo: str
    asunto: str
    cuerpo: str


async def _enviar_resend(asunto: str, cuerpo: str, destinatario: str) -> tuple[bool, str]:
    """Envía email via Resend API. Retorna (True, '') si éxito, (False, error) si falla."""
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        return False, "RESEND_API_KEY no configurada en Railway"

    from_email = os.getenv("RESEND_FROM", "OMAIRA <onboarding@resend.dev>")

    payload = {
        "from": from_email,
        "to": [destinatario],
        "subject": asunto,
        "text": cuerpo,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        if resp.status_code in (200, 201):
            return True, ""
        return False, f"Resend {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


@router.post("/email")
async def enviar_email(payload: EmailPayload):
    """
    Envía email al operador. Llamado desde el frontend en dos situaciones:
    1. Sistema de Credibilidad detecta evidencia BSS suficiente (>=500 outcomes, delta BSS >= 0.15)
    2. Rollback automático se activa por pérdida de outcomes
    """
    destinatario = os.getenv("OPERADOR_EMAIL", OPERADOR_EMAIL_DEFAULT)
    enviado, error = await _enviar_resend(payload.asunto, payload.cuerpo, destinatario)

    return {
        "ok": True,
        "tipo": payload.tipo,
        "destinatario": destinatario,
        "enviado": enviado,
        "modo": "resend" if enviado else "simulado",
        "timestamp": datetime.utcnow().isoformat(),
        "error": error if not enviado else "",
    }
