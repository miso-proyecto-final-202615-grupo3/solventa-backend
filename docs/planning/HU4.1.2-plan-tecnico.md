# HU4.1.2 · Adjuntar evidencia multimedia y geolocalización · Plan técnico (backend)

- Historia: [#82](https://github.com/dzamoranouniandes/misw4501-grupo3-solventa-backend/issues/82) · Sprint 3 (02/11/2026 – 22/11/2026) · Responsable: Sergio Gelvez
- Rama: `feat/HU4.1.2-evidencia-geolocalizacion` (sale de `dev` **después** de integrar HU4.1.1)
- Servicios: `insuranceclaims_service`, `bff_mobile`; infraestructura: bucket de almacenamiento (`storage_bucket`) y llave KMS de datos que ya existen en `solventa-infrastructure`; **MinIO** nuevo en `docker-compose.yml` para local.
- App: `solventa-mobileapp/docs/planning/HU4.1.2-plan-tecnico.md`. **El contrato de la sección 3 es canónico; la sección 4 del plan móvil es su copia.**
- Depende de: HU4.1.1 (siniestro, catálogo `ReglasEvidencia`, `GET /siniestros/{id}`).

> Insumo para el agente que implementa. Describe **qué** construir y **cómo** encaja con el código existente.

---

## 0. Alcance y decisiones de base

| # | Criterio | Decisión |
|---|---|---|
| CA1 | Fotos desde la cámara o el almacenamiento | La app captura o elige la foto, la comprime a JPEG y la sube. El backend solo acepta `image/jpeg`. El campo `origen` (`CAMARA`/`GALERIA`) queda registrado. |
| CA2 | Videos cuando el tipo lo permita | `ReglasEvidencia.videos_max` del catálogo de HU4.1.1; `videos_max = 0` ⇒ `422 TIPO_EVIDENCIA_NO_PERMITIDO`. Solo `video/mp4`. |
| CA3 | Pedir permisos de cámara y ubicación | Responsabilidad de la app (plan móvil). El backend no depende de que haya ubicación. |
| CA4 | Asociar la geolocalización al reporte | `PUT /siniestros/{id}/ubicacion`: latitud, longitud, precisión, fuente y hora de captura, guardadas en el siniestro. |
| CA5 | Evidencias asociadas al siniestro | Tabla nueva `EVIDENCIA_SINIESTRO` (FK al siniestro) y objeto en S3 bajo `siniestros/{siniestro_id}/evidencias/`. |
| CA6 | Si una evidencia falla, informar sin perder el resto | **Cada evidencia es independiente**: tiene su propia solicitud, carga y confirmación con estado propio. Una falla no afecta al siniestro (creado en HU4.1.1) ni a las demás evidencias. |

**Decisiones de esta historia** (estado en la sección 11):
- **E1 · Subida directa a S3 con URL prefirmada (patrón *Valet Key*).** Los archivos no pasan por el BFF ni por los pods: el backend autoriza y firma, la app sube directo y luego confirma. Videos de hasta 50 MB no cargan la memoria de los servicios ni chocan con el límite de cuerpo del ALB/ingress.
- **E2 · `POST` prefirmado con condiciones** (no `PUT`): la política firmada fija la llave exacta, el `Content-Type`, el rango de tamaño y el cifrado. S3 rechaza cualquier otra cosa.
- **E3 · Confirmación verificada:** al confirmar, el backend revisa en S3 el tamaño, el tipo y los primeros bytes del archivo (firma JPEG/MP4). Si no cuadra, borra el objeto y marca la evidencia `RECHAZADA`.
- **E4 · Cifrado en reposo** con SSE-KMS (llave de datos de la aplicación) o, si la llave no está disponible para el servicio, SSE-S3 (`AES256`, ya es el cifrado por defecto del bucket). Configurable.
- **E5 · Ubicación a nivel del siniestro** (un punto, reemplazable). Es opcional: el siniestro sigue válido sin ella si el cliente niega el permiso.
- **E6 · Límites:** foto ≤ 5 MB, video ≤ 50 MB (la app limita la duración a 60 s). Cantidades por tipo según `ReglasEvidencia`. Solo se adjunta mientras el siniestro está `REPORTADO`.

**Fuera de alcance:** descarga o visualización de evidencias por el operador (back-office, HU4.2.x), antivirus, transcodificación de video, limpieza programada de objetos huérfanos (se deja una regla de ciclo de vida sugerida en la sección 7).

---

## 1. Estado actual

| Pieza | Hoy | Falta |
|---|---|---|
| `insuranceclaims_service` | Siniestro asistido de HU4.1.1; `SINIESTRO.evidencia_referencia` (JSON) sin uso | Tabla de evidencias, columnas de ubicación, puerto de almacenamiento, casos de uso, endpoints |
| `bff_mobile` | Router `/siniestros` de HU4.1.1 | 3 endpoints nuevos y el detalle ampliado |
| Infraestructura | Bucket privado `storage_bucket` (bloqueo de acceso público, SSE `AES256`) y llave KMS `appdata` en dev y prod | Permisos S3/KMS del rol de Siniestros (EKS Pod Identity) sobre el prefijo `siniestros/` y la llave (sección 7.1) |
| Local | Sin S3 | MinIO en compose |

`evidencia_referencia` se mantiene para el flujo paramétrico (referencia al evento); el siniestro asistido usa la tabla nueva. Se documenta en la wiki.

---

## 2. Responsabilidades y flujo

| Componente | Es dueño de | No sabe |
|---|---|---|
| App | Captura, compresión, permisos, ubicación, subida a la URL firmada, reintentos por evidencia | Credenciales de AWS, nombre del bucket |
| `bff_mobile` | Token, `cliente_id`, forma del request, formato de error | S3 |
| `insuranceclaims_service` | Reglas (cantidades, tipos, tamaños, estado del siniestro), firmar la carga, verificar el objeto, estados de la evidencia, ubicación | Cognito |
| S3 / MinIO | Guardar el archivo cifrado; hacer cumplir la política firmada | — |

```
Por cada evidencia (independientes entre sí):

1) App ─ POST /siniestros/{id}/evidencias {tipo, content_type, tamano_bytes, origen, capturada_en}
      ─► BFF ─► Siniestros  SolicitarCargaEvidencia
                 · siniestro del cliente y REPORTADO (bloquea la fila del siniestro)
                 · vence las PENDIENTE expiradas; cuenta CARGADA + PENDIENTE vigentes del mismo tipo ≤ máximo
                 · crea EvidenciaSiniestro(PENDIENTE, objeto_clave)
                 · AlmacenEvidenciasPort.generar_carga(clave, content_type, tamano_max, ttl, sse)
   ◄── 201 { evidencia_id, estado: PENDIENTE, carga: { url, campos{…}, expira_en, tamano_max_bytes } }

2) App ─ POST {carga.url} multipart/form-data (campos firmados + archivo) ─► S3/MinIO ─► 204
      (S3 rechaza: tamaño fuera de rango, otro Content-Type, otra llave, política vencida)

3) App ─ POST /siniestros/{id}/evidencias/{evidencia_id}/confirmacion ─► BFF ─► Siniestros ConfirmarCargaEvidencia
                 · AlmacenEvidenciasPort.metadatos(clave) → tamaño, content_type, cifrado
                 · leer_inicio(clave, 12 bytes) → firma JPEG (FF D8 FF) o MP4 ("ftyp" en el byte 4)
                 · OK → CARGADA · no cuadra → borra el objeto, RECHAZADA · no existe → 409 CARGA_NO_ENCONTRADA
   ◄── 200 { evidencia_id, estado: CARGADA, … }

Ubicación (una vez, reemplazable):
   App ─ PUT /siniestros/{id}/ubicacion {latitud, longitud, precision_m, fuente, capturada_en} ─► BFF ─► Siniestros
```

Reglas transversales:
- **Las URL firmadas, los campos de la política, las coordenadas y la descripción no se registran en logs.** Las coordenadas solo se guardan en la base.
- Los archivos nunca se leen completos en el servicio (solo `HEAD` y 12 bytes).
- `X-Correlation-Id` de punta a punta.
- Las llamadas a S3 con `boto3` (síncrono) se ejecutan con `asyncio.to_thread`.

---

## 3. Contrato público (BFF Móvil) — canónico

Prefijo `/api/v1/bff-mobile`, Bearer, formato de error común. Muestras en `docs/contracts/evidencias/*.json` (copia exacta en la app).

### 3.1 `POST /siniestros/{siniestro_id}/evidencias` — solicitar carga

Body (`extra="forbid"`):
```json
{ "tipo": "FOTO", "content_type": "image/jpeg", "tamano_bytes": 845123, "origen": "CAMARA", "capturada_en": "2026-11-10T14:35:00-05:00" }
```
- `tipo` ∈ {`FOTO`, `VIDEO`}; `content_type`: `FOTO` → `image/jpeg`, `VIDEO` → `video/mp4`; `origen` ∈ {`CAMARA`, `GALERIA`}; `tamano_bytes` > 0; `capturada_en` con zona y no futura (tolerancia 5 min).
- Header opcional `Idempotency-Key` (UUID; la app manda el id de su evidencia local). Repetir la solicitud con la misma clave **no crea otra evidencia ni ocupa otro cupo**:
  - `PENDIENTE` (vigente o vencida) o `EXPIRADA` → la renueva con una carga nueva para el mismo objeto y responde `200`.
  - `CARGADA` → `200` con `carga: null` (la app la da por enviada).
  - `RECHAZADA` → `422 EVIDENCIA_RECHAZADA`; la clave usada con otro `tipo` → `409 IDEMPOTENCIA_CONFLICTO`.
  - Cubre la respuesta perdida, la app cerrada a mitad del envío y la sesión vencida (en la app, la carga firmada solo vive en memoria). Columna `evidencia_siniestro.clave_idempotencia`, única por siniestro.

`201`:
```json
{
  "evidencia_id": "5e0c2d8a-1f43-4b7e-9c0d-6a2b8e4f1c33",
  "estado": "PENDIENTE",
  "carga": {
    "url": "https://<bucket>.s3.amazonaws.com/",
    "campos": {
      "key": "siniestros/c41f…/evidencias/5e0c….jpg",
      "Content-Type": "image/jpeg",
      "x-amz-server-side-encryption": "aws:kms",
      "x-amz-algorithm": "AWS4-HMAC-SHA256",
      "x-amz-credential": "…",
      "x-amz-date": "…",
      "policy": "…",
      "x-amz-signature": "…"
    },
    "expira_en": "2026-11-10T20:15:00Z",
    "tamano_max_bytes": 5242880
  }
}
```
- La app debe enviar **todos** los `campos` tal cual y el archivo en la parte `file`, **al final** del formulario.
- Vigencia: 10 min para `FOTO`, 30 min para `VIDEO`.

Errores: `401` · `404 SINIESTRO_NO_ENCONTRADO` · `409 SINIESTRO_NO_ADMITE_EVIDENCIAS` (estado distinto de `REPORTADO`) · `409 LIMITE_EVIDENCIAS` · `409 IDEMPOTENCIA_CONFLICTO` · `422 EVIDENCIA_RECHAZADA` (reintento de una rechazada) · `413 EVIDENCIA_DEMASIADO_GRANDE` · `415 FORMATO_NO_SOPORTADO` · `422 TIPO_EVIDENCIA_NO_PERMITIDO` (video en un tipo sin video) · `422 DATOS_INVALIDOS` · `503 SERVICIO_NO_DISPONIBLE`.

### 3.2 Subida a S3 (la hace la app; no pasa por el BFF)

`POST {carga.url}` · `multipart/form-data` con los `campos` y la parte `file`. Éxito: `204`. Errores de S3 (XML): `403` (política vencida o condición incumplida, p. ej. tamaño) y `400` (`EntityTooLarge`, `EntityTooSmall`). La app los trata como "solicitar una carga nueva" o "archivo inválido" (plan móvil).

### 3.3 `POST /siniestros/{siniestro_id}/evidencias/{evidencia_id}/confirmacion`

Sin cuerpo. `200` (también si ya estaba `CARGADA`: es idempotente):
```json
{ "evidencia_id": "5e0c…", "tipo": "FOTO", "estado": "CARGADA", "tamano_bytes": 845123, "capturada_en": "2026-11-10T19:35:00Z", "cargada_en": "2026-11-10T20:06:41Z" }
```
Errores: `404 EVIDENCIA_NO_ENCONTRADA` · `409 CARGA_NO_ENCONTRADA` (el archivo aún no está en S3; la app puede volver a subir mientras la carga esté vigente) · `409 CARGA_EXPIRADA` (pedir otra carga) · `422 EVIDENCIA_RECHAZADA` (tamaño, tipo o contenido no coinciden; el objeto se borró) · `503`.

### 3.4 `PUT /siniestros/{siniestro_id}/ubicacion`

```json
{ "latitud": 4.6533, "longitud": -74.0836, "precision_m": 18.5, "fuente": "GPS", "capturada_en": "2026-11-10T14:36:10-05:00" }
```
- `latitud` ∈ [-90, 90], `longitud` ∈ [-180, 180], `precision_m` ∈ (0, 5000], `fuente` ∈ {`GPS`, `RED`, `ULTIMA_CONOCIDA`}, `capturada_en` con zona y no futura.

`200`: `{ "ubicacion": { …mismos campos… }, "actualizada_en": "2026-11-10T19:36:12Z" }`. Repetir reemplaza la anterior.
Errores: `401` · `404 SINIESTRO_NO_ENCONTRADO` · `409 SINIESTRO_NO_ADMITE_EVIDENCIAS` · `422 DATOS_INVALIDOS` · `503`.

### 3.5 Cambio en `GET /siniestros/{siniestro_id}` (de HU4.1.1)

Agrega:
```json
"ubicacion": { "latitud": 4.6533, "longitud": -74.0836, "precision_m": 18.5, "fuente": "GPS", "capturada_en": "…" },
"evidencias": [ { "evidencia_id": "…", "tipo": "FOTO", "estado": "CARGADA", "tamano_bytes": 845123, "capturada_en": "…", "cargada_en": "…" } ]
```
`ubicacion` puede ser `null`. `evidencias` no incluye las `EXPIRADA` ni URL de descarga.

---

## 4. MS Siniestros (`insuranceclaims_service`)

### 4.1 Dominio — `src/domain/siniestros/`

**`evidencias.py` (nuevo)**
```python
class TipoEvidencia(str, Enum): FOTO = "FOTO"; VIDEO = "VIDEO"
class OrigenEvidencia(str, Enum): CAMARA = "CAMARA"; GALERIA = "GALERIA"
class EstadoEvidencia(str, Enum): PENDIENTE = "PENDIENTE"; CARGADA = "CARGADA"; RECHAZADA = "RECHAZADA"; EXPIRADA = "EXPIRADA"

@dataclass
class EvidenciaSiniestro:
    siniestro_id: UUID
    tipo: TipoEvidencia
    content_type: str
    tamano_declarado: int
    origen: OrigenEvidencia
    capturada_en: datetime
    objeto_clave: str
    estado: EstadoEvidencia
    solicitada_en: datetime
    expira_en: datetime
    tamano_bytes: int | None = None
    cargada_en: datetime | None = None
    motivo_rechazo: str | None = None
    evidencia_id: UUID = field(default_factory=uuid4)

    def confirmar(self, tamano: int, ahora: datetime) -> None: ...      # PENDIENTE → CARGADA
    def rechazar(self, motivo: str) -> None: ...                       # PENDIENTE → RECHAZADA
    def expirar_si_vencida(self, ahora: datetime) -> bool: ...          # PENDIENTE → EXPIRADA
```
Transiciones válidas: `PENDIENTE → CARGADA | RECHAZADA | EXPIRADA`. Cualquier otra lanza `TransicionInvalida`. (Máquina de estados en la entidad.)

**`ubicacion.py` (nuevo)** — objeto de valor `UbicacionSiniestro(latitud, longitud, precision_m, fuente: FuenteUbicacion, capturada_en)` con validación de rangos en `__post_init__`. `FuenteUbicacion`: `GPS`, `RED`, `ULTIMA_CONOCIDA`.

**`politica_evidencias.py` (nuevo) — reglas puras**
```python
@dataclass(frozen=True)
class LimitesEvidencia:
    foto_max_bytes: int = 5 * 1024 * 1024
    video_max_bytes: int = 50 * 1024 * 1024
    ttl_foto: timedelta = timedelta(minutes=10)
    ttl_video: timedelta = timedelta(minutes=30)

class PoliticaEvidencias:
    CONTENT_TYPES = {TipoEvidencia.FOTO: "image/jpeg", TipoEvidencia.VIDEO: "video/mp4"}
    def __init__(self, limites: LimitesEvidencia) -> None: ...
    def validar_solicitud(self, siniestro: Siniestro, reglas: ReglasEvidencia, tipo: TipoEvidencia,
                          content_type: str, tamano: int, vigentes_del_tipo: int) -> None: ...
    def max_bytes(self, tipo: TipoEvidencia) -> int: ...
    def ttl(self, tipo: TipoEvidencia) -> timedelta: ...
    def firma_valida(self, tipo: TipoEvidencia, primeros_bytes: bytes) -> bool: ...   # JPEG FF D8 FF · MP4 b"ftyp" en [4:8]
```
Orden de `validar_solicitud`: estado `REPORTADO` → `SiniestroNoAdmiteEvidencias`; `VIDEO` con `videos_max == 0` → `TipoEvidenciaNoPermitido`; `content_type` → `FormatoNoSoportado`; tamaño → `EvidenciaDemasiadoGrande`; cantidad (`fotos_max`/`videos_max`) → `LimiteEvidencias`.

**`entities.py`** — `Siniestro` gana `ubicacion: UbicacionSiniestro | None = None` y `ubicacion_actualizada_en: datetime | None = None`.

**`errores.py`** — `SiniestroNoAdmiteEvidencias`, `LimiteEvidencias`, `EvidenciaDemasiadoGrande`, `FormatoNoSoportado`, `TipoEvidenciaNoPermitido`, `EvidenciaNoEncontrada`, `CargaNoEncontrada`, `CargaExpirada`, `EvidenciaRechazada`, `TransicionInvalida`, `AlmacenNoDisponible`.

**`repositories.py`**
- `EvidenciaRepository`: `guardar`, `actualizar`, `obtener(evidencia_id, siniestro_id)`, `listar_de_siniestro(siniestro_id)`, `pendientes_vencidas(siniestro_id, ahora)`.
- `SiniestroRepository`: `obtener_de_cliente_para_actualizar(siniestro_id, cliente_id)` (`SELECT … FOR UPDATE`), `actualizar(siniestro)`.

### 4.2 Puerto de almacenamiento — `src/application/ports/almacen_evidencias.py` (nuevo)

```python
@dataclass(frozen=True)
class CargaPrefirmada:
    url: str
    campos: dict[str, str]
    expira_en: datetime

@dataclass(frozen=True)
class MetadatosObjeto:
    tamano: int
    content_type: str
    cifrado: str | None

class AlmacenEvidenciasPort(Protocol):
    async def generar_carga(self, clave: str, content_type: str, tamano_max: int, ttl: timedelta) -> CargaPrefirmada: ...
    async def metadatos(self, clave: str) -> MetadatosObjeto | None: ...
    async def leer_inicio(self, clave: str, n_bytes: int) -> bytes: ...
    async def eliminar(self, clave: str) -> None: ...
```
Errores de red o credenciales → `AlmacenNoDisponible` (→ `503`).

### 4.3 Adaptadores — `src/infrastructure/storage/` (nuevo)

| Clase | Qué hace |
|---|---|
| `S3AlmacenEvidencias` | `boto3` con `signature_version="s3v4"`. Dos clientes: uno interno (`S3_ENDPOINT_URL`, vacío en AWS) para `head_object`/`get_object(Range="bytes=0-11")`/`delete_object`, y uno para firmar con `S3_PUBLIC_ENDPOINT_URL` (en local, la URL de MinIO alcanzable desde el emulador; vacío en AWS). `generar_carga` usa `generate_presigned_post(Bucket, Key, Fields={"Content-Type", "x-amz-server-side-encryption"[, "x-amz-server-side-encryption-aws-kms-key-id"]}, Conditions=[{"key": clave}, {"Content-Type": ct}, ["content-length-range", 1, tamano_max], {"x-amz-server-side-encryption": sse}], ExpiresIn=ttl)`. Todo con `asyncio.to_thread`. `404` de S3 → `None`. |
| `AlmacenEvidenciasEnMemoria` | Para pruebas: guarda objetos en un `dict`; `simular_subida(clave, bytes, content_type)` permite probar la confirmación. |
| `crear_almacen(settings)` | Factory: `ALMACEN_EVIDENCIAS=s3` (por defecto) o `memoria` (solo pruebas). |

Clave del objeto: `f"{EVIDENCIAS_PREFIX}{siniestro_id}/evidencias/{evidencia_id}.{'jpg' if FOTO else 'mp4'}"`. Nunca contiene datos del cliente.

### 4.4 Casos de uso — `src/application/use_cases/`

| Clase | Firma | Pasos |
|---|---|---|
| `SolicitarCargaEvidenciaUseCase` | `ejecutar(cmd: SolicitudCargaCmd, correlation_id) -> SolicitudCargaResultado` | 1) `obtener_de_cliente_para_actualizar` (bloquea la fila; serializa solicitudes concurrentes del mismo siniestro) o `SiniestroNoEncontrado`. 2) `pendientes_vencidas` → `expirar_si_vencida` (antes de contar). 3) `reglas = catalogo.obtener(siniestro.producto_codigo, siniestro.tipo).reglas` (sin llamar a MS Pólizas). 4) `politica.validar_solicitud(...)`. 5) crea `EvidenciaSiniestro(PENDIENTE, expira_en = ahora + ttl)`, guarda. 6) `almacen.generar_carga(...)`. 7) commit. Si el almacén falla → rollback y `503`. |
| `ConfirmarCargaEvidenciaUseCase` | `ejecutar(siniestro_id, evidencia_id, cliente_id, correlation_id) -> EvidenciaSiniestro` | 1) evidencia del siniestro del cliente o `EvidenciaNoEncontrada`. 2) `CARGADA` → devolverla (idempotente); `RECHAZADA` → `EvidenciaRechazada`; `EXPIRADA` → `CargaExpirada`. 3) `metadatos(clave)`: `None` y vencida → expirar y `CargaExpirada`; `None` y vigente → `CargaNoEncontrada`. 4) tamaño `== tamano_declarado` y `≤ max`, `content_type` igual, cifrado presente, `firma_valida(leer_inicio(12))`; si algo falla → `eliminar`, `rechazar(motivo)`, commit y `EvidenciaRechazada`. 5) `confirmar`, commit. |
| `RegistrarUbicacionUseCase` | `ejecutar(siniestro_id, cliente_id, ubicacion: UbicacionSiniestro) -> Siniestro` | siniestro del cliente y `REPORTADO`; `capturada_en` no futura; reemplaza y fija `ubicacion_actualizada_en`. |
| `ConsultarSiniestroUseCase` (ampliar) | devuelve `SiniestroDetalle(siniestro, evidencias)` | `evidencias` sin las `EXPIRADA`; aplica la expiración perezosa antes de listar. |

