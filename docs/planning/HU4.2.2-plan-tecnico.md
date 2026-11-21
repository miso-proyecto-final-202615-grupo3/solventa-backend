# HU4.2.2 · Recibir notificaciones push sobre el siniestro — plan técnico (backend, contrato canónico)

**Historia:** #85 (Sprint 3). **Como** cliente asegurado **quiero** recibir notificaciones push cuando ocurra un cambio
relevante en mi siniestro **para** conocer oportunamente su avance sin consultar constantemente la aplicación.

- Rama: `feat/HU4.2.2-notificaciones-siniestro` en `solventa-backend` y `solventa-mobileapp`, creada desde `dev` actualizado
  (ya trae HU4.1.1, HU4.1.2 y HU4.2.1).
- Implementa y revisa: Sergio. Plan de la app: `solventa-mobileapp/docs/planning/HU4.2.2-plan-tecnico.md`.
- Este documento es el **contrato canónico**: si la app y el backend difieren, manda este archivo.

---

## 1. Criterios de aceptación y cómo se cumplen

| ID | Criterio (#85) | Cómo se cumple |
|---|---|---|
| CA1 | El cliente recibe notificaciones de sus siniestros | Cada cambio de estado del siniestro escribe un evento en el **outbox** de MS Siniestros; un relay lo convierte en una notificación push a los dispositivos **activos** del dueño (§5). |
| CA2 | La notificación identifica el siniestro | El mensaje lleva `siniestro_id`, `numero` y `estado` (§3.4); la app arma el texto "SIN-2026-… · En evaluación". |
| CA3 | No enviar notificaciones de siniestros de otros clientes | El destino se resuelve **en el servidor** a partir de `siniestro.cliente_id` → dispositivos `ACTIVO` de ese cliente en MS Identidad. Un token registrado por otro cliente **se reasigna** (único por token) y se borra al cerrar sesión. La app nunca dice a quién enviar. |
| CA4 | La app maneja que el usuario no autorice notificaciones | Permiso `POST_NOTIFICATIONS` (Android 13+) pedido en contexto; si se niega, la app funciona igual y muestra un aviso con "Abrir ajustes" (plan de la app). El backend no depende de ello. |
| CA5 | Al tocar la notificación, navegar al detalle | La notificación abre `claims/{siniestro_id}` (pantalla de HU4.2.1). |

---

## 2. Decisiones (aprobadas por Sergio el 17/11/2026)

| ID | Decisión | Alternativas descartadas |
|---|---|---|
| N1 | **Canal:** Firebase Cloud Messaging (FCM) para Android. En AWS se envía por **Amazon SNS Mobile Push** (plataforma `GCM`/FCM v1), como dice el modelo de despliegue de la wiki ("SNS · Notificaciones Push"). | FCM HTTP v1 directo desde el servicio (queda como adaptador opcional si SNS se demora). |
| N2 | **Puerto `NotificadorPush`** con adaptadores intercambiables por `NOTIFICADOR_PUSH`: `sns` (AWS), `registro` (local y CI: solo registra en log y en memoria, sin datos sensibles). Patrón Strategy + Factory, igual que `ALMACEN_EVIDENCIAS` y `POLIZAS_ADAPTER`. | — |
| N3 | **Confiabilidad:** patrón **outbox** en MS Siniestros (tabla `evento_outbox`, misma transacción que el cambio de estado) y `OutboxRelay` que, en vez de SQS, entrega cada evento al `NotificadorPush`. Copiar la estructura de `payments_service/src/infrastructure/messaging/outbox_relay.py` (bloqueo `pg_advisory_xact_lock`, reintentos, "al menos una vez"). | Enviar la notificación dentro de la petición (se pierde si FCM falla); cola SQS + servicio nuevo de notificaciones (más infraestructura para un sprint). |
| N4 | **Dueño de los tokens:** MS Identidad, en `dispositivos_vinculados` (columna `push_token`), porque ahí vive la vinculación del dispositivo (HU3.1.1). MS Siniestros los consulta por un endpoint interno. | Guardarlos en MS Siniestros (duplica la noción de dispositivo). |
| N5 | **Mensaje solo de datos** (`data`, prioridad alta, sin `notification`): la app arma el texto en el idioma del teléfono y controla el toque. Sin datos personales: solo `tipo`, `siniestro_id`, `numero`, `estado`. | Mensaje con `notification` (texto fijo en español, sin control del toque en segundo plano). |
| N6 | **Quién cambia el estado (para la demostración):** endpoint **interno** de operador en MS Siniestros `PUT /siniestros/{id}/estado`, protegido con `X-Operador-Token` (variable `OPERADOR_TOKEN`; vacía → `403`), igual que `LIVENESS_ADMIN_TOKEN`. **No** se expone en el BFF. El back-office real queda fuera de alcance. | Cambiar el estado a mano en la base (no genera evento ni prueba el flujo). |
| N7 | **Transiciones válidas:** `REPORTADO → EN_EVALUACION → APROBADO | RECHAZADO`, `APROBADO → PAGADO`. Cualquier otra → `409 TRANSICION_INVALIDA`. Mismo estado → `200` sin evento (idempotente). Solo los cambios **notifican**. | — |
| N8 | **Tokens inválidos:** si SNS/FCM responde que el token no existe o fue dado de baja, MS Siniestros pide a Identidad borrarlo (`DELETE` interno). | Reintentar indefinidamente. |

---

## 3. Contrato (canónico)

### 3.1 App → BFF Móvil: registrar y borrar el token del dispositivo

`PUT /api/v1/bff-mobile/dispositivos/push` (JWT; el cliente sale del token)

```json
{ "installation_id": "d7008a0d-e34a-4ff8-bc46-77aaf5864296", "token": "<token FCM>", "plataforma": "ANDROID" }
```

- `204` registrado (idempotente: el mismo token y la misma instalación no cambian nada).
- `404 DISPOSITIVO_NO_VINCULADO`: esa instalación no está `ACTIVO` para el cliente → la app no reintenta hasta vincular.
- `422` validación (`token` 1–4096 caracteres, `installation_id` UUID, `plataforma` = `ANDROID`).
- `401`, `503 SERVICIO_NO_DISPONIBLE`.

`DELETE /api/v1/bff-mobile/dispositivos/push?installation_id={uuid}` → `204` siempre (también si no había token). Se llama al **cerrar sesión**.

### 3.2 BFF → MS Identidad (interno)

- `PUT /api/v1/identity-service/clientes/{cliente_id}/dispositivos/{installation_id}/push` body `{ "token", "plataforma" }` → `204` / `404 DISPOSITIVO_NO_VINCULADO`. Si el mismo `token` estaba en **otro** dispositivo o cliente, se le quita allí (CA3).
- `DELETE /api/v1/identity-service/clientes/{cliente_id}/dispositivos/{installation_id}/push` → `204`.

### 3.3 MS Siniestros → MS Identidad (interno)

- `GET /api/v1/identity-service/clientes/{cliente_id}/destinos-push` → `200 { "destinos": [ { "installation_id", "token", "plataforma" } ] }`. Solo dispositivos `ACTIVO` con token.
- `POST /api/v1/identity-service/clientes/destinos-push/eliminacion` body `{ "token" }` → `204` (token inválido reportado por SNS/FCM, N8). El token **nunca va en la URL**: quedaría completo en los logs de acceso. _(Corregido en la revisión del 21/11/2026; antes era `DELETE /destinos-push/{token}`.)_

### 3.4 Mensaje push (data-only)

```json
{
  "tipo": "SINIESTRO_ESTADO",
  "siniestro_id": "c41f0e2a-9b7d-4e55-8a0c-2f6d1b3e9a77",
  "numero": "SIN-2026-C41F0E2A",
  "estado": "EN_EVALUACION",
  "evento_id": "0d6f3e8a-…"
}
```

En SNS Mobile Push: `Publish(TargetArn=<endpoint>, MessageStructure="json", Message={"GCM": "{\"data\": {...}, \"android\": {\"priority\": \"high\"}}"})`
(el endpoint se obtiene con `CreatePlatformEndpoint`, que es idempotente para el mismo token).

### 3.5 Operador → MS Siniestros (interno, solo demostración)

`PUT /api/v1/insuranceclaims-service/siniestros/{siniestro_id}/estado` con `X-Operador-Token`

```json
{ "estado": "EN_EVALUACION" }
```

- `200` con el `SiniestroResponse` actualizado; `403` sin token o token distinto; `404 SINIESTRO_NO_ENCONTRADO`; `409 TRANSICION_INVALIDA`; `422`.

Muestras para pruebas de contrato (crear): `docs/contracts/notificaciones/registro-push-request.json`, `destinos-push-response.json`,
`mensaje-siniestro-estado.json`, `cambio-estado-request.json`, `error-dispositivo-no-vinculado.json`.

---

## 4. Modelo de datos

| Servicio | Cambio | Script |
|---|---|---|
| MS Identidad | `dispositivos_vinculados`: columnas `push_token varchar(4096) null`, `push_plataforma varchar(10) null`, `push_actualizado_en timestamptz null`; índice **único parcial** `uq_dispositivo_push_token` sobre `push_token` donde no es nulo. | `scripts/sql/identity_hu4_2_2.sql` (idempotente: `ADD COLUMN IF NOT EXISTS`, `CREATE UNIQUE INDEX IF NOT EXISTS`). |
| MS Siniestros | Tabla nueva `insuranceclaims.evento_outbox` (misma forma que en `insurancepolicies_service`: `evento_id, tipo, agregado_id, payload, estado, intentos, ultimo_error, creado_en, publicado_en`, índice `estado, creado_en`). Columna `siniestro.estado_actualizado_en timestamptz null`. | `scripts/sql/insuranceclaims_hu4_2_2.sql`. |

`create_all` crea las tablas nuevas, **no** agrega columnas a tablas existentes: por eso los scripts (hay que aplicarlos en dev).

---

## 5. Flujo

1. App: tras iniciar sesión o desbloquear con el dispositivo vinculado, obtiene el token FCM y llama `PUT /dispositivos/push` (también en `onNewToken`).
2. Operador: `PUT /siniestros/{id}/estado` → `CambiarEstadoSiniestroUseCase` valida la transición (N7), actualiza el siniestro y **en la misma transacción** inserta `SiniestroEstadoCambiado` en `evento_outbox`.
3. `OutboxRelay` (tarea en `lifespan`, cada `OUTBOX_INTERVALO_SEGUNDOS`, por defecto 2 s) toma los pendientes con bloqueo y llama a `NotificarCambioEstadoUseCase`:
   - `GET destinos-push` del `cliente_id` del siniestro (CA3: el destino sale del siniestro, no del mensaje).
   - Sin destinos → evento `PUBLICADO` con 0 envíos (no es error).
   - Para cada destino, `NotificadorPush.enviar(token, mensaje)`. Token inválido → `DELETE destinos-push/{token}` y sigue. Error transitorio → el evento queda `PENDIENTE` con `intentos + 1` y `ultimo_error` (máx. `OUTBOX_MAX_INTENTOS = 5`, luego `FALLIDO`).
4. App: `onMessageReceived` arma la notificación del canal "Siniestros"; al tocarla abre el detalle (HU4.2.1).

Logs: `siniestro_id`, `evento_id`, cantidad de destinos y resultado. **Nunca** el token completo (solo los últimos 6 caracteres), ni datos del cliente.

---

## 6. Tareas (para las tarjetas de #85) y detalle de implementación

### T-B01 · Estados del siniestro y cambio de estado por operador (MS Siniestros)
- `src/domain/siniestros/entities.py`: método `Siniestro.cambiar_estado(nuevo, ahora) -> bool` (False si es el mismo) con la tabla de transiciones de N7; error de dominio `TransicionInvalida` (409 `TRANSICION_INVALIDA`) en `errores.py`.
- `src/application/use_cases/cambiar_estado_siniestro_use_case.py`: busca el siniestro con `obtener_por_id` (+ `FOR UPDATE`), cambia, guarda y escribe el evento en el outbox **en la misma sesión/transacción**.
- `src/presentation/routers/operador.py`: `PUT /siniestros/{id}/estado`; dependencia `verificar_operador` (compara `X-Operador-Token` con `settings.OPERADOR_TOKEN` usando `hmac.compare_digest`; vacío → 403).
- `core/config.py`: `OPERADOR_TOKEN: str = ""`.

### T-B02 · Outbox y relay de notificaciones (MS Siniestros)
- Modelo `EventoOutboxModel`, repositorio `SqlAlchemyEventoOutboxRepository` (`guardar`, `obtener_pendientes(n)`, `marcar_publicado`, `registrar_fallo`), copiando el patrón de `payments_service`.
- `src/infrastructure/messaging/outbox_relay.py` con bloqueo advisory y `ejecutar()` en bucle; se inicia en `main.py` (lifespan) si `NOTIFICACIONES_HABILITADAS=true`.
- Script `scripts/sql/insuranceclaims_hu4_2_2.sql`.

### T-B03 · Notificador push (puerto y adaptadores) y caso de uso de notificación (MS Siniestros)
- `src/application/ports/notificador_push.py`: `NotificadorPush.enviar(token, plataforma, datos: dict) -> ResultadoEnvio` (`ENVIADO`, `TOKEN_INVALIDO`, `ERROR_TRANSITORIO`); `src/application/ports/destinos_push.py` (`listar(cliente_id)`, `eliminar(token)`).
- `src/infrastructure/notifications/sns_notificador.py` (boto3 `sns`: `create_platform_endpoint` con `SNS_PLATFORM_APPLICATION_ARN`, `publish`; `EndpointDisabled`/`InvalidParameter` sobre el token → `TOKEN_INVALIDO`), `registro_notificador.py` (log + lista en memoria), `factory.py` (`NOTIFICADOR_PUSH=sns|registro`).
- `src/infrastructure/gateways/identity_destinos_client.py` (httpx, timeout 3 s, `X-Correlation-Id`).
- `src/application/use_cases/notificar_cambio_estado_use_case.py` (§5 paso 3).
- Config: `NOTIFICADOR_PUSH="registro"`, `SNS_PLATFORM_APPLICATION_ARN=""`, `IDENTITY_SERVICE_URL`, `NOTIFICACIONES_HABILITADAS=false`, `OUTBOX_INTERVALO_SEGUNDOS=2`, `OUTBOX_MAX_INTENTOS=5`.

### T-B04 · Tokens de dispositivo en MS Identidad y BFF Móvil
- Identidad: columnas (§4) + script `scripts/sql/identity_hu4_2_2.sql`; casos de uso `RegistrarTokenPushUseCase` (valida dispositivo `ACTIVO` del cliente; quita el token de cualquier otro registro; guarda) y `EliminarTokenPushUseCase`; endpoints internos §3.2 y §3.3.
- BFF: `routers/dispositivos.py` (`PUT`/`DELETE /dispositivos/push`), métodos nuevos en `identity_service_gateway.py`, esquemas en `schemas.py`.

### T-B05 · Contrato, configuración y despliegue
- Muestras en `docs/contracts/notificaciones/` (§3); `docker-compose.yml` (variables nuevas, `NOTIFICADOR_PUSH=registro` por defecto); helm `values.yaml` de `insuranceclaims_service` (`NOTIFICADOR_PUSH: sns`, `NOTIFICACIONES_HABILITADAS: "true"`, ARN y `OPERADOR_TOKEN` desde secreto) y de `identity_service` si aplica; `.env.example`; documento `docs/hu4.2.2-notificaciones.md` (igual estilo que `docs/hu4.1.1-hu4.1.2-siniestros.md`).
- Permisos AWS del rol de MS Siniestros: `sns:CreatePlatformEndpoint` sobre la *platform application*, `sns:Publish` y `sns:GetEndpointAttributes`/`SetEndpointAttributes` sobre `arn:aws:sns:us-east-1:<cuenta>:endpoint/GCM/<app>/*`. Documentarlos; los crea infraestructura.

### T-B06 · Pruebas backend
| Servicio | Archivo | Casos mínimos |
|---|---|---|
| claims | `unit/test_estado_siniestro.py` | todas las transiciones válidas e inválidas; mismo estado sin cambio. |
| claims | `integration/test_cambio_estado_api.py` | `403` sin/otro token; `404`; `409`; `200` escribe **un** evento en el outbox; mismo estado no escribe evento. |
| claims | `unit/test_notificar_cambio_estado.py` (fakes) | envía a todos los destinos del **dueño** (CA3); sin destinos → publicado; token inválido → se elimina y sigue; error transitorio → reintento; payload exacto de §3.4; logs sin token completo. |
| claims | `unit/test_outbox_relay.py` | publica en orden, se detiene en el primer fallo, `FALLIDO` tras `OUTBOX_MAX_INTENTOS`. |
| claims | `unit/test_sns_notificador.py` (`botocore.stub.Stubber`) | `create_platform_endpoint` + `publish` con `MessageStructure=json`; mapeo de errores a `TOKEN_INVALIDO`. |
| claims | `integration/test_outbox_postgres.py` (`@pytest.mark.postgres`) | dos relays a la vez no envían el mismo evento dos veces. |
| identity | `unit/test_token_push.py`, `integration/test_token_push_api.py` | registrar (idempotente), dispositivo no vinculado → 404, token reasignado desde otro cliente, `destinos-push` solo `ACTIVO`, borrar. |
| bff | `integration/test_dispositivos_push_api.py`, `contract/test_notificaciones_contract.py` | 401; validación; reenvío a Identidad con el cliente del token; mapeo de errores; muestras del contrato. |

---

## 7. Dependencias

| ID | Dependencia | Dueño |
|---|---|---|
| DEP-1 | Proyecto de **Firebase** (FCM) con la app `com.solventa.app` y su `google-services.json` (para la app) + cuenta de servicio FCM v1 (para SNS). | Sergio |
| DEP-2 | **SNS platform application** (FCM v1) en dev y permisos del rol de MS Siniestros (T-B05). Mientras no exista: `NOTIFICADOR_PUSH=registro` (demostrable con logs). | Infraestructura (Danny) |
| DEP-3 | Clúster EKS de dev disponible (hoy `solventa-dev-eks` no existe; los despliegues fallan). | Infraestructura |

## 8. Fuera de alcance

Back-office para cambiar estados (solo el endpoint interno de operador), notificaciones de pólizas o pagos, iOS/APNs,
bandeja de notificaciones dentro de la app, preferencias por tipo de notificación.

## 9. Reglas de implementación

1. Crea la rama `feat/HU4.2.2-notificaciones-siniestro` desde `dev` actualizado en los dos repos. **No hagas commit ni push** hasta que Sergio lo indique; al terminar cada tarea deja la lista de archivos en `docs/planning/HU4.2.2-mapa-commits.md` (un commit por tarea).
2. Sigue los patrones existentes: arquitectura hexagonal (dominio sin FastAPI ni SQLAlchemy), puertos + adaptadores con *factory* por variable de entorno, errores `{codigo, mensaje, correlation_id}`, `X-Correlation-Id` de punta a punta, código y nombres del dominio en español.
3. **Ningún secreto en el repo** (`OPERADOR_TOKEN`, ARN, cuenta de servicio, `google-services.json` real): solo `.env` local y Secrets Manager. En `.env.example`, valores vacíos.
4. Nunca registres el token push completo, coordenadas, la descripción del siniestro ni datos del cliente.
5. No cambies el comportamiento de HU4.1.1, HU4.1.2 ni HU4.2.1; si un cambio rompe sus pruebas, detente y avisa.
6. Orden: T-B01 → T-B02 → T-B03 → T-B04 → T-B05 → T-B06 (las pruebas de cada tarea se escriben junto con ella). Cada tarea termina con `pytest` en verde (en contenedor: `pip install -r requirements-dev.txt` y luego `pytest`).
7. Las decisiones N1–N8 están **aprobadas**: no las cambies. Si encuentras un motivo para hacerlo, detente y anótalo en "Preguntas abiertas" al final de este archivo.

## 10. Definición de terminado

- Pruebas en verde en `insuranceclaims_service`, `identity_service` y `bff_mobile`; la de Postgres del outbox pasa contra el Postgres de compose.
- Con `docker compose` y `NOTIFICADOR_PUSH=registro`: registrar un token desde la app, cambiar el estado con el endpoint de operador y ver en el log el envío a ese token (y a ningún otro cliente).
- Scripts SQL aplicados dos veces sin error. README/documento actualizado. Mapa de commits completo.

## Preguntas abiertas

_(Aquí se anota cualquier duda o desvío de las decisiones.)_
