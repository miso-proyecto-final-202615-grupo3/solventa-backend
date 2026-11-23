# HU4.2.3 · Mapa de commits (backend)

Rama `feat/HU4.2.3-siniestro-parametrico` (desde `dev`). Sin commits hasta que Sergio lo indique.

### T-B01 — `feat(HU4.2.3): ingesta durable e idempotente de eventos paramétricos`
- `insuranceclaims_service/src/domain/siniestros/entities.py`, `errores.py`, `repositories.py`
- `insuranceclaims_service/src/infrastructure/persistence/models.py`, `siniestros_repository_impl.py`
- `insuranceclaims_service/src/presentation/routers/parametricos.py`, `src/presentation/dependencies.py`, `src/core/config.py`
- `scripts/sql/insuranceclaims_hu4_2_3.sql`

### T-B02 — `feat(HU4.2.3): suscripción paramétrica, reglas y consumidor de eventos`
- `insuranceclaims_service/src/domain/siniestros/parametricos.py`
- `insuranceclaims_service/src/infrastructure/persistence/polizas_parametricas_repository_impl.py`
- `insuranceclaims_service/src/application/use_cases/eventos_parametricos_use_cases.py`
- `insuranceclaims_service/src/infrastructure/messaging/procesador_eventos_parametricos.py`, `src/main.py`
- `insuranceclaims_service/tests/unit/test_parametricos_dominio.py`, `tests/integration/test_eventos_parametricos_api.py`,
  `tests/integration/test_parametricos_postgres.py`

### T-B02b — `feat(HU4.2.3): bus SQS de eventos paramétricos con DLQ`
- `insuranceclaims_service/src/application/ports/bus_eventos.py`
- `insuranceclaims_service/src/infrastructure/messaging/sqs_eventos_parametricos.py`
- `insuranceclaims_service/tests/integration/test_eventos_parametricos_sqs.py`
- (las colas las crea Terraform en `solventa-infrastructure`, rama `feat/hu4-2-3-sqs-eventos-parametricos`)

### T-B03 — `feat(HU4.2.3): indemnización, solicitud de pago y notificación del siniestro automático`
- `insuranceclaims_service/src/application/ports/solicitudes_pago.py`, `src/infrastructure/pagos/`
- `insuranceclaims_service/src/infrastructure/messaging/outbox_relay.py`
- `insuranceclaims_service/src/application/use_cases/cambiar_estado_siniestro_use_case.py`
- `insuranceclaims_service/tests/unit/test_solicitudes_pago.py`, `tests/integration/test_cambio_estado_api.py`

### T-B04 — `feat(HU4.2.3): canal e indemnización del siniestro en MS Siniestros y BFF Móvil`
- `insuranceclaims_service/src/application/use_cases/evidencias_use_cases.py`
- `insuranceclaims_service/src/presentation/schemas/siniestros.py`, `schemas/evidencias.py`, `routers/siniestros.py`
- `insuranceclaims_service/tests/integration/test_siniestros_api.py`, `test_health_api.py`, `tests/unit/test_parametricos_contrato.py`
- `bff_mobile/src/presentation/schemas.py`, `bff_mobile/tests/integration/test_siniestros_api.py`, `bff_mobile/tests/contract/test_parametricos_contract.py`
- `docs/contracts/parametricos/`, `docs/contracts/{siniestros,evidencias}/` (`canal` en las muestras)

### T-B05 — `chore(HU4.2.3): configuración, helm y documentación de siniestros paramétricos`
- `docker-compose.yml`, `.env.example`, `deployment/helm/config/insuranceclaims_service/values.yaml`
- `docs/hu4.2.3-siniestros-parametricos.md`, `docs/planning/HU4.2.3-plan-tecnico.md`, `docs/planning/HU4.2.3-mapa-commits.md`

## Verificación (21/11/2026)

| Prueba | Resultado |
|---|---|
| `insuranceclaims_service` | 221 en verde, 8 saltadas sin infraestructura |
| `bff_mobile` | 144 en verde |
| Postgres real (`TEST_POSTGRES_URL`) | 2 en verde: dos consumidores no duplican siniestros (`SKIP LOCKED`) y outbox |
| Local (docker compose) | suscripción → evento `202` (repetido `200`) → `SIN-2026-9DDC2952` `APROBADO`, 300.000 COP `PAGO_SOLICITADO`, solicitud de pago y push en el log |
