# 🛰️ SIRGA — Sistema Inteligente de Riesgos Ambientales · Antioquia

**Predicción y gestión de riesgos en tiempo real para municipios de Antioquia, Colombia.**  
Integra IDEAM · SIATA · EPM · IGAC · CORNARE · DAGRAN · Copernicus.

---

## ⚡ Inicio en 1 comando

```bash
git clone <repositorio>
cd riesgo-antioquia
bash start.sh demo        # Demo rápida (sin Docker)
bash start.sh docker      # Sistema completo
```

**Demo abre automáticamente el dashboard en el navegador.**  
API disponible en `http://localhost:8000/docs`

---

## 📊 Qué incluye este repositorio

| Componente | Descripción | Estado |
|---|---|---|
| `backend/` | API FastAPI con todos los endpoints | ✅ Funcional |
| `frontend/index.html` | Dashboard completo (mapa, alertas, wizard) | ✅ Funcional |
| `docker-compose.yml` | PostGIS + Redis + Nginx + API + Frontend | ✅ Listo |
| `docker/init.sql` | Schema PostGIS con tablas y datos iniciales | ✅ Listo |
| `start.sh` | Script de inicio de 1 comando | ✅ Listo |

---

## 🧩 Arquitectura

```
Fuentes (IDEAM · SIATA · EPM · IGAC · Copernicus · DAGRAN)
          ↓
   Ingesta (Kafka/MQTT streaming + Airflow batch)
          ↓
   Procesamiento geoespacial (Grid 10-100m · PostGIS)
          ↓
   Modelos IA + Física: RIESGO = (H × E × V) × F_clima
     · H = Amenaza (ML + física)
     · E = Exposición de elementos
     · V = Vulnerabilidad social
     · F_clima = Factor ENSO (El Niño / La Niña)
          ↓
   API REST + WebSocket (FastAPI)
          ↓
   Frontend Dashboard (Mapa · Alertas · Predicción · Config)
          ↓
   Alertas automáticas (SMS · Email · Push)
```

---

## 🔌 Endpoints API

```http
GET  /api/v1/riesgo/zona/{zona_id}                 # Riesgo actual
GET  /api/v1/riesgo/multihorizonte/{zona_id}        # 1h·6h·24h·72h
GET  /api/v1/riesgo/mapa/{zona_id}                  # GeoJSON para mapa
GET  /api/v1/alertas/{zona_id}                      # Alertas activas
GET  /api/v1/prediccion/{zona_id}                   # Predicción
GET  /api/v1/prediccion/serie/{zona_id}             # Serie temporal
GET  /api/v1/sensores/{zona_id}                     # Lecturas sensores
GET  /api/v1/config/wizard/pasos                    # Pasos del wizard
GET  /api/v1/config/wizard/municipios               # Municipios disponibles
GET  /api/v1/config/wizard/autodetectar/{muni_id}  # Auto-configuración
POST /api/v1/config/guardar                         # Guardar configuración
WS   /ws/alertas                                    # Alertas en tiempo real
WS   /ws/riesgo-live                                # Mapa en tiempo real
```

---

## 🚀 Roadmap de fases

### Fase 1 — MVP (este repositorio) ✅
- API REST funcional
- Modelo de riesgo H×E×V×F_clima
- Dashboard con mapa, alertas y predicciones
- Wizard de configuración no-técnico
- Datos simulados de SIATA/IDEAM/EPM
- Docker completo

### Fase 2 — Integración real (2-3 meses)
- Conexión real API IDEAM
- Ingesta SIATA vía MQTT
- Datos EPM embalse El Peñol
- DEM real IGAC via WCS
- TimescaleDB para series temporales
- Tiles satelitales Copernicus

### Fase 3 — ML avanzado (3-6 meses)
- Modelos XGBoost/LightGBM entrenados con datos históricos DAGRAN
- LSTM para series temporales de lluvia
- Estimación de incertidumbre con Conformal Prediction
- Detección de anomalías con Isolation Forest
- Imputación de datos faltantes con MICE

