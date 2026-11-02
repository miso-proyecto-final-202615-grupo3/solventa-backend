# HU3.1.1 · Revisión de código del backend · 31/10/2026

## Pruebas locales con docker compose (01/11/2026)

- **Concurrencia en PostgreSQL:** 2/2 en verde, ejecutadas dentro de la red de compose. En el PC hay un PostgreSQL nativo de Windows también escuchando en el 5432, así que desde fuera la conexión llega a ese.
- **E2E por BFF → Identity → adaptador:** 15/15 verificaciones.
  - 401 con formato común; admin sin token → 403.
  - Sesión FRAMES con reto del servidor y sin nombre del proveedor; la sesión anterior queda inválida (D11).
  - Rechazo real con MediaPipe (`ROSTRO_NO_DETECTADO`).
  - Cambio dinámico a `didit` por `PUT /admin/liveness-provider`, aprobación y vínculo; la instalación ya vinculada responde 200.
  - Tres rechazos y luego `429 INTENTOS_AGOTADOS`.
- **Bugs encontrados y corregidos:**
  1. A la imagen del adaptador le faltaban librerías del sistema para OpenCV/MediaPipe (`libxcb`, `libGL`, `libEGL`, `libGLES`).
  2. Un `413`/`415`/`422` del adaptador se respondía como `503`; ahora el intento queda `ANULADO` y se responde `422 CAPTURA_INVALIDA`.
- **Trazabilidad:** `CorrelationIdMiddleware` en el BFF y en Identity (4 pruebas en cada uno). Toma o genera `X-Correlation-Id`, lo devuelve en la respuesta y registra `…_request method path status duration_ms correlation_id`, sin query, cuerpos ni headers. Repetido el E2E (15/15): el mismo `correlation_id` aparece en `bff_mobile`, `identity_service` y `liveness_adapter`.
- **Fuera de la historia:** `NoopIdentityProvider` (solo modo local, código previo) registra el correo en un warning del registro web. Conviene enmascararlo en otra historia.
- Evidencias en `solventa-mobileapp/docs/evidencias/HU3.1.1-activacion/` (no se versionan).

## Cuarta pasada · implementación de lo pendiente (sin commit)

**Pruebas:** `identity_service` 134 + 2 omitidas (PostgreSQL) · `bff_mobile` 41 · `liveness_adapter` 37 · `mock_kyc` 4. Todo en verde.

| Id | Estado | Qué se hizo |
|---|---|---|
| Pruebas en rojo | 🟢 | Captura canónica en español; `401` con formato común. |
| B-03 | 🟢 | Conflicto/no encontrada del adaptador → intento `ANULADO`, sesión `CANCELADA`, `409`; adaptador caído al iniciar → `503`; SDK cancelado → `409 SESION_CANCELADA` sin consumir intento. |
| B-09 / D6 | 🟢 | `CONSENTIMIENTO_BIOMETRICO_REQUERIDO`; BFF con `ApiError` → `{codigo, mensaje, correlation_id}` y header `X-Correlation-Id`; 5xx de Identity → `503` sin detalles. |
| B-12 | 🟢 | `ConsultarResumenMovilUseCase`. |
| B-15 | 🟢 | El flag demo solo está en `bff_mobile`. |
| B-17 | 🟢 | Transiciones atómicas en Redis para iniciar, cancelar, verificar y cerrar; si Redis falla → `503` (no hay respaldo que reabra la carrera). |
| B-19 | 🟢 | Helm por ambiente (ECR de prod, secretos de Redis, `ADMIN_TOKEN` y `DIDIT_API_KEY` con el nuevo `extraSecretEnv` del chart, `ENVIRONMENT` por ambiente, `/ready` como readiness); Cognito en el BFF; adaptador en todos los workflows y `mock_kyc` en CI. **Falta:** crear el repositorio ECR `solventa-liveness-adapter` y las llaves `LIVENESS_ADMIN_TOKEN` / `DIDIT_API_KEY` en Secrets Manager (infraestructura). |
| B-21 / D9 | 🟢 | `DiditProvider` contra la API real (`/v3/session/`, decisión), `mock_kyc` la imita, topes día/mes en Redis con fallback a `propio`, `capture.tipo = SDK`. |
| B-23 | 🟢 | Logs `liveness_provider=… correlation_id=… status=…` sin nonce ni frames (prueba con `caplog`). |
| B-24 | 🟢 | Solo `access`, correo validado con `EmailStr`; 8 pruebas con llaves RSA. |
| B-25 | 🟢 | `IntegrityError` al vincular → rollback, `ANULADO`, `503`. |
| B-26 / B-27 / B-28 | 🟢 | Aprobado no consume cupo; parseo separado; TTL desde config. |
| B-29 | 🟢 | `/health` sin Redis; `/ready` con Redis. |
| Concurrencia PostgreSQL | 🟡 | `test_concurrencia_intentos.py` escrita (`-m postgres`); **no se ejecutó** porque Docker no estaba disponible en esta máquina. |
| Prueba con modelo MediaPipe real | 🟡 | Sin ejecutar (requiere la imagen Docker con el modelo y fotos reales). |

