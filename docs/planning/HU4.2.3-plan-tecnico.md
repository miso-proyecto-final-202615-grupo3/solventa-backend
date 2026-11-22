# HU4.2.3 · Procesar automáticamente un siniestro paramétrico — plan técnico (backend)

Historia: issue #86 (Sprint 3). Rama `feat/HU4.2.3-siniestro-parametrico` desde `dev` en backend y app.
Diseño de referencia: wiki *Tácticas y Patrones – Escalabilidad 2* (ASR-ESC-002 / HA8) y *Modelo de Datos*
(`EVENTO_EXTERNO`, `ACTIVACION_PARAMETRICA`, `ACTIVACION_POLIZA`, `SINIESTRO`, `INDEMNIZACION`).
Producto: `SEGURO_PARAMETRICO` del Motor de Cotización, coberturas `LLUVIA_EXTREMA` y `RETRASO_VUELO`.

## 1. Criterios de aceptación → solución

| CA | Solución |
|---|---|
| Recibir o identificar el evento externo | `POST /eventos-parametricos` (fuente autenticada con `X-Fuente-Token`). Valida el contrato mínimo, guarda el evento de forma durable y **después** responde `202` (ACK). |
| Validar que el evento esté cubierto por una póliza vigente | El consumidor busca las pólizas paramétricas suscritas al índice (zona o vuelo), evalúa el umbral de cada una y confirma con MS Pólizas que la póliza es del cliente, está en estado elegible y el evento ocurrió dentro de la vigencia. |
| Crear el siniestro sin reporte manual | Siniestro `canal=PARAMETRICO`, estado `APROBADO`, folio `SIN-AAAA-XXXXXXXX`, ligado a la activación. |
| Calcular la indemnización | Monto de compensación pactado en la suscripción paramétrica (regla del producto: pago fijo predefinido, sin demostrar pérdida). Se guarda en `INDEMNIZACION`. |
| Iniciar el proceso de pago | Evento `PAGO_INDEMNIZACION_SOLICITADO` en el outbox; el relay lo entrega por el puerto `SolicitudesPago` (`registro` local, `sqs` en AWS). La indemnización queda `PAGO_SOLICITADO`. |
| Notificar al cliente | Push de HU4.2.2 (`SINIESTRO_ESTADO`, `canal=PARAMETRICO`) al crear el siniestro y en cada cambio posterior. |
| Auditoría y trazabilidad | `evento_externo` (estado, intentos, error, resultado por póliza, checksum), `activacion_parametrica`, `activacion_poliza`, logs con `event_id`, y `GET /eventos-parametricos/{event_id}` con toda la traza. |

## 2. Supuestos (decididos sin consulta; ver §7 qué cambiaría)

| # | Supuesto |
|---|---|
| P1 | **Ingesta propia en MS Siniestros.** El adaptador de eventos es un endpoint interno del MS (no pasa por el BFF). La fuente se autentica con un token compartido `EVENTOS_FUENTE_TOKEN` (vacío = endpoint apagado, `403`). |
| P2 | **Bus durable = Amazon SQS** (diseño HA8): la ingesta publica en `solventa-<env>-parametricevents` y responde `202` (`ENCOLADO`) solo cuando SQS confirma. El consumidor (competing consumers, long polling) registra el evento en `evento_externo` (idempotencia y traza), lo procesa y recién entonces borra el mensaje; un error transitorio deja el mensaje para que SQS lo reentregue y, tras 5 recepciones, lo mueve a la DLQ `…-parametricevents-dlq`. Para pruebas y entornos sin AWS, `EVENTOS_BUS=postgres` usa la tabla `evento_externo` como bus (`FOR UPDATE SKIP LOCKED`). El ASR de 1.000.000 eventos/10 min no se valida en esta HU. |
| P3 | **Suscripción paramétrica en Siniestros.** MS Pólizas no guarda la zona ni el vuelo asegurados, así que Siniestros mantiene `poliza_parametrica` (póliza, cliente, cobertura, índice, umbral, compensación). Se registra con `PUT /polizas-parametricas/{poliza_id}` (token de operador, como la demo de HU4.2.2). Más adelante debe llegar en el evento `PolizaEmitida`. |
| P4 | **Reglas:** `LLUVIA` → `LLUVIA_EXTREMA` si `precipitacion_mm ≥ umbral` en la zona; `RETRASO_VUELO` → `RETRASO_VUELO` si `retraso_minutos ≥ umbral` del vuelo. Umbral por póliza (por defecto 50 mm y 120 min). Índices comparados en mayúsculas sin espacios. Estrategia por cobertura (patrón Strategy). |
| P5 | **Indemnización = compensación fija pactada** (`monto_compensacion`), moneda COP. No se descuenta deducible (paramétrico). |
| P6 | **Estado inicial `APROBADO`** (no pasa por evaluación). Al marcarlo `PAGADO` (operador o, en el futuro, Pagos) la indemnización pasa a `PAGADA`. |
| P7 | **Pago:** Siniestros solo **solicita** el pago. Pagos y Recaudo consumirá `PAGO_INDEMNIZACION_SOLICITADO` en su propia HU. Adaptador por defecto `registro` (log); `sqs` publica en `PAGO_INDEMNIZACION_QUEUE_URL`. |
| P8 | Un evento afecta a muchas pólizas: una `activacion_parametrica` por (evento, cobertura) cuando al menos una póliza supera el umbral, y una `activacion_poliza` por póliza activada. Las pólizas descartadas (bajo umbral, no vigente) quedan en `evento_externo.resultado`. |
| P9 | **Idempotencia:** `event_id` único (repetido con el mismo contenido → `200` sin efectos; distinto contenido → `409 EVENTO_EN_CONFLICTO`), claves `PARAM:{event_id}:{cobertura}` y `PARAM:{event_id}:{cobertura}:{poliza_id}` en activación, activación de póliza y siniestro. |
| P10 | MS Pólizas caído = error transitorio: el evento se reintenta (máx. `EVENTOS_MAX_INTENTOS`) y luego queda `FALLIDO`. Un evento que no se puede interpretar queda `DESCARTADO` con la causa. |

## 3. Contratos (canónicos; muestras en `docs/contracts/parametricos/`)

### 3.1 `POST /api/v1/insuranceclaims-service/eventos-parametricos` (fuente externa)
Encabezados: `X-Fuente-Token`, `X-Correlation-Id` opcional.
```json
{ "event_id": "IDEAM-BOG-2026-11-21-0001", "fuente": "IDEAM", "tipo": "LLUVIA",
  "ocurrido_en": "2026-11-21T15:00:00-05:00", "datos": { "zona": "BOGOTA", "precipitacion_mm": 72.5 } }
```
`tipo=RETRASO_VUELO` → `datos: { "vuelo": "AV9450", "retraso_minutos": 185 }`.
Respuestas: `202` nuevo, `200` repetido (mismo contenido), `409 EVENTO_EN_CONFLICTO`, `422` contrato inválido, `403` sin token.
```json
{ "event_id": "IDEAM-BOG-2026-11-21-0001", "estado": "RECIBIDO", "recibido_en": "2026-11-21T20:00:01Z" }
```

### 3.2 `GET /api/v1/insuranceclaims-service/eventos-parametricos/{event_id}` (fuente u operador, `X-Fuente-Token`)
Traza: `estado` (`RECIBIDO|PROCESADO|DESCARTADO|FALLIDO`), `intentos`, `ultimo_error`, `procesado_en`, `resultado` (por póliza: `ACTIVADA`, `BAJO_UMBRAL`, `POLIZA_NO_VIGENTE`, con siniestro e indemnización).

