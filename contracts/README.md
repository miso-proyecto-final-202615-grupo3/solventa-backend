# Contratos internos

`proto/perfilamiento.proto` define la RPC gRPC entre `motor_cotizacion` e
`identity_service`. Los stubs generados están versionados en ambos servicios.

Para regenerarlos desde la raíz de `solventa-backend`, instala
`grpcio-tools` en el entorno del servicio y ejecuta:

```powershell
.\identity_service\.venv\Scripts\python.exe contracts\generate_protos.py
```

`ObtenerPerfilFinanciero` responde `PERMISSION_DENIED` si no hay consentimiento
activo. Si el consentimiento es válido pero falla el proveedor, responde con
`proveedor_disponible = false`; así el motor puede aplicar el factor neutral sin