## Tercera pasada (commits `558e450` y `0341416`, 29 commits locales sin publicar)

**Pruebas:** `liveness_adapter` 10/10 · `bff_mobile` 27/28 · `identity_service` 127/128.
**Las mismas 2 pruebas siguen en rojo** (ver la segunda pasada): `test_crea_sesion_nueva_y_reporta_intentos_restantes` y `test_requiere_identidad_demo_en_el_modo_demo`.

| Id | Estado | Comentario |
|---|---|---|
| B-16 MediaPipe bloquea el event loop | 🟢 Resuelto | `run_in_threadpool`. |
| B-17 Doble uso de una sesión | 🟡 Casi | Usa `transition(CREATED → VERIFYING)` ✅. Si `transition` lanza excepción, cae en `transitioned = session["state"] == "CREATED"` (`main.py`, verificación), que vuelve a abrir la carrera. Debe responder `503`. Además, si `_factory.get` falla después de la transición, la sesión queda `VERIFYING` hasta su TTL. |
| B-18 Fallback en memoria | 🟢 Resuelto | Sin diccionario en memoria; Redis caído → `503`. Ver B-29. |
| B-20 JWKS en cada request | 🟢 Resuelto | `lru_cache` + `PyJWKClient(cache_keys=True, lifespan=…)`. |
| B-22 Frames por nombre de archivo | 🟢 Resuelto | |
| B-24 `id_token` aceptado | 🟡 Parcial | Solo `access` ✅. Falta validar que el correo sea un correo. |
| B-03, B-09, B-12, B-15, B-19, B-21, B-23, B-25 a B-28 | 🔴 Sin cambios | Siguen abiertos. **B-19 (despliegue en AWS) y B-23 (logs para la evidencia) son los más importantes.** |

**Hallazgo nuevo:**

**B-29 (medio) · El health check falla si Redis no responde.** `liveness_adapter/src/main.py` (`/health`), `configuration.py`
- `get_active_provider_async` ahora lanza `RuntimeError`, así que `/health` da `500`.
- Helm usa ese endpoint como *liveness probe*: una caída de Redis haría que Kubernetes reinicie los pods en bucle.
- **Ajuste:** `/health` responde `200` sin consultar Redis (vida del proceso). Agregar un `/ready` que sí revise Redis y usarlo como *readiness probe*. En `start_session`, convertir el `RuntimeError` en `503`, no `500`.

**Siguiente paso para el desarrollador:**
1. Las 2 pruebas en rojo.
2. B-17 (fallback de `transition`) y B-29.
3. B-19 y B-23.
4. El resto en el orden de la segunda pasada.

---

# Segunda pasada

Rama `feat/HU3.1.1-activacion-selfie-prueba-vida`, último commit `441f596`. Hay **27 commits locales sin publicar**. Ya se sincronizó con `dev` (merge `0d0792c`, sin conflictos pendientes). Se compara contra [HU3.1.1-plan-tecnico.md](HU3.1.1-plan-tecnico.md) y contra la primera pasada de hoy.

**Pruebas:**

| Servicio | Resultado | Causa de la falla |
|---|---|---|
| `liveness_adapter` | 10/10 en verde | |
| `bff_mobile` | 1 falla | `test_activacion_api.py::test_requiere_identidad_demo_en_el_modo_demo`: espera `422` y recibe `401`. La prueba quedó desactualizada frente al nuevo `get_cliente_autenticado`. |
| `identity_service` | 1 falla | `test_iniciar_activacion_movil_use_case.py::test_crea_sesion_nueva_y_reporta_intentos_restantes`: todavía espera la captura en inglés (`type`); el código ya la normaliza a `tipo`. |

## 1. Estado de los hallazgos de la primera pasada