**Nota sobre el catálogo:** las reglas dependen del **producto** y del **tipo**; por eso HU4.1.1 guarda `producto_codigo` en `SINIESTRO` y aquí no se vuelve a llamar a MS Pólizas.

### 4.5 Persistencia

- `EvidenciaSiniestroModel` (`evidencia_siniestro`): columnas de la entidad; `siniestro_id` FK a `siniestro.siniestro_id` con índice; `objeto_clave` `String(300)` única; `estado` `String(20)`; índice `(siniestro_id, tipo, estado)`.
- `SiniestroModel`: `ubicacion_latitud` `Numeric(9,6)`, `ubicacion_longitud` `Numeric(9,6)`, `ubicacion_precision_m` `Numeric(8,2)`, `ubicacion_fuente` `String(20)`, `ubicacion_capturada_en` `DateTime(tz)`, `ubicacion_actualizada_en` `DateTime(tz)`; relación `evidencias`.
- `scripts/sql/insuranceclaims_hu4_1_2.sql`: `CREATE TABLE IF NOT EXISTS` y `ALTER TABLE … ADD COLUMN IF NOT EXISTS` para dev (mismo criterio que HU4.1.1).

### 4.6 Presentación (API interna, `X-Cliente-Id`)

| Método y ruta | Caso de uso |
|---|---|
| `POST /siniestros/{id}/evidencias` | `SolicitarCargaEvidenciaUseCase` → `201` |
| `POST /siniestros/{id}/evidencias/{evidencia_id}/confirmacion` | `ConfirmarCargaEvidenciaUseCase` → `200` |
| `PUT /siniestros/{id}/ubicacion` | `RegistrarUbicacionUseCase` → `200` |
| `GET /siniestros/{id}` (ampliado) | `ConsultarSiniestroUseCase` |

