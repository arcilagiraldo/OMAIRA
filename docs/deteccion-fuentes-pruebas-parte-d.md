# Parte D — Pruebas end-to-end del clasificador de fuentes
## Sesión 3

---

## Contexto

El backend en Railway corre el código de `main` (sin los endpoints nuevos aún).
Las pruebas de Parte D verifican la lógica del clasificador directamente
en Python, que es la misma que ejecuta el endpoint `POST /analizar` cuando
se despliega la rama `feat/deteccion-fuentes-sesion3`.

Comando usado para reproducir:
```bash
cd riesgo-antioquia
python -c "
import sys; sys.path.insert(0, 'backend')
from app.api.fuentes_deteccion import _clasificar, _extraer_campos
# ... (ver casos abajo)
"
```

---

## Caso 1 — RECONOCIDA: variable única y sin ambigüedad

**URL probada (simulada):**
```
https://api.open-meteo.com/v1/forecast?latitude=6.25&longitude=-75.56&current=precipitation&forecast_days=1
```

**Respuesta JSON:**
```json
{
  "latitude": 6.25,
  "longitude": -75.56,
  "current": {
    "time": "2026-06-17T12:00",
    "precipitation": 2.4
  },
  "current_units": {
    "precipitation": "mm"
  }
}
```

**Campos extraídos:**
```
latitude, longitude, current, current.time, current.precipitation,
current_units, current_units.precipitation
```

**Scoring:**
- `lluvia`: `current.precipitation` → match exacto en campo final (`precipitation` == keyword) → **+3 pts**; `precip` in `current.precipitation` → **+2 pts** más. Total = 5 pts. Sin segundo candidato relevante.
- Criterio: top=5 ≥ 3 ✅ y top=5 ≥ 2×0 ✅ → **RECONOCIDA**

**Resultado:**
```
variable=lluvia, estado=reconocida, confianza=0.62
```

**Estado que entraría a FUENTES_CUSTOM:** `pendiente_aprobacion`, `activa=false`

---

## Caso 1-B — RECONOCIDA: USGS terremotos (sismo)

**Respuesta JSON simulada:**
```json
{
  "features": [{
    "properties": {
      "mag": 2.1,
      "magnitude": 2.1,
      "place": "Colombia",
      "time": 1718000000000
    }
  }]
}
```

**Resultado:**
```
variable=sismo, estado=reconocida, confianza=1.00
```

Score máximo (1.0) porque tanto `mag` como `magnitude` son keywords exactas de `sismo` → 3+3+... pts superan el techo de 8.

---

## Caso 2 — AMBIGUA (sin variable): API de bolsa (irrelevante)

**Respuesta JSON:**
```json
{"symbol": "AAPL", "price": 189.5, "volume": 12345678, "change_pct": -0.45}
```

**Campos extraídos:** `symbol, price, volume, change_pct, market_cap`

**Scoring:** Ninguna keyword IRG tiene match en estos campos. Todos los scores = 0.

**Resultado:**
```
variable='', estado=ambigua, confianza=0.00
```

**Estado que entraría a FUENTES_CUSTOM:** `rechazada_ambigua`, `activa=false`
El panel mostraría el dropdown para selección manual de variable.

---

## Caso extra — AMBIGUA (con candidato): URL con múltiples variables IRG

**URL:**
```
https://api.open-meteo.com/v1/forecast?latitude=6.25&longitude=-75.56&current=precipitation,temperature_2m
```

Esta URL tiene **dos** variables IRG (`lluvia` y `temperatura`).

**Resultado:**
```
variable=temperatura, estado=ambigua, confianza=0.49
```

Temperatura puntúa más alto (keywords `temp`, `temperature`, `temperature_2m` = ~7 pts)
que lluvia (keywords `precipitation`, `precip` = ~5 pts), pero el factor 2× no se cumple
(7 < 10), entonces el sistema **rechaza correctamente como AMBIGUA**.

El desarrollador ve la sección "En revisión" con dropdown y elige cuál de las
dos variables registrar.

---

## Verificación de la regla de no-activación automática

Los tres estados retornados por `/analizar` (`pendiente_aprobacion`, `rechazada_ambigua`,
`rechazada_sin_respuesta`) se guardan en FUENTES_CUSTOM con `activa: false`.
La función `consultarFuentesCustom()` solo itera sobre `FUENTES_CUSTOM.filter(f=>f.activa)`,
por lo que ninguna fuente pendiente o rechazada entra al ciclo IRG.

Solo cuando el desarrollador hace clic en "✅ Aprobar" → `aprobarFuenteCustom(id)` → se
escribe `activa: true` en localStorage.

---

## Próximo paso para prueba HTTP real

Hacer push de la rama y PR → despliegue en Railway → entonces:

```bash
curl -s -X POST "https://invigorating-creativity-production-4a58.up.railway.app/api/v1/fuentes/deteccion/analizar" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://api.open-meteo.com/v1/forecast?latitude=6.25&longitude=-75.56&current=precipitation&forecast_days=1","nombre_sugerido":"Open-Meteo lluvia"}' | python -m json.tool
```

Resultado esperado: `"estado": "pendiente_aprobacion"`, `"variable_sugerida": "lluvia"`.