| Id | Estado | Comentario |
|---|---|---|
| B-01 BFF sin autenticación | 🟢 Resuelto en código | `CognitoJwtValidator` + `get_cliente_autenticado`; el correo sale del token; el modo demo quedó limitado a `development`. Ver B-17 y B-18. |
| B-02 Límite de intentos al verificar | 🟢 Resuelto | |
| B-03 Falla del adaptador | 🟡 Parcial | Adaptador caído → `ANULADO` + `CANCELADA` + `503` ✅. **Falta** capturar `LivenessSessionConflictError` / `LivenessSessionNotFoundError` en verificar, y `LivenessAdapterUnavailableError` en **iniciar** (hoy dan `500`). |
| B-04 Adaptador sin patrón | 🟢 Resuelto en su mayoría | Strategy, Factory, proveedor activo en Redis, `/admin/liveness-provider` con token, `PropioProvider` con MediaPipe y reglas de gesto. Ver B-16 a B-22. |
| B-05 Respuesta fuera de contrato | 🟢 Resuelto | |
| B-06 Captura en inglés | 🟢 Resuelto | El adaptador y la normalización de Identity entregan `tipo` / `reto`. Falta actualizar la prueba (ver arriba). |
| B-07 Fuga de `httpx.AsyncClient` | 🟢 Resuelto | |
| B-08 Sesión de otro cliente | 🟢 Resuelto | |
| B-09 Códigos de error | 🟡 Parcial | `413`, `415`, `422`, `429` y `503` corregidos. Sigue `CONSENTIMIENTO_REQUERIDO` (contrato: `CONSENTIMIENTO_BIOMETRICO_REQUERIDO`), y los errores no traen `mensaje` ni `correlation_id` (D6). |
| B-10 Test de índices | 🟢 Resuelto | |
| B-11 Marcas de tiempo | 🟢 Resuelto | Viajan app → BFF → Identity → adaptador, y el adaptador las valida. |
| B-12 `resumen-movil` en el router | 🔴 Pendiente | |
| B-13 `verify` abstracto | 🟢 Resuelto | |
| B-14 `json` importado en línea | 🟢 Resuelto | |
| B-15 Flag demo en `bff_web` | 🔴 Pendiente | |

## 2. Hallazgos nuevos

### Altos

**B-16 · El análisis de MediaPipe bloquea el event loop.** `liveness_adapter/src/main.py:164`
- `provider.verify(...)` es síncrono y analiza 3 imágenes con CPU dentro de un endpoint `async`.
- Mientras tanto, el pod no atiende otras solicitudes, incluidos los health checks.
- **Ajuste:** `await run_in_threadpool(provider.verify, session, frame_data)` (de `starlette.concurrency`).

**B-17 · Doble uso de una sesión por carrera.** `liveness_adapter/src/main.py:136-170`
- Se lee la sesión, se valida `state == "CREATED"` y se guarda `USED` al final, sin atomicidad.
- Dos verificaciones simultáneas de la misma sesión pueden pasar las dos.
- `RedisLivenessSessionStore.transition` existe, pero no se usa.
- **Ajuste:**
  1. `transition(session_id, "CREATED", "VERIFYING")` al inicio; si devuelve `False` → `409`.
  2. Al final, `VERIFYING → USED`, o `VERIFYING → CANCELLED` si el proveedor falla.

**B-18 · Fallback en memoria que oculta errores y crece sin límite.** `liveness_adapter/src/main.py:30,37-53`, `configuration.py:26,34`
- `_sessions` guarda todas las sesiones en el proceso y nunca las borra (fuga de memoria).
- Los `except Exception: pass` esconden que Redis no está disponible.
- Con más de un pod, una sesión guardada solo en memoria no existe en los demás.
- **Ajuste:** quitar el diccionario y los `except` silenciosos. Si Redis falla, responder `503` y registrar el error. Para pruebas, inyectar un store en memoria.

**B-19 · El despliegue en AWS no funcionaría.** `deployment/helm/config/liveness_adapter/*`, `.github/workflows/*`

| Problema | Consecuencia |
|---|---|
| `values.prod.yaml` y `values.qa.yaml` apuntan al ECR de la cuenta de **dev** (`179201404385`); el resto de servicios de prod usa `839553328585` | Prod tomaría imágenes de dev |
| `redis.existingSecret` no está definido (los otros servicios usan `solventa-<env>-app-secrets`) | El adaptador quedaría con `localhost` y caería en el fallback en memoria de B-18 |
| `ADMIN_TOKEN` no se inyecta | `/admin/liveness-provider` responde siempre `403` |
| `values.yaml` fija `ENVIRONMENT: dev` | Mismo valor para qa y prod |
| `liveness_adapter` solo está en `ci.yml`; falta en `deploy.yml`, `backend-publish-ecr.yml`, `backend-deploy-eks.yml`, `service-publish-ecr.yml` y `service-deploy-eks.yml` | El servicio nunca se publica ni se despliega |
| `bff_mobile/values.yaml` sigue con `cognito.enabled: false` y sin `COGNITO_REGION` | `CognitoJwtValidator` lanza "Cognito no está configurado" y **toda activación en AWS da `401`** |

