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

El mismo comando aplica dentro de `quotingengine_service`.

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
| gRPC de Identidad | `localhost:50051` |
| `mock_kyc` | `http://localhost:8202` |
| `mock_openfinance` | `http://localhost:8200` |
| `mock_opendata` | `http://localhost:8201` |

Los mocks locales usan HTTP. En ambientes desplegados, configura `OPEN_FINANCE_URL`
y `OPEN_DATA_URL` con los endpoints HTTPS de los proveedores.

La consulta de productos queda expuesta por los BFF en `GET /api/v1/bff-web/productos`
y `GET /api/v1/bff-mobile/productos`; la cotización recibe `producto_codigo`, el
saldo pendiente del crédito y la ubicación del inmueble.

## Cognito en local vs. EKS

- **Docker (compose):** el contenedor usa `NoopIdentityProvider` (`COGNITO_ENABLED=false`),
  porque no tiene credenciales AWS. El registro funciona contra la BD local sin depender de AWS.
- **Local uvicorn (fuera de Docker):** para probar Cognito real, crea un `.env` (gitignored)
  con `COGNITO_ENABLED=true`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID` y `AWS_REGION`, y
  corre el servicio con tus credenciales AWS del host (`aws sso login` / access keys válidas).
- **EKS:** la autenticación es automática con **Pod Identity** (no se pasan credenciales al pod).
