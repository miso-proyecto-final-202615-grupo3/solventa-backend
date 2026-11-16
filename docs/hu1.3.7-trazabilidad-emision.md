# HU1.3.7: Trazabilidad de emisión

## Contrato del evento

Cada evento de la línea de tiempo se expone con el mismo contrato:

| Campo | Significado |
| --- | --- |
| `evento_id` | Identificador único e inmutable del evento. |
| `cotizacion_id` | Cotización que agrupa el journey de adquisición. |
| `cliente_id` | Cliente asociado al journey. |
| `tipo` | Aceptación, validación KYC/AML, pago, firma o emisión. |
| `ocurrido_en` | Fecha y hora con zona horaria. |
| `origen` | Cliente, proveedor o servicio que produjo el evento. |
| `actor_id` | Identificador del actor cuando el flujo lo conoce; nulo para procesos de sistema. |
| `resultado` | Resultado de esa acción, sin guardar payloads sensibles. |
| `referencia_id` | Identificador del registro fuente (decisión, verificación, pago, firma o póliza). |
| `correlation_id` | Correlación técnica opcional. No sustituye a `cotizacion_id`. |
| `detalles` | Metadatos mínimos y no sensibles para explicar el resultado. |

Los eventos se guardan en la base de datos del microservicio que ejecuta la operación y en la misma transacción. No se actualizan ni eliminan. `actor_id` queda nulo cuando el servicio no autentica al actor; `origen` identifica al servicio o proveedor en esos casos. El BFF reúne las lecturas por `cotizacion_id`, no accede directamente a esquemas ajenos y ordena por `ocurrido_en` ascendente, con `evento_id` como desempate. Si una fuente requerida no responde, la consulta falla completa en lugar de mostrar una línea de tiempo parcial.

## Origen de eventos

| Evento | Fuente de verdad |
| --- | --- |
| Decisión de condiciones | `quotingengine_service.decision_condiciones` (registro existente append-only). |
| Inicio y resultado KYC/AML | Registro append-only nuevo en `identity_service`; asociado a la cotización recibida por el flujo web. |
| Inicio, aprobación, rechazo o error de pago | Registro append-only nuevo en `payments_service`, junto a cada transición del pago. |
| Validación de cotización, pago y firma; captura/vinculación de firma y emisión | Registro append-only nuevo en `insurancepolicies_service`, junto a la firma o emisión. |

Los eventos no contienen documentos, imágenes de firma, credenciales, datos de tarjeta, respuestas crudas de proveedores ni información personal innecesaria.

## Acceso

La consulta web pasa por el BFF Web y requiere un access token Cognito válido perteneciente al grupo configurado para auditoría. Las APIs de lectura internas requieren además el secreto compartido BFF-servicios; una llamada directa sin ese secreto se rechaza. La interfaz es de solo lectura.

## Persistencia

Los servicios crean únicamente tablas nuevas con `Base.metadata.create_all` en el arranque. No se altera una tabla existente automáticamente. Cualquier secreto compartido y el grupo Cognito deben configurarse en los ambientes; nunca se aceptan roles enviados como campos o headers por el navegador.
