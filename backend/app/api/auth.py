"""
Autenticación con Google OAuth y gestión de usuarios autorizados.

Roles:
  - Propietario: emails en AUTHORIZED_EMAILS (env var). Único que puede gestionar usuarios.
  - Usuario: emails agregados por el propietario, guardados en la base de datos.

Nota sobre CORS: Los endpoints de gestión de usuarios aceptan el email del admin
como query param (?admin=email) en lugar de header personalizado, para evitar
problemas de CORS preflight en navegadores.
"""
import os
import httpx
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _emails_propietario() -> list[str]:
    raw = os.getenv("AUTHORIZED_EMAILS", "arcilagiraldo@gmail.com")
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


async def _emails_usuarios_db() -> list[dict]:
    try:
        from app.services.database import _pool
        if _pool is None:
            return []
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT email, nombre, agregado_por, created_at FROM usuarios_autorizados ORDER BY created_at"
            )
            return [dict(r) for r in rows]
    except Exception:
        return []


async def _emails_autorizados() -> list[str]:
    propietario = _emails_propietario()
    usuarios_db = await _emails_usuarios_db()
    extra = [u["email"] for u in usuarios_db]
    return list(set(propietario + extra))


def _es_propietario(email: str) -> bool:
    return email.strip().lower() in _emails_propietario()


def _get_admin(header_val: Optional[str], query_val: Optional[str]) -> str:
    """Acepta admin email desde header O query param (evita CORS preflight)."""
    return ((query_val or header_val or "")).strip().lower()


# ── Modelos ───────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    credential: str


class EmailRequest(BaseModel):
    email: str
    nombre: Optional[str] = None
    admin_email: Optional[str] = None  # alternativa a query param


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.post("/verify")
async def verify_google_token(req: TokenRequest):
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

    autorizados = await _emails_autorizados()
    if email not in autorizados:
        raise HTTPException(403, f"Acceso no autorizado para {email}")

    return {
        "ok": True,
        "email": email,
        "nombre": info.get("name", email.split("@")[0]),
        "foto": info.get("picture", ""),
        "rol": "propietario" if _es_propietario(email) else "usuario",
    }


# ── Gestión de usuarios ───────────────────────────────────────────────────────

@router.get("/users")
async def get_users(
    admin: Optional[str] = Query(None, description="Email del propietario"),
    x_admin_email: Optional[str] = Header(None),
):
    """Lista propietarios y usuarios. Solo el propietario puede consultarla."""
    admin_email = _get_admin(x_admin_email, admin)
    if not _es_propietario(admin_email):
        raise HTTPException(403, "Solo el propietario puede gestionar usuarios")

    propietarios = [
        {"email": e, "rol": "propietario", "nombre": None, "agregado_por": None}
        for e in _emails_propietario()
    ]
    usuarios_db = await _emails_usuarios_db()
    usuarios = [
        {"email": u["email"], "rol": "usuario",
         "nombre": u.get("nombre"), "agregado_por": u.get("agregado_por")}
        for u in usuarios_db
    ]
    return {"propietarios": propietarios, "usuarios": usuarios}


@router.post("/users")
async def add_user(
    req: EmailRequest,
    admin: Optional[str] = Query(None),
    x_admin_email: Optional[str] = Header(None),
):
    """Agrega un usuario autorizado."""
    admin_email = _get_admin(x_admin_email, admin) or (req.admin_email or "").lower()
    if not _es_propietario(admin_email):
        raise HTTPException(403, "Solo el propietario puede agregar usuarios")

    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Correo inválido")

    autorizados = await _emails_autorizados()
    if email in autorizados:
        raise HTTPException(400, f"{email} ya tiene acceso")

    try:
        from app.services.database import _pool
        if _pool is None:
            raise HTTPException(503, "Base de datos no disponible")
        async with _pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO usuarios_autorizados (email, nombre, agregado_por) VALUES ($1, $2, $3)",
                email, req.nombre or email.split("@")[0], admin_email
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al guardar usuario: {e}")

    return {"ok": True, "email": email, "rol": "usuario"}


@router.delete("/users/{email:path}")
async def remove_user(
    email: str,
    admin: Optional[str] = Query(None),
    x_admin_email: Optional[str] = Header(None),
):
    """Retira acceso a un usuario."""
    admin_email = _get_admin(x_admin_email, admin)
    if not _es_propietario(admin_email):
        raise HTTPException(403, "Solo el propietario puede quitar usuarios")

    email = email.strip().lower()
    if _es_propietario(email):
        raise HTTPException(400, "No se puede quitar el acceso al propietario")

    try:
        from app.services.database import _pool
        if _pool is None:
            raise HTTPException(503, "Base de datos no disponible")
        async with _pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM usuarios_autorizados WHERE email = $1", email
            )
            if result == "DELETE 0":
                raise HTTPException(404, f"{email} no encontrado")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al quitar usuario: {e}")

    return {"ok": True, "email": email}


@router.get("/me")
async def check_session():
    return {"status": "auth-activo"}