### 3.3 `PUT /api/v1/insuranceclaims-service/polizas-parametricas/{poliza_id}` (operador, `X-Operador-Token`)
```json
{ "cliente_id": "…", "cobertura": "LLUVIA_EXTREMA", "indice": "BOGOTA", "umbral": 50, "monto_compensacion": 300000, "moneda": "COP" }
```
Valida con MS Pólizas que la póliza exista, sea del cliente y del producto `SEGURO_PARAMETRICO`. `200` con la suscripción; `404 POLIZA_NO_ENCONTRADA`; `422 POLIZA_NO_PARAMETRICA`.

### 3.4 Cambios en contratos existentes (compatibles hacia atrás)
- `SiniestroResponse` (lista y detalle, MS y BFF): nuevo `canal` (`MOVIL|PARAMETRICO`).
- `SiniestroDetalleResponse`: nuevo `indemnizacion` opcional `{ monto, moneda, estado }`.
- Push `SINIESTRO_ESTADO`: nuevo dato `canal` (la app anterior lo ignora).
- Outbox `PAGO_INDEMNIZACION_SOLICITADO`: `{ indemnizacion_id, siniestro_id, numero, poliza_id, cliente_id, monto, moneda, clave_idempotencia }`.

## 4. Modelo de datos (`scripts/sql/insuranceclaims_hu4_2_3.sql`, idempotente)
- `evento_externo` + `estado`, `intentos`, `ultimo_error`, `datos` (JSON), `resultado` (JSON), `procesado_en`; índice `(estado, recibido_en)`.
- Nueva `poliza_parametrica` (único `poliza_id + cobertura`; índice `cobertura + indice`).
- `activacion_parametrica.cobertura_id` = UUID determinista del código de cobertura (`uuid5`), porque el catálogo de coberturas vive en el Motor de Cotización.

## 5. Flujo
1. Fuente → `POST /eventos-parametricos` → validación → `evento_externo` `RECIBIDO` (commit) → `202`.
2. `ProcesadorEventosParametricos` (cada `EVENTOS_INTERVALO_SEGUNDOS`): toma un evento con bloqueo, normaliza, busca suscripciones del índice, evalúa la regla de cada póliza, valida vigencia en MS Pólizas.
3. Por póliza activada, en **una transacción**: activación, activación de póliza, siniestro `APROBADO`, indemnización `PAGO_SOLICITADO`, outbox `SINIESTRO_ESTADO` y `PAGO_INDEMNIZACION_SOLICITADO`; evento `PROCESADO` con su resultado.
4. Relay del outbox: push (HU4.2.2) y solicitud de pago.
5. App: el siniestro aparece en *Mis siniestros* con la marca "Automático", y el detalle muestra el origen y la compensación.

## 6. Tareas
| Tarjeta | Alcance |
|---|---|
| T-B01 | Ingesta: contrato, token de fuente, idempotencia, `evento_externo` durable, consulta de traza. |
| T-B02 | Suscripción paramétrica + reglas (Strategy) + consumidor con reintentos/FALLIDO/DESCARTADO. |
| T-B03 | Siniestro automático, indemnización, outbox de pago y push; puerto `SolicitudesPago` (`registro`/`sqs`). |
| T-B04 | `canal` e `indemnizacion` en MS y BFF; contratos y pruebas de contrato. |
| T-B05 | SQL, compose, `.env.example`, helm, documentación y pruebas de punta a punta locales. |

## 7. Qué cambia si un supuesto se cambia después
- **P2 → otro broker (Kinesis, EventBridge):** solo se cambia el adaptador `BusEventosParametricos` y el consumidor; el caso de uso `ProcesarEventoParametricoUseCase` no cambia.
- **P3 → la zona/vuelo llegan desde Pólizas:** se reemplaza el endpoint de operador por un consumidor de `PolizaEmitida` que escribe en `poliza_parametrica`.
- **P6 → pasar por evaluación:** solo cambia el estado inicial en el caso de uso.
- **P7 → Pagos expone una API síncrona:** solo cambia el adaptador de `SolicitudesPago`.
