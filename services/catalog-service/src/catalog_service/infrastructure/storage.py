# services/catalog-service/src/catalog_service/infrastructure/storage.py

"""Filesystem adapter canonical N/U storage и human-readable section tree."""

import asyncio
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from catalog_service.application.ports.source_storage import (
    SourceStorageError,
)
from catalog_service.domain.section import Section
from catalog_service.domain.source import (
    ManagedSource,
    SourceKind,
    SourceLifecycle,
)

_INVALID_COMPONENT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

NORMATIVE_DIRECTORY = "N_Нормативные документы"
USER_DIRECTORY = "U_Пользовательские документы"


class LocalSourceStorage:
    """Хранит canonical originals и materialized user-visible tree."""

    def __init__(
        self,
        root_dir: Path,
    ) -> None:
        """Сохраняет canonical storage root."""
        self._root_dir = root_dir

    async def save(
        self,
        *,
        storage_key: str,
        content: bytes,
    ) -> None:
        """Атомарно сохраняет canonical bytes."""
        await asyncio.to_thread(
            self._save_sync,
            storage_key,
            content,
        )

    async def read(
        self,
        *,
        storage_key: str,
    ) -> bytes:
        """Читает canonical bytes вне event loop."""
        return await asyncio.to_thread(
            self._read_sync,
            storage_key,
        )

    async def delete(
        self,
        *,
        storage_key: str,
    ) -> None:
        """Идемпотентно удаляет canonical storage object."""
        await asyncio.to_thread(
            self._delete_sync,
            storage_key,
        )

    async def synchronize_user_tree(
        self,
        *,
        user_id: UUID,
        sections: list[Section],
        sources: list[ManagedSource],
    ) -> None:
        """Атомарно перестраивает visible filesystem tree пользователя."""
        await asyncio.to_thread(
            self._synchronize_user_tree_sync,
            user_id,
            sections,
            sources,
        )

    def _resolve_path(
        self,
        storage_key: str,
    ) -> Path:
        """Проверяет, что internal key остаётся внутри storage root."""
        if not storage_key or "\\" in storage_key:
            raise SourceStorageError("Invalid managed source storage key")

        relative = PurePosixPath(storage_key)

        if relative.is_absolute() or ".." in relative.parts:
            raise SourceStorageError("Invalid managed source storage key")

        root = self._root_dir.resolve()

        target = root.joinpath(*relative.parts).resolve()

        try:
            target.relative_to(root)
        except ValueError as exc:
            raise SourceStorageError("Managed source path escapes storage root") from exc

        return target

    def _save_sync(
        self,
        storage_key: str,
        content: bytes,
    ) -> None:
        """Выполняет synchronous atomic canonical save."""
        target = self._resolve_path(storage_key)

        try:
            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            (
                descriptor,
                temporary_name,
            ) = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=target.parent,
            )

            try:
                with os.fdopen(
                    descriptor,
                    "wb",
                ) as temporary_file:
                    temporary_file.write(content)

                    temporary_file.flush()

                    os.fsync(temporary_file.fileno())

                os.replace(
                    temporary_name,
                    target,
                )
            finally:
                Path(temporary_name).unlink(missing_ok=True)

        except OSError as exc:
            raise SourceStorageError("Failed to save managed source") from exc

    def _read_sync(
        self,
        storage_key: str,
    ) -> bytes:
        """Выполняет synchronous canonical file read."""
        target = self._resolve_path(storage_key)

        try:
            return target.read_bytes()
        except OSError as exc:
            raise SourceStorageError("Failed to read managed source") from exc

    def _delete_sync(
        self,
        storage_key: str,
    ) -> None:
        """Выполняет synchronous idempotent canonical delete."""
        target = self._resolve_path(storage_key)

        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise SourceStorageError("Failed to delete managed source") from exc

    def _synchronize_user_tree_sync(
        self,
        user_id: UUID,
        sections: list[Section],
        sources: list[ManagedSource],
    ) -> None:
        """Строит новое дерево и атомарно заменяет visible user tree."""
        root = self._root_dir.resolve()

        # Короткие служебные paths принципиальны для Windows.
        #
        # pytest уже создаёт длинный temporary path. Если поверх него
        # добавить `.tree-work`, два UUID и человекочитаемые section names,
        # Windows может превысить legacy MAX_PATH ещё до создания
        # настоящего user-visible дерева.
        #
        # Служебные имена пользователю не видны, поэтому делаем их
        # максимально короткими.
        work_root = root / ".tw" / uuid4().hex[:8]

        staging_user_root = work_root / "u"

        target_user_root = root / "users" / str(user_id)

        backup_root = root / ".tb" / uuid4().hex[:8]

        try:
            staging_user_root.mkdir(
                parents=True,
                exist_ok=True,
            )

            section_paths = self._build_section_paths(
                user_id=user_id,
                sections=sections,
            )

            for relative_path in section_paths.values():
                section_root = staging_user_root / relative_path

                (section_root / NORMATIVE_DIRECTORY).mkdir(
                    parents=True,
                    exist_ok=True,
                )

                (section_root / USER_DIRECTORY).mkdir(
                    parents=True,
                    exist_ok=True,
                )

            for source in sources:
                if source.user_id != user_id or source.lifecycle is not SourceLifecycle.ACTIVE:
                    continue

                section_path = section_paths.get(source.section_id)

                if section_path is None:
                    raise SourceStorageError("Active source references missing section")

                canonical = self._resolve_path(source.storage_key)

                if not canonical.is_file():
                    raise SourceStorageError("Canonical managed source is missing")

                kind_directory = (
                    NORMATIVE_DIRECTORY if source.kind is SourceKind.NORMATIVE else USER_DIRECTORY
                )

                mirror_path = (
                    staging_user_root
                    / section_path
                    / kind_directory
                    / self._source_filename(source)
                )

                self._link_or_copy(
                    source=canonical,
                    target=mirror_path,
                )

            self._replace_user_tree(
                staging=staging_user_root,
                target=target_user_root,
                backup=backup_root,
            )

        except SourceStorageError:
            raise

        except OSError as exc:
            raise SourceStorageError("Failed to synchronize managed source directory tree") from exc

        finally:
            # Staging можно удалить всегда.
            #
            # Backup намеренно не удаляется здесь. Если filesystem
            # отказал одновременно при замене и rollback rename,
            # backup остаётся recovery-копией вместо того, чтобы
            # уничтожить последнее корректное visible tree.
            shutil.rmtree(
                work_root,
                ignore_errors=True,
            )

    def _build_section_paths(
        self,
        *,
        user_id: UUID,
        sections: list[Section],
    ) -> dict[UUID, Path]:
        """Строит relative directory paths из section hierarchy."""
        by_id = {section.id: section for section in sections if section.user_id == user_id}

        result: dict[
            UUID,
            Path,
        ] = {}

        resolving: set[UUID] = set()

        def resolve(
            section_id: UUID,
        ) -> Path:
            """Рекурсивно строит path одного section."""
            existing = result.get(section_id)

            if existing is not None:
                return existing

            if section_id in resolving:
                raise SourceStorageError("Section hierarchy contains a cycle")

            section = by_id.get(section_id)

            if section is None:
                raise SourceStorageError("Section hierarchy references missing section")

            resolving.add(section_id)

            own_name = self._section_directory_name(section)

            if section.parent_id is None:
                relative = Path(own_name)
            else:
                if section.parent_id not in by_id:
                    raise SourceStorageError("Section hierarchy references missing parent")

                relative = resolve(section.parent_id) / own_name

            resolving.remove(section_id)

            result[section_id] = relative

            return relative

        for section_id in by_id:
            resolve(section_id)

        return result

    def _replace_user_tree(
        self,
        *,
        staging: Path,
        target: Path,
        backup: Path,
    ) -> None:
        """Меняет user tree через same-filesystem rename с rollback."""
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        backup.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target_existed = target.exists()

        if target_existed:
            target.rename(backup)

        try:
            staging.rename(target)

        except OSError:
            if target_existed and backup.exists() and not target.exists():
                backup.rename(target)

            raise

        if backup.exists():
            shutil.rmtree(backup)

    def _link_or_copy(
        self,
        *,
        source: Path,
        target: Path,
    ) -> None:
        """Создаёт hardlink, а при невозможности безопасную file copy."""
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            os.link(
                source,
                target,
            )

        except OSError:
            try:
                shutil.copy2(
                    source,
                    target,
                )
            except OSError as exc:
                raise SourceStorageError("Failed to materialize managed source mirror") from exc

    @classmethod
    def _section_directory_name(
        cls,
        section: Section,
    ) -> str:
        """Строит понятное collision-safe имя directory section."""
        title = cls._safe_component(
            section.title,
            fallback="section",
            max_length=64,
        )

        return f"{title}__{section.id.hex[:8]}"

    @classmethod
    def _source_filename(
        cls,
        source: ManagedSource,
    ) -> str:
        """Строит понятное collision-safe имя visible source file."""
        original = Path(source.original_name)

        suffix = original.suffix.casefold()

        stem = cls._safe_component(
            original.stem,
            fallback="document",
            max_length=96,
        )

        return f"{stem}__{source.id.hex[:8]}{suffix}"

    @staticmethod
    def _safe_component(
        value: str,
        *,
        fallback: str,
        max_length: int,
    ) -> str:
        """Нормализует имя для Linux/Windows-compatible directory tree."""
        normalized = unicodedata.normalize(
            "NFKC",
            value,
        )

        normalized = _INVALID_COMPONENT.sub(
            "_",
            normalized,
        )

        normalized = _WHITESPACE.sub(
            " ",
            normalized,
        )

        normalized = normalized.strip().rstrip(". ")

        if not normalized:
            normalized = fallback

        normalized = normalized[:max_length].rstrip(". ")

        if normalized.upper() in _WINDOWS_RESERVED_NAMES:
            normalized = f"_{normalized}"

        return normalized
