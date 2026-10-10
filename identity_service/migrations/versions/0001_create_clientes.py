"""crear tabla clientes

Revision ID: 0001
Revises:
Create Date: 2026-10-10

La entidad CLIENTE del MS Identidad (erDiagram asociado a la HU1.1.1):
UUID, tipo/número de documento, estado_kyc y auditoría de fechas.
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clientes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nombres", sa.String(length=100), nullable=False),
        sa.Column("apellidos", sa.String(length=100), nullable=False),
        sa.Column(
            "tipo_documento",
            sa.String(length=3),
            nullable=False,
            server_default="CC",
        ),
        sa.Column("numero_identificacion", sa.String(length=30), nullable=False),
        sa.Column("correo", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=False),
        sa.Column("pais_residencia", sa.String(length=60), nullable=False),
        sa.Column("telefono", sa.String(length=20), nullable=False),
        sa.Column(
            "estado_kyc",
            sa.String(length=20),
            nullable=False,
            server_default="PENDIENTE",
        ),
        sa.Column(
            "fecha_creacion",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "fecha_actualizacion",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correo", name="uq_clientes_correo"),
        sa.UniqueConstraint(
            "tipo_documento",
            "numero_identificacion",
            name="uq_clientes_tipo_documento_numero",
        ),
    )
    op.create_index(
        op.f("ix_clientes_correo"), "clientes", ["correo"], unique=False
    )
    op.create_index(
        op.f("ix_clientes_numero_identificacion"),
        "clientes",
        ["numero_identificacion"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_clientes_numero_identificacion"), table_name="clientes"
    )
    op.drop_index(op.f("ix_clientes_correo"), table_name="clientes")
    op.drop_table("clientes")