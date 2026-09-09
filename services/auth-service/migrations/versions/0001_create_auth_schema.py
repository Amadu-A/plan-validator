# services/auth-service/migrations/versions/0001_create_auth_schema.py

"""Создаёт schema users и opaque sessions Authentication Service."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_auth"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт auth schema, users и sessions."""
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "email",
            sa.String(length=320),
            nullable=False,
        ),
        sa.Column(
            "password_hash",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
        schema="auth",
    )

    op.create_index(
        "uq_auth_users_email",
        "users",
        ["email"],
        unique=True,
        schema="auth",
    )

    op.create_table(
        "sessions",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="auth",
    )

    op.create_index(
        "uq_auth_sessions_token_hash",
        "sessions",
        ["token_hash"],
        unique=True,
        schema="auth",
    )

    op.create_index(
        "ix_auth_sessions_user_id",
        "sessions",
        ["user_id"],
        unique=False,
        schema="auth",
    )

    op.create_index(
        "ix_auth_sessions_expires_at",
        "sessions",
        ["expires_at"],
        unique=False,
        schema="auth",
    )


def downgrade() -> None:
    """Удаляет только database objects Authentication bounded context."""
    op.drop_index(
        "ix_auth_sessions_expires_at",
        table_name="sessions",
        schema="auth",
    )
    op.drop_index(
        "ix_auth_sessions_user_id",
        table_name="sessions",
        schema="auth",
    )
    op.drop_index(
        "uq_auth_sessions_token_hash",
        table_name="sessions",
        schema="auth",
    )
    op.drop_table(
        "sessions",
        schema="auth",
    )

    op.drop_index(
        "uq_auth_users_email",
        table_name="users",
        schema="auth",
    )
    op.drop_table(
        "users",
        schema="auth",
    )

    op.execute("DROP SCHEMA IF EXISTS auth")
