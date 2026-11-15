# Siniestros: reporte, evidencias y ubicación (HU4.1.1 y HU4.1.2)

Detalle de `insuranceclaims_service` y de los endpoints de siniestros del BFF Móvil. El diseño completo está en
[HU4.1.1-plan-tecnico.md](planning/HU4.1.1-plan-tecnico.md) y [HU4.1.2-plan-tecnico.md](planning/HU4.1.2-plan-tecnico.md).

## Reportar un siniestro (HU4.1.1)

- BFF Móvil (JWT; el cliente sale del token, nunca del cuerpo):
  - `GET /api/v1/bff-mobile/siniestros/polizas-elegibles` → pólizas vigentes del cliente con sus `tipos_siniestro`.
  - `POST /api/v1/bff-mobile/siniestros` con `Idempotency-Key: <UUID>` → `201` (nuevo) o `200` (reintento con la misma clave).
  - `GET /api/v1/bff-mobile/siniestros/{id}`.
- MS Siniestros (`insuranceclaims_service`, solo red interna, dueño en `X-Cliente-Id`): los mismos endpoints y
  `GET /api/v1/insuranceclaims-service/tipos-siniestro?producto_codigo=`, la consulta de referencia del catálogo.
- **Catálogo:** tabla `insuranceclaims.tipo_siniestro` (única fuente de los tipos por producto y sus reglas de evidencia),
  cargada al arrancar (`SEED_ON_STARTUP=true`, idempotente). Los seguros de vida no tienen tipos: no se reportan por la app.
- **Pólizas:** MS Siniestros las consulta a MS Pólizas por un puerto (`POLIZAS_ADAPTER=http`). Mientras MS Pólizas no
  exponga el endpoint interno (#265), `POLIZAS_ADAPTER=memoria` usa pólizas ficticias (por defecto en `docker compose`).
- **Base existente:** `create_all` no altera tablas; en ambientes donde `insuranceclaims.siniestro` ya existe, aplicar
  `scripts/sql/insuranceclaims_hu4_1_1.sql` (idempotente).
- Prueba de concurrencia de idempotencia contra Postgres: `TEST_POSTGRES_URL=postgresql+asyncpg://postgres:postgres@db:5432/identity_db`
  (dentro de la red de compose) y `python -m pytest insuranceclaims_service/tests -m postgres`.
- Plan y decisiones: [docs/planning/HU4.1.1-plan-tecnico.md](planning/HU4.1.1-plan-tecnico.md); contrato canónico:
  [docs/contracts/siniestros](contracts/siniestros).

## Evidencias y ubicación del siniestro (HU4.1.2)

- Cada foto o video es independiente (una que falle no afecta al siniestro ni a las demás):
  1. `POST /api/v1/bff-mobile/siniestros/{id}/evidencias` `{tipo: FOTO|VIDEO, content_type, tamano_bytes, origen, capturada_en}`
     → `201 {evidencia_id, estado: PENDIENTE, carga: {url, campos, expira_en, tamano_max_bytes}}`.
  2. La app sube el archivo **directo al almacenamiento**: `POST {carga.url}` multipart con todos los `campos` y la parte `file` al final.
  3. `POST /api/v1/bff-mobile/siniestros/{id}/evidencias/{evidencia_id}/confirmacion` → el servicio verifica tamaño,
     tipo, cifrado y los primeros bytes; `CARGADA`, o `422 EVIDENCIA_RECHAZADA` y borra el objeto.
- `PUT /api/v1/bff-mobile/siniestros/{id}/ubicacion` `{latitud, longitud, precision_m, fuente: GPS|RED|ULTIMA_CONOCIDA, capturada_en}`.
- `GET /api/v1/bff-mobile/siniestros/{id}` incluye `ubicacion` y `evidencias`.
- **URL prefirmada (`POST` con política):** la firma fija la llave exacta, el `Content-Type`, el rango de tamaño
  (foto ≤ 5 MB, video ≤ 50 MB) y el cifrado; vence en 10 min (foto) o 30 min (video). Cantidades por tipo de siniestro:
  tabla `tipo_siniestro`.
- **Local:** MinIO en `docker compose` (`http://localhost:9000`, consola en `:9001`, bucket `solventa-local-storage`,
  SSE `AES256`). La app recibe URLs firmadas con `S3_PUBLIC_ENDPOINT_URL` (`http://10.0.2.2:9000` desde el emulador).
  La imagen oficial de MinIO ya no se publica en Docker Hub: se usa `bitnamilegacy/minio`, solo para desarrollo.
- **AWS:** bucket `storage_bucket` con SSE-KMS (secretos `S3_BUCKET_NAME` y `KMS_KEY_ARN`) y credenciales por EKS Pod
  Identity. Permisos necesarios del rol: sección 7.1 de [docs/planning/HU4.1.2-plan-tecnico.md](planning/HU4.1.2-plan-tecnico.md).
- **Base existente:** aplicar `scripts/sql/insuranceclaims_hu4_1_2.sql` (idempotente) después del de HU4.1.1.
- Pruebas contra infraestructura real (dentro de la red de compose): `TEST_POSTGRES_URL=postgresql+asyncpg://postgres:postgres@db:5432/identity_db`,
  `TEST_S3_ENDPOINT_URL=http://minio:9000` y las credenciales de MinIO en `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`.
- Contrato canónico: [docs/contracts/evidencias](contracts/evidencias).

