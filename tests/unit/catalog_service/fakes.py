# tests/unit/catalog_service/fakes.py

"""In-memory test doubles Catalog application ports."""

from datetime import datetime
from types import TracebackType
from uuid import UUID

from catalog_service.domain.section import Section
from catalog_service.domain.system_prompt import SystemPrompt


class InMemorySectionRepository:
    """In-memory SectionRepository."""

    def __init__(self, storage: dict[UUID, Section]) -> None:
        """Сохраняет shared section storage."""
        self._storage = storage

    async def list_for_user(self, user_id: UUID) -> list[Section]:
        """Возвращает user-owned sections."""
        return sorted(
            (section for section in self._storage.values() if section.user_id == user_id),
            key=lambda value: (
                value.sort_order,
                value.title,
                str(value.id),
            ),
        )

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> Section | None:
        """Возвращает section только его owner."""
        section = self._storage.get(section_id)

        if section is None or section.user_id != user_id:
            return None

        return section

    async def add(self, section: Section) -> None:
        """Добавляет section."""
        self._storage[section.id] = section

    async def update(self, section: Section) -> None:
        """Заменяет immutable section."""
        self._storage[section.id] = section

    async def delete(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет section и descendants как PostgreSQL cascade."""
        pending = {section_id}

        while pending:
            current = pending.pop()

            descendants = {
                section.id
                for section in self._storage.values()
                if section.user_id == user_id and section.parent_id == current
            }

            pending.update(descendants)
            self._storage.pop(current, None)


class InMemorySystemPromptRepository:
    """In-memory SystemPromptRepository."""

    def __init__(self, storage: dict[UUID, SystemPrompt]) -> None:
        """Сохраняет shared prompt storage."""
        self._storage = storage

    async def get_for_user(self, user_id: UUID) -> SystemPrompt | None:
        """Возвращает prompt пользователя."""
        return self._storage.get(user_id)

    async def save(self, prompt: SystemPrompt) -> None:
        """Сохраняет singleton prompt."""
        self._storage[prompt.user_id] = prompt


class FakeUnitOfWork:
    """Fake Catalog transaction."""

    def __init__(
        self,
        *,
        sections: dict[UUID, Section],
        prompts: dict[UUID, SystemPrompt],
    ) -> None:
        """Создаёт repositories поверх shared storages."""
        self.sections = InMemorySectionRepository(sections)
        self.system_prompts = InMemorySystemPromptRepository(prompts)
        self.committed = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        """Открывает fake transaction."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает fake transaction."""
        del exc_type
        del exc
        del traceback

    async def commit(self) -> None:
        """Фиксирует commit marker."""
        self.committed = True

    async def rollback(self) -> None:
        """Сбрасывает commit marker."""
        self.committed = False


class FakeUnitOfWorkFactory:
    """Создаёт UoW поверх общих test storages."""

    def __init__(self) -> None:
        """Инициализирует пустые storages."""
        self.sections: dict[UUID, Section] = {}
        self.prompts: dict[UUID, SystemPrompt] = {}

    def __call__(self) -> FakeUnitOfWork:
        """Создаёт новый fake UoW."""
        return FakeUnitOfWork(
            sections=self.sections,
            prompts=self.prompts,
        )


class FixedClock:
    """Deterministic Clock."""

    def __init__(self, current_time: datetime) -> None:
        """Сохраняет фиксированное время."""
        self.current_time = current_time

    def now(self) -> datetime:
        """Возвращает фиксированное UTC time."""
        return self.current_time