- **Ajuste:** corregir los values por ambiente con el patrón de `identity_service`, agregar los secretos y las matrices, y confirmar con infraestructura el repositorio ECR.

**B-20 · El validador JWT descarga el JWKS en cada request.** `bff_mobile/src/presentation/dependencies.py` (`CognitoJwtValidator()` por llamada)
- Cada request crea un `PyJWKClient` nuevo: latencia, riesgo de throttling de Cognito y la caché `COGNITO_JWKS_TTL_SECONDS` no se usa.
- **Ajuste:** una sola instancia perezosa a nivel de módulo (o `lru_cache`), con `PyJWKClient(..., cache_keys=True, lifespan=settings.COGNITO_JWKS_TTL_SECONDS)`.

### Medios

**B-21 · Didit no está implementado según D9.** `liveness_adapter/src/infrastructure/providers/didit.py`
- **Qué hay:** un doble en memoria que no llama a la API de Didit ni a `mock_kyc`, devuelve una captura `FRAMES` con `BLINK` y **aprueba sin mirar las fotos** (según `MOCK_DIDIT_STATUS`).
- **Riesgo:** si alguien activa `didit` con `DIDIT_ENABLED=true`, cualquier activación se aprueba.
- **Falta (T-B13 / T-B14):**
  - Imitar la API `/v3/session/` en `mock_kyc`.
  - `DiditProvider` contra esa API, con `capture.tipo = SDK`.
  - Topes diario y mensual en Redis.
  - Sandbox de Didit.

**B-22 · Los frames se identifican por el nombre de archivo que manda el cliente.** `liveness_adapter/src/main.py:158`
- `frame.filename.rsplit(".")` depende del `filename` de la petición; si cambia, `PropioProvider` rechaza todo con `CAPTURA_INVALIDA`.
- **Ajuste:** usar el nombre del campo (`{"frame_inicio": frame_inicio, …}`).

**B-23 · Sin logs de trazabilidad.** El adaptador no registra nada. El criterio de terminado (evidencia del cambio dinámico) necesita `liveness_provider=<nombre> correlation_id=<id> status=<…>`.

**B-24 · El JWT acepta también `id_token`.** `bff_mobile/src/presentation/jwt_validator.py:45-47`. El plan define solo `token_use == "access"` (la app envía el access token). Además, validar que el correo sea un correo.

**B-25 · Un `IntegrityError` al vincular da `500`.** `verificar_activacion_movil_use_case.py:81`. Si los índices parciales detectan un vínculo duplicado (carrera), hay que hacer rollback, marcar el intento `ANULADO` y responder `503`.

### Bajos

- **B-26:** con resultado `APROBADO`, `intentos_restantes` se calcula como si el intento contara (`consumidos + 1`). Un aprobado no consume cupo.
- **B-27:** en Identity, `json.loads(metadata)` y el caso de uso comparten el mismo `try` (`routers/clientes.py:84`). Un `KeyError` interno del caso de uso se respondería como `422`. Separar el parseo.
- **B-28:** la vigencia de la sesión del adaptador está fija en `timedelta(minutes=2)` (`main.py:84`); usar `settings.LIVENESS_SESSION_TTL_SECONDS`.

## 3. Lo que está bien

- **El patrón del experimento HA12 está en pie:** `LivenessProvider` (Strategy), `LivenessProviderFactory`, proveedor activo en Redis y `GET`/`PUT /admin/liveness-provider` con token comparado en tiempo constante.
- **`PropioProvider` es real:** reto al azar, nonce, MediaPipe (modelo descargado en la imagen), reglas de parpadeo y giro, consistencia del rostro y frames repetidos.
- **Identity, verificación:** límite de intentos, anulación ante falla del adaptador y respuesta del contrato canónico.
- **BFF:** JWT de Cognito con el correo del token y modo demo restringido.
- **Contrato:** muestras canónicas en `docs/contracts/activacion/` con prueba de contrato en el BFF.

## 4. Siguientes pasos para el desarrollador (en orden)

1. Arreglar las 2 pruebas en rojo.
2. B-16, B-17, B-18 y B-22: robustez del adaptador.
3. B-03 (lo que falta), B-25 y B-27: manejo de errores en Identity.
4. B-19 y B-20: despliegue y caché del JWKS, para que funcione en AWS.
5. B-23: logs de trazabilidad (los necesita la evidencia del criterio de terminado).
6. B-09, B-12, B-15, B-24, B-26 y B-28.
7. B-21: Didit (T-B13 y T-B14).
8. Pendientes del plan: concurrencia en PostgreSQL y prueba de logs sin datos sensibles (T-B12).

Recordatorio: los 27 commits están solo en local. No publicar hasta que Sergio lo indique.
