# services/catalog-service/migrations/versions/0001_create_catalog_schema.py

"""Создаёт PostgreSQL schema пользовательского Catalog."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_catalog"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт catalog.sections и catalog.system_prompts."""
    op.execute("CREATE SCHEMA IF NOT EXISTS catalog")

    op.create_table(
        "sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["catalog.sections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="catalog",
    )

    op.create_index(
        "ix_catalog_sections_user_id",
        "sections",
        ["user_id"],
        unique=False,
        schema="catalog",
    )

    op.create_index(
        "ix_catalog_sections_user_parent_order",
        "sections",
        ["user_id", "parent_id", "sort_order"],
        unique=False,
        schema="catalog",
    )

    op.create_table(
        "system_prompts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
        schema="catalog",
    )


def downgrade() -> None:
    """Удаляет только database objects Catalog bounded context."""
    op.drop_table(
        "system_prompts",
        schema="catalog",
    )

    op.drop_index(
        "ix_catalog_sections_user_parent_order",
        table_name="sections",
        schema="catalog",
    )
    op.drop_index(
        "ix_catalog_sections_user_id",
        table_name="sections",
        schema="catalog",
    )

    op.drop_table(
        "sections",
        schema="catalog",
    )

    op.execute("DROP SCHEMA IF EXISTS catalog")
