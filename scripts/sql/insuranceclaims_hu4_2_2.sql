CREATE SCHEMA IF NOT EXISTS insuranceclaims;
ALTER TABLE IF EXISTS insuranceclaims.siniestro
    ADD COLUMN IF NOT EXISTS estado_actualizado_en TIMESTAMPTZ NULL;
CREATE TABLE IF NOT EXISTS insuranceclaims.evento_outbox (
    evento_id UUID PRIMARY KEY, tipo VARCHAR(100) NOT NULL, agregado_id UUID NOT NULL,
    payload JSONB NOT NULL, estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE', intentos INTEGER NOT NULL DEFAULT 0,
    ultimo_error VARCHAR(500), creado_en TIMESTAMPTZ NOT NULL, publicado_en TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_evento_outbox_estado_creado ON insuranceclaims.evento_outbox (estado, creado_en);
