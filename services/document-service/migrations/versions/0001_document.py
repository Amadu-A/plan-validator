# services/document-service/migrations/versions/0001_document.py

"""Создаёт schema и registry Project Documents."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_document"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт document schema и project_documents."""
    op.execute("CREATE SCHEMA IF NOT EXISTS document")
    op.create_table(
        "project_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("selected_pages", postgresql.JSONB(), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("cleanup_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        schema="document",
    )
    op.create_index(
        "ix_document_project_documents_user_id",
        "project_documents",
        ["user_id"],
        schema="document",
    )
    op.create_index(
        "ix_document_project_documents_lifecycle",
        "project_documents",
        ["lifecycle"],
        schema="document",
    )
    op.create_index(
        "ix_document_project_documents_expires_at",
        "project_documents",
        ["expires_at"],
        schema="document",
    )


def downgrade() -> None:
    """Удаляет registry и schema Document Service."""
    op.drop_table("project_documents", schema="document")
    op.execute("DROP SCHEMA IF EXISTS document")
