import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


def _fk(target: str) -> str:
    schema = Base.metadata.schema
    return f"{schema}.{target}" if schema else target


class SocioModel(Base):
    __tablename__ = "socios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo_socio: Mapped[str] = mapped_column(String(60), nullable=False)
    canal_integracion: Mapped[str] = mapped_column(String(60), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE"
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    registrado_por: Mapped[str] = mapped_column(String(100), nullable=False)


class EventoSocioModel(Base):
    __tablename__ = "eventos_socio"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    socio_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(_fk("socios.id")), nullable=False, index=True
    )
    accion: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
