from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.repositories import ClienteRepository
from src.domain.clientes.value_objects import EstadoKYC
from src.infrastructure.persistence.models import ClienteModel


class SqlAlchemyClienteRepository(ClienteRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def existe_por_correo(self, correo: str) -> bool:
        result = await self.session.execute(
            select(ClienteModel.id).where(
                func.lower(ClienteModel.correo) == correo.lower()
            )
        )
        return result.scalar_one_or_none() is not None

    async def existe_por_documento(
        self, tipo_documento: str, numero_identificacion: str
    ) -> bool:
        result = await self.session.execute(
            select(ClienteModel.id).where(
                ClienteModel.tipo_documento == tipo_documento,
                ClienteModel.numero_identificacion == numero_identificacion,
            )
        )
        return result.scalar_one_or_none() is not None

    async def guardar(self, cliente: Cliente) -> None:
        db_obj = ClienteModel(
            id=cliente.id.value,
            nombres=cliente.nombres,
            apellidos=cliente.apellidos,
            tipo_documento=cliente.tipo_documento,
            numero_identificacion=cliente.numero_identificacion,
            correo=cliente.correo,
            fecha_nacimiento=cliente.fecha_nacimiento,
            pais_residencia=cliente.pais_residencia,
            telefono=cliente.telefono,
            estado_kyc=cliente.estado_kyc,
        )
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)

        cliente.id = ClienteId(value=db_obj.id)
        cliente.fecha_creacion = db_obj.fecha_creacion
        cliente.fecha_actualizacion = db_obj.fecha_actualizacion

    async def obtener_por_id(self, cliente_id: ClienteId) -> Cliente | None:
        result = await self.session.execute(
            select(ClienteModel).where(ClienteModel.id == cliente_id.value)
        )
        db_obj = result.scalars().first()
        if db_obj is None:
            return None

        return Cliente(
            id=ClienteId(value=db_obj.id),
            nombres=db_obj.nombres,
            apellidos=db_obj.apellidos,
            tipo_documento=db_obj.tipo_documento,
            numero_identificacion=db_obj.numero_identificacion,
            correo=db_obj.correo,
            fecha_nacimiento=db_obj.fecha_nacimiento,
            pais_residencia=db_obj.pais_residencia,
            telefono=db_obj.telefono,
            estado_kyc=db_obj.estado_kyc,
            fecha_creacion=db_obj.fecha_creacion,
            fecha_actualizacion=db_obj.fecha_actualizacion,
        )

    async def actualizar_estado_kyc(
        self, cliente_id: ClienteId, estado_kyc: EstadoKYC
    ) -> None:
        await self.session.execute(
            update(ClienteModel)
            .where(ClienteModel.id == cliente_id.value)
            .values(estado_kyc=estado_kyc)
        )
        await self.session.commit()