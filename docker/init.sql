-- Extensiones geoespaciales
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Tabla de zonas de monitoreo
CREATE TABLE IF NOT EXISTS zonas (
    id SERIAL PRIMARY KEY,
    zona_id VARCHAR(100) UNIQUE NOT NULL,
    municipio VARCHAR(200) NOT NULL,
    departamento VARCHAR(100) DEFAULT 'Antioquia',
    geom GEOMETRY(POINT, 4326),
    radio_km FLOAT DEFAULT 25,
    activa BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Tabla de predicciones históricas
CREATE TABLE IF NOT EXISTS predicciones (
    id SERIAL PRIMARY KEY,
    zona_id VARCHAR(100) REFERENCES zonas(zona_id),
    tipo_riesgo VARCHAR(50) NOT NULL,
    horizonte VARCHAR(10) NOT NULL,
    nivel VARCHAR(20) NOT NULL,
    probabilidad FLOAT NOT NULL,
    amenaza FLOAT,
    exposicion FLOAT,
    vulnerabilidad FLOAT,
    factor_clima FLOAT,
    riesgo_total FLOAT,
    modo_degradado BOOLEAN DEFAULT FALSE,
    timestamp_prediccion TIMESTAMP NOT NULL,
    timestamp_horizonte TIMESTAMP NOT NULL
);

-- Índice espacial
CREATE INDEX IF NOT EXISTS idx_zonas_geom ON zonas USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_predicciones_zona ON predicciones(zona_id);
CREATE INDEX IF NOT EXISTS idx_predicciones_ts ON predicciones(timestamp_prediccion);

-- Tabla de alertas
CREATE TABLE IF NOT EXISTS alertas (
    id SERIAL PRIMARY KEY,
    alerta_id VARCHAR(200) UNIQUE NOT NULL,
    zona_id VARCHAR(100),
    tipo_riesgo VARCHAR(50) NOT NULL,
    nivel VARCHAR(20) NOT NULL,
    municipio VARCHAR(200),
    descripcion TEXT,
    acciones JSONB,
    activa BOOLEAN DEFAULT TRUE,
    geom GEOMETRY(POINT, 4326),
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Tabla de lecturas de sensores
CREATE TABLE IF NOT EXISTS lecturas_sensores (
    id SERIAL PRIMARY KEY,
    sensor_id VARCHAR(100) NOT NULL,
    zona_id VARCHAR(100),
    tipo VARCHAR(50),
    valor FLOAT NOT NULL,
    unidad VARCHAR(20),
    calidad FLOAT DEFAULT 1.0,
    fuente VARCHAR(50),
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Datos iniciales: Guatapé
INSERT INTO zonas (zona_id, municipio, geom, radio_km) VALUES
    ('guatape', 'Guatapé', ST_SetSRID(ST_MakePoint(-75.1567, 6.2336), 4326), 25),
    ('medellin', 'Medellín', ST_SetSRID(ST_MakePoint(-75.5812, 6.2442), 4326), 50),
    ('rionegro', 'Rionegro', ST_SetSRID(ST_MakePoint(-75.3769, 6.1546), 4326), 30)
ON CONFLICT (zona_id) DO NOTHING;

-- Tabla configuraciones
CREATE TABLE IF NOT EXISTS configuraciones (
    id SERIAL PRIMARY KEY,
    zona_id VARCHAR(100) UNIQUE NOT NULL,
    config JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Tabla de consultas en lenguaje natural (para mejora continua del sistema)
CREATE TABLE IF NOT EXISTS consultas_ia (
    id SERIAL PRIMARY KEY,
    zona_id VARCHAR(100),
    pregunta TEXT NOT NULL,
    respuesta TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_consultas_zona ON consultas_ia(zona_id);
CREATE INDEX IF NOT EXISTS idx_consultas_ts ON consultas_ia(timestamp);