### Fase 4 — Escala regional (6-12 meses)
- Cobertura todos los municipios de Antioquia (125)
- Grid 10m con GPU processing
- Integración UNGRD nacional
- App móvil ciudadana
- Alertas temprana via WhatsApp Business API

---

## ⚙️ Configuración no técnica

El sistema incluye un **wizard de 5 pasos** accesible desde el dashboard:

1. **Selecciona tu municipio** — el sistema detecta sensores automáticamente
2. **Conecta fuentes de datos** — checkboxes simples, sin tecnicismos
3. **Elige riesgos a monitorear** — deslizamientos, inundaciones, etc.
4. **Nivel de detalle** — bajo / medio / alto
5. **El sistema se configura solo** — resolución de grid, intervalos, modelos

**Fallback automático:** Si una fuente falla, el sistema cambia a modo degradado sin interrumpir el servicio.

---

## 🏗️ Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | FastAPI + Python 3.11 |
| Base de datos | PostgreSQL 16 + PostGIS 3.4 |
| Cache / Pub-Sub | Redis 7 |
| Streaming | Apache Kafka + MQTT (Fase 2) |
| ML | scikit-learn · XGBoost · TensorFlow (Fase 3) |
| GIS | PostGIS · GDAL · Rasterio |
| Frontend | HTML5 + Chart.js (MVP) → React + MapLibre GL (Fase 2) |
| Orquestación | Apache Airflow (Fase 2) |
| Cloud | Docker · Kubernetes · AWS/GCP |
| Proxy | Nginx |

---

## 📁 Estructura

```
riesgo-antioquia/
├── backend/
│   ├── app/
│   │   ├── main.py              # Punto de entrada FastAPI
│   │   ├── api/
│   │   │   ├── riesgo.py        # Endpoints de riesgo
│   │   │   ├── alertas.py       # Endpoints de alertas
│   │   │   ├── configuracion.py # Wizard + auto-config
│   │   │   ├── sensores.py      # Lecturas de sensores
│   │   │   └── prediccion.py    # Predicciones
│   │   ├── models/
│   │   │   └── schemas.py       # Modelos Pydantic
│   │   └── services/
│   │       ├── riesgo_service.py    # Lógica H×E×V×F_clima
│   │       └── websocket_manager.py # WebSocket RT
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── index.html              # Dashboard completo
├── docker/
│   ├── init.sql                # Schema PostGIS
│   └── nginx.conf              # Proxy reverso
├── docker-compose.yml          # Orquestación completa
├── start.sh                    # 1 comando de inicio
└── README.md
```

---

## 🌍 Zona inicial: Guatapé

El sistema está pre-configurado para **Guatapé, Antioquia**:
- Coordenadas: 6.2336°N, 75.1567°W
- Altitud: 1,890 msnm
- Riesgos principales: inundaciones (embalse El Peñol), deslizamientos
- Fuentes: SIATA · EPM · IDEAM

Expandible a cualquier municipio de Antioquia en minutos via el wizard.

---

## 📞 Entidades integradas

| Entidad | Datos aportados | Integración |
|---|---|---|
| IDEAM | Pronósticos, clima, lluvia | API REST (Fase 2) |
| SIATA | Sensores RT, lluvia, temperatura | MQTT (Fase 2) |
| EPM | Nivel embalse El Peñol, caudales | API REST (Fase 2) |
| IGAC | DEM, topografía, cartografía | WCS/WFS (Fase 2) |
| CORNARE | Monitoreo ambiental regional | CSV/API (Fase 2) |
| DAGRAN / UNGRD | Histórico desastres, vulnerabilidad | Base datos (Fase 3) |
| Copernicus / NASA | Imágenes SAR, NDVI, humedad | API (Fase 3) |

---

*Sistema desarrollado para apoyar la gestión del riesgo de desastres en Antioquia, Colombia.*  
*Modelo: RIESGO = (H × E × V) × F_clima — Referencia: UNGRD · SIATA · IPCC AR6*
