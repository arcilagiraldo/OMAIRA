"""
Autenticación con Google OAuth — verificación de token y lista de emails autorizados.
"""
import os
import json
import httpx
from pathlib import Path
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
USERS_FILE = Path("/app/data/authorized_users.json")


def _emails_base() -> list[str]:
    """Emails configurados en variable de entorno (admin fijo)."""
    raw = os.getenv("AUTHORIZED_EMAILS", "arcilagiraldo@gmail.com")
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def _emails_extra() -> list[str]:
    """Emails adicionales gestionados dinámicamente."""
    try:
        if USERS_FILE.exists():
            return [e.lower() for e in json.loads(USERS_FILE.read_text()) if e]
    except Exception:
        pass
    return []


def _emails_autorizados() -> list[str]:
    return list(set(_emails_base() + _emails_extra()))


def _guardar_extra(emails: list[str]):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(list(set(e.lower() for e in emails if e))))


def _es_admin(email: str) -> bool:
    return email.lower() in _emails_base()


class TokenRequest(BaseModel):
    credential: str  # JWT token de Google Identity Services


class EmailRequest(BaseModel):
    email: str


@router.post("/verify")
async def verify_google_token(req: TokenRequest):
    """
    Verifica el token de Google y comprueba si el email está autorizado.
    Retorna {ok: true, email, nombre} o lanza 403.
    """
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"{GOOGLE_TOKEN_INFO_URL}?id_token={req.credential}")
            if r.status_code != 200:
                raise HTTPException(401, "Token de Google inválido")
            info = r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error verificando token: {e}")

    email = info.get("email", "").lower()
    if not email:
        raise HTTPException(401, "Token sin email")

    if email not in _emails_autorizados():
        raise HTTPException(403, f"Acceso no autorizado para {email}")

    return {
        "ok": True,
        "email": email,
        "nombre": info.get("name", email.split("@")[0]),
        "foto": info.get("picture", ""),
    }


@router.get("/users")
async def get_users(x_admin_email: Optional[str] = Header(None)):
    """Lista de emails autorizados — solo para administradores."""
    admin = (x_admin_email or "").lower()
    if not _es_admin(admin):
        raise HTTPException(403, "Solo el administrador puede ver los usuarios")
    return {"emails": _emails_autorizados()}


@router.post("/users")
async def add_user(req: EmailRequest, x_admin_email: Optional[str] = Header(None)):
    """Agrega un email a la lista de autorizados."""
    admin = (x_admin_email or "").lower()
    if not _es_admin(admin):
        raise HTTPException(403, "Solo el administrador puede agregar usuarios")
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Email inválido")
    extra = _emails_extra()
    if email in _emails_autorizados():
        raise HTTPException(400, f"{email} ya tiene acceso")
    extra.append(email)
    _guardar_extra(extra)
    return {"ok": True, "email": email, "total": len(_emails_autorizados())}


@router.delete("/users/{email}")
async def remove_user(email: str, x_admin_email: Optional[str] = Header(None)):
    """Retira acceso a un email (no puede eliminar los del env var)."""
    admin = (x_admin_email or "").lower()
    if not _es_admin(admin):
        raise HTTPException(403, "Solo el administrador puede quitar usuarios")
    email = email.strip().lower()
    if email in _emails_base():
        raise HTTPException(400, "No se puede quitar el acceso al administrador principal")
    extra = [e for e in _emails_extra() if e != email]
    _guardar_extra(extra)
    return {"ok": True, "email": email}


@router.get("/me")
async def check_session():
    """Endpoint de prueba — la sesión real se guarda en el frontend."""
    return {"status": "auth-activo"}