Schemas con `extra="forbid"`; errores nuevos en el handler de dominio (`413`, `415`, `409`, `422`, `503`).

`core/config.py`: `ALMACEN_EVIDENCIAS="s3"`, `S3_BUCKET_NAME=""` y `KMS_KEY_ARN=""` (mismos nombres que los secretos `bucket` y `kmsKey` que ya trae el chart `backend-service`), `EVIDENCIAS_PREFIX="siniestros/"`, `EVIDENCIAS_SSE="aws:kms"` (`AES256` como alternativa), `S3_ENDPOINT_URL=""`, `S3_PUBLIC_ENDPOINT_URL=""`, `AWS_REGION="us-east-1"`, `FOTO_MAX_MB=5`, `VIDEO_MAX_MB=50`. `requirements.txt`: `boto3`.

---

## 5. BFF Móvil (`bff_mobile`)

| Archivo | Cambio |
|---|---|
| `insuranceclaims_service_gateway.py` | `solicitar_carga_evidencia`, `confirmar_carga_evidencia`, `registrar_ubicacion`. |
| `schemas.py` | Schemas de la sección 3 (`extra="forbid"`). `CargaResponse.campos: dict[str, str]` se reenvía sin tocar. |
| `routers/siniestros.py` | Los 3 endpoints; validan los UUID de la ruta. **No** registran `carga.url`, `campos` ni coordenadas. |
| `errors.py` | Códigos nuevos en los mensajes por defecto; `413`/`415` ya existen con otro texto: se toma el `codigo` del servicio. |

