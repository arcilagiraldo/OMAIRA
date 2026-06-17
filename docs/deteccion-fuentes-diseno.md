# Diseño: Sistema de Detección Automática de Fuentes
## OMAIRA — Sesión 3

---

## 1. Contexto: qué existe hoy (`FUENTES_CUSTOM`)

`index.html` líneas 9964–10152 ya implementa un sistema de fuentes personalizadas:

| Función | Qué hace |
|---------|----------|
| `abrirModalNuevaFuente()` | Modal para pegar URL, elegir variable, campo, frecuencia |
| `probarNuevaFuenteModal()` | Llama a la URL desde el browser, muestra valor detectado |
| `guardarNuevaFuente()` | Guarda en localStorage con **`activa: true`** → entra al IRG de inmediato |
| `consultarFuentesCustom()` | Fetch en paralelo a todas las fuentes activas |
| `integrarFuentesCustomEnSensores()` | Switch sobre `lluvia/nivel_rio/temperatura/calidad_aire/embalse` → `s.*` |
| `detectarVariableJSON()` | Heurística básica client-side: busca palabras clave en nombres de campo |
| `renderFuentesCustomEnPanel()` | Lista en panel con badges (En IRG / Dato recibido / Error / Pendiente) |

**Problema:** `guardarNuevaFuente()` activa inmediatamente — viola la regla "nunca se activa nada automáticamente".

**Decisión de diseño:** extender `FUENTES_CUSTOM`, no reemplazarlo. Se agrega el campo `estado` al esquema de cada entrada.

---

## 2. Esquema extendido de `FUENTES_CUSTOM`

```js
{
  id: "custom_1718...",          // timestamp como antes
  nombre: "Mi estación",
  url: "https://...",
  metodo: "GET",
  key: "",
  key_tipo: "param",
  campo: "",                     // ruta JSON al valor (opcional — el backend la detecta)
  variable: "lluvia",            // variable IRG inferida por backend
  frecuencia: 15,
  // NUEVO — estado del ciclo de aprobación:
  estado: "pendiente_aprobacion",
  //   "pendiente_aprobacion"    → analizada, esperando decisión del desarrollador
  //   "aprobada"                → activa en IRG
  //   "rechazada_ambigua"       → backend no pudo determinar variable; requiere acción manual
  //   "rechazada_sin_respuesta" → URL no respondió en 10s
  activa: false,                 // solo true cuando estado === "aprobada"
  // NUEVO — datos del análisis:
  formato_detectado: "json",     // "json" | "xml" | "csv" | "texto_plano" | "desconocido"
  confianza: 0.83,               // 0.0–1.0; < 0.5 → AMBIGUA
  campos_detectados: ["precipitation_mm", "temperature_c"],
  muestra_cruda: "{...}",        // primeros 300 chars de la respuesta
  motivo_ambigua: null,          // string si rechazada_ambigua
  fecha_deteccion: "2026-06-17T...",
  // campos pre-existentes sin cambios:
  ultimo_valor: null, ultimo_update: null, ultimo_error: null, en_irg: false
}
```

---

## 3. Flujo completo

```
1. Desarrollador pega URL en modal (existente)
   ↓
2. Hace clic en "Analizar" (botón nuevo, reemplaza el antiguo flujo directo de "Guardar")
   El browser llama POST /api/v1/fuentes/analizar { url, nombre_sugerido }
   ↓
3. Backend (fuentes_deteccion.py):
   a. Llamada HTTP real a la URL con timeout 10s
   b. Detecta formato: JSON / XML / CSV / texto plano / sin respuesta
   c. Para JSON: extrae todos los nombres de campo (profundidad máx 4)
   d. Aplica heurísticas de clasificación (ver §4)
   e. Retorna: { id, estado, variable_sugerida, confianza, formato, campos, muestra }
   ↓
4. Frontend guarda en FUENTES_CUSTOM con estado del backend (pendiente / rechazada_*)
   activa = false en todos los casos
   ↓
5. Panel "Fuentes en revisión" (sección nueva en panel-fuentes):
   - Muestra cada fuente pendiente con variable sugerida, confianza, muestra cruda
   - Botón "✅ Aprobar" → POST /api/v1/fuentes/{id}/aprobar
   - Botón "❌ Rechazar" → POST /api/v1/fuentes/{id}/rechazar
   - Para AMBIGUA: dropdown para que el desarrollador elija variable manual
   ↓
6. Al aprobar: estado="aprobada", activa=true → entra en el próximo ciclo de consultarFuentesCustom()
   Al rechazar: estado="rechazada_*", activa=false → nunca entra al IRG
```

---

## 4. Heurísticas de clasificación

### Variables mapeables (las que `integrarFuentesCustomEnSensores()` realmente consume)

| Variable | Palabras clave en nombres de campo |
|----------|-----------------------------------|
| `lluvia` | precipitation, precip, rain, rainfall, lluvia, pp_mm, rain_mm, precip_mm |
| `nivel_rio` | nivel, level, stage, altura, water_level, cota, gauge, caudal, flow, discharge |
| `temperatura` | temperatura, temp, temperature, air_temp, t_aire, temp_c, temp_f |
| `viento` | viento, wind, wind_speed, windspeed, velocidad_viento, wind_kmh, wspd |
| `calidad_aire` | ica, aqi, pm25, pm2_5, pm10, no2, co2, ozone, o3, air_quality |
| `embalse` | embalse, reservoir, level_pct, volumen_util, nivel_pct, storage_pct |
| `sismo` | magnitude, magnitud, mag, depth, profundidad, epicenter, richter, mw |

### Algoritmo de puntuación

```
Para cada campo_nombre en la respuesta:
  Para cada variable en HEURISTICAS:
    Si campo_nombre == keyword exacta  → +3 puntos
    Si campo_nombre contiene keyword   → +2 puntos
    Si muestra_cruda contiene keyword  → +1 punto

Estado final:
  score_top >= 3 Y score_top >= 2 × score_segundo → RECONOCIDA (confianza = min(1.0, score/8))
  score_top >= 1 pero criterio no cumplido        → AMBIGUA (confianza = score/8, max 0.49)
  score_top == 0                                  → AMBIGUA sin variable sugerida
  URL no responde                                 → NO_RESPONDE
```

**Umbral:** El factor 2× entre el top y el segundo elimina fuentes que mezclan variables (ej: una API que devuelve temperatura + lluvia → AMBIGUA, el desarrollador elige cuál registrar). El score mínimo de 3 requiere al menos un match exacto de campo, evitando que coincidencias débiles en texto libre produzcan falsos positivos.

---

## 5. Almacenamiento backend

PostgreSQL es opcional en OMAIRA. El estado de las fuentes pendientes se guarda en:
- **Primario:** Dict en memoria del proceso Railway (`_fuentes_pendientes`)
- **Secundario (opcional):** Tabla `fuentes_detectadas` en PostgreSQL (se agrega al schema)

Las fuentes aprobadas se persisten en el localStorage del desarrollador (mismo mecanismo que hoy). La memoria del proceso Railway se reinicia con cada deploy — si hay fuentes pendientes al momento del deploy, el desarrollador vuelve a analizar la URL (son segundos). No es un problema operativo.

---

## 6. Relación con `FUENTES_CUSTOM` existente

| Aspecto | Antes (FUENTES_CUSTOM) | Después (este módulo) |
|---------|------------------------|----------------------|
| Quién analiza la URL | Browser (CORS posible) | Backend Railway (sin CORS) |
| Activación | Inmediata (`activa: true`) | Solo tras aprobación explícita |
| Ambigüedad | Se guarda igual, el dev elige variable | Queda bloqueada hasta que dev confirma |
| Persistencia | localStorage | localStorage + memoria Railway + DB opcional |
| Heurística | `detectarVariableJSON()` simple | Puntuación multi-campo desde backend |

Los campos `id`, `nombre`, `url`, `metodo`, `key`, `campo`, `variable`, `frecuencia`, `activa`, `ultimo_valor`, `ultimo_update`, `ultimo_error`, `en_irg` no cambian. Se agregan: `estado`, `formato_detectado`, `confianza`, `campos_detectados`, `muestra_cruda`, `motivo_ambigua`, `fecha_deteccion`.

---

## 7. Variables IRG que NO son mapeables por fuente externa

Las siguientes variables del `PESOS_IRG` se calculan internamente y no pueden recibir dato externo:

`turismo`, `movilidad`, `vias_problemas`, `puentes_riesgo`, `derrumbes_vias`,
`tormenta_electrica`, `vendaval`, `granizo`, `neblina_peligrosa`, `neblina_vial`,
`creciente_subita`, `saturacion_cuenca`, `restriccion_aerea`, `congestion_emergencia`,
`densidad_exposicion`

Estas son derivadas de las variables primarias (`lluvia`, `viento`, `embalse`, etc.) o de modelos internos. Una fuente externa solo puede alimentar variables primarias.
