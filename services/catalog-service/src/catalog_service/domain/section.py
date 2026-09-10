# services/catalog-service/src/catalog_service/domain/section.py

"""Domain entity раздела пользовательского каталога."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from catalog_service.domain.exceptions import InvalidCatalogValueError

MAX_SECTION_TITLE_LENGTH = 200


@dataclass(frozen=True, slots=True)
class Section:
    """Представляет один узел пользовательского дерева sections."""

    id: UUID
    user_id: UUID
    parent_id: UUID | None
    title: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


def normalize_section_title(title: str) -> str:
    """Нормализует title и защищает domain size invariant."""
    normalized = title.strip()

    if not normalized:
        raise InvalidCatalogValueError("Section title must not be empty")

    if len(normalized) > MAX_SECTION_TITLE_LENGTH:
        raise InvalidCatalogValueError(
            f"Section title must not exceed {MAX_SECTION_TITLE_LENGTH} characters"
        )

    return normalized
