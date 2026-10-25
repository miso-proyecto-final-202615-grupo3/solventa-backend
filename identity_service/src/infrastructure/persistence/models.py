import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Uuid,
    UniqueConstraint,
    func,
    text,
)
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


class ConsentimientoModel(Base):
    __tablename__ = "consentimientos"
    __table_args__ = (
        UniqueConstraint(
            "cliente_id",
            "fuente_datos",
            "proposito",
            name="uq_consentimiento_cliente_fuente_proposito",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clientes.id"), nullable=False, index=True
    )
    fuente_datos: Mapped[str] = mapped_column(String(60), nullable=False)
    proposito: Mapped[str] = mapped_column(String(120), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    otorgado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    vence_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuditoriaConsentimientoModel(Base):
    __tablename__ = "auditoria_consentimientos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clientes.id"), nullable=False, index=True
    )
    tipo_accion: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version_terminos: Mapped[str] = mapped_column(String(40), nullable=False)
    canal: Mapped[str] = mapped_column(String(20), nullable=False)


class DispositivoVinculadoModel(Base):
    """Vínculo de una instalación activada; nunca almacena evidencia biométrica."""

    __tablename__ = "dispositivos_vinculados"
    __table_args__ = (
        Index(
            "uq_dispositivo_activo_cliente",
            "cliente_id",
            unique=True,
            postgresql_where=text("estado = 'ACTIVO'"),
            sqlite_where=text("estado = 'ACTIVO'"),
        ),
        Index(
            "uq_dispositivo_activo_instalacion",
            "installation_id",
            unique=True,
            postgresql_where=text("estado = 'ACTIVO'"),
            sqlite_where=text("estado = 'ACTIVO'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clientes.id"), nullable=False, index=True
    )
    installation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    plataforma: Mapped[str] = mapped_column(String(10), nullable=False)
    modelo: Mapped[str] = mapped_column(String(100), nullable=False)
    version_so: Mapped[str] = mapped_column(String(20), nullable=False)
    folio_verificacion: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[str] = mapped_column(String(10), nullable=False, default="ACTIVO")
    vinculado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revocado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
