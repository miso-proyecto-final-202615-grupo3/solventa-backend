# HU3.1.1 · Arquitectura visual (backend)

Complementa [HU3.1.1-plan-tecnico.md](HU3.1.1-plan-tecnico.md). Mismo estilo y nombres que `../experimentos/docs/visual-architecture.md` (experimento HA12). La línea continua es lo que se construye primero (`propio`); lo punteado es Didit (demostración, desactivado por defecto, D9).

## 1. Componentes

```mermaid
flowchart LR
    App["App Android\nKotlin / Compose"] -->|"HTTPS + Bearer\nX-Correlation-Id"| GW["API Gateway / ALB"]
    GW --> B

    subgraph BFF[bff_mobile]
        B["Routers\n/auth/login\n/activacion/sesiones"] --> JWT["CognitoJwtValidator"]
        B --> IG["IdentityServiceGateway"]
    end
    JWT -. "JWKS" .-> COG["AWS Cognito"]

    IG -->|"HTTP interno"| I

    subgraph Identity[identity_service]
        I["Router activacion-movil"] --> UC["IniciarActivacionMovilUseCase\nVerificarActivacionMovilUseCase"]
        UC --> POL["PoliticaIntentos"]
        UC --> CONS["ConsentimientoBiometricoPort\n(permisivo hasta HU3.1.3)"]
        UC --> REPO["Repos: sesiones, intentos,\ndispositivos (UnidadDeTrabajo)"]
        UC --> LVP["LivenessVerificationPort"]
        LVP --> HC["HttpLivenessAdapterClient"]
    end
    REPO --> PG[("PostgreSQL\nesquema identity")]

    HC -->|"POST /liveness/sessions\nPOST /liveness/verifications"| A

    subgraph Adapter[liveness_adapter]
        A["API FastAPI"] --> SUC["StartLivenessSession\nVerifyLiveness\nCancelLivenessSession"]
        SUC --> CFG["ActiveProviderConfiguration\n(Redis)"]
        SUC --> FAC["LivenessProviderFactory"]
        SUC --> SS["LivenessSessionStore\n(Redis + TTL)"]
        FAC --> LP["LivenessProvider\n(Strategy)"]
        LP --> PP["PropioProvider\nMediaPipe"]
        DP["DiditProvider\n(demo)"] -. "implementa" .-> LP
        ADM["/admin/liveness-provider\nGET / PUT"] --> CH["ChangeActiveProvider"]
        CH --> CFG
    end
    CFG --> RD[("Redis")]
    SS --> RD

    DP -. "x-api-key\n/v3/session/" .-> MK["mock_kyc\n(imita Didit)"]
    DP -. "sandbox / demo" .-> DID["Didit API"]

    OP["Operador\nkubectl port-forward"] -->|"X-Admin-Token"| ADM
```

**Lectura:** la dependencia de Identity termina en `LivenessVerificationPort`. Solo `liveness_adapter` conoce `PropioProvider`, `DiditProvider`, MediaPipe y la API de Didit. El proveedor activo se cambia por `/admin/liveness-provider` sin redesplegar.

## 2. Despliegue (dev / prod en AWS us-east-1)

```mermaid
flowchart TB
    Phone["Teléfono\nApp Android"] -->|"HTTPS"| APIGW["API Gateway / ALB compartido"]
    subgraph EKS["EKS · namespace de la aplicación"]
        ING["Ingress"] --> BFFM["bff-mobile\nClusterIP"]
        BFFM --> IDS["identity-service\nClusterIP"]
        IDS --> LAD["liveness-adapter\nClusterIP · sin ingress"]
        LAD --> MKY["mock-kyc\nClusterIP"]
    end
    APIGW --> ING
    IDS --> RDS[("RDS PostgreSQL")]
    LAD --> RED[("ElastiCache Redis")]
    IDS --> RED
    BFFM -. "JWKS" .-> COGN["Cognito"]
    LAD -. "solo si DIDIT_ENABLED" .-> DIDIT["Didit (internet)"]
    Admin["Operador"] -. "port-forward + X-Admin-Token" .-> LAD
```

