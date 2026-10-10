from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.repositories import ClienteRepository
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