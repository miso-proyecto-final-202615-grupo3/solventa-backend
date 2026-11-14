-- HU4.1.1 · Registrar un siniestro · Cambios en el esquema insuranceclaims (PostgreSQL).
-- El servicio usa create_all, que crea tablas nuevas pero no altera las existentes.
-- Ejecutar una vez en cada ambiente donde la tabla siniestro ya exista (avisar a Danny antes de dev).
-- Idempotente: se puede volver a ejecutar sin errores.

BEGIN;

ALTER TABLE insuranceclaims.siniestro
    ADD COLUMN IF NOT EXISTS cliente_id uuid,
    ADD COLUMN IF NOT EXISTS numero varchar(20),
    ADD COLUMN IF NOT EXISTS canal varchar(20) NOT NULL DEFAULT 'PARAMETRICO',
    ADD COLUMN IF NOT EXISTS descripcion varchar(500),
    ADD COLUMN IF NOT EXISTS poliza_numero varchar(50),
    ADD COLUMN IF NOT EXISTS producto_codigo varchar(50),
    ADD COLUMN IF NOT EXISTS huella_solicitud varchar(64);

-- Mismo nombre que genera SQLAlchemy (unique=True) para que create_all y el script coincidan.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'siniestro_numero_key' AND conrelid = 'insuranceclaims.siniestro'::regclass
    ) THEN
        ALTER TABLE insuranceclaims.siniestro ADD CONSTRAINT siniestro_numero_key UNIQUE (numero);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_insuranceclaims_siniestro_cliente_id ON insuranceclaims.siniestro (cliente_id);
CREATE INDEX IF NOT EXISTS ix_siniestro_cliente_reportado ON insuranceclaims.siniestro (cliente_id, reportado_en);

-- La tabla tipo_siniestro la crea create_all y la llena el servicio al arrancar (SEED_ON_STARTUP).

COMMIT;
