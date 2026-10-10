import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, String, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.domain.clientes.value_objects import EstadoKYC


class ClienteModel(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        UniqueConstraint("correo", name="uq_clientes_correo"),
        UniqueConstraint(
            "tipo_documento",
            "numero_identificacion",
            name="uq_clientes_tipo_documento_numero",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    nombres: Mapped[str] = mapped_column(String(100), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo_documento: Mapped[str] = mapped_column(
        String(3), nullable=False, default="CC"
    )
    numero_identificacion: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )
    correo: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    fecha_nacimiento: Mapped[date] = mapped_column(Date, nullable=False)
    pais_residencia: Mapped[str] = mapped_column(String(60), nullable=False)
    telefono: Mapped[str] = mapped_column(String(20), nullable=False)
    estado_kyc: Mapped[EstadoKYC] = mapped_column(
        Enum(EstadoKYC, name="estado_kyc", native_enum=False, length=20),
        nullable=False,
        default=EstadoKYC.PENDIENTE,
        server_default=EstadoKYC.PENDIENTE.value,
    )
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )