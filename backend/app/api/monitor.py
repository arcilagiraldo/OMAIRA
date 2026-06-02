"""
Monitor web — búsqueda de alertas y emergencias en internet.
Agrega RSS/feeds de fuentes colombianas y globales para complementar los datos en tiempo real.
"""
import httpx
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime
import re

router = APIRouter()

PROXIES_CORS = [
    "https://corsproxy.io/?",
    "https://api.allorigins.win/get?url=",
]


async def _fetch_safe(url: str, timeout: int = 8) -> Optional[str]:
    """Fetch con timeout, sin lanzar excepción."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    return None


def _nivel_desde_texto(texto: str) -> str:
    txt = texto.lower()
    if any(w in txt for w in ["critico", "critica", "rojo", "red", "evacuacion", "emergencia mayor", "alerta roja"]):
        return "critico"
    if any(w in txt for w in ["alto", "grave", "orange", "naranja", "alerta", "inundacion grande", "desbordamiento"]):
        return "alto"
    if any(w in txt for w in ["medio", "moderado", "yellow", "amarillo", "precaución", "aviso"]):
        return "medio"
    return "bajo"


@router.get("/noticias")
async def get_noticias(
    q: str = Query("emergencia Antioquia", description="Términos de búsqueda"),
    zona: str = Query("guatape", description="ID de zona"),
):
    """
    Busca noticias y alertas de emergencias en fuentes colombianas y globales.
    Combina RSS de GDACS, ReliefWeb, Google News Colombia y SGC.
    """
    noticias = []

    # ── Google News RSS Colombia ──────────────────────────────────────────────
    terminos_busqueda = q.replace(" ", "+")
    rss_url = f"https://news.google.com/rss/search?q={terminos_busqueda}+Colombia&hl=es&gl=CO&ceid=CO:es"
    rss_proxy = f"https://corsproxy.io/?{rss_url}"

    texto_rss = await _fetch_safe(rss_proxy, timeout=10)
    if texto_rss:
        try:
            root = ET.fromstring(texto_rss)
            channel = root.find("channel")
            if channel:
                for item in list(channel.findall("item"))[:8]:
                    titulo = (item.findtext("title") or "").strip()
                    desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()[:200]
                    link = (item.findtext("link") or "").strip()
                    pub = (item.findtext("pubDate") or "").strip()
                    fuente_tag = item.find("{https://news.google.com/rss}source")
                    fuente_nombre = fuente_tag.text if fuente_tag is not None else "Google News"

                    if titulo and any(w in titulo.lower() for w in
                                      ["emergencia", "inundaci", "deslizamient", "incendio",
                                       "alerta", "desastre", "terremoto", "sismo", "avalancha",
                                       "evacuaci", "víctimas", "muertos", "heridos", "río"]):
                        noticias.append({
                            "fuente": fuente_nombre,
                            "titulo": titulo[:120],
                            "desc": desc,
                            "nivel": _nivel_desde_texto(titulo + " " + desc),
                            "fecha": pub[:25] if pub else "Reciente",
                            "url": link,
                            "tipo": "noticia",
                        })
        except ET.ParseError:
            pass

    # ── SGC — Servicio Geológico Colombiano (alertas sísmicas) ───────────────
    sgc_url = "https://www2.sgc.gov.co/Paginas/sismos-colombia.aspx"
    # SGC no tiene RSS público — usamos el dato de USGS que ya está integrado en el frontend

    # ── IDEAM alertas hidrometeorológicas ────────────────────────────────────
    ideam_url = "http://www.ideam.gov.co/rss.xml"
    texto_ideam = await _fetch_safe(f"https://corsproxy.io/?{ideam_url}", timeout=6)
    if texto_ideam:
        try:
            root = ET.fromstring(texto_ideam)
            for item in list(root.iter("item"))[:5]:
                titulo = (item.findtext("title") or "").strip()
                if titulo and any(w in titulo.lower() for w in ["alerta", "aviso", "vigilancia"]):
                    noticias.append({
                        "fuente": "IDEAM",
                        "titulo": titulo[:120],
                        "desc": re.sub(r"<[^>]+>", "", item.findtext("description") or "")[:200],
                        "nivel": _nivel_desde_texto(titulo),
                        "fecha": item.findtext("pubDate") or "Reciente",
                        "url": item.findtext("link") or "http://www.ideam.gov.co",
                        "tipo": "alerta_meteo",
                    })
        except ET.ParseError:
            pass

    # Ordenar: por nivel de criticidad descendente
    orden = {"critico": 0, "alto": 1, "medio": 2, "bajo": 3}
    noticias.sort(key=lambda n: orden.get(n.get("nivel", "bajo"), 3))

    return {
        "zona": zona,
        "terminos": q,
        "total": len(noticias),
        "noticias": noticias[:15],
        "timestamp": datetime.utcnow().isoformat(),
    }