| Servicio | Puerto local (compose) | Expuesto fuera del clúster |
|---|---:|---|
| identity_service | 8000 | No (solo vía BFF) |
| bff_web | 8001 | Sí |
| bff_mobile | 8002 | Sí |
| mock_kyc | 8202 | No |
| **liveness_adapter** | **8203** | **No** |

## 3. Clases y puertos

```mermaid
classDiagram
    direction LR

    class IniciarActivacionMovilUseCase {
      +ejecutar(correo, dispositivo, correlation_id)
    }
    class VerificarActivacionMovilUseCase {
      +ejecutar(correo, sesion_id, metadata, frames, correlation_id)
    }
    class PoliticaIntentos {
      +max_intentos = 3
      +ventana = 24h
      +intentos_restantes(consumidos) int
      +bloqueado(consumidos) bool
    }
    class LivenessVerificationPort {
      <<interface>>
      +start_session(customer_id, correlation_id)
      +cancel_session(session_id, correlation_id)
      +verify(session_id, customer_id, correlation_id, metadata, frames)
    }
    class HttpLivenessAdapterClient
    class ConsentimientoBiometricoPort {
      <<interface>>
      +otorgado(cliente_id) bool
    }

    IniciarActivacionMovilUseCase --> LivenessVerificationPort
    VerificarActivacionMovilUseCase --> LivenessVerificationPort
    VerificarActivacionMovilUseCase --> PoliticaIntentos
    IniciarActivacionMovilUseCase --> ConsentimientoBiometricoPort
    LivenessVerificationPort <|.. HttpLivenessAdapterClient

    class StartLivenessSession {
      +execute(StartSessionCommand) SessionStarted
    }
    class VerifyLiveness {
      +execute(VerificationCommand) VerificationResult
    }
    class CancelLivenessSession
    class ChangeActiveProvider {
      +execute(provider_name)
    }
    class LivenessProvider {
      <<interface>>
      +name
      +capture_type
      +start_session(command, session_id) SessionStarted
      +verify(session, command) VerificationResult
    }
    class PropioProvider
    class DiditProvider {
      <<demo>>
    }
    class LivenessProviderFactory {
      +registered() tuple
      +get(name) LivenessProvider
    }
    class ActiveProviderConfiguration {
      <<interface>>
      +get_active_provider() str
      +set_active_provider(name)
    }
    class RedisActiveProviderConfiguration
    class InMemoryActiveProviderConfiguration
    class LivenessSessionStore {
      <<interface>>
      +save(session)
      +get(session_id)
      +transition(session_id, expected, new) bool
    }
    class FaceAnalyzer {
      <<interface>>
      +analyze(image) FaceSignals
    }
    class MediaPipeFaceAnalyzer

    StartLivenessSession --> ActiveProviderConfiguration
    StartLivenessSession --> LivenessProviderFactory
    StartLivenessSession --> LivenessSessionStore
    VerifyLiveness --> LivenessProviderFactory
    VerifyLiveness --> LivenessSessionStore
    CancelLivenessSession --> LivenessSessionStore
    ChangeActiveProvider --> LivenessProviderFactory
    ChangeActiveProvider --> ActiveProviderConfiguration
    LivenessProviderFactory --> LivenessProvider
    LivenessProvider <|.. PropioProvider
    LivenessProvider <|.. DiditProvider
    ActiveProviderConfiguration <|.. RedisActiveProviderConfiguration
    ActiveProviderConfiguration <|.. InMemoryActiveProviderConfiguration
    PropioProvider --> FaceAnalyzer
    FaceAnalyzer <|.. MediaPipeFaceAnalyzer
```

