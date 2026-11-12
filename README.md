# Solventa Backend

Monorepo de microservicios de Solventa (FastAPI + Clean Architecture).
Cada servicio es autocontenido: su propia app (`src`), sus dependencias por
ambiente y su imagen Docker. Cada servicio se despliega como un pod independiente.

## Servicios

| Servicio | Descripción | Prefijo de API |
| --- | --- | --- |
| `bff_web` | Backend For Frontend del cliente web | `/api/v1/bff-web` |
| `bff_mobile` | Backend For Frontend de la app móvil Android | `/api/v1/bff-mobile` |
| `identity_service` | Identidad y registro de clientes | `/api/v1/identity-service` |
| `quotingengine_service` | Motor de cotización y suscripción | `/api/v1/quotingengine-service` |
| `insurancepolicies_service` | Gestión de pólizas y firma digital manuscrita (HU1.3.5) | `/api/v1/insurancepolicies-service` |
| `insuranceclaims_service` | Gestión de siniestros (solo `/health` por ahora) | `/api/v1/insuranceclaims-service` |
| `payments_service` | Pagos y recaudo (sin endpoints de negocio por ahora) | `/api/v1/payments-service` |
| `liveness_adapter` | Adaptador de retos y verificación de prueba de vida | `/api/v1/liveness-adapter` |

## Requisitos

- Python 3.13+
- Docker (opcional, para la imagen)

## Ejecutar en local (por servicio)

```bash
cd identity_service
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Levantar el servicio desde la raíz del repositorio:

```bash
uvicorn src.main:app --reload --app-dir identity_service
```

La API queda en `http://localhost:8002` y el health check en
`http://localhost:8002/health`.

Quoting Engine expone consulta de productos en
`GET /api/v1/quotingengine-service/productos` y solicitud de cotización en
`POST /api/v1/quotingengine-service/cotizaciones`. Los BFF Web y Mobile actúan como
fachada y reenvían esas operaciones. Identity entrega el perfil del cliente por gRPC
en el puerto interno `50051`, validando el consentimiento antes de consultar Open Finance.
Open Data se consulta desde Quoting Engine; ambos proveedores degradan de forma controlada.

El BFF Web también reenvía las condiciones de una cotización:

- `GET /api/v1/bff-web/cotizaciones/{cotizacion_id}/condiciones`.
- `POST /api/v1/bff-web/cotizaciones/{cotizacion_id}/condiciones/decisiones`,
  con el body `{"condiciones_cotizacion_id": "<uuid>", "decision": "ACEPTADA"}`;
  también se admite `RECHAZADA`. La respuesta conserva el `cliente_id` asociado
  a la cotización. El cliente no debe enviarlo en el body.

Estos endpoints no autentican ni autorizan al solicitante. Antes de exponerlos a
usuarios finales se debe implementar autenticación y comprobación de propiedad
de la cotización; conocer los identificadores no demuestra autorización.

La consulta de pólizas del cliente queda expuesta por el BFF Web:

- `GET /api/v1/bff-web/polizas/mis-polizas`.
- `GET /api/v1/bff-web/polizas/{poliza_id}`.

Ambos endpoints requieren el encabezado interno `X-Client-Id`. El MS de pólizas
valida que la póliza pertenezca al cliente indicado y responde `403` si no coincide.
La sustitución de este encabezado por el principal del JWT queda pendiente de la
integración de autenticación del BFF.

Para ejecutar Quoting Engine fuera de Compose:

```powershell
cd quotingengine_service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn src.main:app --reload
```

## Pruebas (por servicio)

Desde la carpeta del servicio (usa su `pytest.ini`):

```bash
cd identity_service
python -m pytest -v
```


## Docker

Cada servicio tiene su imagen en `docker/services/Dockerfile.<service_name>`.
La imagen solo instala las dependencias de runtime (`requirements.txt`), no las de dev.

```bash
docker build -f docker/services/Dockerfile.identity_service -t solventa/identity-service .
```

## CI/CD

- **CI (`ci.yml`):** corre `pytest` con cobertura por servicio y construye sus imágenes en cada
  push/PR a `dev` y `main`.
- **Despliegue:** portado del template de referencia (`template-solventa-backend-services`):
  - Workflows manuales de ECR/EKS: `backend-publish-ecr`, `backend-deploy-eks`,
    `service-publish-ecr`, `service-deploy-eks`, `eks-deploy-base-services`.
  - Helm: chart genérico en `deployment/helm/charts/backend-service` con `values` por servicio
    y ambiente (`deployment/helm/config/<service>/values.<env>.yaml`).
  - Kustomize: SecretStore + ExternalSecrets + ServiceAccount + Ingress ALB en
    `deployment/kuztomize`.
- Requiere: GitHub Environments (`dev`/`qa`/`prod`) con
  `AWS_REGION`, `AWS_ROLE_ARN` y `DATABASE_URL`, y los repos ECR configurados en los `values`.

