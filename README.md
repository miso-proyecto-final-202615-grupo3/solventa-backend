# Solventa Backend

Monorepo de microservicios de Solventa (FastAPI + Clean Architecture).
Cada servicio es autocontenido: su propia app (`src`), sus dependencias por
ambiente y su imagen Docker. Cada servicio se despliega como un pod independiente.

## Servicios

| Servicio | Descripción | Prefijo de API |
| --- | --- | --- |
| `identity_service` | Identidad y registro de clientes | `/api/v1/identity-service` |
| `bff_web` | Backend For Frontend del cliente web | `/api/v1/bff-web` |
| `bff_mobile` | Backend For Frontend de la app móvil Android | `/api/v1/bff-mobile` |
| `liveness_adapter` | Reto y verificación de prueba de vida | `/api/v1/liveness-adapter` |

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
`http://localhost:8000/health`.

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

- **CI (`ci.yml`):** corre `pytest` por servicio (`identity_service`, `bff_web`, `bff_mobile`) y build de
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
docker compose up --build
```

El servicio de observabilidad `lgtm` es opcional para el flujo funcional local.
Para incluirlo (su imagen es considerablemente más grande), usa:

```bash
docker compose --profile observability up --build
```

| Servicio | URL local |
| --- | --- |
| `identity_service` | `http://localhost:8000` |
| `bff_web` | `http://localhost:8001` |
| `bff_mobile` | `http://localhost:8002` (desde el emulador Android: `http://10.0.2.2:8002`) |
| `mock_kyc` | `http://localhost:8202` |
| `liveness_adapter` | `http://localhost:8203` |

### BFF Mobile

`POST /api/v1/bff-mobile/auth/login` con `{"correo", "password"}` devuelve
`access_token`, `refresh_token`, `expires_in`, `token_type` y el `correo` del cliente.
Credenciales inválidas → `401`; MS Identidad caído → `503`.

### Demostración local de activación sin JWT

Solo para desarrollo local, se puede habilitar el inicio de activación sin JWT.
No habilites esta opción en QA o producción: la ruta rechaza la solicitud fuera de
`dev`, `development` o `local` incluso si el flag está activo.

En PowerShell, antes de levantar Compose:

```powershell
$env:COGNITO_ENABLED = "false"
$env:ALLOW_DEMO_ACTIVATION_WITHOUT_JWT = "true"
$env:POSTGRES_DB = "identity_db"
docker compose up --build -d
```

Comprueba que los contenedores estén listos:

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8000/api/v1/identity-service/health
```

Para crear un reto de prueba de vida, primero registra un cliente y luego llama
al BFF móvil. La respuesta entrega `sesion_id`, `captura.challenge.gesture` y
`captura.challenge.nonce`; esos valores sirven para enviar los tres frames JPEG
al adaptador. La sesión se vence a los dos minutos y un reto nuevo invalida el
anterior.

```powershell
$cliente = @{
  nombres = "Ana"; apellidos = "Perez"; tipo_documento = "CC"
  numero_identificacion = "1020304050"; correo = "ana.demo@example.com"
  password = "Secreta123"; consentimiento_datos = $true
  fecha_nacimiento = "1990-01-01"; pais_residencia = "Colombia"; telefono = "+573001234567"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/identity-service/clientes/registro -ContentType "application/json" -Body $cliente

$reto = @{
  correo = "ana.demo@example.com"; installation_id = "11111111-1111-4111-8111-111111111111"
  plataforma = "ANDROID"; modelo = "Demo device"; version_so = "15"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8002/api/v1/bff-mobile/activacion/sesiones -ContentType "application/json" -Body $reto
```

La app móvil aún no tiene el cliente ni la pantalla de captura de la prueba de
vida. Por ahora el flujo puede demostrarse contra este endpoint; la app podrá
lanzarse para autenticación, pero no iniciará ni enviará la captura hasta que
se implemente ese bloque Android.

## Cognito en local vs. EKS

- **Docker (compose):** el contenedor usa `NoopIdentityProvider` (`COGNITO_ENABLED=false`),
  porque no tiene credenciales AWS. El registro funciona contra la BD local sin depender de AWS.
- **Local uvicorn (fuera de Docker):** para probar Cognito real, crea un `.env` (gitignored)
  con `COGNITO_ENABLED=true`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID` y `AWS_REGION`, y
  corre el servicio con tus credenciales AWS del host (`aws sso login` / access keys válidas).
- **EKS:** la autenticación es automática con **Pod Identity** (no se pasan credenciales al pod).
