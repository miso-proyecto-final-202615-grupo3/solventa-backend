-- HU4.2.3 · Siniestros paramétricos (idempotente). En bases nuevas lo crea el servicio al arrancar.
CREATE SCHEMA IF NOT EXISTS insuranceclaims;
ALTER TABLE IF EXISTS insuranceclaims.evento_externo
    ADD COLUMN IF NOT EXISTS estado VARCHAR(20) NOT NULL DEFAULT 'RECIBIDO',
    ADD COLUMN IF NOT EXISTS intentos INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ultimo_error VARCHAR(500),
    ADD COLUMN IF NOT EXISTS datos JSON,
    ADD COLUMN IF NOT EXISTS resultado JSON,
    ADD COLUMN IF NOT EXISTS procesado_en TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_evento_externo_estado_recibido ON insuranceclaims.evento_externo (estado, recibido_en);
CREATE TABLE IF NOT EXISTS insuranceclaims.poliza_parametrica (
    poliza_parametrica_id UUID PRIMARY KEY,
    poliza_id UUID NOT NULL,
    cliente_id UUID NOT NULL,
    poliza_numero VARCHAR(50) NOT NULL,
    cobertura VARCHAR(50) NOT NULL,
    indice VARCHAR(50) NOT NULL,
    umbral NUMERIC(12, 2) NOT NULL,
    monto_compensacion NUMERIC(18, 2) NOT NULL,
    moneda VARCHAR(10) NOT NULL,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    actualizada_en TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_poliza_parametrica_poliza_cobertura UNIQUE (poliza_id, cobertura)
);
CREATE INDEX IF NOT EXISTS ix_poliza_parametrica_cobertura_indice ON insuranceclaims.poliza_parametrica (cobertura, indice);
CREATE INDEX IF NOT EXISTS ix_poliza_parametrica_cliente_id ON insuranceclaims.poliza_parametrica (cliente_id);
