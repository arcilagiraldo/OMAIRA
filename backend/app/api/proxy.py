"""
Proxy inverso para recursos externos con restricciones CORS.
El frontend llama a estos endpoints en lugar de usar corsproxy.io,
eliminando la dependencia de un tercero que bloquea peticiones de Railway.
"""
import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

router = APIRouter()


@router.get("/noaa-oni", response_class=PlainTextResponse)
async def proxy_noaa_oni():
    """Proxy NOAA ONI — text/plain, actualización mensual, caché en cliente 6 h."""
    url = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            return PlainTextResponse(r.text, headers={"Cache-Control": "public, max-age=21600"})
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"NOAA no disponible: {e}")
