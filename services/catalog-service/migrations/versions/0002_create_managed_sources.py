# services/catalog-service/migrations/versions/0002_create_managed_sources.py

"""Создаёт managed N/U sources и transactional outbox Stage 7."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_catalog_sources"
down_revision: str | Sequence[str] | None = "0001_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт catalog.managed_sources и source_outbox_messages."""
    op.create_table(
        "managed_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=1), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("last_cleanup_error", sa.Text(), nullable=True),
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
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "kind IN ('N', 'U')",
            name="ck_catalog_managed_sources_kind",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('active', 'delete_pending', 'cleanup_failed', 'deleted')",
            name="ck_catalog_managed_sources_lifecycle",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_catalog_managed_sources_size_bytes",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["catalog.sections.id"],
            name="fk_catalog_managed_sources_section",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_catalog_managed_sources_storage_key",
        ),
        schema="catalog",
    )

    op.create_index(
        "ix_catalog_managed_sources_user_id",
        "managed_sources",
        ["user_id"],
        unique=False,
        schema="catalog",
    )
    op.create_index(
        "ix_catalog_managed_sources_section_id",
        "managed_sources",
        ["section_id"],
        unique=False,
        schema="catalog",
    )
    op.create_index(
        "ix_catalog_managed_sources_user_kind_section_created",
        "managed_sources",
        [
            "user_id",
            "kind",
            "section_id",
            "created_at",
        ],
        unique=False,
        schema="catalog",
    )

    op.create_table(
        "source_outbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_catalog_source_outbox_attempt_count",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="catalog",
    )

    op.create_index(
        "ix_catalog_source_outbox_pending",
        "source_outbox_messages",
        [
            "published_at",
            "created_at",
        ],
        unique=False,
        schema="catalog",
    )
    op.create_index(
        "ix_catalog_source_outbox_source_id",
        "source_outbox_messages",
        ["source_id"],
        unique=False,
        schema="catalog",
    )


def downgrade() -> None:
    """Удаляет Stage 7 database objects в обратном порядке."""
    op.drop_index(
        "ix_catalog_source_outbox_source_id",
        table_name="source_outbox_messages",
        schema="catalog",
    )
    op.drop_index(
        "ix_catalog_source_outbox_pending",
        table_name="source_outbox_messages",
        schema="catalog",
    )
    op.drop_table(
        "source_outbox_messages",
        schema="catalog",
    )

    op.drop_index(
        "ix_catalog_managed_sources_user_kind_section_created",
        table_name="managed_sources",
        schema="catalog",
    )
    op.drop_index(
        "ix_catalog_managed_sources_section_id",
        table_name="managed_sources",
        schema="catalog",
    )
    op.drop_index(
        "ix_catalog_managed_sources_user_id",
        table_name="managed_sources",
        schema="catalog",
    )
    op.drop_table(
        "managed_sources",
        schema="catalog",
    )
