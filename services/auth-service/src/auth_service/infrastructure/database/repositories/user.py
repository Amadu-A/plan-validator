# services/auth-service/src/auth_service/infrastructure/database/repositories/user.py

"""SQLAlchemy implementation UserRepository."""

from uuid import UUID

from sqlalchemy import (
    select,
    update,
)
from sqlalchemy.exc import (
    IntegrityError,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from auth_service.domain.exceptions import (
    EmailAlreadyRegisteredError,
)
from auth_service.domain.user import User
from auth_service.infrastructure.database.models.user import (
    UserModel,
)


class SqlAlchemyUserRepository:
    """Реализует data access только aggregate User."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """Сохраняет transaction-scoped SQLAlchemy session."""
        self._session = session

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:
        """Возвращает User по normalized email."""
        statement = select(UserModel).where(UserModel.email == email)

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def get_by_id(
        self,
        user_id: UUID,
    ) -> User | None:
        """Возвращает User по UUID."""
        model = await self._session.get(
            UserModel,
            user_id,
        )

        return self._to_domain(model) if model is not None else None

    async def add(
        self,
        user: User,
    ) -> None:
        """Добавляет User и преобразует unique race в domain conflict."""
        model = UserModel(
            id=user.id,
            email=user.email,
            password_hash=user.password_hash,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

        self._session.add(model)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise EmailAlreadyRegisteredError("Email is already registered") from exc

    async def update_password_hash(
        self,
        *,
        user_id: UUID,
        password_hash: str,
    ) -> None:
        """Обновляет password hash без загрузки полного model повторно."""
        statement = (
            update(UserModel).where(UserModel.id == user_id).values(password_hash=password_hash)
        )

        await self._session.execute(statement)

    @staticmethod
    def _to_domain(
        model: UserModel,
    ) -> User:
        """Преобразует SQLAlchemy model в Domain User."""
        return User(
            id=model.id,
            email=model.email,
            password_hash=model.password_hash,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