## Stack local (Docker Compose)

```bash
docker compose up --build
```

| Servicio | URL local |
| --- | --- |
| `bff_web` | `http://localhost:8000` |
| `bff_mobile` | `http://localhost:8001` (desde el emulador Android: `http://10.0.2.2:8001`) |
| `identity_service` | `http://localhost:8002` |
| `quotingengine_service` | `http://localhost:8003` |
| `insurancepolicies_service` | `http://localhost:8004` |
| `insuranceclaims_service` | `http://localhost:8005` |
| `payments_service` | `http://localhost:8006` |
| gRPC de Identidad | `localhost:50051` |
| `mock_openfinance` | `http://localhost:8200` |
| `mock_opendata` | `http://localhost:8201` |
| `mock_kyc` | `http://localhost:8202` |
| `liveness_adapter` | `http://localhost:8203` |

Payments expone `GET /`, `GET /health` y métricas Prometheus en `GET /metrics`;
todavía no expone endpoints de negocio.

Los mocks locales usan HTTP. En ambientes desplegados, configura `OPEN_FINANCE_URL`
y `OPEN_DATA_URL` con los endpoints HTTPS de los proveedores.

Para las fotos de las verificaciones KYC/AML, `identity_service` usa S3 por defecto (`KYC_DOCUMENT_STORAGE=s3`); configura `S3_BUCKET_NAME`. Para desarrollo local se puede establecer
`KYC_DOCUMENT_STORAGE=local`: los archivos se guardan bajo
`/tmp/verificaciones-kyc-aml/{cliente_id}/{verificacion_id}/` y sus referencias persistidas son rutas locales absolutas.

La consulta de productos queda expuesta por los BFF en `GET /api/v1/bff-web/productos`
y `GET /api/v1/bff-mobile/productos`; la cotización recibe `producto_codigo`, el
saldo pendiente del crédito y la ubicación del inmueble.

## Firma digital (HU1.3.5)

`insurancepolicies_service` captura la firma manuscrita (imagen PNG o JPEG del canvas) con
`POST /api/v1/insurancepolicies-service/cotizaciones/{cotizacion_id}/firma-digital`
(`multipart/form-data` con `cliente_id`, `producto_id` y un único archivo `firma`; header
`Idempotency-Key` obligatorio) y la consulta con `GET` sobre la misma ruta. La auditoría queda en
`insurancepolicies.firma_digital` (hash de la firma, fingerprint del contrato, fecha/hora del servidor y
ruta relativa de la imagen, sin IP ni user agent). Una nueva firma reemplaza a la `CAPTURADA` de la cotización.

El BFF Web enruta ambas operaciones en
`/api/v1/bff-web/cotizaciones/{cotizacion_id}/firma-digital`. Reenvía el multipart,
`Idempotency-Key`, `X-Correlation-Id` y `Authorization`, y conserva el código de respuesta
del servicio (incluidos `201` para creación y `200` para un reintento). La dirección del
servicio se configura con `INSURANCEPOLICIES_SERVICE_URL`. El límite del multipart completo
en el BFF es `FIRMA_MAX_REQUEST_BYTES` (2 MiB por defecto); ajústalo si cambia
`FIRMA_MAX_BYTES` en el servicio de pólizas, dejando espacio para el multipart.
El reenvío de `Authorization` no implica validación de identidad ni de propiedad de la
cotización: esas verificaciones aún no están implementadas en estas rutas.

El almacenamiento se elige con `FIRMA_STORAGE`: `s3` (por defecto; bucket privado `S3_BUCKET_NAME`, SSE-S3,
credenciales por la cadena por defecto de boto3) o `local` (bajo `FIRMA_LOCAL_BASE_DIR`, por defecto `/tmp`).
En ambos casos la ruta es `firma-digital/{cliente_id}/{firma_id}/firma.{png|jpg}`. `FIRMA_MAX_BYTES`
(1 MiB por defecto) limita el tamaño.

Para ejecutar la prueba de sistema del proceso de adquisición, instala `requirements-dev.txt`,
copia `tests/system/.env.example` a `tests/system/.env` y configura las URLs de identidad,
cotización y pólizas. Con los servicios y sus dependencias disponibles, ejecuta:

```bash
python tests/system/test_insurance_policy_acquiring_process.py local insurancepolicies-service
python tests/system/test_insurance_policy_acquiring_process.py local bff-web
```

El argumento `insurancepolicies-service` accede directamente a identidad, cotización y pólizas;
`bff-web` enruta los seis casos a través del BFF Web usando `SYSTEM_TESTS_BFF_WEB_BASE_URL`.
También se admiten los entornos `dev` y `prod`, usando sus URLs base configuradas. La prueba
registra un cliente y crea datos reales en el entorno elegido; utiliza imágenes simuladas y espera
que el proveedor KYC/AML apruebe ambas verificaciones. Para pruebas locales, configura el
almacenamiento de documentos y firmas (`KYC_DOCUMENT_STORAGE` y `FIRMA_STORAGE`) y el proveedor.

