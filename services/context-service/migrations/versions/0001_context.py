# services/context-service/migrations/versions/0001_context.py

"""Создаёт registry временного Project Context и recoverable indexing jobs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_context"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт schema context и Stage 10 persistent registries."""
    op.execute("CREATE SCHEMA IF NOT EXISTS context")

    op.create_table(
        "project_contexts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("cleanup_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('active', 'cleanup_pending', 'cleaned')",
            name="ck_context_project_context_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="context",
    )

    op.create_index(
        "ix_context_project_contexts_user_state",
        "project_contexts",
        ["user_id", "state"],
        unique=False,
        schema="context",
    )

    op.create_index(
        "ix_context_project_contexts_expiration",
        "project_contexts",
        ["state", "expires_at"],
        unique=False,
        schema="context",
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("context_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=2), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("active_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('T', 'PZ')",
            name="ck_context_source_kind",
        ),
        sa.CheckConstraint(
            "state IN ('awaiting_chunks', 'indexed', 'deleted')",
            name="ck_context_source_state",
        ),
        sa.CheckConstraint(
            "chunk_count >= 0",
            name="ck_context_source_chunk_count",
        ),
        sa.ForeignKeyConstraint(
            ["context_id"],
            ["context.project_contexts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "context_id",
            "kind",
            name="uq_context_source_kind",
        ),
        schema="context",
    )

    op.create_index(
        "ix_context_sources_owner",
        "sources",
        ["user_id", "context_id", "kind", "state"],
        unique=False,
        schema="context",
    )

    op.create_table(
        "index_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("context_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=2), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("chunks", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            ("state IN ('queued', 'running', 'retry_wait', 'succeeded', 'failed', 'canceled')"),
            name="ck_context_index_job_state",
        ),
        sa.CheckConstraint(
            "attempt >= 0",
            name="ck_context_index_job_attempt",
        ),
        sa.CheckConstraint(
            "max_attempts >= 1",
            name="ck_context_index_job_max_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["context_id"],
            ["context.project_contexts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["context.sources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="context",
    )

    op.create_index(
        "ix_context_index_jobs_source_fingerprint",
        "index_jobs",
        ["source_id", "fingerprint", "state"],
        unique=False,
        schema="context",
    )

    op.create_index(
        "ix_context_index_jobs_recovery",
        "index_jobs",
        [
            "state",
            "deadline_at",
            "next_attempt_at",
            "lease_expires_at",
            "dispatched_at",
        ],
        unique=False,
        schema="context",
    )


def downgrade() -> None:
    """Удаляет Stage 10 tables и context schema."""
    op.drop_index(
        "ix_context_index_jobs_recovery",
        table_name="index_jobs",
        schema="context",
    )
    op.drop_index(
        "ix_context_index_jobs_source_fingerprint",
        table_name="index_jobs",
        schema="context",
    )
    op.drop_table(
        "index_jobs",
        schema="context",
    )

    op.drop_index(
        "ix_context_sources_owner",
        table_name="sources",
        schema="context",
    )
    op.drop_table(
        "sources",
        schema="context",
    )

    op.drop_index(
        "ix_context_project_contexts_expiration",
        table_name="project_contexts",
        schema="context",
    )
    op.drop_index(
        "ix_context_project_contexts_user_state",
        table_name="project_contexts",
        schema="context",
    )
    op.drop_table(
        "project_contexts",
        schema="context",
    )

    op.execute("DROP SCHEMA IF EXISTS context")
