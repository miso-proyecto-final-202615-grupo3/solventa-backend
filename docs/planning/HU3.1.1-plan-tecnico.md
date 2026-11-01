# HU3.1.1 · Activación móvil con selfie y prueba de vida · Plan técnico (backend)

- Historia: [#87](https://github.com/dzamoranouniandes/misw4501-grupo3-solventa-backend/issues/87) · Sprint 2 (19/10/2026 – 01/11/2026)
- Rama: `feat/HU3.1.1-activacion-selfie-prueba-vida` (sale de `dev`)
- Servicios: **`liveness_adapter` (nuevo)**, `identity_service`, `bff_mobile`, `mock_kyc` (+ `docker-compose.yml`, `deployment/helm`, workflows)
- Diagramas (componentes, despliegue, clases, secuencias, estados, modelo de datos): [HU3.1.1-diagramas.md](HU3.1.1-diagramas.md).
- App: `solventa-mobileapp/docs/planning/HU3.1.1-plan-tecnico.md` (misma rama). **El contrato de la sección 3 es el mismo en ambos documentos; si cambia, se cambia en los dos.**
- **Referencia obligatoria:** el experimento HA12 en `../experimentos` (README, `docs/architecture.md`, `docs/visual-architecture.md`, `docs/experiment-results.md`, código de `liveness-adapter` e `identity-service`). Este plan **lleva ese diseño a producción**; no lo reemplaza. También la wiki *Tácticas y Patrones – FM2* (MOD-2) y HA12 (#94).

> Insumo para el agente que implementa. Describe **qué** construir y **cómo** encaja con el código existente.

---

## 0. Alcance y decisiones de base

**Para qué es la prueba de vida** (revisado contra backlog y wiki, 2026-10-24):
- Es la **activación del acceso móvil**: se hace una vez por instalación, para verificar al titular de la cuenta creada en la web y vincular el teléfono (E3 → F3.1 → HU3.1.1). Los accesos siguientes usan la biometría nativa (HU3.1.2).
- **No** es el KYC/AML para adquirir un producto (flujo web de HU1.3.3 #63, Sprint 3, dueño de `clientes.estado_kyc`). **Esta historia no modifica `estado_kyc`.**

**Diseño del experimento HA12 que se respeta tal cual:**

| Elemento del experimento | Cómo queda aquí |
|---|---|
| Microservicio adaptador `liveness-adapter`, el único que conoce a los proveedores | Nuevo servicio **`liveness_adapter`** en el monorepo. Identity **nunca** conoce Didit ni MediaPipe. |
| Identity consume solo el adaptador por HTTP: puerto `LivenessVerificationPort` + `HttpLivenessAdapterClient` | Igual, en `identity_service`. |
| Puerto `LivenessProvider` con una implementación por proveedor (**Strategy**) | `PropioProvider` (real, activo por defecto) y `DiditProvider` (demostración, desactivado por defecto). |
| Diccionario de proveedores registrados | Formalizado como **Factory**: `LivenessProviderFactory` crea y registra las estrategias a partir de la configuración. |
| `ActiveProviderConfiguration` + `InMemoryActiveProviderConfiguration` | Mismo puerto; implementación **persistente en Redis** (el experimento advierte que la versión en memoria es solo experimental). |
| Casos de uso `VerifyLiveness` y `ChangeActiveProvider` | Iguales, más `StartLivenessSession` (ver abajo). |
| **Activación por endpoint:** `GET` / `PUT /admin/liveness-provider` | Iguales. `PUT` con un proveedor no registrado → `422`. |
| Contrato normalizado `{verification_id, status: approved\|rejected, correlation_id}`; el proveedor **no se expone** al consumidor | Igual. El proveedor solo aparece en logs (`liveness_provider=<nombre> correlation_id=<id>`). |
| `X-Correlation-Id` propagado y registrado en todos los servicios | Igual: app → BFF → Identity → adaptador → proveedor. |

**Extensión necesaria (limitación que el propio experimento dejó escrita):** el experimento validó solo liveness pasivo con `evidence_ref`, y concluyó que si el proveedor exige movimientos o SDK propio "se requiere … un flujo genérico de sesión". Aquí se agrega ese flujo:
- `POST /liveness/sessions` (`StartLivenessSession`) crea el reto con el proveedor activo.
- `POST /liveness/verifications` (`VerifyLiveness`) recibe la evidencia de esa sesión.
- La sesión **queda fijada al proveedor con el que se creó**, aunque el activo cambie con `PUT /admin/liveness-provider` mientras la persona captura.
- Lo único que la app necesita saber es **cómo capturar** (`capture.type = FRAMES | SDK`), no qué proveedor decide.

**Proveedores:**
- **`propio`, activo por defecto y el primero que se construye.** La app captura con su cámara 3 frames con un reto (gesto + nonce) emitido por el servidor, y el adaptador verifica el gesto con MediaPipe Face Landmarker.
  - Límite: valida el gesto y una consistencia básica del rostro. **No** es una detección de ataques de presentación certificada (ISO 30107-3) ni evita por completo una secuencia grabada previamente.
  - **Riesgo aceptado** para el alcance académico (decisión D8). Didit queda como la alternativa para un uso real.
- **`didit`, integración real solo para demostración, desactivada por defecto** (`DIDIT_ENABLED=false`). Didit es el proveedor de la wiki (MOD-2). **Costo objetivo: cero.**
  - Desarrollo y pruebas: aplicación **sandbox** de Didit (no factura y permite forzar el resultado), o `mock_kyc` sin internet.
  - Demo: workflow **solo con *passive liveness*** (dentro de las 500 gratis al mes). **Prohibido** activar *active liveness* (USD 0,15), *Face Match*, *ID verification*, *custom branding* u otra función de pago.
  - **No usar** la API directa `POST /v3/passive-liveness/`, que cobra desde la primera llamada (USD 0,05).
  - Topes en Redis: `DIDIT_MAX_SESIONES_DIA=5` y `DIDIT_MAX_SESIONES_MES=100`; al superarlos, la sesión se crea con `propio`.
  - Cuenta en plan gratuito **sin tarjeta**: si se acaba la cuota, Didit rechaza la solicitud en vez de cobrar, y se vuelve a `propio`.
- **Didit se implementa en esta historia (decisión D9),** en el backend (T-B13, T-B14) y en la app (T-M13).
  - **Orden:** primero el patrón (adaptador, Strategy, Factory, proveedor activo por endpoint) y la validación propia de punta a punta (T-B01–T-B12, T-M01–T-M12). Después Didit.
  - Responsable: Sergio Gelvez.
  - Estimación: T-B13 3 h, T-B14 5 h, T-M13 6 h.
  - Didit se configura con costo cero (sandbox y passive liveness gratuito, topes, sin tarjeta) y queda desactivado por defecto (`DIDIT_ENABLED=false`), con `propio` como proveedor activo.

---

## 1. Estado actual

| Pieza | Hoy en `dev` | Falta |
|---|---|---|
| `liveness_adapter` | No existe en el monorepo (solo en `../experimentos`) | Crear el servicio (sección 4) |
| `mock_kyc` | `POST /verify` por documento | Imitar la API de sesiones de Didit (sección 7) |
| `identity_service` | `KycVerifier`, `VerificarKycUseCase` (documento) | Puerto y cliente HTTP del adaptador, sesiones/intentos/dispositivos, casos de uso, endpoints internos, `obtener_por_correo` |
| `bff_mobile` | `POST /auth/login` sin datos del cliente, sin validar JWT | Validar el JWT de Cognito, endpoints de activación, `cliente` en el login |
| Consentimiento biométrico | No existe (HU3.1.3, asr88) | Puerto + flag en Identity (5.5) |

---

## 2. Responsabilidades y flujo

| Servicio | Es dueño de | No sabe |
|---|---|---|
| `bff_mobile` | Validar el token, validar tamaño y formato de lo que llega de la app, traducir errores al formato común | Nada de proveedores ni de reglas de intentos |
| `identity_service` | Cliente, consentimiento, **regla de 3 intentos**, sesiones del cliente (propiedad y antirreplay), **vínculo del dispositivo**, auditoría | Qué proveedor se usa ni cómo decide |
| `liveness_adapter` | Proveedores (Strategy + Factory), proveedor activo, reto y nonce, estado técnico de la sesión con el proveedor, normalizar el resultado | Clientes, intentos, dispositivos |
| `mock_kyc` | Imitar la API de Didit para pruebas | — |

```
1) App ─ POST /activacion/sesiones ─► BFF ─► Identity ─┬─ cliente · consentimiento · intentos
                                                        └─ HttpLivenessAdapterClient ─► adapter POST /liveness/sessions
                                                              StartLivenessSession: proveedor activo (Redis) → Factory → Strategy
                                                                propio: gesto al azar + nonce
                                                                didit : POST /v3/session/ (sandbox o mock_kyc), con topes
   ◄──── { sesion_id, expira_en, intentos_restantes, captura: FRAMES{reto} | SDK{didit_token} }

2) App captura: FRAMES con su cámara (3 frames) · SDK con el lanzador de Didit (simulado por defecto)

3) App ─ POST /activacion/sesiones/{id}/verificacion ─► BFF ─► Identity
        TX1: bloquea cliente, valida que la sesión es suya y está vigente, reserva intento EN_CURSO
        HttpLivenessAdapterClient ─► adapter POST /liveness/verifications
              VerifyLiveness: proveedor fijado en la sesión → Strategy.verify() → {status approved|rejected, reason}
        TX2: cierra intento; si approved revoca vínculos previos y vincula
   ◄──── { resultado, folio, intento, intentos_restantes, dispositivo_vinculado, vinculado_en, motivo }

Admin ─ GET/PUT /admin/liveness-provider ─► adapter (ChangeActiveProvider), sin redesplegar nada
```

Reglas transversales:
- **Los frames no se persisten ni se registran en logs ni en trazas** en ningún servicio; viajan en memoria y se descartan.
- El reto lo emite el servidor (adaptador); la app no elige el gesto.
- Si el proveedor no está disponible: el adaptador responde `502` (como en el experimento), Identity marca el intento `ANULADO` (**no consume intento**) y el BFF responde `503`.
- Si el adaptador está caído: Identity → `503` sin consumir intento.

---

## 3. Contrato público (BFF Móvil)

> **Contrato canónico (decisión D10).** Esta sección es la fuente única. La sección 4 del plan móvil es su copia de consumo. Cualquier cambio exige actualizar los dos documentos **y** las pruebas de contrato en la misma rama:
> - Backend: ejemplos JSON en `docs/contracts/activacion/*.json`, validados contra los schemas de `bff_mobile` en `bff_mobile/tests/contract/test_activacion_contract.py`.
> - App: las mismas muestras copiadas en `app/src/test/resources/contracts/activacion/`, parseadas en `RemoteActivationRepositoryTest`.

Formato de error común para los endpoints nuevos (no cambiar el de `/auth/login`):
```json
{ "codigo": "INTENTOS_AGOTADOS", "mensaje": "Superaste los intentos permitidos.", "correlation_id": "4b1d…" }
```
La app puede enviar `X-Correlation-Id`; si no, el BFF lo genera. Se devuelve en el header de la respuesta y en los errores.

### 3.1 `POST /api/v1/bff-mobile/activacion/sesiones`

Bearer. Body JSON:
```json
{ "installation_id": "6f1c2a0e-5d1b-4c39-9a57-1f0f3b8d2e11", "plataforma": "ANDROID", "modelo": "samsung SM-A546E", "version_so": "14" }
```
`201`:
```json
{
  "sesion_id": "0b7e…",
  "expira_en": "2026-10-24T15:06:05Z",
  "intentos_restantes": 3,
  "captura": { "tipo": "FRAMES", "reto": { "gesto": "BLINK", "nonce": "q8Zt…" } }
}
```
Con el SDK: `"captura": { "tipo": "SDK", "sdk": { "nombre": "DIDIT", "session_token": "…" } }`.
- `gesto` ∈ {`BLINK`, `TURN_LEFT`, `TURN_RIGHT`}. Vigencia: 2 min.
- **Cada llamada crea una sesión nueva.** Si la instalación tenía una sesión `CREADA`, esa sesión se **invalida** (`CANCELADA` en Identity y en el adaptador) y no se puede usar después. Una sesión `FRAMES` nunca se reutiliza ni se reenvía su reto (decisión D11).
- El `nonce` se devuelve en claro **solo en esta respuesta**. El servidor guarda solo su hash, nunca lo recupera y nunca lo registra.
- Si la instalación ya está vinculada y activa para ese cliente: `200 { "dispositivo_vinculado": true }`, sin captura.

Errores: `401` · `403 CONSENTIMIENTO_BIOMETRICO_REQUERIDO` · `404 CLIENTE_NO_REGISTRADO` · `422 DATOS_INVALIDOS` · `429 INTENTOS_AGOTADOS` · `503 SERVICIO_NO_DISPONIBLE`.

### 3.2 `POST /api/v1/bff-mobile/activacion/sesiones/{sesion_id}/verificacion`

Bearer. `multipart/form-data`:

| Parte | `FRAMES` | `SDK` |
|---|---|---|
| `metadata` (string JSON) | `{ "nonce": "q8Zt…", "capturas": { "inicio": "…Z", "gesto": "…Z", "fin": "…Z" } }` | `{ "resultado_sdk": "COMPLETED" }` (`COMPLETED` \| `CANCELLED` \| `FAILED`) |
| `frame_inicio`, `frame_gesto`, `frame_fin` | JPEG (el de `fin` es la "selfie" del criterio) | — |

Límites: cada frame ≤ 512 KB, total ≤ 2 MB, lado mayor ≤ 1280 px.

`200`:
```json
{ "resultado": "APROBADO", "folio": "a3e9…", "intento": 1, "intentos_restantes": 2, "dispositivo_vinculado": true, "vinculado_en": "2026-10-24T15:04:06Z", "motivo": null }
```
Con `RECHAZADO`: `dispositivo_vinculado = false`, `vinculado_en = null`, `motivo` ∈ {`GESTO_NO_DETECTADO`, `ROSTRO_NO_DETECTADO`, `VARIOS_ROSTROS`, `ROSTRO_INCONSISTENTE`, `CAPTURA_INVALIDA`, `PRUEBA_VIDA_FALLIDA`}.

Errores: `401` · `404 SESION_NO_ENCONTRADA` · `409 SESION_INVALIDA` (expirada, usada o nonce distinto) · `409 SESION_CANCELADA` · `413 CAPTURA_DEMASIADO_GRANDE` · `415 FORMATO_NO_SOPORTADO` · `422 DATOS_INVALIDOS` · `429 INTENTOS_AGOTADOS` · `503 SERVICIO_NO_DISPONIBLE` (no consume intento).

### 3.3 Cambio en `POST /api/v1/bff-mobile/auth/login`

- Request agrega `installation_id: UUID | None = None` (sigue `extra="forbid"`).
- Response agrega `cliente` opcional:
  ```json
  "cliente": { "id": "uuid", "nombre": "Ana", "estado_kyc": "VALIDADO", "dispositivo_vinculado": true }
  ```
- El BFF llama `GET /clientes/resumen-movil` después de autenticar. Si falla, responde **sin** `cliente`.
- La app trata la ausencia como **no vinculado** y va a activación. Ahí `POST /activacion/sesiones` reconoce la instalación ya vinculada (3.1) y no repite la prueba. Una falla no permite saltarse la activación.

---

## 4. `liveness_adapter` (servicio nuevo)

Estructura igual a los demás servicios del monorepo (`src/core`, `src/domain`, `src/application`, `src/infrastructure`, `src/presentation`, `tests/unit`, `tests/integration`, `pytest.ini`, `requirements*.txt`). Puerto local 8203 en compose. `API_PREFIX = /api/v1/liveness-adapter`. Código base: el del experimento (`../experimentos/liveness-adapter`), adaptado al estilo del monorepo (async, `pydantic-settings`, telemetría de `src/core/telemetry.py` como en `bff_mobile`).

### 4.1 Dominio — `src/domain/models.py`

```python
class LivenessStatus(StrEnum): APPROVED = "approved"; REJECTED = "rejected"
class CaptureType(StrEnum): FRAMES = "FRAMES"; SDK = "SDK"
class Gesture(StrEnum): BLINK = "BLINK"; TURN_LEFT = "TURN_LEFT"; TURN_RIGHT = "TURN_RIGHT"
class SessionState(StrEnum): CREATED = "CREATED"; VERIFYING = "VERIFYING"; USED = "USED"; CANCELLED = "CANCELLED"

@dataclass(frozen=True)
class StartSessionCommand:
    customer_id: str
    correlation_id: str

@dataclass(frozen=True)
class LivenessSession:                 # estado técnico, guardado en Redis con TTL
    session_id: str
    customer_id: str
    provider: str                      # proveedor fijado al crear la sesión
    capture_type: CaptureType
    gesture: Gesture | None
    nonce_hash: str | None             # sha256; el nonce en claro se devuelve una vez y nunca se guarda, recupera ni registra
    provider_session_id: str | None
    state: SessionState
    expires_at: datetime

@dataclass(frozen=True)
class SessionStarted:
    session: LivenessSession
    nonce: str | None = None
    sdk_name: str | None = None
    sdk_session_token: str | None = None

@dataclass(frozen=True)
class Frame:
    label: str                          # "inicio" | "gesto" | "fin"
    content: bytes
    content_type: str
    captured_at: datetime

@dataclass(frozen=True)
class VerificationCommand:              # mismo nombre que en el experimento, con evidencia real en vez de evidence_ref
    session_id: str
    customer_id: str
    correlation_id: str
    nonce: str | None = None
    frames: tuple[Frame, ...] = ()
    sdk_result: str | None = None

@dataclass(frozen=True)
class VerificationResult:               # igual que en el experimento + reason
    verification_id: str
    status: LivenessStatus
    correlation_id: str
    reason: str | None = None
```

### 4.2 Puertos — `src/application/ports.py` (Strategy)

```python
class LivenessProvider(Protocol):
    """Estrategia: una implementación por proveedor externo (igual que en el experimento)."""
    name: str
    capture_type: CaptureType
    async def start_session(self, command: StartSessionCommand, session_id: str) -> SessionStarted: ...
    async def verify(self, session: LivenessSession, command: VerificationCommand) -> VerificationResult: ...

class ActiveProviderConfiguration(Protocol):          # igual que en el experimento
    async def get_active_provider(self) -> str: ...
    async def set_active_provider(self, provider_name: str) -> None: ...

class LivenessSessionStore(Protocol):
    async def save(self, session: LivenessSession) -> None: ...
    async def get(self, session_id: str) -> LivenessSession | None: ...
    async def transition(self, session_id: str, expected: SessionState, new: SessionState) -> bool: ...  # atómico

class ProviderUnavailableError(Exception): ...        # → 502 (como el experimento)
class ProviderQuotaExceededError(Exception): ...      # solo didit: tope gratuito alcanzado
```

### 4.3 Factory — `src/infrastructure/provider_factory.py`

```python
class LivenessProviderFactory:
    """Crea las estrategias a partir de la configuración y conoce cuáles están registradas."""
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient, redis: Redis) -> None
    def registered(self) -> tuple[str, ...]          # ("propio",) o ("propio", "didit") si DIDIT_ENABLED
    def get(self, name: str) -> LivenessProvider      # ProviderNotRegisteredError si no está
```
- Las instancias se crean una vez al arrancar (`lifespan`) y se reusan. `didit` **solo** se registra con `DIDIT_ENABLED=true`.
- Agregar un proveedor = una clase que cumple `LivenessProvider` + una entrada en la fábrica. No cambian casos de uso, endpoints, Identity ni la app (criterio de HA12, igual que con `AlternativeProvider` en el experimento).

### 4.4 Configuración del proveedor activo — `src/infrastructure/configuration.py`

- `RedisActiveProviderConfiguration(ActiveProviderConfiguration)`: clave `liveness:active_provider`; valor inicial `settings.LIVENESS_PROVIDER` (default `propio`) si la clave no existe.
- Caché local de 10 s, para que el cambio por endpoint se vea en todos los pods en ≤ 10 s.
- Si Redis no responde: el último valor conocido o `LIVENESS_PROVIDER`.
- Reemplaza a `InMemoryActiveProviderConfiguration` del experimento por lo que su propio documento pide para un despliegue persistente. Se conserva `InMemoryActiveProviderConfiguration` para las pruebas.

### 4.5 Casos de uso — `src/application/use_cases.py`

```python
class StartLivenessSession:
    # proveedor activo → factory.get() → strategy.start_session()
    # si es didit y lanza ProviderQuotaExceededError → usa "propio" y registra liveness_provider_fallback=quota
    # guarda la sesión en el store con TTL = LIVENESS_SESSION_TTL_SECONDS (120)

class VerifyLiveness:
    # sesión del store; si no existe → SessionNotFoundError; si es de otro customer_id → SessionNotFoundError
    # transition(CREATED → VERIFYING); si falla → SessionInvalidError (ya usada, cancelada o expirada)
    # frames: nonce → sha256 == nonce_hash, si no → SessionInvalidError
    # sdk_result == "CANCELLED" → estado CANCELLED, SessionCancelledError
    # strategy = factory.get(session.provider)   ← proveedor FIJADO en la sesión, no el activo
    # ProviderUnavailableError → FRAMES: transition(VERIFYING → CANCELLED) (D11: el reto no se reenvía);
    #                            SDK: transition(VERIFYING → CREATED) (la decisión de Didit puede llegar después);
    #                            y se propaga (502)
    # resultado → transition(VERIFYING → USED)

class CancelLivenessSession:
    # transition(CREATED → CANCELLED); idempotente si ya estaba CANCELLED; no toca sesiones USED

class ChangeActiveProvider:                 # igual que en el experimento
class GetActiveProvider:
```
Log por operación, como el experimento: `liveness_provider=<nombre> correlation_id=<id> status=<approved|rejected> reason=<motivo>`.

`RedisLivenessSessionStore`: hash `liveness:session:<id>` con `EXPIRE`. `transition` atómico con un script Lua (o `WATCH`/`MULTI`). Para pruebas, `InMemoryLivenessSessionStore`.

### 4.6 Estrategia `propio` — `src/infrastructure/providers/propio/`

| Archivo | Responsabilidad |
|---|---|
| `propio_provider.py` | `PropioProvider` (`name="propio"`, `capture_type=FRAMES`). `start_session`: gesto con `secrets.choice`, nonce `secrets.token_urlsafe(24)`. `verify`: valida la evidencia, analiza los frames, aplica las reglas. `verification_id = "propio-<uuid4>"` (prefijo como `alternative-` en el experimento). |
| `face_analyzer.py` | Puerto `FaceAnalyzer.analyze(image: bytes) -> FaceSignals` + `MediaPipeFaceAnalyzer`. |
| `gesture_rules.py` | Funciones **puras** sobre `FaceSignals`, sin MediaPipe: fáciles de probar. |

`FaceSignals(face_count, blink_left, blink_right, yaw, pitch, face_width_ratio, interocular_ratio, width, height)`.

`MediaPipeFaceAnalyzer`:
- `mediapipe` (wheel `py3-none`, compatible con Python 3.13 de las imágenes), Tasks API `FaceLandmarker`: `output_face_blendshapes=True`, `output_facial_transformation_matrixes=True`, `num_faces=2`, modo `IMAGE`.
- Parpadeo con los blendshapes `eyeBlinkLeft` / `eyeBlinkRight`; yaw y pitch con la matriz de transformación.
- El modelo `face_landmarker.task` se descarga en `Dockerfile.liveness_adapter` a `/app/models/` (`PROPIO_MODEL_PATH`); no se versiona.
- Singleton con `threading.Lock`, **precargado al arrancar** (≈6 s con 1 CPU): `/ready` responde `503` hasta tenerlo cargado y `/health` no espera. Análisis CPU con `run_in_threadpool`; decodificar con Pillow (`ImageOps.exif_transpose`).
- MediaPipe 1.x entrega la matriz de transformación como `numpy.ndarray` 4×4: se lee con `numpy.asarray` (su `.data` es un memoryview multidimensional que no se puede recorrer).
- Error del modelo o `MemoryError` → `ProviderUnavailableError`, con log `propio_analysis_failed error=<tipo>`. Un gesto rechazado registra `propio_gesture_rejected` con ángulos y parpadeo redondeados, nunca la imagen.

Reglas (`PROPIO_*` en config):

| Regla | Rechazo (`reason`) |
|---|---|
| Exactamente 3 frames `inicio`, `gesto`, `fin` | `CAPTURA_INVALIDA` |
| Timestamps crecientes, dentro de la vigencia de la sesión, duración total entre 0,3 s y 15 s | `CAPTURA_INVALIDA` |
| Frames distintos (SHA-256 distinto y diferencia media en escala de grises 64×64 > umbral) | `CAPTURA_INVALIDA` |
| Un rostro por frame, `face_width_ratio ≥ 0,2` | `ROSTRO_NO_DETECTADO` / `VARIOS_ROSTROS` |
| Mismo rostro: `interocular_ratio` con variación < 25 % entre frames | `ROSTRO_INCONSISTENTE` |
| BLINK: `inicio` y `fin` con ambos `eyeBlink` < 0,35; `gesto` con ambos > 0,55 | `GESTO_NO_DETECTADO` |
| TURN_LEFT / TURN_RIGHT: `\|yaw\|` < 12° en `inicio` y `fin`; en `gesto` giro > 20° hacia el lado pedido. Signo calibrado en dispositivo real (Android, cámara frontal): girar a la derecha da yaw negativo (`PROPIO_RIGHT_TURN_YAW_SIGN=-1`; medido 3° / −23° / 1°) | `GESTO_NO_DETECTADO` |

### 4.7 Estrategia `didit` (demostración, desactivada por defecto) — `src/infrastructure/providers/didit_provider.py`

`DiditProvider` (`name="didit"`, `capture_type=SDK`), con httpx async contra el **contrato real** de Didit:
- `start_session`:
  1. `ProviderBudget.consume()` (Redis, `INCR liveness:didit:sessions:<AAAAMMDD>` con expiración de 48 h y `…:<AAAAMM>` con expiración de 40 días). Si supera `DIDIT_MAX_SESIONES_DIA` o `DIDIT_MAX_SESIONES_MES`, o Redis no responde → `ProviderQuotaExceededError` (falla segura: no gasta).
  2. `POST {DIDIT_BASE_URL}/v3/session/` con `x-api-key`, `{ "workflow_id", "vendor_data": customer_id, "metadata": { "session_id", "correlation_id" } }`. Lee `session_id`, `session_token`.
- `verify`: `GET /v3/session/{provider_session_id}/decision/`.
  - `Approved` → `approved`; `Declined` → `rejected` con `PRUEBA_VIDA_FALLIDA`.
  - `In Review`, `Not Started`, `In Progress` → `ProviderUnavailableError` (no consume intento).
  - `429` (respetar `Retry-After`), `400` por créditos insuficientes, `5xx` o timeout → `ProviderUnavailableError`.
  - `verification_id` = `session_id` de Didit.
- `DIDIT_BASE_URL`: `http://mock_kyc:8000` en local y pruebas; `https://verification.didit.me` para la demo (API key de la app sandbox en dev; de la app con workflow solo pasivo para presentar). Claves en Secrets Manager. Webhook fuera de alcance.

### 4.8 Presentación

| Método | Ruta | Uso |
|---|---|---|
| `POST` | `/api/v1/liveness-adapter/liveness/sessions` | JSON `{customer_id}` + header `X-Correlation-Id` → `201 {session_id, expires_at, capture: {type, challenge?: {gesture, nonce}, sdk?: {name, session_token}}}` |
| `POST` | `/api/v1/liveness-adapter/liveness/sessions/{session_id}/cancel` | `204`; invalida una sesión `CREATED` (la usa Identity al crear otra para la misma instalación) |
| `POST` | `/api/v1/liveness-adapter/liveness/verifications` | multipart: `metadata` (`{session_id, customer_id, nonce?, captured_at?, sdk_result?}`) + `frame_*` → `200 {verification_id, status, reason, correlation_id}` |
| `GET` | `/api/v1/liveness-adapter/admin/liveness-provider` | `{provider}` (igual que el experimento) |
| `PUT` | `/api/v1/liveness-adapter/admin/liveness-provider` | `{provider}`; `422` si no está registrado en la fábrica (igual que el experimento) |
| `GET` | `/api/v1/liveness-adapter/health` | liveness probe (vida del proceso, sin Redis) |
| `GET` | `/api/v1/liveness-adapter/ready` | readiness probe (modelo precargado y Redis disponible) |

Detalles:
- Errores: `404 SESSION_NOT_FOUND`, `409 SESSION_INVALID`, `409 SESSION_CANCELLED`, `413`, `415`, `422`, `502` (proveedor no disponible), `500` (proveedor activo no registrado, como el experimento).
- **Seguridad de `/admin`:** el servicio es `ClusterIP` y **no** se publica en el ingress ni en el API Gateway. Además, header `X-Admin-Token` comparado con `ADMIN_TOKEN` (secreto) usando `hmac.compare_digest`. Uso: `kubectl port-forward` o Postman en local.
- Lectura acotada de cada `UploadFile` por bloques de 64 KB, con corte al superar `MAX_FRAME_BYTES` + 1 → `413`. `content_type` `image/jpeg` **y** firma `FF D8 FF` → si no, `415`.
- `config.py`: `LIVENESS_PROVIDER="propio"`, `LIVENESS_SESSION_TTL_SECONDS=120`, `MAX_FRAME_BYTES=524_288`, `PROPIO_MODEL_PATH`, umbrales `PROPIO_*`, `DIDIT_ENABLED=False`, `DIDIT_MAX_SESIONES_DIA=5`, `DIDIT_MAX_SESIONES_MES=100`, `DIDIT_BASE_URL`, `DIDIT_API_KEY=""`, `DIDIT_WORKFLOW_ID=""`, `DIDIT_TIMEOUT_SECONDS=5.0`, `REDIS_ENDPOINT`, `REDIS_AUTH_TOKEN`, `ADMIN_TOKEN=""`.
- `requirements.txt`: `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `httpx`, `python-multipart`, `redis`, `mediapipe`, `pillow`, `numpy` y OpenTelemetry (mismas versiones mínimas que los otros servicios).
- Postman: copiar y ampliar `../experimentos/postman/HA12-liveness.postman_collection.json` en `docs/postman/` con sesiones, verificaciones y admin.

---

## 5. MS Identidad (`identity_service`)

### 5.1 Puerto hacia el adaptador (igual que el experimento)

- `src/application/ports/liveness.py`: `LivenessVerificationPort` con `start_session(customer_id, correlation_id)`, `cancel_session(session_id, correlation_id)` y `verify(session_id, customer_id, correlation_id, metadata, frames)`. Devuelve modelos normalizados propios de Identity (`LivenessSessionInfo`, `LivenessVerification`) y `LivenessAdapterUnavailableError`.
- `src/infrastructure/gateways/http_liveness_client.py`: `HttpLivenessAdapterClient` (httpx async, `LIVENESS_ADAPTER_URL`, timeout `LIVENESS_ADAPTER_TIMEOUT_SECONDS=15`, `transport` inyectable). Propaga `X-Correlation-Id`.
  - El `customer_id` que manda es el `cliente_id` (uuid). El adaptador nunca recibe el correo.
  - `502`, `5xx`, timeout o error de red → `LivenessAdapterUnavailableError`. `404`/`409` → errores de sesión.
- Identity **no** conoce `propio`, `didit`, MediaPipe ni Didit.

### 5.2 Dominio — `src/domain/activacion_movil/`

`entities.py`:
```python
class Plataforma(StrEnum): ANDROID = "ANDROID"; IOS = "IOS"
class EstadoSesion(StrEnum): CREADA = "CREADA"; EN_VERIFICACION = "EN_VERIFICACION"; USADA = "USADA"; CANCELADA = "CANCELADA"
class EstadoIntento(StrEnum): EN_CURSO = "EN_CURSO"; APROBADO = "APROBADO"; RECHAZADO = "RECHAZADO"; ANULADO = "ANULADO"
class EstadoDispositivo(StrEnum): ACTIVO = "ACTIVO"; REVOCADO = "REVOCADO"

@dataclass(frozen=True)
class DatosDispositivo:
    installation_id: uuid.UUID
    plataforma: Plataforma
    modelo: str
    version_so: str
```
Entidades `SesionActivacion` (id = `session_id` del adaptador, `cliente_id`, dispositivo, `tipo_captura`, estado, `creada_en`, `expira_en`), `IntentoPruebaVida` (id, `cliente_id`, `sesion_id`, `installation_id`, estado, folio, motivo, `creado_en`, `resuelto_en`) y `DispositivoVinculado` (id, `cliente_id`, dispositivo, `folio_verificacion`, estado, `vinculado_en`, `revocado_en`).

`politica_intentos.py` (pura): `PoliticaIntentos(max_intentos=3, ventana=timedelta(hours=24))` con `intentos_restantes(consumidos)` y `bloqueado(consumidos)`.

**Política aprobada (decisiones D2 y D3):**
- Máximo **3 intentos en 24 horas móviles**.
- Cuentan `RECHAZADO` y, de forma temporal, `EN_CURSO`. `ANULADO` y `APROBADO` no cuentan.
- **Recuperación de intentos colgados (D12):** antes de contar, todo intento `EN_CURSO` cuya sesión venció pasa a `ANULADO` (y la sesión a `CANCELADA`).
  - "Venció" = `expira_en + LIVENESS_ADAPTER_TIMEOUT_SECONDS < ahora`. El margen evita anular una verificación que todavía está en vuelo.
  - Así una caída entre TX1 y TX2 no deja bloqueado al cliente.
  - Lo hace `IntentoPruebaVidaRepository.anular_en_curso_vencidos(cliente_id, ahora)` dentro de la misma TX1 en la que se cuenta, con el cliente ya bloqueado.
- **Un vínculo activo por cliente y por instalación.** Vincular otra cuenta en el mismo teléfono revoca el vínculo anterior de ese teléfono. Vincular un teléfono nuevo revoca el vínculo anterior del cliente.

`ClienteRepository` agrega `obtener_por_correo(correo)` y `bloquear_para_actualizar(cliente_id)` (`SELECT … FOR UPDATE`; en SQLite se ignora). Actualizar los fakes de las pruebas existentes.

### 5.3 Casos de uso — `src/application/use_cases/`

**`IniciarActivacionMovilUseCase.ejecutar(correo, dispositivo, correlation_id)`**
1. Cliente por correo; si no existe → `ClienteNoRegistradoError`.
2. Instalación `ACTIVA` para ese cliente → `ya_vinculado=True`.
3. Consentimiento (5.5) → `ConsentimientoBiometricoRequeridoError`.
4. Bloquear el cliente, `anular_en_curso_vencidos` (D12) y contar los consumidos; si está bloqueado → `IntentosAgotadosError`.
5. Si hay una `SesionActivacion` `CREADA` para la instalación: marcarla `CANCELADA` y llamar a `liveness_port.cancel_session(...)`. Si el adaptador no responde, se registra un warning y se sigue: la fila de Identity ya está `CANCELADA` y rechaza cualquier verificación posterior. **Nunca se reutiliza** (D11).
6. `liveness_port.start_session(...)`; guardar la nueva `SesionActivacion` `CREADA`.

**`VerificarActivacionMovilUseCase.ejecutar(correo, sesion_id, metadata, frames, correlation_id)`**
- *TX1 (corta):*
  1. Cliente + `bloquear_para_actualizar`.
  2. Sesión del cliente, `CREADA` y vigente; si no → `SesionNoEncontradaError` / `SesionInvalidaError`.
  3. `anular_en_curso_vencidos` (D12) y contar los consumidos; si está bloqueado → `IntentosAgotadosError`.
  4. Intento `EN_CURSO`; sesión `EN_VERIFICACION`; commit.
- *Adaptador (fuera de la transacción):* `liveness_port.verify(...)`.
  - No disponible → intento `ANULADO`; sesión `CANCELADA` si es `FRAMES` (la app pide otra) o `CREADA` si es `SDK`; commit y se propaga (`503`).
  - Cancelada → intento `ANULADO`, sesión `CANCELADA`, `SesionCanceladaError`.
- *TX2:*
  1. Intento `APROBADO` / `RECHAZADO` con folio (= `verification_id`) y motivo; sesión `USADA`.
  2. Si aprobado: `dispositivo_repo.vincular(...)` revoca en la misma transacción **cualquier** vínculo `ACTIVO` del cliente **y** cualquier vínculo `ACTIVO` de esa `installation_id` (teléfono compartido), e inserta el nuevo.
  3. Commit.
- **No** tocar `estado_kyc`.

Las transacciones las maneja el caso de uso con un `UnidadDeTrabajo` simple sobre la misma `AsyncSession`. **Los repositorios nuevos no hacen `commit()` por su cuenta.**

**`ConsultarResumenMovilUseCase.ejecutar(correo, installation_id | None)`** → `ResumenMovil(id, nombre, estado_kyc, dispositivo_vinculado)`.

Logs: `logger.info("activacion_movil", extra={cliente_id, sesion_id, estado, folio, motivo, correlation_id})`. Nunca frames, nonce ni el correo completo.

### 5.4 Persistencia (esquema `identity`, `create_all` del `lifespan`)

```
sesiones_activacion
  id varchar(64) PK (session_id del adaptador) · cliente_id uuid FK (index) · installation_id uuid · plataforma · modelo · version_so
  tipo_captura varchar(10) · estado varchar(16) · creada_en timestamptz · expira_en timestamptz
  INDEX (installation_id, estado)

intentos_prueba_vida            -- auditoría: nunca se borra
  id uuid PK · cliente_id uuid FK · sesion_id varchar(64) FK · installation_id uuid
  estado varchar(10) · folio varchar(64) NULL · motivo varchar(40) NULL · creado_en timestamptz · resuelto_en timestamptz NULL
  INDEX (cliente_id, creado_en)

dispositivos_vinculados
  id uuid PK · cliente_id uuid FK · installation_id uuid · plataforma · modelo · version_so
  folio_verificacion varchar(64) · estado varchar(10) · vinculado_en timestamptz · revocado_en timestamptz NULL · ultimo_acceso_en timestamptz NULL
  UNIQUE INDEX uq_dispositivo_activo_cliente     (cliente_id)      WHERE estado = 'ACTIVO'
  UNIQUE INDEX uq_dispositivo_activo_instalacion (installation_id) WHERE estado = 'ACTIVO'
```
- Índices parciales con `Index(..., unique=True, postgresql_where=..., sqlite_where=...)`: funcionan en Postgres y en SQLite.
- `IntegrityError` al vincular → rollback, intento `ANULADO`, `503` y log de error.
- El proveedor usado **no** se guarda en Identity (no lo conoce); queda en los logs del adaptador con el mismo `correlation_id` y en el prefijo del folio.
- Actualizar `Arquitectura-ModeloDatos.md` de la wiki con estas tres tablas.

### 5.5 Consentimiento biométrico (dependencia de HU3.1.3)

- Puerto `ConsentimientoBiometricoPort.otorgado(cliente_id) -> bool`; `ConsentimientoBiometricoPermisivo` (retorna `True`) mientras `REQUIRE_BIOMETRIC_CONSENT=False`.
- Los endpoints `GET` y `POST /api/v1/bff-mobile/consentimientos/biometrico` son de **HU3.1.3** (asr88). La app consume el contrato definido en la sección 4.3 del plan de la app, y lo simula hasta que HU3.1.3 lo implemente; ese contrato se le entrega a asr88 para su implementación.
- **Excepción transitoria formal (decisión D5):** `REQUIRE_BIOMETRIC_CONSENT=false` es una excepción temporal, válida solo hasta que se entregue HU3.1.3.
  - **Responsable:** asr88.
  - **Condición de salida:** el endpoint y la persistencia del consentimiento biométrico están disponibles en `dev`.
  - **Acción posterior:**
    1. Implementar el adaptador real de `ConsentimientoBiometricoPort`.
    2. Poner `REQUIRE_BIOMETRIC_CONSENT=true` en QA y producción.
    3. Eliminar la simulación del consentimiento en la app (`solventa.useMockConsent`).
  - Mientras dure: al arrancar, si `ENVIRONMENT ∈ {qa, prod}` y el flag está en `false` → `logger.warning`.

### 5.6 Endpoints internos (solo para el BFF)

| Método | Ruta | Entrada | Salida |
|---|---|---|---|
| `POST` | `/clientes/activacion-movil/sesiones` | JSON dispositivo + `correo` (lo pone el BFF tras validar el token) | 3.1 |
| `POST` | `/clientes/activacion-movil/sesiones/{sesion_id}/verificacion` | multipart como 3.2; `metadata` incluye `correo` | 3.2 |
| `GET` | `/clientes/resumen-movil?correo=&installation_id=` | query | `ResumenMovilResponse` |

- Errores con `detail={"codigo", "mensaje"}`. Lectura acotada de frames (igual que el adaptador).
- Los frames se reenvían al adaptador **sin escribirlos** en disco.
- `config.py`: `LIVENESS_ADAPTER_URL="http://localhost:8203"`, `LIVENESS_ADAPTER_TIMEOUT_SECONDS=15`, `LIVENESS_MAX_INTENTOS=3`, `LIVENESS_VENTANA_HORAS=24`, `LIVENESS_MAX_FRAME_BYTES=524_288`, `REQUIRE_BIOMETRIC_CONSENT=False`.
- `requirements.txt`: `python-multipart`.

---

## 6. BFF Móvil (`bff_mobile`)

### 6.1 Validación del token — `src/presentation/jwt_validator.py`

- **Validador:** `CognitoJwtValidator` con `pyjwt[crypto]` y `PyJWKClient` (JWKS del pool, precargado o en `run_in_threadpool`).
- **Qué verifica:** firma RS256, `exp`, `iss`, `token_use == "access"` y `client_id`. El access token de Cognito no trae `aud`, así que `verify_aud` va en `False`.
- **`client_id` correcto:** el login lo hace Identity con *su* `COGNITO_CLIENT_ID`, así que el BFF usa **el mismo** pool y client id que Identity (mismo secreto en Helm).
- **Identidad del cliente:** el pool usa el correo como alias, así que el access token solo trae `sub` y `username` (UUID), sin correo. El BFF lo obtiene con `GetUser` de Cognito usando el mismo token (API pública, sin credenciales IAM; además rechaza tokens revocados) y lo guarda en caché `sub → correo` acotada (`COGNITO_USERINFO_CACHE_SECONDS=300`, timeout `COGNITO_USERINFO_TIMEOUT_SECONDS=3`). Cognito rechaza el token → `401`; Cognito no responde → `503 SERVICIO_NO_DISPONIBLE`. Validado con JWT reales del pool de dev (E2E local y dispositivo).
- **Auditoría:** `bff_auth metodo=<cognito_jwt|demo|ninguno> resultado=<aceptado|rechazado|cognito_no_disponible> sub_hash=<sha256 corto> correlation_id=<id>`, sin correo ni token.
- **Dependencia:** `get_cliente_autenticado` → `ClienteAutenticado(correo, sub)`; `401 NO_AUTENTICADO` con el formato común `{codigo, mensaje, correlation_id}`.
- **Modo demo sin JWT:** solo si `ENVIRONMENT == "development"` **y** `ALLOW_DEMO_ACTIVATION_WITHOUT_JWT=true` se acepta `X-Demo-Correo`. En dev/qa/prod de EKS `ENVIRONMENT` no es `development`, así que el bypass queda apagado aunque el flag esté en `true` (verificado en local con `ENVIRONMENT=dev`).

### 6.2 Gateway, router y login

- **Gateway** (`identity_service_gateway.py`): `iniciar_activacion`, `verificar_activacion` (multipart con httpx) y `obtener_resumen_movil`. Timeout `ACTIVATION_TIMEOUT_SECONDS=20`; propaga `X-Correlation-Id`. `IdentityGatewayError` agrega `codigo`.
- **Router** (`routers/activacion.py`): los dos endpoints de la sección 3.
  - Validación previa: `Content-Length` > 2 MB + margen → `413` sin leer el cuerpo; lectura acotada por parte; `metadata` contra su schema.
  - El correo sale **del token y nunca del cuerpo**.
  - Errores al formato común (`ApiError` + `exception_handler`; `correlation_id` del header o `uuid4`). `5xx` de Identity → `503 SERVICIO_NO_DISPONIBLE` sin detalles.
- **Login:** tras autenticar, `obtener_resumen_movil` en `try/except`. Si falla, el login responde sin `cliente`.
- **`requirements.txt`:** `python-multipart`, `pyjwt[crypto]`.

---

## 7. `mock_kyc` — imitación de la API de Didit

El mock `didit-mock` del experimento imitaba un contrato inventado (`/v1/liveness/checks`). Aquí se imita **el contrato real** de Didit, para que `DiditProvider` sea el mismo código en mock, sandbox y demo.
- Mantener `POST /verify` tal cual.
- `POST /v3/session/`: header `x-api-key` obligatorio (`401` si falta) y `workflow_id`. Responde `201` con `session_id`, `session_token`, `url`, `status: "Not Started"`, `vendor_data` y `metadata`. Guarda la sesión en memoria con TTL.
- `GET /v3/session/{session_id}/decision/`: `404` si no existe. `status` según `MOCK_DIDIT_STATUS` (`Approved` por defecto, `Declined`, `In Review`); si `vendor_data` termina en `0` → `Declined`.
- `MOCK_LATENCY_MS` (default 0). Documentar en `docs/kyc-contract.md` con enlace a la documentación de Didit.

---

## 8. Configuración y despliegue

| Archivo | Cambio |
|---|---|
| `docker/services/Dockerfile.liveness_adapter` | Igual a los otros (`python:3.13-slim`) + descarga del modelo de MediaPipe. |
| `docker-compose.yml` | Servicio `liveness_adapter` (`8203:8000`, `depends_on: redis`, mock_kyc). `identity_service`: `LIVENESS_ADAPTER_URL=http://liveness_adapter:8000`. `liveness_adapter`: `LIVENESS_PROVIDER=propio`, `DIDIT_ENABLED=false`, `DIDIT_BASE_URL=http://mock_kyc:8000`, `DIDIT_API_KEY=mock`, `ADMIN_TOKEN` desde `.env`. `bff_mobile`: `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `AWS_REGION`. `mock_kyc`: `MOCK_DIDIT_STATUS`. |
| `.env.example` | Las variables nuevas con valores de ejemplo (sin secretos reales). |
| `deployment/helm/config/liveness_adapter/values*.yaml` | Nuevo, con la misma forma que `bff_mobile`: `ClusterIP`, **sin ingress**, `redis.enabled: true`, secretos `ADMIN_TOKEN` y `DIDIT_API_KEY`; `resources.limits.memory` ≈ 768 Mi por MediaPipe. |
| `deployment/helm/config/identity_service/values*.yaml` | `LIVENESS_ADAPTER_URL: http://liveness-adapter:80`. |
| `deployment/helm/config/bff_mobile/values.yaml` | `cognito.enabled: true` con los mismos `secretKey` de Identity; `AWS_REGION: us-east-1`. |
| `.github/workflows/ci.yml` | Agregar `liveness_adapter` a las matrices `test` y `build`. |
| `.github/workflows/depoly.yml` y `backend-publish-ecr.yml` | Agregar `liveness_adapter` (y `bff_mobile` si falta) a `service_name`. Confirmar con infraestructura que existe el repositorio ECR. |
| API Gateway / ALB / ingress | Confirmar que `/api/v1/bff-mobile/activacion/*` acepta un body de 2 MB. El adaptador **no** se publica. |

**Ningún secreto (DB, Redis, KMS, API key de Didit, `ADMIN_TOKEN`) va en archivos del repo**: solo en `.env` local o en Secrets Manager.

Ambientes:
- Dev y prod en AWS `us-east-1` (EKS detrás de un ALB compartido), cada uno con su pool de Cognito, RDS, Redis y llave KMS. Los valores están en la hoja de ambientes del equipo y en Secrets Manager.
- `mock_kyc` debe estar desplegado en dev.
- SNS y SQS siguen pendientes y esta historia no los usa.

---

## 9. Pruebas (pytest, `asyncio_mode = auto`)

| Servicio | Archivo | Casos mínimos |
|---|---|---|
| adapter | `unit/test_use_cases.py` (basado en el del experimento) | `VerifyLiveness` usa el proveedor **de la sesión** aunque cambie el activo; `ChangeActiveProvider` rechaza no registrados; `StartLivenessSession` con el proveedor activo; cuota de Didit → `propio`. |
| adapter | `unit/test_provider_factory.py` | `registered()` con y sin `DIDIT_ENABLED`; `get()` de uno no registrado. |
| adapter | `unit/test_configuration.py` | valor inicial desde env; `set`/`get` en Redis falso; caché de 10 s; Redis caído. |
| adapter | `unit/test_session_store.py` | `transition` atómico; TTL; sesión ajena. |
| adapter | `unit/test_gesture_rules.py` | BLINK y giros válidos e inválidos; sin rostro; dos rostros; inconsistente; timestamps; frames idénticos (`FaceSignals` armadas a mano). |
| adapter | `unit/test_propio_provider.py` | con `FaceAnalyzer` falso: aprobado, cada motivo, error del analizador → no disponible; nonce incorrecto. |
| adapter | `integration/test_mediapipe_analyzer.py` (`@pytest.mark.modelo`, se salta sin el modelo) | imágenes de prueba sin datos personales. |
| adapter | `unit/test_didit_provider.py` (`httpx.MockTransport`) | sesión con `x-api-key`/`workflow_id`/`vendor_data`; `Approved`, `Declined`, `In Review`; 400 por créditos, 429, 5xx, timeout; topes día/mes y Redis caído → cuota agotada. |
| adapter | `integration/test_api.py` | sesiones, verificaciones, `GET`/`PUT /admin/liveness-provider` (con y sin `X-Admin-Token`, `422`), `502`, `413`, `415`, `X-Correlation-Id` propagado. |
| identity | `unit/test_politica_intentos.py` | 0–3 consumidos; `ANULADO` y `APROBADO` no cuentan. |
| identity | `unit/test_http_liveness_client.py` | mapeo de 201/200/404/409/502/timeout; propaga `X-Correlation-Id`; envía `cliente_id` y no el correo. |
| identity | `unit/test_iniciar_activacion_use_case.py` / `unit/test_verificar_activacion_use_case.py` (puerto falso) | inexistente; ya vinculado; sin consentimiento; bloqueado; aprobado vincula **sin tocar `estado_kyc`**; rechazado; adaptador caído → `ANULADO`; cancelada; tercer rechazo → bloqueo; revoca el vínculo previo del cliente y el de otro cliente en la misma instalación. |
| identity | `integration/test_activacion_movil_api.py` (SQLite) | códigos de la sección 3; índices parciales. |
| identity | `integration/test_concurrencia_intentos.py` (`@pytest.mark.postgres`, **obligatoria**, contra el Postgres de `docker compose`) | dos verificaciones simultáneas no superan el límite; dos aprobaciones simultáneas no crean dos vínculos activos; `EN_CURSO` de una sesión vencida pasa a `ANULADO` antes de contar. |
| identity | `unit/test_anular_en_curso_vencidos.py` | `EN_CURSO` vencido → `ANULADO`; `EN_CURSO` dentro del margen se respeta. |
| identity | `unit/test_sesion_no_reutilizable.py` | crear otra sesión cancela la anterior en Identity y en el adaptador; la anterior responde `409 SESION_INVALIDA`; si el adaptador no responde al cancelar, la anterior igual queda inválida en Identity. |
| todos | `unit/test_sin_datos_sensibles_en_logs.py` (con `caplog`) | en un flujo completo, los logs no contienen bytes de frames, el nonce, el token, la API key ni `ADMIN_TOKEN`. |
| bff_mobile | `contract/test_activacion_contract.py` | las muestras de `docs/contracts/activacion/*.json` validan contra los schemas de respuesta y request. |
| bff_mobile | `unit/test_cognito_jwt_validator.py` | llaves RSA y JWKS falsos: válido, vencido, `iss`, `token_use`, `client_id`, sin `sub`; correo por `GetUser` (caché, usuario sin correo válido, token revocado → 401, Cognito caído → 503). |
| bff_mobile | `integration/test_activacion_api.py` / `test_auth_api.py` (ampliar) | 401; 413 por `Content-Length` y por lectura; 415; 422; el correo sale del token; formato común; login con `cliente` y sin él. |
| mock_kyc | `mock_kyc/tests/test_didit_mock.py` | sesión, falta de api key, decisión por env y por `vendor_data`, 404. |

Comando: `python -m pytest <servicio>/tests` (como `ci.yml`). En local: `python -m venv .venv` y `pip install -r <servicio>/requirements-dev.txt`. Ejecutar cada servicio desde la raíz con su ruta (todos usan el paquete `src`, como advierte el README del experimento con `app`).

---

## 10. Reglas para el agente que implementa

1. Rama `feat/HU3.1.1-activacion-selfie-prueba-vida`. **No hacer commit ni push.**
2. Partir del código del experimento (`../experimentos/liveness-adapter`, `../experimentos/identity-service`) y conservar sus nombres de puertos, casos de uso y endpoints. Adaptarlo al estilo del monorepo: async, `src/`, `pydantic-settings`, telemetría, dominio de Identity en español.
3. Nunca persistir ni registrar frames, nonces, API keys ni `ADMIN_TOKEN`. Nunca confiar en un correo que mande la app. Identity nunca importa nada de proveedores.
4. No cambiar el comportamiento de `/auth/login` para clientes que no envían `installation_id`.
5. Orden: T-B01 → T-B12 (validación propia de punta a punta) y después T-B13 → T-B14 (Didit; ver D9). IDs del tasking de la historia. Durante T-B01–T-B12, Didit no se registra en la fábrica.
6. Al terminar cada tarea: pruebas en verde y lista de archivos tocados, para la revisión de código.

## 11. Decisiones

| # | Decisión | Estado |
|---|---|---|
| D1 | Patrón de proveedores | **Resuelta:** el del experimento HA12. Microservicio adaptador + Strategy + Factory + proveedor activo por endpoint `/admin/liveness-provider`, persistido en Redis. `propio` activo por defecto; `didit` solo demo, desactivado y con costo cero. |
| D2 | Vínculos por cliente / por instalación | **Aprobada:** un vínculo activo por cliente y por instalación; vincular otra cuenta en el mismo teléfono revoca el vínculo anterior. |
| D3 | Intentos | **Aprobada:** máximo 3 en 24 h móviles; cuentan `RECHAZADO` y temporalmente `EN_CURSO`; `ANULADO` no cuenta. |
| D4 | ¿Cambia `estado_kyc`? | **Resuelta:** no (es del KYC de documentos de HU1.3.3). |
| D5 | Consentimiento biométrico | **Aprobada como excepción transitoria:** `REQUIRE_BIOMETRIC_CONSENT=false` hasta HU3.1.3. Responsable asr88; salida y acción posterior en 5.5. |
| D6 | Formato de error común | **Aprobada:** `{codigo, mensaje, correlation_id}` en los endpoints nuevos del BFF. |
| D7 | Extensión del experimento con sesiones | **Aprobada:** `/liveness/sessions` (y su `cancel`) agregado al adaptador, como pidió la sección 6 de los resultados del experimento; el contrato `/liveness/verifications` mantiene `{verification_id, status, correlation_id}`. |
| D8 | Riesgo de la validación propia | **Aceptado:** valida gesto y consistencia básica; no es PAD certificado ni evita por completo una secuencia grabada. Se acepta para el alcance académico; Didit es la alternativa futura. |
| D9 | Didit en esta historia | **Aprobada:** se implementa (T-B13, T-B14, T-M13) después del patrón y la validación propia. Responsable Sergio Gelvez; 14 h en total. Costo cero y desactivado por defecto. |
| D10 | Fuente única del contrato | **Aprobada:** la sección 3 de este plan es canónica; la sección 4 del plan móvil es su copia; los cambios actualizan ambos y las pruebas de contrato. |
| D11 | Ciclo de vida de la sesión | **Aprobada:** una sesión `FRAMES` nunca se reutiliza; pedir otro reto invalida la anterior y crea otra. El nonce se guarda solo como hash. |
| D12 | Intentos colgados | **Aprobada:** todo `EN_CURSO` de una sesión vencida pasa a `ANULADO` antes de contar los intentos de las últimas 24 h. |

## 12. Criterio de terminado de la historia (común a app y backend)

La historia HU3.1.1 está terminada cuando se cumple **todo** lo siguiente:

1. **Pruebas unitarias** en verde en `liveness_adapter`, `identity_service`, `bff_mobile`, `mock_kyc` y la app (`testDebugUnitTest`).
2. **Integración BFF – Identity – adapter**: el flujo completo con `docker compose`, con los dos casos (aprobado y rechazado) y la vinculación del dispositivo. Evidencia: requests, respuestas y logs con el mismo `X-Correlation-Id` en los tres servicios.
3. **Prueba de concurrencia en PostgreSQL** (`test_concurrencia_intentos.py`) en verde: ni más de 3 intentos ni dos vínculos activos.
4. **Evidencia del cambio dinámico de proveedor**: `GET` → `PUT /admin/liveness-provider` → `GET` y una activación con cada proveedor, sin redesplegar ni tocar Identity, el BFF o la app (como las figuras 7 a 11 del experimento).
5. **Revisión de datos sensibles**: no se persisten ni registran frames, nonce, token ni secretos. Se valida con `test_sin_datos_sensibles_en_logs.py`, con una búsqueda en los logs del flujo de integración y con revisión de código.
6. **Pruebas de contrato** en verde en backend y app con las mismas muestras (D10).
7. La app probada en un dispositivo Android real con la captura `FRAMES`.
8. Documentación actualizada: README, `contratos-pendientes.md` de la app, `docs/kyc-contract.md` y el modelo de datos de la wiki.
9. Didit integrado (T-B13, T-B14, T-M13): verificación aprobada y rechazada con el sandbox de Didit y con `mock_kyc`, desactivado por defecto y sin generar cobro.
