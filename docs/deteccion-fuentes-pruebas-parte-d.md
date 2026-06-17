# Parte D — Pruebas end-to-end del clasificador de fuentes
## Sesión 3

---

## Método de ejecución

Pruebas ejecutadas con curl real contra backend local (localhost:8002)
con el código de esta rama (`feat/deteccion-fuentes-sesion3`).

El backend fue levantado con:
```bash
cd backend
python -m uvicorn app.main:app --port 8002
```

PostgreSQL no disponible localmente (esperado) — la app arranca sin histórico,
el clasificador no depende de DB. Railway production corre `main` y no tiene
estos endpoints aún; la prueba HTTP contra Railway se puede correr post-merge
(comando al final de este documento).

---

## Caso 1 — EJECUTADO CON CURL REAL: Open-Meteo (precipitación)

**Comando ejecutado:**
```bash
curl -s -X POST "http://localhost:8002/api/v1/fuentes/deteccion/analizar" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://api.open-meteo.com/v1/forecast?latitude=6.25&longitude=-75.56&current=precipitation&forecast_days=1","nombre_sugerido":"Open-Meteo lluvia Medellin"}'
```

**Output completo del servidor (sin modificar):**
```json
{"id":"fd_1781726524756","url":"https://api.open-meteo.com/v1/forecast?latitude=6.25&longitude=-75.56&current=precipitation&forecast_days=1","nombre_sugerido":"Open-Meteo lluvia Medellin","estado":"pendiente_aprobacion","formato_detectado":"json","variable_sugerida":"lluvia","confianza":0.625,"campos_detectados":["latitude","longitude","generationtime_ms","utc_offset_seconds","timezone","timezone_abbreviation","elevation","current_units","current_units.time","current_units.interval","current_units.precipitation","current","current.time","current.interval","current.precipitation"],"muestra_cruda":"{\"latitude\":6.2214413,\"longitude\":-75.55185,\"generationtime_ms\":0.03838539123535156,\"utc_offset_seconds\":0,\"timezone\":\"GMT\",\"timezone_abbreviation\":\"GMT\",\"elevation\":1509.0,\"current_units\":{\"time\":\"iso8601\",\"interval\":\"seconds\",\"precipitation\":\"mm\"},\"current\":{\"time\":\"2026-06-17T20:00\",\"interval\":900,\"precipitation\":0.10}}","motivo_rechazo":null,"fecha_deteccion":"2026-06-17T20:02:09.188737+00:00"}
```

**Resultado:** `estado=pendiente_aprobacion`, `variable_sugerida=lluvia`, `confianza=0.625`.
Open-Meteo respondió en vivo con `precipitation: 0.10 mm`. El campo `current.precipitation`
produjo match exacto contra la keyword `precipitation` de la variable `lluvia` → RECONOCIDA.

---

## Caso 2 — EJECUTADO CON CURL REAL: Coinbase BTC/USD (sin variables IRG)

**Comando ejecutado:**
```bash
curl -s -X POST "http://localhost:8002/api/v1/fuentes/deteccion/analizar" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://api.coinbase.com/v2/prices/BTC-USD/spot","nombre_sugerido":"Precio Bitcoin (irrelevante)"}'
```

**Output completo del servidor (sin modificar):**
```json
{"id":"fd_1781726537188","url":"https://api.coinbase.com/v2/prices/BTC-USD/spot","nombre_sugerido":"Precio Bitcoin (irrelevante)","estado":"rechazada_ambigua","formato_detectado":"json","variable_sugerida":null,"confianza":0.0,"campos_detectados":["data","data.amount","data.base","data.currency"],"muestra_cruda":"{\"data\":{\"amount\":\"64259.14\",\"base\":\"BTC\",\"currency\":\"USD\"}}","motivo_rechazo":"No se detectaron campos compatibles con ninguna variable IRG. Formato: json. Campos encontrados: data, data.amount, data.base, data.currency.","fecha_deteccion":"2026-06-17T20:02:17.961514+00:00"}
```

**Resultado:** `estado=rechazada_ambigua`, `variable_sugerida=null`, `confianza=0.0`.
Coinbase respondió en vivo con `amount: "64259.14"`, `base: "BTC"`, `currency: "USD"`.
Ningún campo coincide con keywords IRG → confianza 0.0, motivo de rechazo incluido.

---

## Caso 3 — TEÓRICO, NO EJECUTADO CON CURL: USGS terremotos (sismo)

> **Este caso no fue ejecutado con curl.** El JSON de abajo fue construido a mano
> para ilustrar cómo respondería el clasificador. No representa una captura real.

**JSON de entrada hipotético:**
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

**Resultado del clasificador (Python, no HTTP):**
```
variable=sismo, estado=reconocida, confianza=1.00
```

Los campos `mag` y `magnitude` son keywords exactas de la variable `sismo`,
lo que produce un score que supera el techo de 8 pts → confianza 1.0.

---

## Caso 4 — TEÓRICO, NO EJECUTADO CON CURL: URL con dos variables IRG mezcladas

> **Este caso no fue ejecutado con curl.** Ilustra el comportamiento esperado
> cuando una URL devuelve múltiples variables IRG simultáneamente.

**URL hipotética** (Open-Meteo con `precipitation` y `temperature_2m`):
```
https://api.open-meteo.com/v1/forecast?latitude=6.25&longitude=-75.56&current=precipitation,temperature_2m
```

**Resultado del clasificador (Python, no HTTP):**
```
variable=temperatura, estado=ambigua, confianza=0.49
```

`temperatura` puntúa ~7 pts (keywords `temp`, `temperature`, `temperature_2m`),
`lluvia` puntúa ~5 pts (keywords `precipitation`, `precip`).
El factor 2× no se cumple (7 < 10) → AMBIGUA correctamente.
El desarrollador vería el dropdown en el panel para elegir cuál de las dos registrar.

---

## Verificación de la regla de no-activación automática

Los tres estados posibles de `/analizar` (`pendiente_aprobacion`, `rechazada_ambigua`,
`rechazada_sin_respuesta`) se guardan en FUENTES_CUSTOM con `activa: false`.
`consultarFuentesCustom()` solo itera `FUENTES_CUSTOM.filter(f => f.activa)`,
por lo que ninguna fuente pendiente o rechazada entra al ciclo IRG.
Solo `aprobarFuenteCustom(id)` escribe `activa: true`.

---

## Prueba HTTP pendiente post-merge (Railway)

Una vez que esta rama se merge a `main` y Railway redespliega:

```bash
curl -s -X POST "https://invigorating-creativity-production-4a58.up.railway.app/api/v1/fuentes/deteccion/analizar" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://api.open-meteo.com/v1/forecast?latitude=6.25&longitude=-75.56&current=precipitation&forecast_days=1","nombre_sugerido":"Open-Meteo lluvia"}' | python -m json.tool
```

Resultado esperado: `"estado": "pendiente_aprobacion"`, `"variable_sugerida": "lluvia"`.
