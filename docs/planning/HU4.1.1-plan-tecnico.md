# HU4.1.1 · Registrar un siniestro · Plan técnico (backend)

- Historia: [#81](https://github.com/dzamoranouniandes/misw4501-grupo3-solventa-backend/issues/81) · Sprint 3 (02/11/2026 – 22/11/2026) · Responsable: Sergio Gelvez
- Rama: `feat/HU4.1.1-registrar-siniestro` (sale de `dev`, en este repo y en `solventa-mobileapp`)
- Servicios: `insuranceclaims_service` (MS Siniestros), `bff_mobile`, y una dependencia de `insurancepolicies_service` (MS Pólizas, tarea #265 de HU1.3.8)
- App: `solventa-mobileapp/docs/planning/HU4.1.1-plan-tecnico.md`. **El contrato de la sección 3 es canónico; la sección 4 del plan móvil es su copia. Si cambia, se cambian los dos y las pruebas de contrato (D10 de HU3.1.1).**
- Siguiente historia: HU4.1.2 (evidencias y geolocalización) se apoya en el siniestro que crea esta. Ver `HU4.1.2-plan-tecnico.md`.

> Insumo para el agente que implementa. Describe **qué** construir y **cómo** encaja con el código existente.

---

## 0. Alcance y decisiones de base

**Criterios de aceptación → decisión técnica**

| # | Criterio | Decisión |
|---|---|---|
| CA1 | Seleccionar una póliza asociada a su cuenta | `GET /siniestros/polizas-elegibles`: MS Siniestros pide a MS Pólizas las pólizas **del cliente autenticado** y devuelve solo las vigentes, cada una con los tipos de siniestro que admite su producto. |
| CA2 | Registrar la información básica del evento | Tipo (del catálogo del producto), descripción breve (10–500 caracteres) y fecha/hora de ocurrencia (dentro de la vigencia y no futura). Igual que el prototipo móvil: "¿Qué pasó? · Cuéntanos brevemente · ¿Cuándo ocurrió?". |
| CA3 | Confirmar el envío | La app muestra un resumen y envía solo al confirmar. El envío es **idempotente** (`Idempotency-Key`), así que reintentar tras una falla de red nunca crea dos siniestros. |
| CA4 | Generar un identificador | `siniestro_id` (UUID) y un folio legible `numero` = `SIN-AAAA-XXXXXXXX`. |
| CA5 | Confirmación de registro correcto | `201` con folio, estado `REPORTADO` y `reportado_en`; `GET /siniestros/{id}` permite volver a consultarlo. |

**Fuera de alcance:** evidencias y ubicación (HU4.1.2), asistencia en sitio (HU4.1.3), consulta del estado y línea de tiempo (HU4.2.1), notificaciones (HU4.2.2), siniestro paramétrico (HU4.2.3), evaluación y pago.

**Decisiones de esta historia** (detalle y estado en la sección 11):
- **S1 · Dos pasos.** HU4.1.1 crea el siniestro y HU4.1.2 le adjunta evidencias. Así una evidencia que falle no pierde el reporte (criterio de HU4.1.2) y cada historia se entrega sola.
- **S2 · Dueños.** MS Siniestros es dueño del siniestro y de sus reglas. MS Pólizas es la fuente de verdad de la póliza (propiedad, estado, vigencia, producto). El BFF Móvil valida el token, resuelve el cliente y traduce errores. La app **nunca** envía `cliente_id`.
- **S3 · Idempotencia.** `Idempotency-Key` → columna `clave_idempotencia` (ya existe y es única en `SINIESTRO`).
- **S4 · Catálogo de tipos por producto en una tabla** (`tipo_siniestro`, esquema `insuranceclaims`), con las reglas de evidencia que usará HU4.1.2. Es la **única fuente**: la app, el BFF, la web o el back-office la consultan por la API de MS Siniestros; nadie copia la lista en código. Los productos de vida quedan fuera de la app (no tienen filas).

---

## 1. Estado actual (`origin/dev`, 06/11/2026)

| Pieza | Hoy | Falta |
|---|---|---|
| `insuranceclaims_service` | Esqueleto hexagonal: entidades y modelos `Siniestro`, `Indemnizacion`, `EventoExterno`, `ActivacionParametrica`, `ActivacionPoliza`; repositorio genérico `guardar` / `obtener_por_id`; solo `/health`. Puerto 8005 en compose. | Columnas del siniestro asistido, catálogo, puerto de pólizas, casos de uso, router, errores. |
| `insurancepolicies_service` | Esqueleto: `Poliza` (`cliente_id`, `producto_id`, `numero`, `estado`, vigencias), `PolizaCobertura`; solo `/health`. | Consulta de pólizas por cliente (tarea **#265**, JuanTapia911). |
| `bff_mobile` | JWT de Cognito (`get_cliente_autenticado` → `correo`), `IdentityServiceGateway.obtener_resumen_movil` (devuelve `id`), errores comunes `ApiError`. | Gateway de Siniestros, resolución de `cliente_id`, router `/siniestros`. |

---

## 2. Responsabilidades y flujo

| Servicio | Es dueño de | No sabe |
|---|---|---|
| `bff_mobile` | Validar el token, obtener `cliente_id` desde Identidad, validar forma y tamaño del request, `Idempotency-Key` obligatorio, traducir errores al formato común | Reglas de vigencia, catálogo, folios |
| `insuranceclaims_service` | Catálogo de tipos, reglas del reporte, idempotencia, folio, persistencia, autorización por dueño del siniestro | Cognito, correos |
| `insurancepolicies_service` | Pólizas del cliente, estado, vigencia, producto | Siniestros |
| `identity_service` | `cliente_id` a partir del correo (`GET /clientes/resumen-movil`, ya existe) | — |

```
1) App ─ GET /siniestros/polizas-elegibles ─► BFF ─ correo (JWT) ─► Identity resumen-movil → cliente_id (caché 5 min)
                                                 └─► Siniestros GET /siniestros/polizas-elegibles  (X-Cliente-Id)
                                                       ListarPolizasElegibles: PolizasPort.listar_por_cliente → filtra vigentes
                                                       → agrega tipos_siniestro del CatalogoTiposSiniestro por producto
   ◄──── { polizas: [ {poliza, producto, vigencia, tipos_siniestro[]} ] }

2) App ─ POST /siniestros  (Idempotency-Key) ─► BFF ─► Siniestros POST /siniestros (X-Cliente-Id, Idempotency-Key)
        ReportarSiniestro:
          a. ¿existe la clave? → misma huella: devuelve el existente (200) · otra huella: 409
          b. PolizasPort.obtener(poliza_id) → dueño = cliente, estado vigente, ocurrido_en ∈ vigencia
          c. tipo ∈ catálogo del producto; descripción; fecha no futura
          d. crea Siniestro(REPORTADO, canal MOVIL, numero) → commit (UK clave_idempotencia protege la carrera)
   ◄──── 201 { siniestro_id, numero, estado, … }

3) App ─ GET /siniestros/{id} ─► BFF ─► Siniestros (solo si el siniestro es del cliente; si no, 404)
```

Reglas transversales:
- **Sin datos personales en logs**: no se registra la descripción ni el correo; el cliente solo como hash corto (igual que `_log_auth`).
- `X-Correlation-Id` de punta a punta (middleware que ya existe en los tres servicios).
- MS Pólizas caído o con timeout → `503 SERVICIO_NO_DISPONIBLE`; **no** se crea nada.
- 404 uniforme: una póliza o un siniestro de otro cliente responde igual que uno inexistente (no se revela su existencia).

---

## 3. Contrato público (BFF Móvil) — canónico

Prefijo `/api/v1/bff-mobile`. Todos con `Authorization: Bearer <access_token de Cognito>`. Formato de error común (D6 de HU3.1.1):
```json
{ "codigo": "POLIZA_NO_VIGENTE", "mensaje": "La póliza no está vigente.", "correlation_id": "4b1d…" }
```
Muestras para pruebas de contrato: `docs/contracts/siniestros/*.json` (copia exacta en `app/src/test/resources/contracts/siniestros/`).

### 3.1 `GET /siniestros/polizas-elegibles`

`200`:
```json
{
  "polizas": [
    {
      "poliza_id": "8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10",
      "numero": "SLV-2026-08341",
      "producto": { "codigo": "SEGURO_VIAJE", "nombre": "Seguro de viaje" },
      "vigencia_desde": "2026-03-12",
      "vigencia_hasta": "2027-03-12",
      "tipos_siniestro": [
        { "codigo": "GASTO_MEDICO", "nombre": "Gasto médico", "evidencia": { "fotos_max": 5, "videos_max": 0 } },
        { "codigo": "EQUIPAJE", "nombre": "Pérdida o daño de equipaje", "evidencia": { "fotos_max": 5, "videos_max": 1 } }
      ]
    }
  ]
}
```
- Lista vacía si el cliente no tiene pólizas elegibles (no es error).
- `nombre` del tipo sale de la tabla `tipo_siniestro` en el idioma del header `Accept-Language` (`es` por defecto, `en` si empieza por `en`). La app no tiene una lista propia de tipos.
- `evidencia` la usa HU4.1.2 (`videos_max = 0` ⇒ el tipo no admite video).

Errores: `401` · `404 CLIENTE_NO_REGISTRADO` · `503 SERVICIO_NO_DISPONIBLE`.

### 3.2 `POST /siniestros`

Headers: `Idempotency-Key: <UUID v4>` (**obligatorio**; lo genera la app una vez por reporte y lo reutiliza en los reintentos).

Body (`extra="forbid"`):
```json
{
  "poliza_id": "8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10",
  "tipo": "GASTO_MEDICO",
  "descripcion": "Me atendieron en urgencias por una intoxicación durante el viaje.",
  "ocurrido_en": "2026-11-10T14:30:00-05:00"
}
```
`201` (y `200` con el mismo cuerpo si es un reintento con la misma clave y los mismos datos):
```json
{
  "siniestro_id": "c41f0e2a-9b7d-4e55-8a0c-2f6d1b3e9a77",
  "numero": "SIN-2026-C41F0E2A",
  "estado": "REPORTADO",
  "poliza_id": "8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10",
  "poliza_numero": "SLV-2026-08341",
  "tipo": "GASTO_MEDICO",
  "ocurrido_en": "2026-11-10T19:30:00Z",
  "reportado_en": "2026-11-10T20:02:11Z"
}
```

Validaciones y errores:

| Caso | Respuesta |
|---|---|
| Sin token / token inválido | `401 NO_AUTENTICADO` |
| Falta `Idempotency-Key` o no es UUID | `400 DATOS_INVALIDOS` |
| Cuerpo mal formado, campos extra, `descripcion` fuera de 10–500 caracteres (tras `strip`), `ocurrido_en` sin zona horaria | `422 DATOS_INVALIDOS` |
| `ocurrido_en` en el futuro (tolerancia 5 min) | `422 FECHA_INVALIDA` |
| La póliza no existe o no es del cliente | `404 POLIZA_NO_ENCONTRADA` |
| La póliza no está vigente (estado no elegible) | `409 POLIZA_NO_VIGENTE` |
| `ocurrido_en` fuera de `[vigencia_desde, vigencia_hasta]` | `409 FECHA_FUERA_DE_VIGENCIA` |
| `tipo` no pertenece al catálogo del producto | `422 TIPO_NO_PERMITIDO` |
| Misma `Idempotency-Key` con otros datos | `409 IDEMPOTENCIA_CONFLICTO` |
| MS Pólizas, Identidad o Siniestros no disponibles | `503 SERVICIO_NO_DISPONIBLE` |

### 3.3 `GET /siniestros/{siniestro_id}`

`200`: mismo cuerpo de 3.2. HU4.1.2 le agrega `ubicacion` y `evidencias`.
Errores: `401` · `404 SINIESTRO_NO_ENCONTRADO` (inexistente o de otro cliente) · `503`.

---

## 4. MS Siniestros (`insuranceclaims_service`)

`API_PREFIX = /api/v1/insuranceclaims-service`. Estructura existente: `src/domain`, `src/application`, `src/infrastructure`, `src/presentation`, `src/core`.

### 4.1 Dominio — `src/domain/siniestros/`

**`entities.py` (modificar `Siniestro`)** — campos nuevos, todos con valor por defecto para no romper el flujo paramétrico:

| Campo | Tipo | Nota |
|---|---|---|
| `cliente_id` | `uuid.UUID \| None` | Dueño. Obligatorio en el canal móvil. |
| `numero` | `str` | Folio legible, único. |
| `canal` | `CanalReporte` | `MOVIL` en esta historia; `PARAMETRICO` para HU4.2.3. |
| `descripcion` | `str \| None` | 10–500 caracteres en el canal móvil. |
| `poliza_numero` | `str \| None` | Copia del número para mostrar sin llamar a Pólizas. |
| `producto_codigo` | `str \| None` | Copia del producto; HU4.1.2 lo usa para leer las reglas de evidencia del catálogo sin llamar a Pólizas. |
| `huella_solicitud` | `str \| None` | SHA-256 del cuerpo normalizado, para detectar reuso de la clave con otros datos. |

**`enums.py` (nuevo)**
- `EstadoSiniestro(str, Enum)`: `REPORTADO`, `EN_EVALUACION`, `APROBADO`, `RECHAZADO`, `PAGADO`. Solo se usa `REPORTADO`; el resto se define ahora para HU4.2.1.
- `CanalReporte(str, Enum)`: `MOVIL`, `PARAMETRICO`.

**`catalogo.py` (nuevo) — objetos de valor y puerto del catálogo**
```python
@dataclass(frozen=True)
class ReglasEvidencia:
    fotos_max: int
    videos_max: int          # 0 ⇒ no admite video

@dataclass(frozen=True)
class TipoSiniestro:
    producto_codigo: str
    codigo: str
    nombre: str              # en el idioma pedido
    reglas: ReglasEvidencia

class CatalogoTiposSiniestro(ABC):
    """Lectura de la tabla `tipo_siniestro`: única fuente de los tipos por producto."""
    async def tipos_de(self, producto_codigo: str, idioma: str = "es") -> list[TipoSiniestro]: ...   # solo activos, por `orden`; vacío ⇒ el producto no se reporta por la app
    async def obtener(self, producto_codigo: str, tipo_codigo: str, idioma: str = "es") -> TipoSiniestro | None: ...
    async def listar(self, producto_codigo: str | None = None, idioma: str = "es") -> list[TipoSiniestro]: ...
```

**Tabla de referencia `tipo_siniestro` (esquema `insuranceclaims`)**

| Columna | Tipo | Nota |
|---|---|---|
| `tipo_siniestro_id` | `uuid` PK | |
| `producto_codigo` | `varchar(50)` | Código de `producto_seguro.codigo` del Motor de Cotización (fuente de los productos). Sin FK entre esquemas. |
| `codigo` | `varchar(40)` | `UNIQUE (producto_codigo, codigo)` |
| `nombre` | `varchar(100)` | Español |
| `nombre_en` | `varchar(100)` | Inglés |
| `fotos_max` | `smallint` | `CHECK (fotos_max BETWEEN 0 AND 10)` |
| `videos_max` | `smallint` | `CHECK (videos_max BETWEEN 0 AND 3)`; `0` ⇒ no admite video |
| `activo` | `boolean` | Desactivar un tipo no borra los siniestros que lo usan |
| `orden` | `smallint` | Orden en pantalla |

Contenido inicial (**aprobado**; códigos de producto del seed de `quotingengine_service`):

| `producto_codigo` | `codigo` | `nombre` / `nombre_en` | Fotos | Videos | En la app |
|---|---|---|---|---|---|
| `SEGURO_VIAJE` | `GASTO_MEDICO` | Gasto médico / Medical expense | 5 | 0 | Sí |
| `SEGURO_VIAJE` | `EQUIPAJE` | Pérdida o daño de equipaje / Lost or damaged luggage | 5 | 1 | Sí |
| `SEGURO_VIAJE` | `CANCELACION_VIAJE` | Cancelación del viaje / Trip cancellation | 3 | 0 | Sí |
| `PROTECCION_DISPOSITIVOS` | `DANO_DISPOSITIVO` | Daño al dispositivo / Device damage | 5 | 1 | Sí |
| `PROTECCION_DISPOSITIVOS` | `ROBO` | Robo / Theft | 3 | 1 | Sí |
| `MICROSEGURO_VIDA` | — | Sin filas | — | — | No: lo reportan los beneficiarios por el canal asistido |
| `VIDA_HIPOTECARIO` | — | Sin filas | — | — | No: ídem |

Quién la consulta (siempre por MS Siniestros, nunca con una copia):
- `ListarPolizasElegiblesUseCase` y `ReportarSiniestroUseCase` (esta historia).
- `SolicitarCargaEvidenciaUseCase` (HU4.1.2, reglas de evidencia).
- `GET /tipos-siniestro` (4.6) para la web, el back-office o el flujo paramétrico (HU4.2.3).

**`folio.py` (nuevo)** — `generar_numero(siniestro_id: UUID, reportado_en: datetime) -> str` → `SIN-{año}-{8 primeros hex en mayúscula}`. Es portable (no usa secuencias de Postgres, así funciona en SQLite de pruebas); la columna es única y el caso de uso reintenta una vez con un `siniestro_id` nuevo si choca.

**`errores.py` (nuevo)** — excepciones de dominio con `codigo`: `PolizaNoEncontrada`, `PolizaNoVigente`, `FechaFueraDeVigencia`, `FechaInvalida`, `TipoNoPermitido`, `IdempotenciaConflicto`, `SiniestroNoEncontrado`, `ServicioNoDisponible`.

**`repositories.py` (ampliar `SiniestroRepository`)**
- `obtener_por_clave_idempotencia(clave: str) -> Siniestro | None`
- `obtener_de_cliente(siniestro_id: UUID, cliente_id: UUID) -> Siniestro | None`

### 4.2 Puerto de pólizas — `src/application/ports/polizas.py` (nuevo)

```python
@dataclass(frozen=True)
class PolizaResumen:
    poliza_id: UUID
    cliente_id: UUID
    numero: str
    estado: str
    producto_codigo: str
    producto_nombre: str
    vigencia_desde: date
    vigencia_hasta: date

class PolizasPort(Protocol):
    async def listar_por_cliente(self, cliente_id: UUID, correlation_id: str) -> list[PolizaResumen]: ...
    async def obtener(self, poliza_id: UUID, correlation_id: str) -> PolizaResumen | None: ...

class PolizasNoDisponibles(Exception): ...
```
- Regla de elegibilidad en el caso de uso: `estado ∈ ESTADOS_POLIZA_ELEGIBLES` (config, por defecto `VIGENTE`) y hoy ∈ vigencia.

### 4.3 Adaptadores — `src/infrastructure/gateways/`

| Clase | Qué hace |
|---|---|
| `HttpPolizasClient` | `httpx.AsyncClient` con `POLIZAS_TIMEOUT_SECONDS` (3 s). Llama al endpoint interno de MS Pólizas (dependencia **DEP-1**, sección 10), propaga `X-Correlation-Id`, mapea `404 → None`, `5xx`/timeout/conexión → `PolizasNoDisponibles`. Valida la respuesta con un schema Pydantic propio (no confía en la forma). |
| `PolizasEnMemoria` | **Excepción transitoria** mientras #265 no esté en `dev`: lee pólizas semilla de `POLIZAS_SEMILLA_PATH` (JSON, sin datos reales). Se elige con `POLIZAS_ADAPTER=memoria`; el valor por defecto es `http`. Se retira cuando #265 llegue a `dev`. |
| `crear_polizas_port(settings)` | Factory que devuelve el adaptador según `POLIZAS_ADAPTER`. |

### 4.4 Casos de uso — `src/application/use_cases/`

**`listar_polizas_elegibles_use_case.py`**
```python
class ListarPolizasElegiblesUseCase:
    def __init__(self, polizas: PolizasPort, catalogo: CatalogoTiposSiniestro, reloj: Callable[[], datetime]) -> None: ...
    async def ejecutar(self, cliente_id: UUID, correlation_id: str) -> list[PolizaElegible]: ...
```
Filtra estado y vigencia, descarta productos sin tipos en el catálogo y ordena por `vigencia_hasta` descendente.

**`reportar_siniestro_use_case.py`**
```python
@dataclass(frozen=True)
class ReporteSiniestroCmd:
    cliente_id: UUID
    clave_idempotencia: str
    poliza_id: UUID
    tipo: str
    descripcion: str
    ocurrido_en: datetime          # con zona; se guarda en UTC

class ReportarSiniestroUseCase:
    def __init__(self, repo: SiniestroRepository, polizas: PolizasPort, catalogo: CatalogoTiposSiniestro,
                 reloj: Callable[[], datetime], session: AsyncSession) -> None: ...
    async def ejecutar(self, cmd: ReporteSiniestroCmd, correlation_id: str) -> ResultadoReporte: ...
```
Pasos, en este orden:
1. `huella = sha256(json normalizado de {cliente_id, poliza_id, tipo, descripcion, ocurrido_en en UTC})`.
2. `existente = repo.obtener_por_clave_idempotencia(clave)`: si existe y es del mismo cliente con la misma huella → `ResultadoReporte(siniestro, repetido=True)`; si no → `IdempotenciaConflicto`.
3. `ocurrido_en > ahora + 5 min` → `FechaInvalida`.
4. `poliza = polizas.obtener(poliza_id)`; `None` o `poliza.cliente_id != cliente_id` → `PolizaNoEncontrada`; estado no elegible → `PolizaNoVigente`; fecha fuera de vigencia → `FechaFueraDeVigencia`.
5. `catalogo.obtener(poliza.producto_codigo, tipo)` → `None` ⇒ `TipoNoPermitido`.
6. Crea `Siniestro(estado=REPORTADO, canal=MOVIL, reportado_en=ahora, numero=generar_numero(...))`, `guardar`, `commit`.
7. `IntegrityError` en la clave → otra solicitud ganó la carrera: `rollback` y volver al paso 2 (una vez). En el `numero` → regenerar y reintentar una vez.

**`consultar_siniestro_use_case.py`** — `ejecutar(siniestro_id, cliente_id) -> Siniestro` o `SiniestroNoEncontrado`.

### 4.5 Persistencia — `src/infrastructure/persistence/`

- `models.py`, `SiniestroModel`: columnas `cliente_id` (`Uuid`, `index=True`, nullable), `numero` (`String(20)`, `unique=True`, nullable=False), `canal` (`String(20)`, nullable=False, default `PARAMETRICO`), `descripcion` (`String(500)`), `poliza_numero` (`String(50)`), `producto_codigo` (`String(50)`), `huella_solicitud` (`String(64)`). Índice compuesto `ix_siniestro_cliente_reportado (cliente_id, reportado_en)` para HU4.2.1.
- `siniestros_repository_impl.py`: implementar los dos métodos nuevos con `select(...)`.
- `TipoSiniestroModel` (`tipo_siniestro`) con las columnas, la restricción única y los `CHECK` de 4.1; `SqlAlchemyCatalogoTiposSiniestro` implementa el puerto, con caché en memoria de 5 min (la tabla casi no cambia).
- **Carga inicial:** `src/infrastructure/persistence/seed_tipos_siniestro.py` con las filas de 4.1, ejecutado en el `lifespan` después de `create_all` con *upsert* por `(producto_codigo, codigo)` (idempotente, igual que el seed de `quotingengine_service`). Cambiar el catálogo = cambiar el seed o la tabla, no los casos de uso.
- **Migración:** el servicio usa `create_all` (no altera tablas existentes). Agregar `scripts/sql/insuranceclaims_hu4_1_1.sql` con los `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` e índices, para aplicarlo en la RDS de dev. Si la tabla está vacía en dev, también vale borrar el esquema `insuranceclaims` y dejar que `create_all` lo recree (acordarlo con Danny).

### 4.6 Presentación — `src/presentation/`

- `routers/siniestros.py` (`APIRouter(prefix="/siniestros")`, montado con `API_PREFIX`). **Solo red interna** (Service `ClusterIP`, sin ingress):

| Método y ruta | Headers | Caso de uso |
|---|---|---|
| `GET /siniestros/polizas-elegibles` | `X-Cliente-Id` | `ListarPolizasElegiblesUseCase` |
| `POST /siniestros` | `X-Cliente-Id`, `Idempotency-Key` | `ReportarSiniestroUseCase` (`201` nuevo, `200` repetido) |
| `GET /siniestros/{siniestro_id}` | `X-Cliente-Id` | `ConsultarSiniestroUseCase` |
| `GET /tipos-siniestro?producto_codigo=` | `Accept-Language` | `CatalogoTiposSiniestro.listar` (consulta de referencia para otros consumidores; sin datos del cliente) |

- El idioma de `nombre` sale de `Accept-Language` (el BFF lo reenvía desde la app).

- `schemas/siniestros.py`: `ReportarSiniestroRequest` (`extra="forbid"`, `descripcion: constr(strip_whitespace=True, min_length=10, max_length=500)`, `ocurrido_en: AwareDatetime`, `tipo: constr(pattern=r"^[A-Z_]{3,40}$")`), `SiniestroResponse`, `PolizasElegiblesResponse`.
- `errors.py`: handler de las excepciones de dominio → `HTTPException(status, detail={"codigo", "mensaje"})`, como Identity. `PolizasNoDisponibles` → `503`.
- `dependencies.py`: `get_polizas_port`, `get_catalogo`, `get_reloj`, y las factories de los casos de uso. `X-Cliente-Id` se valida como UUID (`422` si no).
- `main.py`: `app.include_router(siniestros.router, prefix=settings.API_PREFIX)` y el handler de errores.
- `core/config.py`: `POLIZAS_ADAPTER="http"`, `INSURANCEPOLICIES_SERVICE_URL="http://localhost:8004"`, `POLIZAS_TIMEOUT_SECONDS=3.0`, `POLIZAS_SEMILLA_PATH=""`, `ESTADOS_POLIZA_ELEGIBLES="VIGENTE"`.
- `requirements.txt`: agregar `httpx`.

---

## 5. BFF Móvil (`bff_mobile`)

| Archivo | Cambio |
|---|---|
| `src/infrastructure/gateways/insuranceclaims_service_gateway.py` (nuevo) | `InsuranceClaimsServiceGateway` (igual a `IdentityServiceGateway`): `listar_polizas_elegibles(cliente_id, correlation_id)`, `reportar_siniestro(cliente_id, clave, body, correlation_id) -> tuple[int, dict]` (devuelve el status para distinguir `201`/`200`), `obtener_siniestro(cliente_id, siniestro_id, correlation_id)`. Timeout `CLAIMS_TIMEOUT_SECONDS=8`. Errores → `ClaimsGatewayError(status, detail)`. |
| `src/presentation/cliente_resolver.py` (nuevo) | `ClienteIdResolver`: `correo → cliente_id` con `IdentityServiceGateway.obtener_resumen_movil(correo, None)`. Caché en memoria por correo con TTL `CLIENTE_ID_CACHE_SECONDS=300` (táctica: reducir llamadas repetidas). `404` de Identidad → `ApiError(404, "CLIENTE_NO_REGISTRADO")`; caída → `503`. |
| `src/presentation/dependencies.py` | `get_cliente_id` (usa `get_cliente_autenticado` + resolver) y `get_insuranceclaims_service_gateway`. |
| `src/presentation/errors.py` | Generalizar `ApiError.desde_identidad` en `desde_servicio(status, detail)` (mismo comportamiento; `desde_identidad` queda como alias). Agregar los códigos de la sección 3 a los mensajes por defecto. |
| `src/presentation/schemas.py` | Schemas públicos de la sección 3 (`extra="forbid"` en el request). |
| `src/presentation/routers/siniestros.py` (nuevo) | Los 3 endpoints de la sección 3. Valida `Idempotency-Key` (UUID). Reenvía `Accept-Language` a Siniestros. Propaga el status del servicio (`201`/`200`). Nunca registra la descripción. |
| `src/main.py` | `include_router(siniestros.router, prefix=settings.API_PREFIX)`. |
| `src/core/config.py` | `INSURANCECLAIMS_SERVICE_URL`, `CLAIMS_TIMEOUT_SECONDS`, `CLIENTE_ID_CACHE_SECONDS`. |

---

## 6. Patrones y tácticas

| Táctica / patrón | Atributo | Dónde |
|---|---|---|
| Puertos y adaptadores (encapsular) | Modificabilidad | `PolizasPort` con `HttpPolizasClient` y `PolizasEnMemoria`; Siniestros no conoce la API de Pólizas. |
| Diferir el enlace (configuración) | Modificabilidad | `POLIZAS_ADAPTER` elige el adaptador sin tocar código; `ESTADOS_POLIZA_ELEGIBLES` por entorno. |
| Tabla de referencia como única fuente (parametrización) | Modificabilidad, consistencia | `tipo_siniestro` detrás del puerto `CatalogoTiposSiniestro`: agregar un producto o tipo es una fila; todos los consumidores leen lo mismo. |
| Intermediario (BFF por canal) | Modificabilidad, seguridad | La app solo habla con el BFF Móvil; Siniestros y Pólizas no se publican. |
| Operación idempotente + reintento | Disponibilidad | `Idempotency-Key` + `UNIQUE(clave_idempotencia)`; la app reintenta sin duplicar. |
| Timeout y fallo explícito | Disponibilidad | 3 s hacia Pólizas, 8 s hacia Siniestros; `503` sin efectos parciales. |
| Autenticar y autorizar actores | Seguridad | JWT de Cognito en el BFF; el dueño de la póliza y del siniestro se valida en Siniestros. |
| Limitar la exposición | Seguridad | `cliente_id` nunca viaja desde la app; `404` uniforme para recursos ajenos. |
| Validar la entrada | Seguridad | Schemas `extra="forbid"`, longitudes, zona horaria, patrón del tipo. |
| Trazabilidad | Auditabilidad | `X-Correlation-Id`, `reportado_en`, `canal`, logs sin PII. |
| Caché con TTL | Rendimiento | `ClienteIdResolver` en el BFF. |

---

## 7. Configuración y despliegue

| Archivo | Cambio |
|---|---|
| `docker-compose.yml` | `insuranceclaims_service`: `INSURANCEPOLICIES_SERVICE_URL=http://insurancepolicies_service:8000`, `POLIZAS_ADAPTER=${POLIZAS_ADAPTER:-memoria}` (mientras falte DEP-1), `POLIZAS_SEMILLA_PATH=/app/seed/polizas.json`. `bff_mobile`: `INSURANCECLAIMS_SERVICE_URL=http://insuranceclaims_service:8000`, `depends_on`. |
| `insuranceclaims_service/seed/polizas.json` (nuevo) | 2–3 pólizas ficticias (viaje y dispositivos, una vencida) para el adaptador en memoria. Sin datos reales. |
| `.env.example` | Variables nuevas sin secretos. |
| `deployment/helm/config/insuranceclaims_service/values*.yaml` | Variables nuevas; `ClusterIP`, sin ingress. |
| `deployment/helm/config/bff_mobile/values*.yaml` | `INSURANCECLAIMS_SERVICE_URL: http://insuranceclaims-service:80`. |
| `.github/workflows/ci.yml` | Verificar que `insuranceclaims_service` está en las matrices `test` y `build` (lo agregó Danny; si no, agregarlo). |
| `scripts/sql/insuranceclaims_hu4_1_1.sql` | `ALTER TABLE` de la sección 4.5. |

---

## 8. Pruebas (pytest, `asyncio_mode = auto`)

| Servicio | Archivo | Casos mínimos |
|---|---|---|
| claims | `unit/test_catalogo.py` (SQLite) | seed idempotente (dos ejecuciones = mismas filas); tipos por producto en orden; inactivos excluidos; productos de vida → vacío; `obtener` inexistente → `None`; idioma `es`/`en`. |
| claims | `unit/test_folio.py` | formato `SIN-AAAA-XXXXXXXX`; año de `reportado_en`. |
| claims | `unit/test_listar_polizas_elegibles.py` (puerto falso) | filtra estado y vigencia; descarta productos sin catálogo; orden; lista vacía. |
| claims | `unit/test_reportar_siniestro.py` (puerto falso, SQLite) | éxito; póliza ajena → `PolizaNoEncontrada`; no vigente; fuera de vigencia (bordes inclusivos); fecha futura (tolerancia); tipo no permitido; repetido con la misma huella → `repetido=True`; misma clave con otros datos → conflicto; Pólizas caído → `ServicioNoDisponible` sin guardar nada. |
| claims | `unit/test_http_polizas_client.py` (`httpx.MockTransport`) | mapeo 200/404/500/timeout; propaga `X-Correlation-Id`; respuesta mal formada → no disponible. |
| claims | `integration/test_siniestros_api.py` (SQLite) | los 3 endpoints, `201` y `200`, todos los códigos de la sección 3, `X-Cliente-Id` faltante o inválido. |
| claims | `integration/test_idempotencia_postgres.py` (`@pytest.mark.postgres`, contra el Postgres de compose) | 10 `POST` simultáneos con la misma clave crean **un** siniestro y todos responden el mismo `siniestro_id`. |
| bff | `unit/test_cliente_resolver.py` | caché y TTL; 404 → `CLIENTE_NO_REGISTRADO`; Identidad caída → 503. |
| bff | `integration/test_siniestros_api.py` (gateways falsos) | 401; `Idempotency-Key` faltante o inválida; `extra="forbid"`; traducción de errores; propaga `201`/`200`; `correlation_id` en el error. |
| bff | `contract/test_siniestros_contract.py` | las muestras de `docs/contracts/siniestros/*.json` validan contra los schemas públicos. |
| todos | `unit/test_sin_pii_en_logs.py` (`caplog`) | en un reporte completo los logs no contienen la descripción, el correo ni el token. |

Muestras de contrato: `polizas-elegibles.json`, `reporte-request.json`, `reporte-response.json`, `error-poliza-no-vigente.json`.

---

## 9. Reglas para el agente que implementa

1. Rama `feat/HU4.1.1-registrar-siniestro`. **No hacer commit ni push** hasta que Sergio lo indique.
2. Seguir el estilo del monorepo: async, dominio en español, `pydantic-settings`, telemetría y correlación de `src/core`.
3. No tocar las entidades paramétricas (`EventoExterno`, `ActivacionParametrica`, `ActivacionPoliza`) más allá de lo que exige la sección 4.5.
4. Nunca registrar la descripción, el correo ni el token. Nunca aceptar `cliente_id` desde la app.
5. Orden: T-B01 → T-B06 (sección 12). Al terminar cada tarea: pruebas en verde y lista de archivos tocados para la revisión.

---

## 10. Dependencias con otras historias

| ID | Dependencia | Dueño | Mientras tanto |
|---|---|---|---|
| DEP-1 | ✅ **Resuelta el 13/11/2026** con `GET /polizas/mis-polizas` y `GET /polizas/{id}` (header `X-Client-Id`, respuesta con `producto_id`; el código y el nombre del producto se leen de `GET /productos` del Motor de Cotización). Texto original: endpoint **interno** de MS Pólizas: `GET /api/v1/insurancepolicies-service/polizas?cliente_id=…` y `GET /polizas/{poliza_id}`, con `numero`, `estado`, vigencias, `producto_codigo` y `producto_nombre`. La tarea #265 define `GET /polizas/mis-polizas` con JWT para el BFF Web: hay que acordar con JuanTapia911 la variante interna (o que acepte `X-Cliente-Id`) y que incluya el producto. | JuanTapia911 (#265) | `PolizasEnMemoria` (`POLIZAS_ADAPTER=memoria`). |
| DEP-2 | Valores reales de `poliza.estado` (¿`VIGENTE`, `EMITIDA`, `CANCELADA`, `VENCIDA`?). | JuanTapia911 | `ESTADOS_POLIZA_ELEGIBLES=VIGENTE`. |
| DEP-3 | La billetera (HU3.2.1, asr88) también lista pólizas en el BFF Móvil. Este endpoint es solo para el reporte (incluye tipos de siniestro); si la billetera crea `GET /polizas`, no se duplican reglas: cada uno consume MS Pólizas. | asr88 | — |

---

## 11. Decisiones

| ID | Tema | Estado |
|---|---|---|
Aprobadas por Sergio Gelvez el 07/11/2026.

| ID | Tema | Estado |
|---|---|---|
| S1 | Reporte y evidencias en dos pasos (HU4.1.1 crea, HU4.1.2 adjunta) | **Aprobada** |
| S2 | Dueños: Siniestros (siniestro), Pólizas (póliza), BFF (token y cliente); la app no envía `cliente_id` | **Aprobada** |
| S3 | Idempotencia con `Idempotency-Key` sobre `clave_idempotencia` única; reintento → `200` con el mismo cuerpo, otros datos → `409` | **Aprobada** |
| S4 | Catálogo de tipos por producto en la tabla `tipo_siniestro` (única fuente, consultada por la API de Siniestros); productos de vida fuera de la app | **Aprobada** |
| S5 | Folio `SIN-AAAA-XXXXXXXX` derivado del UUID (portable, sin secuencias) | **Aprobada** |
| S6 | Adaptador de pólizas en memoria como excepción transitoria hasta DEP-1 | **Aprobada** |
| S7 | Migración con script `ALTER` (sin Alembic, como el resto del monorepo); avisar a Danny antes de aplicarlo en dev | **Aprobada** |

---

## 12. Tareas (tarjetas) y criterio de terminado

| ID | Tarea | Estimación |
|---|---|---|
| T-B01 | Dominio y persistencia del siniestro asistido y tabla `tipo_siniestro` con su carga inicial (4.1, 4.5) | 2,5 h |
| T-B02 | Integración con MS Pólizas: puerto y adaptadores (4.2, 4.3) | 1,5 h |
| T-B03 | Casos de uso y API interna de Siniestros (4.4, 4.6) | 2,5 h |
| T-B04 | Endpoints públicos en el BFF Móvil (5) | 1,5 h |
| T-B05 | Contrato, configuración y despliegue (3, 7) | 1 h |
| T-B06 | Pruebas backend (8) | 2 h |

Estimaciones con el descuento por uso de IA, como la historia base del equipo (HU5.1.4: 3 puntos = 7 h).

**Terminado cuando:**
1. Pruebas en verde en `insuranceclaims_service` y `bff_mobile` (incluida la de idempotencia en Postgres).
2. Flujo con `docker compose`: listar pólizas → reportar → consultar, con el mismo `X-Correlation-Id` en los logs del BFF y de Siniestros.
3. Reintento con la misma clave sin duplicados (evidencia: un solo registro en la tabla).
4. Pruebas de contrato en verde en backend y app con las mismas muestras.
5. Sin PII en logs (prueba + búsqueda en los logs del flujo).
6. Documentación: README de `insuranceclaims_service`, modelo de datos de la wiki (columnas nuevas de `SINIESTRO`) y `contratos-pendientes.md` de la app.