---

## 6. Patrones y tácticas

| Táctica / patrón | Atributo | Dónde |
|---|---|---|
| Valet Key (URL prefirmada) | Rendimiento, escalabilidad, disponibilidad | Los archivos van de la app a S3; BFF y Siniestros solo firman y verifican. |
| Limitar el acceso (política firmada con condiciones y TTL) | Seguridad | Llave exacta, tipo, rango de tamaño, cifrado y vencimiento en la firma. |
| Cifrar datos en reposo y en tránsito | Seguridad | SSE-KMS (o SSE-S3) y HTTPS hacia S3. |
| Validar la entrada (dos veces) | Seguridad | Al solicitar (declarado) y al confirmar (real: `HEAD` + firma de bytes). |
| Autorizar actores | Seguridad | Cada operación valida que el siniestro sea del cliente; `404` uniforme. |
| Puertos y adaptadores / diferir el enlace | Modificabilidad | `AlmacenEvidenciasPort` con S3, MinIO (mismo adaptador, otro endpoint) y memoria. |
| Máquina de estados | Corrección | `EvidenciaSiniestro`: transiciones explícitas. |
| Aislamiento de fallas por elemento | Disponibilidad, usabilidad | Una evidencia fallida no afecta a las demás ni al siniestro. |
| Operaciones idempotentes | Disponibilidad | Confirmar dos veces y `PUT` de ubicación son seguros de repetir. |
| Bloqueo pesimista de la fila | Corrección | Los límites por siniestro no se superan con solicitudes concurrentes. |
| Expiración perezosa | Simplicidad | Las `PENDIENTE` vencidas pasan a `EXPIRADA` antes de contar (mismo criterio que D12 de HU3.1.1). |

