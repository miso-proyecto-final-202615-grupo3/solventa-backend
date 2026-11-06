import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class PagoModel(Base):
    __tablename__ = "pago"

    pago_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    poliza_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    indemnizacion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False)
    estado: Mapped[str] = mapped_column(String(50), nullable=False)
    clave_idempotencia: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    procesado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
