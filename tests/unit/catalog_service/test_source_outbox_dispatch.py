# tests/unit/catalog_service/test_source_outbox_dispatch.py

"""Unit tests Catalog transactional outbox dispatcher use-case."""

import asyncio
from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID

import pytest
from catalog_service.application.ports.source_event_publisher import SourceEventPublishError
from catalog_service.application.use_cases.dispatch_source_outbox import (
    DispatchNextSourceOutboxMessageUseCase,
)
from catalog_service.domain.source import SourceOutboxMessage

MESSAGE_ID = UUID("11111111-1111-1111-1111-111111111111")
SOURCE_ID = UUID("22222222-2222-2222-2222-222222222222")
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


class FakeClock:
    """Возвращает deterministic publish timestamp."""

    def now(self) -> datetime:
        """Возвращает фиксированное UTC время."""
        return NOW


class FakeOutboxRepository:
    """Имитирует один pending source event."""

    def __init__(self, message: SourceOutboxMessage | None) -> None:
        """Сохраняет pending message и captured transitions."""
        self.message = message
        self.published_at: datetime | None = None
        self.failed_error: str | None = None

    async def get_next_pending_for_update(self) -> SourceOutboxMessage | None:
        """Возвращает configured pending event."""
        return self.message

    async def mark_published(self, *, message_id: UUID, published_at: datetime) -> None:
        """Фиксирует confirmed delivery."""
        assert message_id == MESSAGE_ID
        self.published_at = published_at

    async def mark_failed(self, *, message_id: UUID, error_message: str) -> None:
        """Фиксирует failed delivery."""
        assert message_id == MESSAGE_ID
        self.failed_error = error_message

    async def add(self, message: SourceOutboxMessage) -> None:
        """Не используется dispatcher use-case."""
        del message
        raise AssertionError("add must not be called")


class FakeUow:
    """Минимальный Catalog UoW для dispatcher tests."""

    def __init__(self, outbox: FakeOutboxRepository) -> None:
        """Сохраняет outbox и commit count."""
        self.source_outbox = outbox
        self.commit_count = 0

    async def __aenter__(self) -> "FakeUow":
        """Открывает fake transaction."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает fake transaction без действий."""
        del exc_type
        del exc
        del traceback

    async def commit(self) -> None:
        """Фиксирует commit call."""
        self.commit_count += 1

    async def rollback(self) -> None:
        """Fake rollback ничего не меняет."""


class FakeUowFactory:
    """Возвращает один fake UoW."""

    def __init__(self, uow: FakeUow) -> None:
        """Сохраняет fake UoW."""
        self.uow = uow

    def __call__(self) -> FakeUow:
        """Возвращает fake transaction scope."""
        return self.uow


class FakePublisher:
    """Configurable confirmed/failed source event publisher."""

    def __init__(self, *, fail: bool = False) -> None:
        """Сохраняет failure mode и published ids."""
        self.fail = fail
        self.published: list[UUID] = []

    async def publish(self, message: SourceOutboxMessage) -> None:
        """Фиксирует publish либо эмулирует publisher-confirm failure."""
        if self.fail:
            raise SourceEventPublishError("broker unavailable")

        self.published.append(message.id)


def _message() -> SourceOutboxMessage:
    """Создаёт deterministic pending outbox event."""
    return SourceOutboxMessage(
        id=MESSAGE_ID,
        source_id=SOURCE_ID,
        event_type="catalog.source.uploaded.v1",
        payload={"source_id": str(SOURCE_ID)},
        created_at=NOW,
        published_at=None,
        attempt_count=0,
        last_error=None,
    )


def test_dispatch_marks_event_published_after_confirm() -> None:
    """Проверяет publish-confirm перед DB published_at transition."""
    outbox = FakeOutboxRepository(_message())
    uow = FakeUow(outbox)
    publisher = FakePublisher()
    use_case = DispatchNextSourceOutboxMessageUseCase(
        uow_factory=FakeUowFactory(uow),  # type: ignore[arg-type]
        publisher=publisher,
        clock=FakeClock(),
    )

    assert asyncio.run(use_case.execute()) is True
    assert publisher.published == [MESSAGE_ID]
    assert outbox.published_at == NOW
    assert outbox.failed_error is None
    assert uow.commit_count == 1


def test_dispatch_persists_failed_attempt_and_reraises() -> None:
    """Проверяет retry-safe row при RabbitMQ publish failure."""
    outbox = FakeOutboxRepository(_message())
    uow = FakeUow(outbox)
    use_case = DispatchNextSourceOutboxMessageUseCase(
        uow_factory=FakeUowFactory(uow),  # type: ignore[arg-type]
        publisher=FakePublisher(fail=True),
        clock=FakeClock(),
    )

    with pytest.raises(SourceEventPublishError):
        asyncio.run(use_case.execute())

    assert outbox.published_at is None
    assert outbox.failed_error == "broker unavailable"
    assert uow.commit_count == 1
