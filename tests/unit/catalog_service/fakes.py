# tests/unit/catalog_service/fakes.py

"""In-memory test doubles Catalog application ports."""

from datetime import datetime
from types import TracebackType
from uuid import UUID

from catalog_service.domain.section import Section
from catalog_service.domain.source import (
    ManagedSource,
    SourceKind,
    SourceLifecycle,
    SourceOutboxMessage,
)
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
                if (section.user_id == user_id and section.parent_id == current)
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


class InMemoryManagedSourceRepository:
    """In-memory ManagedSourceRepository."""

    def __init__(
        self,
        *,
        storage: dict[UUID, ManagedSource],
        sections: dict[UUID, Section],
    ) -> None:
        """Сохраняет shared source и section storages."""
        self._storage = storage
        self._sections = sections

    async def list_for_user_section(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: SourceKind,
    ) -> list[ManagedSource]:
        """Возвращает не удалённые sources заданного kind."""
        values = [
            source
            for source in self._storage.values()
            if (
                source.user_id == user_id
                and source.section_id == section_id
                and source.kind is kind
                and source.lifecycle is not SourceLifecycle.DELETED
            )
        ]

        return sorted(
            values,
            key=lambda value: (
                value.created_at,
                value.original_name,
                str(value.id),
            ),
            reverse=True,
        )

    async def get_for_user_kind(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: SourceKind,
    ) -> ManagedSource | None:
        """Возвращает source только внутри ownership/kind scope."""
        source = self._storage.get(source_id)

        if source is None or source.user_id != user_id or source.kind is not kind:
            return None

        return source

    async def get_for_user_kind_for_update(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: SourceKind,
    ) -> ManagedSource | None:
        """Возвращает source как fake row-lock lookup."""
        return await self.get_for_user_kind(
            user_id=user_id,
            source_id=source_id,
            kind=kind,
        )

    async def add(self, source: ManagedSource) -> None:
        """Добавляет source metadata."""
        self._storage[source.id] = source

    async def update(self, source: ManagedSource) -> None:
        """Заменяет immutable source state."""
        self._storage[source.id] = source

    async def has_live_in_subtree(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> bool:
        """Проверяет live sources в in-memory section subtree."""
        section_ids = self._subtree_ids(
            user_id=user_id,
            section_id=section_id,
        )

        return any(
            source.user_id == user_id
            and source.section_id in section_ids
            and source.lifecycle is not SourceLifecycle.DELETED
            for source in self._storage.values()
        )

    async def purge_deleted_in_subtree(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет deleted source metadata внутри subtree."""
        section_ids = self._subtree_ids(
            user_id=user_id,
            section_id=section_id,
        )

        to_delete = [
            source_id
            for source_id, source in self._storage.items()
            if (
                source.user_id == user_id
                and source.section_id in section_ids
                and source.lifecycle is SourceLifecycle.DELETED
            )
        ]

        for source_id in to_delete:
            self._storage.pop(source_id, None)

    def _subtree_ids(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> set[UUID]:
        """Вычисляет section subtree для fake repository."""
        result = {section_id}
        changed = True

        while changed:
            changed = False

            for section in self._sections.values():
                if (
                    section.user_id == user_id
                    and section.parent_id in result
                    and section.id not in result
                ):
                    result.add(section.id)
                    changed = True

        return result


class InMemorySourceOutboxRepository:
    """In-memory SourceOutboxRepository."""

    def __init__(
        self,
        storage: dict[UUID, SourceOutboxMessage],
    ) -> None:
        """Сохраняет shared outbox storage."""
        self._storage = storage

    async def add(self, message: SourceOutboxMessage) -> None:
        """Добавляет durable event в fake transaction state."""
        self._storage[message.id] = message


class FakeUnitOfWork:
    """Fake Catalog transaction."""

    def __init__(
        self,
        *,
        sections: dict[UUID, Section],
        prompts: dict[UUID, SystemPrompt],
        sources: dict[UUID, ManagedSource],
        source_outbox: dict[UUID, SourceOutboxMessage],
    ) -> None:
        """Создаёт repositories поверх shared storages."""
        self.sections = InMemorySectionRepository(sections)
        self.system_prompts = InMemorySystemPromptRepository(prompts)
        self.sources = InMemoryManagedSourceRepository(
            storage=sources,
            sections=sections,
        )
        self.source_outbox = InMemorySourceOutboxRepository(source_outbox)
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
        self.sources: dict[UUID, ManagedSource] = {}
        self.source_outbox: dict[UUID, SourceOutboxMessage] = {}

    def __call__(self) -> FakeUnitOfWork:
        """Создаёт новый fake UoW."""
        return FakeUnitOfWork(
            sections=self.sections,
            prompts=self.prompts,
            sources=self.sources,
            source_outbox=self.source_outbox,
        )


class FixedClock:
    """Deterministic Clock."""

    def __init__(self, current_time: datetime) -> None:
        """Сохраняет фиксированное время."""
        self.current_time = current_time

    def now(self) -> datetime:
        """Возвращает фиксированное UTC time."""
        return self.current_time
