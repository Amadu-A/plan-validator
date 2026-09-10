# tests/unit/catalog_service/test_use_cases.py

"""Unit tests Catalog application use-cases."""

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from catalog_service.application.use_cases import (
    CreateSectionUseCase,
    DeleteSectionUseCase,
    GetSystemPromptUseCase,
    ListSectionsUseCase,
    SaveSystemPromptUseCase,
    UpdateSectionUseCase,
)
from catalog_service.domain.exceptions import InvalidSectionHierarchyError
from tests.unit.catalog_service.fakes import FakeUnitOfWorkFactory, FixedClock

NOW = datetime(
    2026,
    9,
    10,
    0,
    0,
    tzinfo=UTC,
)


def run_async[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Запускает coroutine без отдельного async pytest plugin."""
    return asyncio.run(coroutine)


def build_use_cases() -> tuple[
    FakeUnitOfWorkFactory,
    CreateSectionUseCase,
    UpdateSectionUseCase,
    DeleteSectionUseCase,
    ListSectionsUseCase,
    GetSystemPromptUseCase,
    SaveSystemPromptUseCase,
]:
    """Собирает Catalog use-cases поверх deterministic fakes."""
    factory = FakeUnitOfWorkFactory()
    clock = FixedClock(NOW)

    return (
        factory,
        CreateSectionUseCase(
            uow_factory=factory,
            clock=clock,
        ),
        UpdateSectionUseCase(
            uow_factory=factory,
            clock=clock,
        ),
        DeleteSectionUseCase(factory),
        ListSectionsUseCase(factory),
        GetSystemPromptUseCase(factory),
        SaveSystemPromptUseCase(
            uow_factory=factory,
            clock=clock,
        ),
    )


def test_create_nested_sections_and_list() -> None:
    """Проверяет создание root/child tree."""
    (
        _,
        create,
        _,
        _,
        list_sections,
        _,
        _,
    ) = build_use_cases()

    user_id = uuid4()

    root = run_async(
        create.execute(
            user_id=user_id,
            title="  Нормативные документы  ",
            parent_id=None,
            sort_order=0,
        )
    )

    child = run_async(
        create.execute(
            user_id=user_id,
            title="СП",
            parent_id=root.id,
            sort_order=1,
        )
    )

    sections = run_async(
        list_sections.execute(user_id=user_id)
    )

    assert root.title == "Нормативные документы"
    assert child.parent_id == root.id
    assert {section.id for section in sections} == {
        root.id,
        child.id,
    }


def test_move_section_under_descendant_is_rejected() -> None:
    """Проверяет cycle protection при изменении parent."""
    (
        _,
        create,
        update,
        _,
        _,
        _,
        _,
    ) = build_use_cases()

    user_id = uuid4()

    root = run_async(
        create.execute(
            user_id=user_id,
            title="Root",
            parent_id=None,
            sort_order=0,
        )
    )
    child = run_async(
        create.execute(
            user_id=user_id,
            title="Child",
            parent_id=root.id,
            sort_order=0,
        )
    )

    with pytest.raises(InvalidSectionHierarchyError):
        run_async(
            update.execute(
                user_id=user_id,
                section_id=root.id,
                title=None,
                parent_id=child.id,
                parent_id_supplied=True,
                sort_order=None,
            )
        )


def test_delete_parent_cascades_fake_descendants() -> None:
    """Проверяет Catalog-only cascade semantics."""
    (
        factory,
        create,
        _,
        delete,
        _,
        _,
        _,
    ) = build_use_cases()

    user_id = uuid4()

    root = run_async(
        create.execute(
            user_id=user_id,
            title="Root",
            parent_id=None,
            sort_order=0,
        )
    )

    run_async(
        create.execute(
            user_id=user_id,
            title="Child",
            parent_id=root.id,
            sort_order=0,
        )
    )

    run_async(
        delete.execute(
            user_id=user_id,
            section_id=root.id,
        )
    )

    assert not factory.sections


def test_system_prompt_empty_default_and_save() -> None:
    """Проверяет singleton system prompt lifecycle."""
    (
        _,
        _,
        _,
        _,
        _,
        get_prompt,
        save_prompt,
    ) = build_use_cases()

    user_id = uuid4()

    initial = run_async(
        get_prompt.execute(user_id=user_id)
    )

    assert initial.prompt == ""
    assert initial.updated_at is None

    saved = run_async(
        save_prompt.execute(
            user_id=user_id,
            prompt="Проверяй чертёж строго по нормативной базе.",
        )
    )

    assert "нормативной" in saved.prompt

    loaded = run_async(
        get_prompt.execute(user_id=user_id)
    )

    assert loaded == saved
