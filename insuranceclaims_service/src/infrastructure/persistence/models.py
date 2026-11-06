import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Uuid
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
