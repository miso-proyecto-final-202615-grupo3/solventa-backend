import uuid
from datetime import datetime
from decimal import Decimal

from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

def _fk(target: str) -> str:
    """FK calificada con el esquema (se omite si el metadata no lo tiene, p. ej. tests)."""
    schema = Base.metadata.schema
    return f"{schema}.{target}" if schema else target


class PolizaModel(Base):
    __tablename__ = "poliza"
    __table_args__ = (
        # Una sola póliza por cotización: hace idempotente la emisión ante mensajes duplicados.
        Index("uq_poliza_cotizacion_id", "cotizacion_id", unique=True),
    )

    poliza_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    # cliente, cotización y producto pertenecen a otros servicios: sin FK física
    cliente_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    cotizacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    producto_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    numero: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    vigencia_desde: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    vigencia_hasta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    emitida_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ramo: Mapped[str] = mapped_column(
        String(80), nullable=False, default="SEGURO", server_default="SEGURO"
    )
    titular_nombre: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default=""
    )
    estado_certificado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE"
    )
    ruta_certificado: Mapped[str | None] = mapped_column(String(512), nullable=True)

    coberturas: Mapped[list["PolizaCoberturaModel"]] = relationship(
        back_populates="poliza"
    )


class PolizaCoberturaModel(Base):
    __tablename__ = "poliza_cobertura"
    __table_args__ = (
        UniqueConstraint(
            "poliza_id",
            "cobertura_id",
            name="uq_poliza_cobertura_poliza_cobertura",
        ),
    )

    poliza_cobertura_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    poliza_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(_fk("poliza.poliza_id")),
        nullable=False,
        index=True,
    )
    # la cobertura pertenece al catálogo del motor de cotización: sin FK física
    cobertura_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, index=True
    )
    limite_asegurado: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    deducible: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    prima: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    poliza: Mapped[PolizaModel] = relationship(back_populates="coberturas")


_ESTADOS_FIRMA_ACTIVA = text("estado IN ('CAPTURADA', 'VINCULADA')")


class FirmaDigitalModel(Base):
    """Auditoría de la firma manuscrita; la imagen vive en disco o S3 y aquí solo su ruta relativa."""

    __tablename__ = "firma_digital"
    __table_args__ = (
        UniqueConstraint(
            "cliente_id", "idempotency_key", name="uq_firma_digital_cliente_idempotency"
        ),
        # Una sola firma vigente por cotización, también bajo concurrencia.
        Index(
            "uq_firma_digital_activa_por_cotizacion",
            "cotizacion_id",
            unique=True,
            postgresql_where=_ESTADOS_FIRMA_ACTIVA,
            sqlite_where=_ESTADOS_FIRMA_ACTIVA,
        ),
    )

    firma_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    # cliente, cotización y producto pertenecen a otros servicios: sin FK física
    cliente_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    cotizacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    producto_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # se completa cuando la póliza se emite (HU1.3.6)
    poliza_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(_fk("poliza.poliza_id")), nullable=True, index=True
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    proveedor_firma: Mapped[str] = mapped_column(String(40), nullable=False)
    ruta_imagen: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    firma_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint_contrato: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    capturada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PolizaContratoModel(Base):
    """Instantánea de lo contratado, con la que se genera el certificado."""

    __tablename__ = "poliza_contrato"

    poliza_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(_fk("poliza.poliza_id")), primary_key=True
    )
    datos: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


_GENERACION_EN_PROCESO = text("estado = 'EN_PROCESO'")


class GeneracionCertificadoModel(Base):
    """Auditoría de cada intento de generar el certificado PDF; el archivo vive en disco o S3."""

    __tablename__ = "generacion_certificado"
    __table_args__ = (
        # Un solo intento en proceso por póliza, también bajo concurrencia.
        Index(
            "uq_generacion_certificado_en_proceso",
            "poliza_id",
            unique=True,
            postgresql_where=_GENERACION_EN_PROCESO,
            sqlite_where=_GENERACION_EN_PROCESO,
        ),
    )

    generacion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    poliza_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(_fk("poliza.poliza_id")), nullable=False, index=True
    )
    # el cliente pertenece a otro servicio: sin FK física
    cliente_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    plantilla: Mapped[str] = mapped_column(String(100), nullable=False)
    datos_plantilla: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ruta_certificado: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_codigo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_detalle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    iniciada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalizada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EventoOutboxModel(Base):
    """Eventos por publicar en SQS; se escriben en la misma transacción que el cambio de negocio."""

    __tablename__ = "evento_outbox"
    __table_args__ = (Index("ix_evento_outbox_estado_creado", "estado", "creado_en"),)

    evento_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    agregado_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
