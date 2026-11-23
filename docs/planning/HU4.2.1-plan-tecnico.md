# HU4.2.1 · Consultar el estado de un siniestro — plan técnico

**Historia:** #84 (Sprint 3). **Como** cliente asegurado **quiero** consultar desde la app el estado de mis siniestros
**para** conocer el avance de su atención sin contactar a Solventa.

Rama `feat/HU4.2.1-consultar-siniestros` (backend y app), sobre `dev` con HU4.1.1 y HU4.1.2 integradas.

## 1. Criterios de aceptación

| ID | Criterio | Cómo se cumple |
|---|---|---|
| CA1 | Ver los siniestros asociados a su cuenta | `GET /siniestros` (paginado, más reciente primero). Pantalla **Mis siniestros** desde Inicio. |
| CA2 | Consultar el detalle de un siniestro | `GET /siniestros/{id}` (ya existe, HU4.1.2): estado, póliza, ubicación y evidencias. Pantalla **Detalle del siniestro**. |
| CA3 *(propuesto)* | Filtrar sus siniestros por póliza | Parámetro opcional `poliza_id`; en la app, selector de póliza. |
| CA4 *(propuesto)* | Ver las evidencias que adjuntó | `GET …/evidencias/{id}/descarga`: URL de lectura temporal (Valet Key, igual que la subida). |

CA3 y CA4 se proponen al equipo como criterios nuevos de la historia.

## 2. Decisiones

| ID | Decisión |
|---|---|
| C1 | El listado reutiliza `SiniestroResponse` de HU4.1.1 (sin descripción ni evidencias); el detalle sigue en `GET /siniestros/{id}`. |
| C2 | Paginación por `pagina` (desde 1) y `tamano` (1–50, por defecto 20), con `total`. Orden: `reportado_en` descendente. |
| C3 | El dueño sale siempre del token (BFF → `X-Cliente-Id`); un `poliza_id` de otro cliente devuelve la lista vacía, no un error (no revela que existe). |
| C4 | La descarga es una **URL prefirmada `GET`** de S3 que vence en 5 min (`EVIDENCIAS_DESCARGA_TTL_SECONDS=300`), con `Content-Disposition: inline`. El archivo nunca pasa por los servicios. |
| C5 | Solo se descargan evidencias `CARGADA`; las demás responden `409 EVIDENCIA_NO_DISPONIBLE`. |
| C6 | No hacen falta permisos nuevos: el rol ya tiene `s3:GetObject` y `kms:Decrypt` (plan HU4.1.2 §7.1). La URL firmada hereda esos permisos. |
| C7 | Nunca se registra la URL firmada (mismo criterio que la carga). |

## 3. Contrato (canónico)

### `GET /api/v1/bff-mobile/siniestros?poliza_id={uuid}&pagina=1&tamano=20`

MS Siniestros: `GET /api/v1/insuranceclaims-service/siniestros` con `X-Cliente-Id`.

```json
{
  "siniestros": [
    {
      "siniestro_id": "c41f0e2a-7d5b-4c1e-9f3a-2b6d8e1a4c77",
      "numero": "SIN-2026-C41F0E2A",
      "estado": "REPORTADO",
      "poliza_id": "8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10",
      "poliza_numero": "SLV-2026-08341",
      "tipo": "GASTO_MEDICO",
      "ocurrido_en": "2026-11-10T19:30:00Z",
      "reportado_en": "2026-11-10T20:02:11Z"
    }
  ],
  "pagina": 1,
  "tamano": 20,
  "total": 1
}
```

Errores: `401`, `422` (validación: `pagina` < 1, `tamano` fuera de 1–50 o `poliza_id` que no es UUID), `503 SERVICIO_NO_DISPONIBLE`.

### `GET /api/v1/bff-mobile/siniestros/{siniestro_id}/evidencias/{evidencia_id}/descarga`

```json
{
  "evidencia_id": "5e0c2d8a-1f43-4b7e-9c0d-6a2b8e4f1c33",
  "tipo": "FOTO",
  "content_type": "image/jpeg",
  "tamano_bytes": 284311,
  "url": "https://<bucket>.s3.amazonaws.com/siniestros/…?X-Amz-Signature=…",
  "expira_en": "2026-11-10T20:10:00Z"
}
```

Errores: `401`, `404 SINIESTRO_NO_ENCONTRADO` / `EVIDENCIA_NO_ENCONTRADA`, `409 EVIDENCIA_NO_DISPONIBLE`, `503 SERVICIO_NO_DISPONIBLE`.

Muestras: `docs/contracts/siniestros/listado-response.json` y `docs/contracts/evidencias/descarga-response.json`.

## 4. Tareas

| ID | Tarea | Repo |
|---|---|---|
| T-B01 | Listar los siniestros del cliente con filtro por póliza (repositorio, caso de uso, MS Siniestros y BFF). | backend |
| T-B02 | URL de descarga temporal de una evidencia (puerto `generar_descarga`, S3/MinIO y memoria, caso de uso, MS Siniestros y BFF). | backend |
| T-B03 | Pruebas y contrato (unitarias, integración, contrato del BFF; un cliente no ve siniestros ni evidencias de otro). | backend |
| T-M01 | Pantalla **Mis siniestros** con filtro por póliza, estado vacío y error. | app |
| T-M02 | **Detalle del siniestro** con sus evidencias; tocar una abre la URL temporal. | app |
| T-M03 | Pruebas de la app (repositorio, ViewModels, pantallas) y prueba en el teléfono. | app |

## 5. Fuera de alcance

Notificaciones (HU4.2.2), cambios de estado del siniestro por un operador (back-office) y miniaturas generadas en el servidor.
