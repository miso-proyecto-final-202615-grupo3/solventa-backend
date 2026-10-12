# Solventa Backend

Monorepo de microservicios de Solventa (FastAPI + Clean Architecture).
Cada servicio es autocontenido: su propia app (`src`), sus dependencias por
ambiente y su imagen Docker. Cada servicio se despliega como un pod independiente.

## Servicios

| Servicio | Descripción | Prefijo de API |
| --- | --- | --- |
| `identity_service` | Identidad y registro de clientes | `/api/v1/identity-service` |
| `bff_web` | Backend For Frontend del cliente web | `/api/v1/bff-web` |

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

La API queda en `http://localhost:8000` y el health check en
`http://localhost:8000/api/v1/identity-service/health`.

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

- **CI (`ci.yml`):** corre `pytest` por servicio (`identity_service`, `bff_web`) y build de
  las imágenes en cada push/PR a `dev` y `main`.
- **Despliegue:** portado del template de referencia (`template-solventa-backend-services`):
  - Workflows manuales de ECR/EKS: `backend-publish-ecr`, `backend-deploy-eks`,
    `service-publish-ecr`, `service-deploy-eks`, `eks-setup-init`.
  - Helm: chart genérico en `deployment/helm/charts/backend-service` con `values` por servicio
    y ambiente (`deployment/helm/config/<service>/values.<env>.yaml`).
  - Kustomize: SecretStore + ExternalSecrets + ServiceAccount + Ingress ALB en
    `deployment/kuztomize`.
- Requiere (igual que el template): GitHub Environments (`dev`/`qa`/`prod`) con
  `AWS_REGION`, `AWS_ROLE_ARN` y `DATABASE_URL`, y los repos ECR configurados en los `values`.

## Stack local (Docker Compose)

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Cognito en local vs. EKS

- **Docker (compose):** el contenedor usa `NoopIdentityProvider` (`COGNITO_ENABLED=false`),
  porque no tiene credenciales AWS. El registro funciona contra la BD local sin depender de AWS.
- **Local uvicorn (fuera de Docker):** para probar Cognito real, crea un `.env` (gitignored)
  con `COGNITO_ENABLED=true`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID` y `AWS_REGION`, y
  corre el servicio con tus credenciales AWS del host (`aws sso login` / access keys válidas).
- **EKS:** la autenticación es automática con **Pod Identity** (no se pasan credenciales al pod).