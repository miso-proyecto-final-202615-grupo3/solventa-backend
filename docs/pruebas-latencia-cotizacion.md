# Pruebas de latencia de cotización

La meta de HU1.2.4 es `p95 <= 400 ms` de extremo a extremo, incluso con
proveedores degradados. El motor consulta Open Finance y Open Data en paralelo;
Open Finance tiene `200 ms`, Open Data `250 ms` y gRPC `300 ms` por defecto,
todos por debajo del límite de `700 ms`.

## Ejecución

Usa un cliente registrado con consentimiento activo en la base local:

```powershell
python motor_cotizacion/.venv/Scripts/python.exe scripts/load_quote.py `
  --cliente-id <UUID_DEL_CLIENTE> `
  --requests 200 `
  --concurrency 20
```

El comando devuelve el p95 y termina con error si hay respuestas distintas de
`200` o si supera `400 ms`.

## Degradación

Configura el `.env` local con `MOCK_OPEN_FINANCE_STATUS=UNAVAILABLE` y
`MOCK_OPEN_DATA_STATUS=UNAVAILABLE`, y reinicia solo esos mocks antes de repetir
la medición. El motor debe continuar con el factor financiero neutral y el
último factor territorial en caché, o con `1.00` si no existe.