**Punto de extensión (HA12):** un proveedor nuevo implementa `LivenessProvider` y se registra en `LivenessProviderFactory`. No cambian los casos de uso, Identity, el BFF ni la app.

## 4. Secuencia: activación con captura `FRAMES` aprobada

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant B as BFF Móvil
    participant I as Identity
    participant A as liveness_adapter
    participant C as ActiveProviderConfiguration
    participant P as PropioProvider

    App->>B: POST /activacion/sesiones (Bearer, X-Correlation-Id)
    B->>B: valida JWT → correo
    B->>I: POST /clientes/activacion-movil/sesiones
    I->>I: cliente, consentimiento, bloquea cliente, anula EN_CURSO vencidos, cuenta intentos
    I->>A: POST /liveness/sessions/{anterior}/cancel (si había una CREADA)
    I->>A: POST /liveness/sessions
    A->>C: get_active_provider()
    C-->>A: propio
    A->>P: start_session()
    P-->>A: gesto + nonce
    A-->>I: session_id, capture FRAMES, challenge
    I-->>B: sesión CREADA
    B-->>App: 201 captura FRAMES {gesto, nonce}

    App->>App: guía ML Kit, captura inicio / gesto / fin en memoria
    App->>B: POST /activacion/sesiones/{id}/verificacion (3 frames + nonce)
    B->>I: reenvía (correo del token)
    I->>I: TX1 bloquea cliente, valida sesión, intento EN_CURSO
    I->>A: POST /liveness/verifications
    A->>A: sesión CREATED → VERIFYING, valida nonce
    A->>P: verify(session, frames)
    P-->>A: approved
    A-->>I: verification_id propio-…, status approved
    I->>I: TX2 intento APROBADO, revoca vínculos previos, vincula
    I-->>B: APROBADO, dispositivo_vinculado
    B-->>App: 200 APROBADO
    App->>App: borra frames, sesión vinculada → oferta biométrica (HU3.1.2)
```

## 5. Secuencia: rechazo, falla técnica y bloqueo

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant I as Identity (vía BFF)
    participant A as liveness_adapter

    App->>I: verificación (intento 1)
    I->>A: POST /liveness/verifications
    A-->>I: status rejected, reason GESTO_NO_DETECTADO
    I-->>App: RECHAZADO, intentos_restantes 2
    App->>I: POST /activacion/sesiones (sesión nueva, otro gesto)
    App->>I: verificación (intento 2)
    I->>A: POST /liveness/verifications
    A-->>I: 502 proveedor no disponible
    I->>I: intento ANULADO, sesión CANCELADA (no consume)
    I-->>App: 503, intentos_restantes 2
    App->>I: POST /activacion/sesiones (sesión nueva)
    Note over App,I: intentos 2 y 3 rechazados
    App->>I: POST /activacion/sesiones
    I-->>App: 429 INTENTOS_AGOTADOS (hasta salir de la ventana de 24 h)
```

## 6. Secuencia: cambio dinámico de proveedor (evidencia del criterio de terminado)

```mermaid
sequenceDiagram
    autonumber
    participant Op as Operador
    participant A as liveness_adapter
    participant F as LivenessProviderFactory
    participant R as Redis
    participant App
    participant I as Identity

    Op->>A: GET /admin/liveness-provider
    A-->>Op: propio
    Op->>A: PUT /admin/liveness-provider {didit} + X-Admin-Token
    A->>F: registered() contiene didit
    A->>R: SET liveness:active_provider didit
    A-->>Op: 200 didit
    App->>I: POST /activacion/sesiones (mismo contrato)
    I->>A: POST /liveness/sessions (mismo contrato)
    A-->>I: capture SDK DIDIT
    Note over App,I: Identity, BFF y app sin cambios ni redespliegue
    Op->>A: PUT /admin/liveness-provider {propio}
```

