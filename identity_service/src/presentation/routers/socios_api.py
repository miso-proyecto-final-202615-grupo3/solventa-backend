import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.identity_provider import IdentityProviderError
from src.application.use_cases.registrar_cliente_use_case import DuplicateClienteError, RegistrarClienteUseCase
from src.core.config import settings
from src.domain.clientes.entities import ClienteId
from src.infrastructure.persistence.cliente_repository_impl import SqlAlchemyClienteRepository
from src.infrastructure.persistence.models import (
    ClienteModel,
    ClienteSocioModel,
    EventoSocioModel,
    SocioApiKeyModel,
    SocioModel,
)
from src.presentation.dependencies import get_db, get_registrar_cliente_use_case
from src.presentation.routers.clientes import _cliente_response
from src.presentation.schemas.cliente_schemas import ClienteCreate, ClienteResponse, ProspectoCreate

router = APIRouter(prefix="/socios", tags=["API socios"])


class ApiKeyResponse(BaseModel):
    api_key_id: UUID
    fecha_generacion: datetime


class ApiKeyCreadaResponse(ApiKeyResponse):
    api_key: str


class ValidarApiKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr


def _cifrador() -> Fernet:
    try:
        return Fernet(settings.SOCIOS_API_KEY_ENCRYPTION_KEY.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise HTTPException(503, "Cifrado de API keys no configurado correctamente.") from exc


async def _socio(db: AsyncSession, socio_id: UUID) -> SocioModel:
    socio = await db.get(SocioModel, socio_id)
    if socio is None:
        raise HTTPException(404, "Socio no encontrado.")
    return socio


def _respuesta(key: SocioApiKeyModel) -> ApiKeyResponse:
    return ApiKeyResponse(api_key_id=key.id, fecha_generacion=key.generado_en)


@router.post("/{socio_id}/api-keys", response_model=ApiKeyCreadaResponse, status_code=201)
async def crear_api_key(
    socio_id: UUID,
    response: Response,
    actor_id: str = Header(alias="X-Actor-Id", min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreadaResponse:
    socio = await _socio(db, socio_id)
    if socio.estado != "ACTIVO":
        raise HTTPException(403, "El socio no está activo.")
    cifrador = _cifrador()
    valor = secrets.token_urlsafe(32)
    key = SocioApiKeyModel(
        socio_id=socio_id,
        valor_cifrado=cifrador.encrypt(valor.encode()).decode(),
        huella=hashlib.sha256(valor.encode()).hexdigest(),
    )
    db.add(key)
    db.add(
        EventoSocioModel(
            socio_id=socio_id,
            accion="CREDENCIAL_GENERADA",
            actor_id=actor_id,
            ocurrido_en=datetime.now(UTC),
        )
    )
    await db.commit()
    await db.refresh(key)
    response.headers["Cache-Control"] = "no-store"
    return ApiKeyCreadaResponse(**_respuesta(key).model_dump(), api_key=valor)


@router.get("/{socio_id}/api-keys", response_model=list[ApiKeyResponse])
async def listar_api_keys(socio_id: UUID, db: AsyncSession = Depends(get_db)) -> list[ApiKeyResponse]:
    await _socio(db, socio_id)
    keys = await db.scalars(select(SocioApiKeyModel).where(SocioApiKeyModel.socio_id == socio_id).order_by(SocioApiKeyModel.generado_en))
    return [_respuesta(key) for key in keys]


async def _api_key(db: AsyncSession, socio_id: UUID, key_id: UUID) -> SocioApiKeyModel:
    key = await db.scalar(select(SocioApiKeyModel).where(SocioApiKeyModel.id == key_id, SocioApiKeyModel.socio_id == socio_id))
    if key is None:
        raise HTTPException(404, "API key no encontrada.")
    return key


@router.get("/{socio_id}/api-keys/{key_id}", response_model=ApiKeyResponse)
async def consultar_api_key(socio_id: UUID, key_id: UUID, db: AsyncSession = Depends(get_db)) -> ApiKeyResponse:
    return _respuesta(await _api_key(db, socio_id, key_id))


@router.delete("/{socio_id}/api-keys/{key_id}", status_code=204)
async def borrar_api_key(socio_id: UUID, key_id: UUID, db: AsyncSession = Depends(get_db)) -> Response:
    await db.delete(await _api_key(db, socio_id, key_id))
    await db.commit()
    return Response(status_code=204)


@router.post("/validar-api-key")
async def validar_api_key(payload: ValidarApiKeyRequest, db: AsyncSession = Depends(get_db)) -> dict[str, UUID]:
    valor = payload.api_key.get_secret_value()
    huella = hashlib.sha256(valor.encode()).hexdigest()
    result = await db.execute(
        select(SocioApiKeyModel, SocioModel)
        .join(SocioModel, SocioModel.id == SocioApiKeyModel.socio_id)
        .where(SocioApiKeyModel.huella == huella, SocioModel.estado == "ACTIVO")
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(401, "API key inválida.")
    try:
        descifrado = _cifrador().decrypt(row[0].valor_cifrado.encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise HTTPException(503, "No se pudo validar la API key.") from exc
    if not secrets.compare_digest(descifrado, valor):
        raise HTTPException(401, "API key inválida.")
    return {"socio_id": row[1].id}


@router.get("/{socio_id}/clientes/{cliente_id}/autorizacion", status_code=204)
async def validar_autorizacion(socio_id: UUID, cliente_id: UUID, db: AsyncSession = Depends(get_db)) -> Response:
    asociado = await db.get(ClienteSocioModel, (cliente_id, socio_id))
    if asociado is None:
        raise HTTPException(403, "El cliente no está asociado al socio.")
    return Response(status_code=204)


@router.post("/{socio_id}/prospectos", response_model=ClienteResponse, status_code=201)
async def registrar_prospecto(
    socio_id: UUID,
    payload: ProspectoCreate,
    db: AsyncSession = Depends(get_db),
    use_case: RegistrarClienteUseCase = Depends(get_registrar_cliente_use_case),
) -> ClienteResponse:
    socio = await _socio(db, socio_id)
    if socio.estado != "ACTIVO":
        raise HTTPException(403, "El socio no está activo.")
    por_documento = await db.scalar(select(ClienteModel).where(
        ClienteModel.tipo_documento == payload.tipo_documento.value,
        ClienteModel.numero_identificacion == payload.numero_identificacion,
    ))
    por_correo = await db.scalar(select(ClienteModel).where(func.lower(ClienteModel.correo) == str(payload.correo).lower()))
    if por_correo is not None and (por_documento is None or por_correo.id != por_documento.id):
        raise HTTPException(409, "El correo pertenece a otro documento.")
    if por_documento is not None:
        if await db.get(ClienteSocioModel, (por_documento.id, socio_id)) is None:
            try:
                async with db.begin_nested():
                    db.add(ClienteSocioModel(cliente_id=por_documento.id, socio_id=socio_id))
                    await db.flush()
                await db.commit()
            except IntegrityError:
                if await db.get(ClienteSocioModel, (por_documento.id, socio_id)) is None:
                    raise
        cliente = await SqlAlchemyClienteRepository(db).obtener_por_id(ClienteId(value=por_documento.id))
        if cliente is None:
            raise HTTPException(404, "Cliente no encontrado.")
        return _cliente_response(cliente)
    command = ClienteCreate(**payload.model_dump(), password="solv" + payload.numero_identificacion)
    try:
        cliente = await use_case.ejecutar(command, socio_id=socio_id)
    except DuplicateClienteError as exc:
        raise HTTPException(409, exc.detalle) from exc
    except IdentityProviderError as exc:
        raise HTTPException(503, "No se pudo crear la identidad del prospecto.") from exc
    return _cliente_response(cliente)
