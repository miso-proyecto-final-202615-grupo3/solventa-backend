# Notificaciones push del siniestro (HU4.2.2)

Plan y contrato canónico: [HU4.2.2-plan-tecnico.md](planning/HU4.2.2-plan-tecnico.md). Muestras: [docs/contracts/notificaciones](contracts/notificaciones).

## Cómo funciona

1. La app (con el teléfono vinculado) registra su token de Firebase: `PUT /api/v1/bff-mobile/dispositivos/push` → MS Identidad lo guarda en `dispositivos_vinculados.push_token`. Al cerrar sesión lo borra (`DELETE`).
2. Un operador cambia el estado: `PUT /api/v1/insuranceclaims-service/siniestros/{id}/estado` con `X-Operador-Token` (solo red interna). En la misma transacción se escribe el evento `SINIESTRO_ESTADO` en `insuranceclaims.evento_outbox`.
3. El relay del outbox (cada 2 s) pide a Identidad los dispositivos **del dueño del siniestro** y envía por el adaptador de `NOTIFICADOR_PUSH`:
   - `registro`: solo deja una línea `push_registrado … token_final=XXXXXX` en el log (local y CI).
   - `sns`: Amazon SNS Mobile Push → FCM v1 → teléfono (mensaje solo de datos).
4. La app muestra la notificación del canal "Siniestros"; al tocarla abre el detalle del siniestro.

Un token que FCM da de baja (`EndpointDisabled`) se borra en Identidad. Cualquier otro error deja el evento `PENDIENTE` y se reintenta hasta `OUTBOX_MAX_INTENTOS` (luego `FALLIDO`). Ningún log contiene el token completo.

## Variables

| Variable | Servicio | Valor |
|---|---|---|
| `NOTIFICACIONES_HABILITADAS` | Siniestros | `true` para iniciar el relay (por defecto `false`). |
| `NOTIFICADOR_PUSH` | Siniestros | `registro` (defecto) o `sns`. |
| `SNS_PLATFORM_APPLICATION_ARN` | Siniestros | ARN de la *platform application* FCM v1 (secreto en AWS). |
| `SNS_AWS_PROFILE` | Siniestros | Solo local: perfil de `~/.aws` con permisos de SNS. En AWS, EKS Pod Identity. |
| `OPERADOR_TOKEN` | Siniestros | Token del endpoint de operador. Vacío = endpoint apagado (`403`). En AWS, secreto `INSURANCECLAIMS_OPERADOR_TOKEN`. |
| `IDENTITY_SERVICE_URL` | Siniestros | URL interna de MS Identidad. |

Bases ya creadas: aplicar `scripts/sql/identity_hu4_2_2.sql` y `scripts/sql/insuranceclaims_hu4_2_2.sql` (idempotentes).

## Prueba local sin Firebase (`registro`)

```bash
# .env: NOTIFICACIONES_HABILITADAS=true, NOTIFICADOR_PUSH=registro, OPERADOR_TOKEN=<cualquier valor local>
docker compose up -d --build identity_service insuranceclaims_service bff_mobile
docker exec -i solventa-db psql -U postgres -d identity_db < scripts/sql/identity_hu4_2_2.sql
docker exec -i solventa-db psql -U postgres -d identity_db < scripts/sql/insuranceclaims_hu4_2_2.sql
```

Registrar un token de prueba para un dispositivo vinculado (desde la red de compose) y cambiar el estado:

```bash
docker exec solventa-bff-mobile python -c "import httpx; print(httpx.put('http://identity_service:8000/api/v1/identity-service/clientes/<cliente_id>/dispositivos/<installation_id>/push', json={'token':'token-de-prueba-123456','plataforma':'ANDROID'}).status_code)"
docker exec solventa-bff-mobile python -c "import httpx; print(httpx.put('http://insuranceclaims_service:8000/api/v1/insuranceclaims-service/siniestros/<siniestro_id>/estado', json={'estado':'EN_EVALUACION'}, headers={'X-Operador-Token':'<OPERADOR_TOKEN>'}).text)"
docker logs solventa-insuranceclaims-service 2>&1 | grep push_
```

Se espera `push_registrado … token_final=123456` y `push_cambio_estado … destinos=1 enviados=1`.

## Prueba con Firebase y SNS reales (backend local)

1. **Firebase** (consola de Firebase): proyecto con la app Android `com.solventa.app`; descargar `google-services.json` a `solventa-mobileapp/app/` (está en `.gitignore`). En *Configuración del proyecto → Cuentas de servicio*, generar una clave privada (JSON). **No se sube a ningún repositorio.**
2. **SNS** (us-east-1), con un usuario con permiso `sns:CreatePlatformApplication`:
   ```bash
   aws sns create-platform-application --name solventa-dev-android --platform GCM \
     --attributes PlatformCredential="$(cat cuenta-servicio-firebase.json)" --region us-east-1 --profile <perfil>
   ```
   Guardar el `PlatformApplicationArn`. El perfil que use el servicio necesita la política de `solventa-infrastructure/iam-policies/insuranceclaims-sns-mobile-push.json`.
3. **Backend**: en `.env` `NOTIFICADOR_PUSH=sns`, `SNS_PLATFORM_APPLICATION_ARN=<arn>`, `SNS_AWS_PROFILE=<perfil>`. Montar `~/.aws` en `insuranceclaims_service` **y en `identity_service`** (si el `.env` trae `AWS_PROFILE` para Cognito, sin el montaje el login falla con `ProfileNotFound`) con un *override* local, no en el compose base.
4. **App**: compilar con el `google-services.json`, iniciar sesión con un cliente con teléfono vinculado, aceptar el permiso de notificaciones.
5. Cambiar el estado con el endpoint de operador → la notificación llega; al tocarla abre el detalle.

## AWS (dev)

- Crear la *platform application* en la cuenta de dev y guardar su ARN en `solventa-dev-app-secrets` como `SNS_PLATFORM_APPLICATION_ARN`, y el token de operador como `INSURANCECLAIMS_OPERADOR_TOKEN`.
- Asociar la política de `iam-policies/insuranceclaims-sns-mobile-push.json` (repo de infraestructura) al rol del `ServiceAccount` `solventa-app-sa`.
- Helm (`deployment/helm/config/insuranceclaims_service/values.yaml`) ya trae `NOTIFICACIONES_HABILITADAS=true`, `NOTIFICADOR_PUSH=sns` y los secretos como opcionales: si faltan, el servicio arranca, registra `notificaciones_push_sin_configurar` y los eventos quedan pendientes.
