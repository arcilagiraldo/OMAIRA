"""
API Router — Notificaciones por email al operador

Envía emails automáticos cuando el sistema de Credibilidad detecta
evidencia suficiente para recomendar unificación de modelos, o cuando
ocurre un rollback automático por pérdida de outcomes.

Requiere variables de entorno en Railway:
  SMTP_HOST     — servidor SMTP (ej: smtp.gmail.com)
  SMTP_PORT     — puerto (ej: 587 para TLS, 465 para SSL)
  SMTP_USER     — cuenta emisora (ej: tu-cuenta@gmail.com)
  SMTP_PASSWORD — contraseña de aplicación (no la contraseña de cuenta)
  OPERADOR_EMAIL — destinatario (ej: criaderolasluciernagas@gmail.com)

Si no están configuradas: el endpoint retorna ok:true con modo:simulado.
Los emails nunca bloquean el flujo principal — fire-and-forget desde frontend.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

OPERADOR_EMAIL_DEFAULT = "criaderolasluciernagas@gmail.com"


class EmailPayload(BaseModel):
    tipo: str                    # "recomendacion_modelo" | "rollback_modelo"
    asunto: str
    cuerpo: str


def _enviar_smtp(asunto: str, cuerpo: str, destinatario: str) -> tuple[bool, str]:
    """Intenta enviar via SMTP. Retorna (True, '') si éxito, (False, error) si falla."""
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")

    if not all([host, user, password]):
        vars_faltantes = [k for k, v in {"SMTP_HOST": host, "SMTP_USER": user, "SMTP_PASSWORD": password}.items() if not v]
        return False, f"Variables no configuradas: {vars_faltantes}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = user
    msg["To"] = destinatario
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    try:
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.ehlo()
            s.starttls()
            s.login(user, password)
            s.sendmail(user, [destinatario], msg.as_string())
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


@router.post("/email")
async def enviar_email(payload: EmailPayload):
    """
    Envía email al operador. Llamado desde el frontend en dos situaciones:
    1. Sistema de Credibilidad detecta evidencia BSS suficiente (≥500 outcomes, Δ BSS ≥ 0.15)
    2. Rollback automático se activa por pérdida de outcomes
    """
    destinatario = os.getenv("OPERADOR_EMAIL", OPERADOR_EMAIL_DEFAULT)
    enviado, error = _enviar_smtp(payload.asunto, payload.cuerpo, destinatario)

    return {
        "ok": True,
        "tipo": payload.tipo,
        "destinatario": destinatario,
        "enviado": enviado,
        "modo": "smtp" if enviado else "simulado",
        "timestamp": datetime.utcnow().isoformat(),
        "error": error if not enviado else "",
    }
