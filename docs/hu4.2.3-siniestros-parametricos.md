# Siniestros paramétricos (HU4.2.3)

Plan, supuestos y contrato canónico: [HU4.2.3-plan-tecnico.md](planning/HU4.2.3-plan-tecnico.md).
Muestras: [docs/contracts/parametricos](contracts/parametricos).

## Cómo funciona

1. Una fuente externa (clima o vuelos) envía el evento a `POST /api/v1/insuranceclaims-service/eventos-parametricos`
   con `X-Fuente-Token`. MS Siniestros valida el contrato, lo guarda (`evento_externo`, `RECIBIDO`) y **después** responde `202`.
2. El consumidor paramétrico (cada `EVENTOS_INTERVALO_SEGUNDOS`) toma el evento con `FOR UPDATE SKIP LOCKED`, busca las pólizas
   suscritas al índice (zona o vuelo), evalúa el umbral de cada una y confirma con MS Pólizas que la póliza sigue vigente.
3. Por cada póliza activada, en una transacción: activación, siniestro `APROBADO` (`canal=PARAMETRICO`), indemnización
   `PAGO_SOLICITADO` y dos eventos en el outbox: `SINIESTRO_ESTADO` (push al cliente) y `PAGO_INDEMNIZACION_SOLICITADO` (Pagos).
4. El relay del outbox envía el push (HU4.2.2) y la solicitud de pago (`SOLICITUDES_PAGO=registro|sqs`).
5. La app muestra el siniestro en *Mis siniestros* como "Automático" y, en el detalle, la compensación y el estado del pago.

Estados del evento: `RECIBIDO` → `PROCESADO`; error transitorio (p. ej. MS Pólizas caído) → se reintenta hasta
`EVENTOS_MAX_INTENTOS` y queda `FALLIDO`; evento ininterpretable → `DESCARTADO`. Todo queda en `GET /eventos-parametricos/{event_id}`.

## Variables (MS Siniestros)

| Variable | Valor |
|---|---|
| `EVENTOS_FUENTE_TOKEN` | Token de la fuente. Vacío = ingesta apagada (`403`). En AWS, secreto `INSURANCECLAIMS_EVENTOS_FUENTE_TOKEN`. |
| `EVENTOS_PARAMETRICOS_HABILITADOS` | `true` inicia el consumidor (por defecto). |
| `EVENTOS_INTERVALO_SEGUNDOS` / `EVENTOS_MAX_INTENTOS` | Frecuencia del consumidor y reintentos antes de `FALLIDO`. |
| `SOLICITUDES_PAGO` | `registro` (log, por defecto) o `sqs`. |
| `PAGO_INDEMNIZACION_QUEUE_URL` | Cola SQS de las solicitudes de pago (solo con `sqs`). |
| `EVENTOS_BUS` | `sqs` (diseño HA8) o `postgres` (la tabla `evento_externo` hace de cola; pruebas y local sin AWS). |
| `EVENTOS_PARAMETRICOS_QUEUE_URL` / `EVENTOS_PARAMETRICOS_DLQ_URL` | Cola y DLQ creadas por Terraform (`solventa-<env>-parametricevents[-dlq]`). |
| `SQS_AWS_PROFILE` | Solo local: perfil de `~/.aws` con permisos sobre las colas. |
| `OPERADOR_TOKEN` | Ya existe (HU4.2.2); protege `PUT /polizas-parametricas/{poliza_id}`. |

Bases ya creadas: aplicar `scripts/sql/insuranceclaims_hu4_2_3.sql` (idempotente).

## Prueba local

```bash
# .env: EVENTOS_FUENTE_TOKEN y OPERADOR_TOKEN con cualquier valor local
docker exec -i solventa-db psql -U postgres -d identity_db < scripts/sql/insuranceclaims_hu4_2_3.sql
docker compose up -d --build insuranceclaims_service bff_mobile
```

1. Suscribir una póliza del producto `SEGURO_PARAMETRICO` (desde la red de compose):
   ```bash
   docker exec solventa-insuranceclaims-service python -c "import httpx,os; print(httpx.put('http://localhost:8000/api/v1/insuranceclaims-service/polizas-parametricas/<poliza_id>', headers={'X-Operador-Token': os.environ['OPERADOR_TOKEN']}, json={'cliente_id': '<cliente_id>', 'cobertura': 'LLUVIA_EXTREMA', 'indice': 'BOGOTA', 'umbral': 50, 'monto_compensacion': 300000}).text)"
   ```
2. Enviar el evento (muestra `docs/contracts/parametricos/evento-lluvia-request.json`):
   ```bash
   docker exec solventa-insuranceclaims-service python -c "import httpx,os,json; print(httpx.post('http://localhost:8000/api/v1/insuranceclaims-service/eventos-parametricos', headers={'X-Fuente-Token': os.environ['EVENTOS_FUENTE_TOKEN']}, json=json.load(open('/dev/stdin'))).text)" < docs/contracts/parametricos/evento-lluvia-request.json
   ```
3. Ver la traza y los logs:
   ```bash
   docker exec solventa-insuranceclaims-service python -c "import httpx,os; print(httpx.get('http://localhost:8000/api/v1/insuranceclaims-service/eventos-parametricos/IDEAM-BOG-2026-11-21-0001', headers={'X-Fuente-Token': os.environ['EVENTOS_FUENTE_TOKEN']}).text)"
   docker logs solventa-insuranceclaims-service 2>&1 | grep -E "evento_parametrico|siniestro_parametrico|pago_indemnizacion|push_"
   ```
4. Marcar el siniestro como pagado (la indemnización pasa a `PAGADA` y el cliente recibe el push):
   `PUT /siniestros/{siniestro_id}/estado` con `{"estado": "PAGADO"}` y `X-Operador-Token`.

## AWS (dev)

- Guardar `INSURANCECLAIMS_EVENTOS_FUENTE_TOKEN` en `solventa-<env>-app-secrets` (opcional: sin él la ingesta responde `403`).
- Aplicar `scripts/sql/insuranceclaims_hu4_2_3.sql`.
- **Cola de eventos (SQS):** la crea Terraform en `solventa-infrastructure` (módulos `parametricevents_queue` y `parametricevents_dlq`, ver `docs/hu4.2.3-sqs-eventos-parametricos.md` de ese repo). Con las salidas, configurar `EVENTOS_BUS=sqs`, `EVENTOS_PARAMETRICOS_QUEUE_URL` y `EVENTOS_PARAMETRICOS_DLQ_URL` y dar al rol de `solventa-app-sa` la política `iam-policies/insuranceclaims-sqs-parametric-events.json`.
- Para `SOLICITUDES_PAGO=sqs`: crear la cola, configurar `PAGO_INDEMNIZACION_QUEUE_URL` y dar `sqs:SendMessage` al rol de
  `solventa-app-sa`. Mientras Pagos no la consuma, dejar `registro`.
