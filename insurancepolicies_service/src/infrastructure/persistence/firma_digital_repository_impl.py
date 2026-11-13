import uuid
from datetime import UTC

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.firmas.entities import EstadoFirma, FirmaDigital
from src.domain.firmas.repositories import FirmaDigitalRepository, FirmaDuplicadaError
from src.infrastructure.persistence.models import FirmaDigitalModel


def _a_entidad(model: FirmaDigitalModel | None) -> FirmaDigital | None:
    if model is None:
        return None
    capturada_en = model.capturada_en
    if capturada_en.tzinfo is None:
        capturada_en = capturada_en.replace(tzinfo=UTC)
    return FirmaDigital(
        firma_id=model.firma_id,
        cliente_id=model.cliente_id,
        cotizacion_id=model.cotizacion_id,
        producto_id=model.producto_id,
        poliza_id=model.poliza_id,
        estado=EstadoFirma(model.estado),
        proveedor_firma=model.proveedor_firma,
        ruta_imagen=model.ruta_imagen,
        content_type=model.content_type,
        tamano_bytes=model.tamano_bytes,
        firma_hash=model.firma_hash,
        fingerprint_contrato=model.fingerprint_contrato,
        idempotency_key=model.idempotency_key,
        correlation_id=model.correlation_id,
        capturada_en=capturada_en,
    )


class SqlAlchemyFirmaDigitalRepository(FirmaDigitalRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def crear(self, firma: FirmaDigital) -> None:
        self.session.add(
            FirmaDigitalModel(
                firma_id=firma.firma_id,
                cliente_id=firma.cliente_id,
                cotizacion_id=firma.cotizacion_id,
                producto_id=firma.producto_id,
                poliza_id=firma.poliza_id,
                estado=firma.estado.value,
                proveedor_firma=firma.proveedor_firma,
                ruta_imagen=firma.ruta_imagen,
                content_type=firma.content_type,
                tamano_bytes=firma.tamano_bytes,
                firma_hash=firma.firma_hash,
                fingerprint_contrato=firma.fingerprint_contrato,
                idempotency_key=firma.idempotency_key,
                correlation_id=firma.correlation_id,
                capturada_en=firma.capturada_en,
            )
        )
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise FirmaDuplicadaError() from exc

    async def obtener_por_idempotency_key(
        self, cliente_id: uuid.UUID, idempotency_key: str
    ) -> FirmaDigital | None:
        result = await self.session.execute(
            select(FirmaDigitalModel)
            .where(
                FirmaDigitalModel.cliente_id == cliente_id,
                FirmaDigitalModel.idempotency_key == idempotency_key,
            )
            .execution_options(populate_existing=True)
        )
        return _a_entidad(result.scalar_one_or_none())

    async def obtener_activa_por_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> FirmaDigital | None:
        result = await self.session.execute(
            select(FirmaDigitalModel)
            .where(
                FirmaDigitalModel.cotizacion_id == cotizacion_id,
                FirmaDigitalModel.estado.in_(
                    (EstadoFirma.CAPTURADA.value, EstadoFirma.VINCULADA.value)
                ),
            )
            .execution_options(populate_existing=True)
        )
        return _a_entidad(result.scalar_one_or_none())

    async def reemplazar_capturada(self, cotizacion_id: uuid.UUID) -> None:
        # Update condicional: si otro request ya reemplazó la firma, no afecta filas.
        await self.session.execute(
            update(FirmaDigitalModel)
            .where(
                FirmaDigitalModel.cotizacion_id == cotizacion_id,
                FirmaDigitalModel.estado == EstadoFirma.CAPTURADA.value,
            )
            .values(estado=EstadoFirma.REEMPLAZADA.value)
            .execution_options(synchronize_session=False)
        )

    async def obtener_por_poliza(self, poliza_id: uuid.UUID) -> FirmaDigital | None:
        result = await self.session.execute(
            select(FirmaDigitalModel)
            .where(
                FirmaDigitalModel.poliza_id == poliza_id,
                FirmaDigitalModel.estado == EstadoFirma.VINCULADA.value,
            )
            .execution_options(populate_existing=True)
        )
        return _a_entidad(result.scalar_one_or_none())

    async def vincular_a_poliza(self, firma_id: uuid.UUID, poliza_id: uuid.UUID) -> bool:
        # Update condicional: solo una firma aún CAPTURADA puede quedar ligada a la póliza.
        result = await self.session.execute(
            update(FirmaDigitalModel)
            .where(
                FirmaDigitalModel.firma_id == firma_id,
                FirmaDigitalModel.estado == EstadoFirma.CAPTURADA.value,
            )
            .values(estado=EstadoFirma.VINCULADA.value, poliza_id=poliza_id)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1
