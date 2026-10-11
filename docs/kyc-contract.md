# Contrato de integración KYC — MS Identidad (HU1.1.1 · sub-issue #189)

Fecha: 2026-10-11 · Estado: **propuesta para validar en equipo** (confirmar con Danny/Beto
la forma de su proveedor/mock objetivo; este contrato captura lo esencial compartido por
proveedores reales).

## 1. Contexto

KYC (Know Your Customer) es un **proceso regulatorio general** (verificación de identidad y
listas) ejecutado por un **proveedor externo**. El MS de Identidad no construye el proveedor:
lo **consume** para validar el documento del cliente y actualizar `estado_kyc` en su BD.

Patrón común en proveedores reales (Entrust/ex-Onfido, Persona, Veriff, Jumio, Truv, y en
Colombia Conficontrol / TransUnion / Experian / Sisdoc para la CC): se envía la identidad y se
devuelve un **estado de verificación** (`PASSED`/`FAILED`/`PENDING` o equivalente). Este
contrato define la interfaz del **mock** que usamos en desarrollo para imitar a cualquier
proveedor; el adapter del MS está desacoplado del proveedor real.

## 2. Contrato del mock (`mock-kyc`)

Base URL: `http://<mock-kyc>:8202` (local: `localhost:8202`).

### POST /verify

Síncrono. Valida el estado del documento.

Request:
```json
{
  "document_type": "CC",
  "document_number": "1020304050",
  "full_name": "Ana Pérez",
  "birth_date": "1990-05-15"
}
```

Response `200`:
```json
{
  "verification_id": "9f0e2e3e-...",
  "status": "PASSED"
}
```
`status` ∈ {`PASSED`, `FAILED`, `PENDING`}.

Errores: `400` payload inválido · `429` rate-limit · `503` no disponible.

### Calidad (del caso MISW4501, §6.1)

- Presupuesto por dependencia externa: **≤ 120 ms**.
- **Timeout duro: 700 ms**.
- Degradación: si el proveedor falla o excede el timeout → estado **`PENDIENTE`** (no rompe
  el journey), audible/vuelve a intentarse después.

## 3. Mapeo a `estado_kyc`

| Mock status | Solicitud `estado_kyc` |
| --- | --- |
| `PASSED` | `VALIDADO` |
| `FAILED` | `RECHAZADO` |
| `PENDING` (o error/desconocido) | `PENDIENTE` |

## 4. Integración en el MS Identidad

- **Port:** `KycVerifier.verificar(tipo_documento, numero_identificacion) -> EstadoKYC`
  (aplicación; única dependencia del caso de uso).
- **Adapter:** `KycHttpClient` (httpx async, timeout 700 ms) que llama a `POST /verify`.
- **Endpoints expuestos por el MS:**
  - `POST /api/v1/identity-service/clientes/registro` (existe) — crea el cliente con
    `estado_kyc=PENDIENTE`.
  - `POST /api/v1/identity-service/clientes/{id}/verificar-kyc` — dispara la validación del
    documento y actualiza `estado_kyc` (200 con el cliente actualizado; 404 si no existe).

## 5. Cómo cambiar de proveedor

Se sustituye el adapter `KycHttpClient` (nuevo proveedor) **detrás del mismo port**; el caso de
uso, endpoint, BD y cliente no cambian.

## 6. Pendiente de validación

- [ ] Confirmar con el equipo el proveedor objetivo (o el mock definitivo) y su contrato.
- [ ] Definir reglas del mock: qué documentos devuelven `PASSED`/`FAILED`/`PENDING`
      (hoy: configurable por `MOCK_KYC_STATUS`, default `PASSED`).