---

## 7. Configuración y despliegue

| Archivo | Cambio |
|---|---|
| `docker-compose.yml` | Servicio `minio` (imagen `minio/minio` con etiqueta `RELEASE.*` fija, no `latest`; puertos `9000` API y `9001` consola; volumen `minio_data`; credenciales desde `.env`). Servicio `minio_init` (`minio/mc`) que crea el bucket local y termina. `insuranceclaims_service`: `S3_ENDPOINT_URL=http://minio:9000`, `S3_PUBLIC_ENDPOINT_URL=${S3_PUBLIC_ENDPOINT_URL:-http://10.0.2.2:9000}` (emulador; con teléfono físico, la IP del PC o `adb reverse tcp:9000 tcp:9000` y `http://localhost:9000`), `S3_BUCKET_NAME=solventa-local-storage`, `EVIDENCIAS_SSE=AES256` (MinIO sin KMS), credenciales de MinIO como `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` **solo locales**. |
| `.env.example` | `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` de ejemplo y las variables nuevas, sin secretos reales. |
| `deployment/helm/config/insuranceclaims_service/values*.yaml` | `bucket.enabled: true` (`S3_BUCKET_NAME`) y `kmsKey.enabled: true` (`KMS_KEY_ARN`), igual que `identity_service`; `EVIDENCIAS_SSE=aws:kms`; sin `S3_ENDPOINT_URL`. Credenciales: **nunca** llaves en el chart; EKS Pod Identity (sección 7.1). |
| `solventa-infrastructure` (coordinar) | Permisos de la sección 7.1. |

