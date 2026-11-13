import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Index, Integer, Numeric, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


_ESTADOS_PAGO_ACTIVO = text("estado IN ('PENDIENTE', 'APROBADO', 'ERROR')")


class PagoPrimaModel(Base):
    """Pago de la prima inicial; no guarda datos de tarjeta, solo marca y últimos 4 dígitos."""

    __tablename__ = "pago_prima"
    __table_args__ = (
        UniqueConstraint("cliente_id", "idempotency_key", name="uq_pago_prima_cliente_idempotency"),
        # Un solo pago activo por cotización, también bajo concurrencia.
        Index(
            "uq_pago_prima_activo_por_cotizacion",
            "cotizacion_id",
            unique=True,
            postgresql_where=_ESTADOS_PAGO_ACTIVO,
            sqlite_where=_ESTADOS_PAGO_ACTIVO,
        ),
    )

    pago_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # cotización y cliente pertenecen a otros servicios: sin FK física
    cotizacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    cliente_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    monto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False)
    metodo_pago: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    proveedor: Mapped[str] = mapped_column(String(40), nullable=False)
    proveedor_referencia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    codigo_rechazo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_codigo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tarjeta_ultimos4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    tarjeta_marca: Mapped[str | None] = mapped_column(String(20), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    hash_solicitud: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    procesado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class EventoOutboxModel(Base):
    """Eventos por publicar en SQS; se escriben en la misma transacción que el cambio de negocio."""

    __tablename__ = "evento_outbox"
    __table_args__ = (Index("ix_evento_outbox_estado_creado", "estado", "creado_en"),)

    evento_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    agregado_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
