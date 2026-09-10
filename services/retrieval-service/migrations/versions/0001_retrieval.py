# services/retrieval-service/migrations/versions/0001_retrieval.py

"""Создаёт Retrieval source-index registry."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_retrieval"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт retrieval schema и managed source index registry."""
    op.execute("CREATE SCHEMA IF NOT EXISTS retrieval")

    op.create_table(
        "managed_source_indexes",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=1), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("active_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("vector_dimension", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('N', 'U')",
            name="ck_retrieval_source_kind",
        ),
        sa.CheckConstraint(
            "state IN ('awaiting_chunks', 'indexed', 'deleted')",
            name="ck_retrieval_source_state",
        ),
        sa.CheckConstraint(
            "chunk_count >= 0",
            name="ck_retrieval_chunk_count",
        ),
        sa.PrimaryKeyConstraint("source_id"),
        schema="retrieval",
    )

    op.create_index(
        "ix_retrieval_sources_user_kind_state",
        "managed_source_indexes",
        ["user_id", "kind", "state"],
        unique=False,
        schema="retrieval",
    )
    op.create_index(
        "ix_retrieval_sources_section",
        "managed_source_indexes",
        ["user_id", "section_id", "kind"],
        unique=False,
        schema="retrieval",
    )


def downgrade() -> None:
    """Удаляет Retrieval registry и schema."""
    op.drop_index(
        "ix_retrieval_sources_section",
        table_name="managed_source_indexes",
        schema="retrieval",
    )
    op.drop_index(
        "ix_retrieval_sources_user_kind_state",
        table_name="managed_source_indexes",
        schema="retrieval",
    )
    op.drop_table("managed_source_indexes", schema="retrieval")
    op.execute("DROP SCHEMA IF EXISTS retrieval")
