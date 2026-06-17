"""
Proxy inverso para recursos externos con restricciones CORS.
El frontend llama a estos endpoints en lugar de usar corsproxy.io,
eliminando la dependencia de un tercero que bloquea peticiones de Railway.
"""
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
