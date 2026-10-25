# Contrato de cotización HU1.2.4

## Solicitud

La web consume el BFF. El BFF reenvía la solicitud al motor de cotización.

```http
POST /api/v1/bff-web/cotizaciones
Content-Type: application/json
```

```json
{
  "cliente_id": "844d0eca-9846-4806-8732-2e6f4982ef8c",
  "ramo": "VIDA_HIPOTECARIO",
  "consentimiento_version": "1.0",
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
  "estado": "COTIZADA",
  "ramo": "VIDA_HIPOTECARIO",
  "moneda": "COP",
  "prima_mensual": 48046.25,
  "desglose": {
    "prima_base": 50000.0,
    "ajustes": -9625.0,
    "prima_neta": 40375.0,
    "impuestos": 7671.25
  },
  "explicacion_ajustes": [
    "Descuento Open Finance por perfil financiero excelente.",
    "Descuento Open Data por zona de bajo riesgo."
  ],
  "fuente_perfil": "PROVEEDORES",
  "vigencia_hasta": "2026-10-25T12:00:00Z"
}
```

La respuesta no expone ingresos, ahorros, endeudamiento, sobregiros ni score.
`fuente_perfil` puede ser `PROVEEDORES`, `CACHE`, `FALLBACK` o `PARCIAL`.

## Degradación

- Consentimiento ausente o revocado: responder `403 CONSENTIMIENTO_NO_ACTIVO` y no consultar Open Finance.
- Open Finance no disponible con consentimiento activo: continuar con `F_OF = 1.00`.
- Open Data no disponible: usar el último factor territorial válido de Redis.
- Open Data no disponible y sin caché: continuar con `F_OD = 1.00`.
- Timeout por proveedor configurable, máximo `0.7` segundos. Valores locales por defecto: `0.2` segundos para Open Finance y `0.25` segundos para Open Data; gRPC usa `0.3` segundos para permitir el fallback financiero.
- En Compose, `OPEN_FINANCE_URL` y `OPEN_DATA_URL` apuntan a los mocks locales. En otros ambientes deben configurarse con las URLs HTTPS acordadas para los proveedores; si están vacías, el motor usa el fallback definido.

## Errores

| HTTP | Código | Condición |
| ---: | --- | --- |
| 403 | `CONSENTIMIENTO_NO_ACTIVO` | No existe consentimiento Open Finance activo. |
| 404 | `CLIENTE_O_RAMO_NO_ENCONTRADO` | Cliente no encontrado. |
| 422 | `PARAMETROS_INVALIDOS` | Ramo no soportado, saldo, ubicación o datos de solicitud inválidos. |
| 503 | `PERFILAMIENTO_NO_DISPONIBLE` | No se pudo validar el consentimiento con Identidad. |

Los errores de disponibilidad de Open Finance/Open Data no generan `5xx` si la
cotización estándar o degradada puede calcularse.