### 7.1 Permisos en AWS (S3 y KMS)

**Cómo obtienen credenciales los pods hoy.** Todos los servicios usan la cuenta de servicio `solventa-app-sa`, asociada por **EKS Pod Identity** al rol `SolventaAppRole` (workflow `eks-setup.yml` de `solventa-infrastructure`; el rol no está en Terraform). Por eso, un permiso que se agregue a `SolventaAppRole` lo reciben **todos** los servicios.
- **Recomendado (mínimo privilegio):** cuenta de servicio propia `solventa-claims-sa` con el rol `SolventaClaimsRole` y su asociación de Pod Identity; `serviceAccountName: solventa-claims-sa` en el `values.yaml` de Siniestros.
- **Mínimo aceptable para el sprint:** agregar la política de abajo a `SolventaAppRole`, limitada al prefijo `siniestros/`.

**Permisos del rol de MS Siniestros**

| Permiso | Recurso | Para qué |
|---|---|---|
| `s3:PutObject` | `arn:aws:s3:::<storage_bucket>/siniestros/*` | Firmar el `POST` prefirmado. S3 evalúa la subida de la app **con los permisos de quien firmó**: sin este permiso la URL se genera, pero S3 responde `403`. |
| `s3:GetObject` | ídem | `HeadObject` (exige `GetObject`) y la lectura de los primeros 12 bytes al confirmar. |
| `s3:DeleteObject` | ídem | Borrar evidencias rechazadas o vencidas. |
| `s3:ListBucket` con condición `s3:prefix = siniestros/*` | `arn:aws:s3:::<storage_bucket>` | Que un objeto que no existe responda `404`. Sin este permiso S3 responde `403` y no se distingue "aún no se subió" (`CARGA_NO_ENCONTRADA`) de "sin permiso". |
| `kms:GenerateDataKey` con condición `kms:ViaService = s3.us-east-1.amazonaws.com` | ARN de la llave `appdata` | S3 cifra el objeto con SSE-KMS al subirlo, con la identidad del firmante. |
| `kms:Decrypt` con la misma condición | ídem | Leer los 12 bytes de un objeto cifrado con SSE-KMS (`HeadObject` no descifra). |

