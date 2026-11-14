-- HU4.1.2 · Evidencias y geolocalización · Cambios en el esquema insuranceclaims (PostgreSQL).
-- Requiere haber aplicado insuranceclaims_hu4_1_1.sql. Idempotente.
-- La tabla evidencia_siniestro la crea create_all al arrancar; este script es para ambientes donde
-- prefieran crearla a mano y para agregar la ubicación a la tabla siniestro existente.

BEGIN;

ALTER TABLE insuranceclaims.siniestro
    ADD COLUMN IF NOT EXISTS ubicacion_latitud numeric(9, 6),
    ADD COLUMN IF NOT EXISTS ubicacion_longitud numeric(9, 6),
    ADD COLUMN IF NOT EXISTS ubicacion_precision_m numeric(8, 2),
    ADD COLUMN IF NOT EXISTS ubicacion_fuente varchar(20),
    ADD COLUMN IF NOT EXISTS ubicacion_capturada_en timestamptz,
    ADD COLUMN IF NOT EXISTS ubicacion_actualizada_en timestamptz;

CREATE TABLE IF NOT EXISTS insuranceclaims.evidencia_siniestro (
    evidencia_id uuid PRIMARY KEY,
    siniestro_id uuid NOT NULL REFERENCES insuranceclaims.siniestro (siniestro_id),
    tipo varchar(10) NOT NULL,
    content_type varchar(50) NOT NULL,
    tamano_declarado bigint NOT NULL,
    tamano_bytes bigint,
    origen varchar(10) NOT NULL,
    capturada_en timestamptz NOT NULL,
    objeto_clave varchar(300) NOT NULL UNIQUE,
    estado varchar(20) NOT NULL,
    solicitada_en timestamptz NOT NULL,
    expira_en timestamptz NOT NULL,
    cargada_en timestamptz,
    motivo_rechazo varchar(100)
);

CREATE INDEX IF NOT EXISTS ix_insuranceclaims_evidencia_siniestro_siniestro_id
    ON insuranceclaims.evidencia_siniestro (siniestro_id);
CREATE INDEX IF NOT EXISTS ix_evidencia_siniestro_tipo_estado
    ON insuranceclaims.evidencia_siniestro (siniestro_id, tipo, estado);

-- Idempotency-Key de la solicitud de carga (una por evidencia local de la app): reintentar no crea otra fila.
ALTER TABLE insuranceclaims.evidencia_siniestro
    ADD COLUMN IF NOT EXISTS clave_idempotencia varchar(36);
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidencia_siniestro_clave
    ON insuranceclaims.evidencia_siniestro (siniestro_id, clave_idempotencia);

COMMIT;
