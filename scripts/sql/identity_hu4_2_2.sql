ALTER TABLE IF EXISTS identity.dispositivos_vinculados ADD COLUMN IF NOT EXISTS push_token VARCHAR(1024) NULL;
ALTER TABLE IF EXISTS identity.dispositivos_vinculados ADD COLUMN IF NOT EXISTS push_plataforma VARCHAR(10) NULL;
ALTER TABLE IF EXISTS identity.dispositivos_vinculados ADD COLUMN IF NOT EXISTS push_actualizado_en TIMESTAMPTZ NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_dispositivo_push_token ON identity.dispositivos_vinculados (push_token) WHERE push_token IS NOT NULL;