## Prueba de vida (HU3.1.1)

Diseño del experimento HA12: `liveness_adapter` es el único servicio que conoce a los proveedores
(Strategy `LivenessProvider` + `LivenessProviderFactory`). El proveedor activo se cambia en caliente:

```bash
curl -H "X-Admin-Token: $LIVENESS_ADMIN_TOKEN" http://localhost:8203/api/v1/liveness-adapter/admin/liveness-provider
curl -X PUT -H "X-Admin-Token: $LIVENESS_ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"provider":"didit"}' http://localhost:8203/api/v1/liveness-adapter/admin/liveness-provider
```

- `propio` (por defecto): reto del servidor + 3 frames verificados con MediaPipe. Riesgo aceptado: no es PAD certificado.
- `didit` (demo, `DIDIT_ENABLED=false` por defecto): API real de sesiones de Didit o `mock_kyc`, con topes
  `DIDIT_MAX_SESIONES_DIA` / `DIDIT_MAX_SESIONES_MES` para no salir de la cuota gratuita.
- Sin `LIVENESS_ADMIN_TOKEN` en `.env`, `/admin` responde 403. En EKS el servicio no tiene ingress (usar `port-forward`).
- Probes: `/api/v1/liveness-adapter/health` (vida del proceso) y `/api/v1/liveness-adapter/ready`
  (modelo de MediaPipe precargado y Redis disponible; tarda unos segundos al arrancar).
- Logs de trazabilidad: `liveness_provider=<nombre> correlation_id=<id> status=<approved|rejected>`.
  Si se rechaza un gesto, `propio_gesture_rejected` registra ángulos y parpadeo redondeados (nunca la imagen).
- Prueba de concurrencia en PostgreSQL (criterio de terminado):
  `POSTGRES_TEST_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/appdata python -m pytest -m postgres identity_service/tests/integration/test_concurrencia_intentos.py`
- Plan y decisiones: [docs/planning/HU3.1.1-plan-tecnico.md](docs/planning/HU3.1.1-plan-tecnico.md).

## Consentimiento biométrico (HU3.1.3)

- BFF Móvil (JWT; el correo sale del token):
  - `GET /api/v1/bff-mobile/consentimientos/biometrico` → `{otorgado, version_vigente, version_aceptada, decidido_en}`.
  - `POST /api/v1/bff-mobile/consentimientos/biometrico` `{decision: ACEPTADO|RECHAZADO, version_terminos, installation_id, decidido_en}`
    → `201 {decision, version_terminos, registrado_en}`. Errores: `401`, `409 VERSION_TERMINOS_DESACTUALIZADA`,
    `422` (datos o `decidido_en` fuera de rango: más de 5 min en el futuro o más de 24 h atrás), `503`.
- Identity guarda **cada decisión, también el rechazo**, en `identity.consentimientos_biometricos` (solo inserción):
  decisión, versión del texto legal, instalación, canal, `decidido_en` (cliente) y `registrado_en` (servidor).
  Vale la última decisión, y solo otorga si acepta la versión vigente (`BIOMETRIC_TERMS_VERSION`).
- Sin consentimiento vigente, `POST /activacion/sesiones` responde `403 CONSENTIMIENTO_BIOMETRICO_REQUERIDO`
  (`REQUIRE_BIOMETRIC_CONSENT=true` por defecto; `false` solo para demostraciones).
- Contrato canónico: [docs/contracts/consentimiento-biometrico](docs/contracts/consentimiento-biometrico).

## Cognito en local vs. EKS

- **Docker (compose):** el contenedor usa `NoopIdentityProvider` (`COGNITO_ENABLED=false`),
  porque no tiene credenciales AWS. El registro funciona contra la BD local sin depender de AWS.
- **Docker con Cognito real (pool de dev):** con `COGNITO_ENABLED=true`, `COGNITO_USER_POOL_ID`,
  `COGNITO_CLIENT_ID` y `AWS_PROFILE` en `.env`, el override monta `~/.aws` en solo lectura:
  `docker compose -f docker-compose.yml -f docker-compose.cognito.yml up -d identity_service bff_mobile`.
  El BFF valida el token con el mismo pool y app client que Identity, y obtiene el correo con
  `GetUser` de Cognito (el access token solo trae el `sub`).
- **Local uvicorn (fuera de Docker):** para probar Cognito real, crea un `.env` (gitignored)
  con `COGNITO_ENABLED=true`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID` y `AWS_REGION`, y
  corre el servicio con tus credenciales AWS del host (`aws sso login` / access keys válidas).
- **EKS:** la autenticación es automática con **Pod Identity** (no se pasan credenciales al pod).