**No se necesitan:** `s3:PutObjectAcl`, `s3:GetBucket*`, permisos sobre otros prefijos, `kms:Encrypt`, `kms:CreateGrant`, ni acceso público. La app nunca recibe credenciales de AWS: solo la URL firmada, válida 10–30 min para una llave exacta.

**Política de la llave KMS.** El módulo `kms` no define política propia, así que la llave usa la política por defecto (la cuenta delega en IAM) y basta con la política IAM del rol. Si alguien agrega una política de llave explícita, debe incluir este rol.

Política IAM de referencia (los ARN reales están en la hoja de ambientes; no se escriben en el repo):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "EvidenciasObjetos", "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::<storage_bucket>/siniestros/*" },
    { "Sid": "EvidenciasListarPrefijo", "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::<storage_bucket>",
      "Condition": { "StringLike": { "s3:prefix": "siniestros/*" } } },
    { "Sid": "EvidenciasKms", "Effect": "Allow",
      "Action": ["kms:GenerateDataKey", "kms:Decrypt"],
      "Resource": "<arn de la llave appdata>",
      "Condition": { "StringEquals": { "kms:ViaService": "s3.us-east-1.amazonaws.com" } } }
  ]
}
```

**Endurecimiento opcional del bucket** (política del bucket, coordinar con infraestructura porque el bucket es compartido):
- Negar cualquier acceso sin TLS (`aws:SecureTransport = false`).
- Negar `PutObject` en `siniestros/*` sin `s3:x-amz-server-side-encryption = aws:kms`.
- Activar *S3 Bucket Key* para reducir llamadas (y costo) a KMS.
- Regla de ciclo de vida sobre `siniestros/` para objetos huérfanos (S3 no conoce el estado `PENDIENTE`; la limpieza fina queda para una tarea futura).

En local (MinIO) no hay KMS: `EVIDENCIAS_SSE=AES256` y credenciales de MinIO solo en `.env`.
| CI | El job de pruebas no usa MinIO: las pruebas con `@pytest.mark.minio` se saltan si no hay `S3_ENDPOINT_URL`. |

---

## 8. Pruebas (pytest)

| Servicio | Archivo | Casos mínimos |
|---|---|---|
| claims | `unit/test_evidencia_estados.py` | transiciones válidas e inválidas; `expirar_si_vencida` en el borde. |
| claims | `unit/test_politica_evidencias.py` | orden de validaciones; video sin permiso; content-type; tamaño en el borde (= máx, máx + 1); límites por tipo; firmas JPEG y MP4 válidas e inválidas. |
| claims | `unit/test_ubicacion.py` | rangos; precisión 0 y > 5000; fecha futura. |
| claims | `unit/test_solicitar_carga.py` (almacén en memoria, SQLite) | éxito con clave correcta; siniestro ajeno → 404; no `REPORTADO` → 409; límite alcanzado; las `PENDIENTE` vencidas no cuentan; almacén caído → `503` sin evidencia guardada. |
| claims | `unit/test_confirmar_carga.py` | éxito; doble confirmación idempotente; objeto ausente vigente → `CARGA_NO_ENCONTRADA`; ausente vencido → `CARGA_EXPIRADA`; tamaño distinto / content-type distinto / firma inválida → objeto borrado y `RECHAZADA`; evidencia ajena → 404. |
| claims | `unit/test_s3_almacen.py` (`botocore.stub.Stubber`) | `generate_presigned_post` con todas las condiciones (llave, tipo, rango, cifrado) y TTL; `head_object` 404 → `None`; `Range` de 12 bytes; error de credenciales → `AlmacenNoDisponible`. |
| claims | `integration/test_evidencias_api.py` (SQLite + memoria) | los 3 endpoints y el detalle ampliado; todos los códigos de la sección 3. |
| claims | `integration/test_limite_evidencias_postgres.py` (`@pytest.mark.postgres`) | 8 solicitudes simultáneas de fotos con `fotos_max = 5` crean exactamente 5. |
| claims | `integration/test_minio_e2e.py` (`@pytest.mark.minio`) | solicitar → subir con `httpx` usando los `campos` → confirmar `CARGADA`; subir 6 MB a una carga de foto → S3 rechaza; subir con otro `Content-Type` → S3 rechaza. |
| bff | `integration/test_evidencias_api.py` | 401; validaciones; traducción de errores; reenvío de `campos` sin cambios. |
| bff | `contract/test_evidencias_contract.py` | muestras de `docs/contracts/evidencias/*.json`. |
| todos | `unit/test_sin_datos_sensibles_en_logs.py` | los logs no contienen la URL firmada, `policy`, `x-amz-signature`, coordenadas ni el token. |

Muestras: `solicitud-request.json`, `solicitud-response.json`, `confirmacion-response.json`, `ubicacion-request.json`, `detalle-con-evidencias.json`, `error-limite-evidencias.json`.

---

## 9. Reglas para el agente que implementa

1. Rama `feat/HU4.1.2-evidencia-geolocalizacion` sobre `dev` con HU4.1.1 integrada. **No hacer commit ni push** hasta que Sergio lo indique.
2. Nunca leer el archivo completo en el servicio; nunca registrar URL firmadas, campos de la política ni coordenadas.
3. Ningún secreto en el repo (credenciales de MinIO solo en `.env`; en AWS, EKS Pod Identity).
4. Orden: T-B01 → T-B05 (sección 12). Al terminar cada tarea: pruebas en verde y lista de archivos tocados.

## 10. Dependencias

| ID | Dependencia | Dueño |
|---|---|---|
| DEP-1 | HU4.1.1 integrada (siniestro, catálogo, `producto_codigo` en `SINIESTRO`). | Sergio |
| DEP-2 | Permisos S3/KMS de la sección 7.1 para el rol de Siniestros (`SolventaClaimsRole` propio o, como mínimo, `SolventaAppRole`) vía EKS Pod Identity. | Infraestructura (Danny) |
| DEP-3 | Consistencia con la subida de documentos KYC (#242, cifrado KMS con URL firmada): mismo bucket con otro prefijo y mismo criterio de cifrado. | dzamoranouniandes |

## 11. Decisiones

| ID | Tema | Estado |
|---|---|---|
Aprobadas por Sergio Gelvez el 07/11/2026.

| ID | Tema | Estado |
|---|---|---|
| E1 | Subida directa a S3 con URL prefirmada (Valet Key) en lugar de multipart por el BFF | **Aprobada** |
| E2 | `POST` prefirmado con condiciones (llave, tipo, tamaño, cifrado) en lugar de `PUT` | **Aprobada** |
| E3 | Confirmación verificada (`HEAD` + 12 bytes) y borrado si no cuadra | **Aprobada** |
| E4 | SSE-KMS con la llave `appdata` (permisos de la sección 7.1); SSE-S3 mientras infraestructura no otorgue los permisos de KMS | **Aprobada** |
| E5 | Ubicación única por siniestro, opcional y reemplazable | **Aprobada** |
| E6 | Límites: foto ≤ 5 MB (JPEG), video ≤ 50 MB (MP4, ≤ 60 s en la app); cantidades por tipo leídas de la tabla `tipo_siniestro` | **Aprobada** |
| E7 | MinIO como S3 local; mismo adaptador con otro endpoint | **Aprobada** |

## 12. Tareas (tarjetas) y criterio de terminado

| ID | Tarea | Estimación |
|---|---|---|
| T-B01 | Modelo de evidencias y ubicación, política de evidencias y migración (4.1, 4.5) | 2 h |
| T-B02 | Almacenamiento de evidencias en S3 con URL prefirmada: puerto y adaptadores (4.2, 4.3) | 2 h |
| T-B03 | Casos de uso y API: solicitar carga, confirmar, ubicación, detalle; endpoints del BFF (4.4, 4.6, 5) | 2,5 h |
| T-B04 | MinIO local, configuración, helm y permisos S3/KMS con infraestructura (7) | 1,5 h |
| T-B05 | Pruebas backend: unitarias, integración, contrato, concurrencia en Postgres y MinIO (8) | 2 h |

**Terminado cuando:**
1. Pruebas en verde en `insuranceclaims_service` y `bff_mobile`, incluidas las de Postgres y MinIO en local.
2. Flujo completo con `docker compose` + MinIO: foto y video subidos y `CARGADA`, ubicación registrada, detalle con evidencias; mismo `X-Correlation-Id` en los logs.
3. Evidencia de que S3/MinIO rechaza un archivo más grande que el permitido y un `Content-Type` distinto.
4. Evidencia de que una evidencia rechazada o fallida no afecta al siniestro ni a las demás.
5. Pruebas de contrato en verde en backend y app.
6. Sin URL firmadas, coordenadas ni tokens en los logs.
7. Wiki actualizada: modelo de datos (`EVIDENCIA_SINIESTRO`, ubicación en `SINIESTRO`) y vista de despliegue (S3 de evidencias y MinIO local).
