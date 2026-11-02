# Contrato de cotización HU1.2.4

## Solicitud

La web consume el BFF. El BFF reenvía la solicitud a `quotingengine_service`.
Su endpoint interno es `POST /api/v1/quotingengine-service/cotizaciones`.

```http
POST /api/v1/bff-web/cotizaciones
Content-Type: application/json
```

```json
{
  "cliente_id": "844d0eca-9846-4806-8732-2e6f4982ef8c",
  "producto_codigo": "VIDA_HIPOTECARIO",
  "parametros": {
    "saldo_credito": 200000000,
    "ubicacion": {
      "municipio": "Bogotá D.C.",
      "zona": "URBANA",
      "estrato": 4
    }
  }
}
```

El saldo pendiente del crédito es el monto asegurado. La ubicación se consulta
en Open Data y no sustituye el saldo como monto asegurado.

## Respuesta

```json
{
  "cotizacion_id": "c5e8e270-8f0f-4b77-83a7-f54a3a6b5ec0",
  "cliente_id": "844d0eca-9846-4806-8732-2e6f4982ef8c",
  "producto_codigo": "VIDA_HIPOTECARIO",
  "estado": "EMITIDA",
  "moneda": "COP",
  "prima_base": 50000.0,
  "ajustes": [
    {"concepto": "OPEN_FINANCE", "tipo": "DEDUCCION", "valor": 7500.0,
     "motivo": "Perfil financiero categoría A."},
    {"concepto": "OPEN_DATA", "tipo": "DEDUCCION", "valor": 2125.0,
     "motivo": "Riesgo territorial categoría BAJO_RIESGO."}
  ],
  "impuestos": [{"concepto": "IVA", "tasa": 0.19, "valor": 7671.25}],
  "prima_total": 48046.25,
  "degradada": false,
  "motivos_degradacion": [],
  "coberturas": [
    {"codigo": "FALLECIMIENTO", "nombre": "Fallecimiento del asegurado",
     "prima": 24023.13, "limite_asegurado": 2000000000.0, "deducible": 0.0},
    {"codigo": "INVALIDEZ_TOTAL", "nombre": "Invalidez total y permanente",
     "prima": 24023.12, "limite_asegurado": 2000000000.0, "deducible": 0.0}
  ],
  "expira_en": "2026-11-09T12:00:00Z",
  "creada_en": "2026-10-25T12:00:00Z"
}
```

La respuesta no expone ingresos, ahorros, endeudamiento, sobregiros ni score. Los
datos de perfil se registran únicamente como señal consultada en la auditoría.

## Degradación

- Consentimiento ausente o revocado: responder HTTP `403` y no consultar Open Finance.
- Open Finance no disponible con consentimiento activo: continuar con `F_OF = 1.00`.
- Open Data no disponible: usar la última categoría territorial válida de Redis.
- Open Data no disponible y sin caché: continuar con `F_OD = 1.00`.
- Timeout por proveedor configurable, máximo `0.7` segundos. Valores locales por defecto: `0.2` segundos para Open Finance y `0.25` segundos para Open Data; gRPC usa `0.12` segundos para mantener el presupuesto de latencia.
- En Compose, `OPEN_FINANCE_URL` y `OPEN_DATA_URL` apuntan a los mocks locales. En otros ambientes deben configurarse con las URLs HTTPS acordadas para los proveedores; si están vacías, el motor usa el fallback definido.

## Errores

| HTTP | Código | Condición |
| ---: | --- | --- |
| 403 | consentimiento no activo | No existe consentimiento Open Finance activo. |
| 404 | cliente o producto no encontrado | El cliente o producto no existe o no está activo. |
| 422 | `PARAMETROS_INVALIDOS` | Ramo no soportado, saldo, ubicación o datos de solicitud inválidos. |
| 503 | servicio de pricing no disponible | Regla vigente o estrategia de producto no disponible. |

Los errores de disponibilidad de Open Finance/Open Data no generan `5xx` si la
cotización estándar o degradada puede calcularse.
