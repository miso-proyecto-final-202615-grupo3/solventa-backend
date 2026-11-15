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
| `insurancepolicies_service` | Gestión de pólizas, firma digital manuscrita, emisión de la póliza y certificado PDF | `/api/v1/insurancepolicies-service` |
| `insuranceclaims_service` | Gestión de siniestros (solo `/health` por ahora) | `/api/v1/insuranceclaims-service` |
| `payments_service` | Pago de la prima inicial con PayPal o tarjeta de crédito | `/api/v1/payments-service` |
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

La API queda en `http://localhost:8002` y el health check en `http://localhost:8002/health`.

Para ejecutar fuera de Compose:

```powershell
cd identity_service
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

### Autoescalado

Todos los servicios del chart `backend-service` incluyen en sus `values.yaml`
la sección `autoscaling`, deshabilitada por defecto:

```yaml
autoscaling:
  enabled: false
  cpuUtilization: 70
  min: 1
  max: 10
```

Para activar el HPA de un servicio en un ambiente, establece
`autoscaling.enabled: true` en el `values.<ambiente>.yaml` correspondiente.
El HPA `autoscaling/v2` utiliza el promedio de utilización de CPU como
porcentaje del `resources.requests.cpu` de los contenedores. Requiere la API de
métricas de recursos disponible en el clúster, por ejemplo, Metrics Server.
Su comportamiento es común a todos los servicios: espera 300 segundos para
reducir y usa políticas de 20 % o un pod por minuto; para aumentar usa 100 % o
cuatro pods cada 15 segundos, seleccionando `Max` en ambos casos.

Con HPA activo, el Deployment no fija `replicas`; con HPA desactivado se usa
`replicaCount`. Al desactivar el HPA, el Deployment vuelve al `replicaCount`
configurado. Los flujos de despliegue actualizan el release sin eliminarlo y
reinician gradualmente el Deployment para actualizar la imagen `latest`.

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
| `mock_paymentprovider` | `http://localhost:8204` |
| `localstack` (SQS, opcional) | `http://localhost:4566`; su servicio está comentado en `docker-compose.yml` |

## Pasarela simulada y SQS local

`mock_paymentprovider` (`http://localhost:8204`) simula la pasarela con operaciones síncronas, sin redirecciones
ni webhooks, y sin guardar estado. La documentación interactiva está en `/docs`.

| Operación | Escenario |
| --- | --- |
| `POST /paypal/payments` | `payer_email` que empieza por `declined` → `INSTRUMENT_DECLINED`; por `nofunds` → `INSUFFICIENT_FUNDS`; otro → `COMPLETED` |
| `POST /credit-card/tokens` | Tokeniza los datos enviados por `payments_service`; devuelve `tok_<MARCA>_<últimos4>` |
| `POST /credit-card/charges` | Últimos 4 del token: `0002` → `card_declined`, `9995` → `insufficient_funds`, `0069` → `expired_card`; otro → `succeeded` |

Por defecto los servicios usan el **SQS remoto** de AWS: define las URL de las colas existentes en `.env`
(`PAGO_APROBADO_QUEUE_URL` y `POLIZA_EMITIDA_QUEUE_URL`) y credenciales `AWS_*` con permisos sobre ellas; sin URL, el
proceso que depende de esa cola no se inicia. Para probar SQS en local, descomenta el servicio `localstack` y sus
`depends_on` en `docker-compose.yml` y usa las variables comentadas de `.env.example`. `scripts/localstack/init-sqs.sh`
crea las colas `solventa-pago-aprobado` y `solventa-poliza-emitida`, cada una con su DLQ (5 recepciones). La imagen
`localstack/localstack:latest` exige `LOCALSTACK_AUTH_TOKEN` (token de una cuenta de LocalStack). Para ver los eventos:

```bash
aws --endpoint-url http://localhost:4566 --region us-east-1 \
  sqs receive-message --queue-url http://localhost:4566/000000000000/solventa-pago-aprobado
```

En ambientes desplegados la cola SQS, los permisos del servicio y el repositorio ECR de `mock-paymentprovider`
no los crea este repositorio.

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
