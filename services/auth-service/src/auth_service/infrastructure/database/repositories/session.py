# services/auth-service/src/auth_service/infrastructure/database/repositories/session.py

"""SQLAlchemy implementation SessionRepository."""

from datetime import datetime

from sqlalchemy import (
    select,
    update,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from auth_service.domain.session import (
    AuthSession,
)
from auth_service.infrastructure.database.models.session import (
    AuthSessionModel,
)


class SqlAlchemySessionRepository:
    """Реализует persistence только opaque auth sessions."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """Сохраняет transaction-scoped SQLAlchemy session."""
        self._session = session

    async def add(
        self,
        session: AuthSession,
    ) -> None:
        """Добавляет token hash без raw token."""
        model = AuthSessionModel(
            id=session.id,
            user_id=session.user_id,
            token_hash=session.token_hash,
            created_at=session.created_at,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
        )

        self._session.add(model)

        await self._session.flush()

    async def get_by_token_hash(
        self,
        token_hash: str,
    ) -> AuthSession | None:
        """Возвращает session только по deterministic hash."""
        statement = select(AuthSessionModel).where(AuthSessionModel.token_hash == token_hash)

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def revoke(
        self,
        *,
        token_hash: str,
        revoked_at: datetime,
    ) -> None:
        """Устанавливает revoked_at найденной session."""
        statement = (
            update(AuthSessionModel)
            .where(AuthSessionModel.token_hash == token_hash)
            .values(revoked_at=revoked_at)
        )

        await self._session.execute(statement)

    @staticmethod
    def _to_domain(
        model: AuthSessionModel,
    ) -> AuthSession:
        """Преобразует persistence model в Domain AuthSession."""
        return AuthSession(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            created_at=model.created_at,
            expires_at=model.expires_at,
            revoked_at=model.revoked_at,
        )
