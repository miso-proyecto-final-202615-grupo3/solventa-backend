import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

SCHEMA = "quotingengine"


def _fk(target: str) -> str:
    """FK calificada con el esquema (se omite si el metadata no lo tiene, p. ej. tests)."""
    schema = Base.metadata.schema
    return f"{schema}.{target}" if schema else target


class ProductoSeguroModel(Base):
    __tablename__ = "producto_seguro"

    producto_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    ramo: Mapped[str] = mapped_column(String(50), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    pais: Mapped[str] = mapped_column(String(60), nullable=False)

    coberturas: Mapped[list["CoberturaModel"]] = relationship(
        back_populates="producto"
    )
    reglas_rating: Mapped[list["ReglaRatingModel"]] = relationship(
        back_populates="producto"
    )
    cotizaciones: Mapped[list["CotizacionModel"]] = relationship(
        back_populates="producto"
    )


class CoberturaModel(Base):
    __tablename__ = "cobertura"

    cobertura_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    producto_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(_fk("producto_seguro.producto_id")),
        nullable=False,
        index=True,
    )
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    limite_asegurado: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    deducible: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)

    producto: Mapped[ProductoSeguroModel] = relationship(back_populates="coberturas")


class ReglaRatingModel(Base):
    __tablename__ = "regla_rating"

    regla_rating_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    producto_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(_fk("producto_seguro.producto_id")),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    definicion: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    vigente_desde: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    vigente_hasta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    producto: Mapped[ProductoSeguroModel] = relationship(
        back_populates="reglas_rating"
    )


class CotizacionModel(Base):
    __tablename__ = "cotizacion"

    cotizacion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    # cliente, socio y perfil de riesgo pertenecen a otros servicios: sin FK física
    cliente_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    producto_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(_fk("producto_seguro.producto_id")),
        nullable=False,
        index=True,
    )
    socio_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    perfil_riesgo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    prima_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False)
    expira_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    producto: Mapped[ProductoSeguroModel] = relationship(
        back_populates="cotizaciones"
    )
    coberturas: Mapped[list["CotizacionCoberturaModel"]] = relationship(
        back_populates="cotizacion"
    )
    auditorias: Mapped[list["AuditoriaDecisionModel"]] = relationship(
        back_populates="cotizacion"
    )


class CotizacionCoberturaModel(Base):
    __tablename__ = "cotizacion_cobertura"
    __table_args__ = (
        UniqueConstraint(
            "cotizacion_id",
            "cobertura_id",
            name="uq_cotizacion_cobertura_cotizacion_cobertura",
        ),
    )

    cotizacion_cobertura_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    cotizacion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(_fk("cotizacion.cotizacion_id")),
        nullable=False,
        index=True,
    )
    cobertura_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(_fk("cobertura.cobertura_id")),
        nullable=False,
        index=True,
    )
    prima: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    limite_asegurado: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    deducible: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    cotizacion: Mapped[CotizacionModel] = relationship(back_populates="coberturas")
    cobertura: Mapped[CoberturaModel] = relationship()


class AuditoriaDecisionModel(Base):
    __tablename__ = "auditoria_decision"

    auditoria_decision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    cotizacion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(_fk("cotizacion.cotizacion_id")),
        nullable=False,
        index=True,
    )
    regla_rating_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(_fk("regla_rating.regla_rating_id")),
        nullable=False,
        index=True,
    )
    tipo_decision: Mapped[str] = mapped_column(String(50), nullable=False)
    entradas: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    resultado: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    decidida_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    cotizacion: Mapped[CotizacionModel] = relationship(back_populates="auditorias")
    regla_rating: Mapped[ReglaRatingModel] = relationship()
