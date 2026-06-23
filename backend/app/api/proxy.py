"""
Proxy inverso para recursos externos con restricciones CORS.
El frontend llama a estos endpoints en lugar de usar corsproxy.io,
eliminando la dependencia de un tercero que bloquea peticiones de Railway.
"""
import os
import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

router = APIRouter()


@router.get("/gdacs")
async def proxy_gdacs():
    """Proxy GDACS RSS — evita restricciones CORS del navegador."""
    url = "https://www.gdacs.org/xml/rss.xml"
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            return Response(content=r.content, media_type="application/xml",
                            headers={"Cache-Control": "public, max-age=900"})
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"GDACS no disponible: {e}")


@router.get("/adsb")
async def proxy_adsb(
    lat: float = Query(..., description="Latitud del punto central"),
    lon: float = Query(..., description="Longitud del punto central"),
    dist: int = Query(200, description="Radio en km"),
):
    """Proxy ADS-B (opendata.adsb.fi) — evita restricciones CORS del navegador."""
    url = f"https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{dist}"
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            return Response(content=r.content, media_type="application/json")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"ADS-B no disponible: {e}")


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


@router.get("/tomtom-tile/{z}/{x}/{y}")
async def proxy_tomtom_tile(z: int, x: int, y: int,
                            tipo: str = Query("flow",
                                             description="flow | incidents")):
    """
    Proxy de tiles de tráfico TomTom — TOMTOM_API_KEY vive en Railway.
    El frontend usa esta URL en Leaflet; la clave nunca se expone en el navegador.
    Caché 5 min (tiles de tráfico cambian frecuentemente).
    """
    api_key = os.getenv("TOMTOM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503,
                            detail="TOMTOM_API_KEY no configurada en Railway")
    if tipo == "incidents":
        url = f"https://api.tomtom.com/traffic/map/4/tile/incidents/s3/{z}/{x}/{y}.png?key={api_key}"
    else:
        url = f"https://api.tomtom.com/traffic/map/4/tile/flow/relative-delay/{z}/{x}/{y}.png?key={api_key}"

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            return Response(content=r.content, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=300"})
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"TomTom tile no disponible: {e}")
