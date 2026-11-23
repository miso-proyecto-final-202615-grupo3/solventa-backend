# HU4.2.2 · Mapa de commits (backend)

Rama `feat/HU4.2.2-notificaciones-siniestro` (sale de `dev` con HU4.2.1). Sin commits hasta que Sergio lo indique.
Un commit por tarjeta, en este orden. Revisión y ajustes del 21/11/2026 incluidos.

### #372 · T-B01 — `feat(HU4.2.2): cambio de estado del siniestro por operador`
- `insuranceclaims_service/src/domain/siniestros/entities.py` (transiciones N7 y `EventoOutbox`)
- `insuranceclaims_service/src/domain/siniestros/errores.py` (`TransicionInvalida`)
- `insuranceclaims_service/src/application/use_cases/cambiar_estado_siniestro_use_case.py`
- `insuranceclaims_service/src/presentation/routers/operador.py`
- `insuranceclaims_service/src/presentation/dependencies.py`
- `insuranceclaims_service/src/core/config.py`
- `insuranceclaims_service/tests/unit/test_estado_siniestro.py`
- `insuranceclaims_service/tests/integration/test_cambio_estado_api.py`
- `insuranceclaims_service/tests/integration/test_health_api.py`

### #373 · T-B02 — `feat(HU4.2.2): outbox y relay de eventos de cambio de estado`
- `insuranceclaims_service/src/domain/siniestros/repositories.py`
- `insuranceclaims_service/src/infrastructure/persistence/models.py`
- `insuranceclaims_service/src/infrastructure/persistence/siniestros_repository_impl.py`
- `insuranceclaims_service/src/infrastructure/messaging/outbox_relay.py`
- `insuranceclaims_service/src/main.py`
- `scripts/sql/insuranceclaims_hu4_2_2.sql`
- `insuranceclaims_service/tests/unit/test_outbox_relay.py`
- `insuranceclaims_service/tests/integration/test_outbox_postgres.py`

### #374 · T-B03 — `feat(HU4.2.2): envío de notificaciones push por SNS Mobile Push`
- `insuranceclaims_service/src/application/ports/notificador_push.py`
- `insuranceclaims_service/src/application/ports/destinos_push.py`
- `insuranceclaims_service/src/application/use_cases/notificar_cambio_estado_use_case.py`
- `insuranceclaims_service/src/infrastructure/notifications/` (`factory.py`, `registro_notificador.py`, `sns_notificador.py`)
- `insuranceclaims_service/src/infrastructure/gateways/identity_destinos_client.py`
- `insuranceclaims_service/tests/unit/test_notificar_cambio_estado.py`
- `insuranceclaims_service/tests/unit/test_sns_notificador.py`

### #375 · T-B04 — `feat(HU4.2.2): tokens push de dispositivos en Identidad y BFF Móvil`
- `identity_service/src/application/ports/tokens_push.py`
- `identity_service/src/application/use_cases/tokens_push_use_cases.py`
- `identity_service/src/infrastructure/persistence/tokens_push_repository_impl.py`
- `identity_service/src/infrastructure/persistence/models.py`
- `identity_service/src/presentation/routers/clientes.py`
- `identity_service/src/presentation/dependencies.py`
- `scripts/sql/identity_hu4_2_2.sql`
- `identity_service/tests/integration/test_token_push_api.py`
- `bff_mobile/src/presentation/routers/dispositivos.py`, `bff_mobile/src/presentation/schemas.py`,
  `bff_mobile/src/infrastructure/gateways/identity_service_gateway.py`, `bff_mobile/src/main.py`
- `bff_mobile/tests/integration/test_dispositivos_push_api.py`

### #376 · T-B05 — `chore(HU4.2.2): contrato, configuración, helm y documentación de notificaciones`
- `docs/contracts/notificaciones/` (5 muestras)
- `bff_mobile/tests/contract/test_notificaciones_contract.py`
- `docker-compose.yml`, `.env.example`
- `deployment/helm/charts/backend-service/templates/deployment.yaml` (bloque opcional `extraSecrets`)
- `deployment/helm/config/insuranceclaims_service/values*.yaml`
- `docs/hu4.2.2-notificaciones.md`
- `docs/planning/HU4.2.2-plan-tecnico.md`, `docs/planning/HU4.2.2-mapa-commits.md`

### #377 · T-B06 — pruebas
Van dentro del commit de cada tarea (arriba).

## Verificación (21/11/2026)

| Servicio | Resultado |
|---|---|
| `insuranceclaims_service` | 193 en verde, 8 saltadas sin infraestructura (incluye la del outbox en Postgres) |
| `identity_service` | 245 en verde |
| `bff_mobile` | 142 en verde |
| Outbox en Postgres real (`TEST_POSTGRES_URL`) | 1 en verde |
| Flujo local con `registro` (docker compose) | token registrado → cambio de estado → `push_registrado` y `destinos=1 enviados=1`; sin token de operador `403`, transición inválida `409` |

## Ajustes de la revisión (21/11)

- El token inválido se borra con `POST /clientes/destinos-push/eliminacion` (cuerpo), no con el token en la URL (quedaba completo en los logs de acceso).
- SNS: un `InvalidParameter` ya no borra el token; se reutiliza y habilita el endpoint existente (`Get/SetEndpointAttributes`). Solo `EndpointDisabled`/`NotFound` son token inválido.
- Identidad: lógica del token en casos de uso + repositorio; índice único del token también en el modelo; token de hasta 1024 caracteres.
- `main.py` configura el logger `src` en INFO: antes los logs del relay y de push se descartaban.
- Relay con logs, bloqueo solo en Postgres y error claro si falta configuración (el servicio arranca igual).
- Estado desconocido → `422`; sin claves AWS estáticas (perfil local o Pod Identity); sin montaje de `~/.aws` en el compose base.
