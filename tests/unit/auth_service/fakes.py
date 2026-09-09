# tests/unit/auth_service/fakes.py

"""In-memory test doubles application ports Authentication Service."""

from datetime import datetime
from types import TracebackType
from uuid import UUID

from auth_service.application.ports.security import (
    IssuedSessionToken,
)
from auth_service.domain.session import (
    AuthSession,
)
from auth_service.domain.user import (
    User,
)


class InMemoryUserRepository:
    """In-memory implementation UserRepository для unit tests."""

    def __init__(
        self,
        storage: dict[UUID, User],
    ) -> None:
        """Сохраняет shared test storage."""
        self._storage = storage

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:
        """Ищет user по normalized email."""
        return next(
            (user for user in self._storage.values() if user.email == email),
            None,
        )

    async def get_by_id(
        self,
        user_id: UUID,
    ) -> User | None:
        """Возвращает user по UUID."""
        return self._storage.get(user_id)

    async def add(
        self,
        user: User,
    ) -> None:
        """Добавляет user в test storage."""
        self._storage[user.id] = user

    async def update_password_hash(
        self,
        *,
        user_id: UUID,
        password_hash: str,
    ) -> None:
        """Заменяет immutable test User новым значением hash."""
        user = self._storage[user_id]

        self._storage[user_id] = User(
            id=user.id,
            email=user.email,
            password_hash=password_hash,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class InMemorySessionRepository:
    """In-memory implementation SessionRepository для unit tests."""

    def __init__(
        self,
        storage: dict[
            str,
            AuthSession,
        ],
    ) -> None:
        """Сохраняет shared session storage."""
        self._storage = storage

    async def add(
        self,
        session: AuthSession,
    ) -> None:
        """Добавляет session keyed by token hash."""
        self._storage[session.token_hash] = session

    async def get_by_token_hash(
        self,
        token_hash: str,
    ) -> AuthSession | None:
        """Возвращает session по hash."""
        return self._storage.get(token_hash)

    async def revoke(
        self,
        *,
        token_hash: str,
        revoked_at: datetime,
    ) -> None:
        """Заменяет session новым revoked domain object."""
        session = self._storage[token_hash]

        self._storage[token_hash] = AuthSession(
            id=session.id,
            user_id=session.user_id,
            token_hash=session.token_hash,
            created_at=session.created_at,
            expires_at=session.expires_at,
            revoked_at=revoked_at,
        )


class FakeUnitOfWork:
    """Unit of Work поверх shared in-memory storages."""

    def __init__(
        self,
        *,
        users: dict[UUID, User],
        sessions: dict[
            str,
            AuthSession,
        ],
    ) -> None:
        """Создаёт repositories текущего fake transaction."""
        self.users = InMemoryUserRepository(users)
        self.sessions = InMemorySessionRepository(sessions)
        self.committed = False

    async def __aenter__(
        self,
    ) -> "FakeUnitOfWork":
        """Открывает fake transaction."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает fake transaction без дополнительных side effects."""
        del exc_type
        del exc
        del traceback

    async def commit(self) -> None:
        """Фиксирует факт commit для assertions."""
        self.committed = True

    async def rollback(self) -> None:
        """Сбрасывает commit marker."""
        self.committed = False


class FakeUnitOfWorkFactory:
    """Создаёт UoW поверх общих test storages."""

    def __init__(self) -> None:
        """Создаёт пустые storages users/sessions."""
        self.users: dict[
            UUID,
            User,
        ] = {}
        self.sessions: dict[
            str,
            AuthSession,
        ] = {}

    def __call__(
        self,
    ) -> FakeUnitOfWork:
        """Создаёт новый fake transaction scope."""
        return FakeUnitOfWork(
            users=self.users,
            sessions=self.sessions,
        )


class FakePasswordHasher:
    """Deterministic PasswordHasher unit-test double."""

    def hash_password(
        self,
        password: str,
    ) -> str:
        """Создаёт deterministic fake hash."""
        return f"hashed:{password}"

    def verify_password(
        self,
        *,
        password: str,
        password_hash: str | None,
    ) -> bool:
        """Проверяет deterministic fake hash."""
        if password_hash is None:
            return False

        return password_hash == f"hashed:{password}"

    def needs_rehash(
        self,
        password_hash: str,
    ) -> bool:
        """Fake hashes никогда не требуют upgrade."""
        del password_hash
        return False


class FakeTokenManager:
    """Deterministic token manager unit-test double."""

    def __init__(self) -> None:
        """Инициализирует monotonically increasing token counter."""
        self._counter = 0

    def issue_token(
        self,
    ) -> IssuedSessionToken:
        """Создаёт deterministic raw/hash pair."""
        self._counter += 1
        raw_token = f"raw-token-{self._counter}"

        return IssuedSessionToken(
            raw_token=raw_token,
            token_hash=(self.hash_token(raw_token)),
        )

    def hash_token(
        self,
        raw_token: str,
    ) -> str:
        """Создаёт deterministic fake token hash."""
        return f"hash:{raw_token}"


class FixedClock:
    """Deterministic Clock unit-test double."""

    def __init__(
        self,
        current_time: datetime,
    ) -> None:
        """Сохраняет фиксированное timezone-aware время."""
        self.current_time = current_time

    def now(self) -> datetime:
        """Возвращает фиксированное время."""
        return self.current_time