## 7. Secuencia: captura `SDK` con Didit (demostración)

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant I as Identity (vía BFF)
    participant A as liveness_adapter
    participant D as DiditProvider
    participant DA as Didit API o mock_kyc

    App->>I: POST /activacion/sesiones
    I->>A: POST /liveness/sessions
    A->>D: start_session()
    D->>D: ProviderBudget (5/día, 100/mes)
    alt tope superado o Redis caído
        D-->>A: ProviderQuotaExceededError
        A->>A: usa propio
    else dentro del tope
        D->>DA: POST /v3/session/ (x-api-key, workflow solo pasivo)
        DA-->>D: session_id, session_token
    end
    A-->>I: capture SDK DIDIT, session_token
    I-->>App: captura SDK
    App->>App: lanzador Didit (simulado o SDK real)
    App->>I: verificación {resultado_sdk COMPLETED}
    I->>A: POST /liveness/verifications
    A->>D: verify()
    D->>DA: GET /v3/session/{id}/decision/
    DA-->>D: Approved
    D-->>A: approved
    A-->>I: status approved
```

## 8. Estados

```mermaid
stateDiagram-v2
    direction LR
    state "Sesión de activación (Identity)" as S {
        [*] --> CREADA
        CREADA --> EN_VERIFICACION: verificación recibida
        CREADA --> CANCELADA: otra sesión para la instalación / vencida
        EN_VERIFICACION --> USADA: aprobado o rechazado
        EN_VERIFICACION --> CANCELADA: FRAMES con proveedor caído
        EN_VERIFICACION --> CREADA: SDK con proveedor caído
        USADA --> [*]
        CANCELADA --> [*]
    }
```

```mermaid
stateDiagram-v2
    direction LR
    [*] --> EN_CURSO: TX1
    EN_CURSO --> APROBADO: approved
    EN_CURSO --> RECHAZADO: rejected
    EN_CURSO --> ANULADO: proveedor o adaptador caído
    EN_CURSO --> ANULADO: sesión vencida (D12, antes de contar)
    APROBADO --> [*]
    RECHAZADO --> [*]
    ANULADO --> [*]
    note right of EN_CURSO : Cuentan para el límite RECHAZADO y EN_CURSO
```

## 9. Modelo de datos (esquema `identity`)

```mermaid
erDiagram
    CLIENTES ||--o{ SESIONES_ACTIVACION : inicia
    CLIENTES ||--o{ INTENTOS_PRUEBA_VIDA : registra
    CLIENTES ||--o{ DISPOSITIVOS_VINCULADOS : vincula
    SESIONES_ACTIVACION ||--o{ INTENTOS_PRUEBA_VIDA : origina

    CLIENTES {
        uuid id PK
        string correo UK
        string estado_kyc "no lo modifica HU3.1.1"
    }
    SESIONES_ACTIVACION {
        string id PK "session_id del adaptador"
        uuid cliente_id FK
        uuid installation_id
        string tipo_captura "FRAMES o SDK"
        string estado
        timestamptz creada_en
        timestamptz expira_en
    }
    INTENTOS_PRUEBA_VIDA {
        uuid id PK
        uuid cliente_id FK
        string sesion_id FK
        uuid installation_id
        string estado "EN_CURSO APROBADO RECHAZADO ANULADO"
        string folio
        string motivo
        timestamptz creado_en
        timestamptz resuelto_en
    }
    DISPOSITIVOS_VINCULADOS {
        uuid id PK
        uuid cliente_id FK "único si ACTIVO"
        uuid installation_id "único si ACTIVO"
        string plataforma
        string modelo
        string version_so
        string folio_verificacion
        string estado "ACTIVO REVOCADO"
        timestamptz vinculado_en
        timestamptz revocado_en
    }
```

El adaptador no tiene tablas: su estado técnico vive en Redis (`liveness:active_provider`, `liveness:session:<id>` con TTL, contadores `liveness:didit:sessions:*`).
