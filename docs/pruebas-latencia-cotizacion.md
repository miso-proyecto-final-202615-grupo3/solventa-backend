# Pruebas de latencia de cotización

La meta de HU1.2.4 es `p95 <= 400 ms` de extremo a extremo, incluso con
proveedores degradados. Quoting Engine consulta en paralelo Open Data e Identity;
Identity consulta Open Finance solo después de validar el consentimiento. Los
timeouts locales son `120 ms` para gRPC, `200 ms` para Open Finance y `250 ms` para
Open Data, por debajo del límite de proveedor de `700 ms`.

## Ejecución

Usa un cliente registrado con consentimiento activo en la base local:

```powershell
python quotingengine_service/.venv/Scripts/python.exe scripts/load_quote.py `
  --cliente-id <UUID_DEL_CLIENTE> `
  --requests 200 `
  --concurrency 20
```

El comando devuelve el p95 y termina con error si hay respuestas distintas de
`201` o si supera `400 ms`.

## Degradación

Configura el `.env` local con `MOCK_OPENFINANCE_STATUS=UNAVAILABLE` y
`MOCK_OPENDATA_STATUS=UNAVAILABLE`, y reinicia solo esos mocks antes de repetir
la medición. El motor debe continuar con el factor financiero neutral y el
último factor territorial en caché, o con `1.00` si no existe.
