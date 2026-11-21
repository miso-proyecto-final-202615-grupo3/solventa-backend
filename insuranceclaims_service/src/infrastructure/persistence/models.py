import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


def _fk(target: str) -> str:
    schema = Base.metadata.schema
    return f"{schema}.{target}" if schema else target


class EventoExternoModel(Base):
    __tablename__ = "evento_externo"

    evento_externo_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    fuente: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    checksum: Mapped[str] = mapped_column(String(255), nullable=False)
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recibido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_referencia: Mapped[str] = mapped_column(String(2048), nullable=False)

    activaciones: Mapped[list["ActivacionParametricaModel"]] = relationship(back_populates="evento_externo")


class EventoOutboxModel(Base):
    __tablename__ = "evento_outbox"
    __table_args__ = (Index("ix_evento_outbox_estado_creado", "estado", "creado_en"),)
    evento_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    agregado_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE")
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActivacionParametricaModel(Base):
    __tablename__ = "activacion_parametrica"

    activacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evento_externo_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(_fk("evento_externo.evento_externo_id")), nullable=False, index=True
    )
    cobertura_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    regla_aplicada: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[str] = mapped_column(String(50), nullable=False)
    clave_idempotencia: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    activada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evento_externo: Mapped["EventoExternoModel"] = relationship(back_populates="activaciones")
    polizas: Mapped[list["ActivacionPolizaModel"]] = relationship(back_populates="activacion")
    siniestros: Mapped[list["SiniestroModel"]] = relationship(back_populates="activacion")


class ActivacionPolizaModel(Base):
    __tablename__ = "activacion_poliza"

    activacion_poliza_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    activacion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(_fk("activacion_parametrica.activacion_id")), nullable=False, index=True
    )
    poliza_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    estado: Mapped[str] = mapped_column(String(50), nullable=False)
    clave_idempotencia: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    identificada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    activacion: Mapped["ActivacionParametricaModel"] = relationship(back_populates="polizas")


class SiniestroModel(Base):
    __tablename__ = "siniestro"

    siniestro_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    poliza_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    activacion_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(_fk("activacion_parametrica.activacion_id")), nullable=True, index=True
    )
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    estado: Mapped[str] = mapped_column(String(50), nullable=False)
    clave_idempotencia: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reportado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidencia_referencia: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    # Siniestro asistido reportado desde la app (HU4.1.1).
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    canal: Mapped[str] = mapped_column(String(20), nullable=False, default="PARAMETRICO")
    descripcion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    poliza_numero: Mapped[str | None] = mapped_column(String(50), nullable=True)
    producto_codigo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    huella_solicitud: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Ubicación del evento (HU4.1.2).
    ubicacion_latitud: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    ubicacion_longitud: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    ubicacion_precision_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    ubicacion_fuente: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ubicacion_capturada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ubicacion_actualizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estado_actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_siniestro_cliente_reportado", "cliente_id", "reportado_en"),)

    activacion: Mapped["ActivacionParametricaModel | None"] = relationship(back_populates="siniestros")
    indemnizacion: Mapped["IndemnizacionModel | None"] = relationship(back_populates="siniestro")


class IndemnizacionModel(Base):
    __tablename__ = "indemnizacion"

    indemnizacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    siniestro_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(_fk("siniestro.siniestro_id")), nullable=False, unique=True
    )
    monto_aprobado: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False)
    estado: Mapped[str] = mapped_column(String(50), nullable=False)
    aprobada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    siniestro: Mapped["SiniestroModel"] = relationship(back_populates="indemnizacion")


class TipoSiniestroModel(Base):
    """Fuente única de los tipos de siniestro por producto y sus reglas de evidencia (HU4.1.1, S4)."""

    __tablename__ = "tipo_siniestro"
    __table_args__ = (
        UniqueConstraint("producto_codigo", "codigo", name="uq_tipo_siniestro_producto_codigo"),
        CheckConstraint("fotos_max BETWEEN 0 AND 10", name="ck_tipo_siniestro_fotos_max"),
        CheckConstraint("videos_max BETWEEN 0 AND 3", name="ck_tipo_siniestro_videos_max"),
    )

    tipo_siniestro_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Código de `producto_seguro.codigo` del Motor de Cotización; sin FK entre esquemas.
    producto_codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    nombre_en: Mapped[str] = mapped_column(String(100), nullable=False)
    fotos_max: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    videos_max: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    orden: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)


class EvidenciaSiniestroModel(Base):
    """Evidencias del siniestro asistido (HU4.1.2): una fila por foto o video, con su estado."""

    __tablename__ = "evidencia_siniestro"
    __table_args__ = (
        Index("ix_evidencia_siniestro_tipo_estado", "siniestro_id", "tipo", "estado"),
        UniqueConstraint("siniestro_id", "clave_idempotencia", name="uq_evidencia_siniestro_clave"),
    )

    evidencia_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    siniestro_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(_fk("siniestro.siniestro_id")), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tamano_declarado: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tamano_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    origen: Mapped[str] = mapped_column(String(10), nullable=False)
    capturada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    objeto_clave: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    solicitada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cargada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_rechazo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    clave_idempotencia: Mapped[str | None] = mapped_column(String(36), nullable=True)
