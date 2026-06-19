# Auditoría completa "Acerca de" — Sesión 11 (2026-06-19)

Verificación de cada afirmación del panel "Acerca de" contra el código real
en `frontend/index.html` y el backend (`backend/app/`). Metodología: grep
del código + lectura de las memorias de sesiones anteriores.

---

## Tabla de inventario

| # | Subsección | Línea | Afirmación actual | Estado verificado | Acción |
|---|---|---|---|---|---|
| 1 | ¿Qué es OMAIRA? | 1614 | "plataforma web de **inteligencia artificial**" | ENGAÑOSO — la plataforma usa fórmulas H×E×V para riesgo; IA real es solo el chatbot (Claude/GPT/Gemini) | Corregir (Commit B) |
| 2 | ¿Qué es OMAIRA? | 1614 | "**sin servidores propios**" | INCORRECTO — hay backend activo en Railway (FastAPI + Python) | Corregir (Commit B) |
| 3 | ¿Qué es OMAIRA? | 1614 | "en **el el** territorio" | TYPO — doble "el" | Corregir (Commit B) |
| 4 | Sistema de Credibilidad | 1724 | "basado en el estado del arte en **machine learning probabilístico**" | ENGAÑOSO — Brier Score, ECE, Isotonic Regression y Platt Scaling son métricas estadísticas clásicas, no ML moderno | Corregir (Commit C) |
| 5 | IA multi-modelo | 1765 | "integra **5 modelos de IA**" | IMPRECISO — Motor local y Simulación son motores de reglas expertas, no IA; IA real son solo los 3 LLMs | Corregir con distinción explícita (Commit B) |
| 6 | Fuentes — Institucionales | 1662 | "EPM — Embalse El Peñol · Institucional" | INCORRECTO — EPM no tiene token activo; la fuente activa real para embalses es XM/SIMEM (automática, sin API key, desplegada en Sesión 2) | Reemplazar por XM/SIMEM (Commit D) |
| 7 | Fuentes | — | Detección automática de fuentes | AUSENTE — la funcionalidad construida en Sesión 3 (endpoints `/api/v1/fuentes/deteccion/`, modal "Analizar y agregar a revisión") no se menciona en ningún lugar de "Acerca de" | Agregar (Commit D) |
| 8 | Despliegue | 1819 | No menciona notificaciones email | AUSENTE — Resend implementado hoy (post-Sesión 10) no aparece | Agregar fila Resend (Commit D) |
| 9 | Arquitectura | 1625 | Fuentes en tiempo real: no menciona proxies Railway | INCOMPLETO — los proxies Railway para NOAA ONI, ADS-B, GDACS (Sesión 2, antes via corsproxy.io) no están descritos | Agregar nota (Commit D) |

---

## Lo que está CORRECTO (verificado, sin cambios)

| Subsección | Afirmación | Verificado en |
|---|---|---|
| Header | "OMAIRA v6" | línea 1598 |
| Cobertura | "123 municipios" | línea 1794 |
| Credibilidad | "Isotonic Regression activa con ≥10 outcomes" | `index.html:9550` — `ok: N_out>=10` |
| Credibilidad | "Platt Scaling implementada, disponible, no activa" | línea 1733 — descripción exacta |
| Credibilidad | "rollback si BSS < -0.5 con < 50 outcomes" | `index.html:9116-9117` — `BSS_MINIMO=-0.5`, `UMBRAL_N=50` |
| Credibilidad | "≥500 outcomes y diferencia BSS ≥0.15 para notificación" | `index.html:9061-9062` |
| Credibilidad | Climatología tasas reales UNGRD/BanRep | línea 1758 |
| Credibilidad | 3 modelos con roles complementarios | líneas 1747-1754 ✓ (Sesión 10) |
| Credibilidad | Email al operador automático | líneas 1758-1759 ✓ |
| Arquitectura | PostgreSQL Railway mencionado | línea 1629 ✓ (Sesión 7) |
| Motor científico | No usa término "IA" — describe fórmulas matemáticas | Sección completa ✓ |
| Marco normativo | Referencias correctas y consistentes | líneas 1800-1813 ✓ |
| Predicción multi-horizonte | Fiabilidades marcadas como referenciales en tabla | líneas 1782-1786 — son estimaciones orientativas estándar para modelos GFS/ECMWF, aceptable |
| Footer | "3 modelos de riesgo + 5 modelos IA" | línea 1835 ✓ (Sesión 10) |

---

## Notas de decisión

- **"5 modelos IA" en footer**: se mantiene como está. Motor local y Simulación son capacidades de diagnóstico del sistema, y el footer los agrupa con los LLMs por brevedad. La distinción se hace en el cuerpo de la sección.
- **Porcentajes de fiabilidad en Predicción** (~92%, ~85%, ~70%): son estimaciones orientativas estándar para los modelos meteorológicos GFS/ECMWF de Open-Meteo. No se cambian — son referenciales, no afirmaciones de precisión propia.
- **"sin servidores propios" en Despliegue · Frontend** (línea 1822): se refiere específicamente al frontend (GitHub Pages es estático). Esta frase en contexto de la fila de frontend es correcta. No se cambia.
