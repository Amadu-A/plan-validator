# services/retrieval-service/src/retrieval_service/infrastructure/qdrant_initializer.py

"""One-shot initializer shared Qdrant managed-source collection и alias."""

import asyncio
import logging

from plan_validator_common.observability import configure_logging
from qdrant_client import models

from retrieval_service.core.settings import RetrievalSettings, load_retrieval_settings
from retrieval_service.infrastructure.vector_store.qdrant import build_qdrant_client

_LOGGER = logging.getLogger(__name__)
_PAYLOAD_KEYWORD_FIELDS = (
    "kind",
    "section_id",
    "source_id",
    "version_key",
)


async def initialize_qdrant(settings: RetrievalSettings) -> None:
    """Создаёт physical collection/indexes и stable alias idempotently."""
    qdrant = settings.retrieval_qdrant
    client = build_qdrant_client(
        host=qdrant.host,
        http_port=qdrant.http_port,
        grpc_port=qdrant.grpc_port,
        prefer_grpc=qdrant.prefer_grpc,
        timeout_seconds=qdrant.timeout_seconds,
    )

    try:
        if not await client.collection_exists(qdrant.collection_name):
            await client.create_collection(
                collection_name=qdrant.collection_name,
                vectors_config=models.VectorParams(
                    size=qdrant.vector_size,
                    distance=models.Distance.COSINE,
                ),
                hnsw_config=models.HnswConfigDiff(m=0, payload_m=16),
            )

        info = await client.get_collection(qdrant.collection_name)
        vectors = info.config.params.vectors
        actual_size = getattr(vectors, "size", None)

        if actual_size != qdrant.vector_size:
            raise RuntimeError(
                "Existing managed-source collection vector size mismatch: "
                f"expected={qdrant.vector_size}, actual={actual_size}"
            )

        payload_fields = set(info.payload_schema)

        if "user_id" not in payload_fields:
            await client.create_payload_index(
                collection_name=qdrant.collection_name,
                field_name="user_id",
                field_schema=models.KeywordIndexParams(
                    type=models.KeywordIndexType.KEYWORD,
                    is_tenant=True,
                ),
                wait=True,
            )

        for field_name in _PAYLOAD_KEYWORD_FIELDS:
            if field_name in payload_fields:
                continue

            await client.create_payload_index(
                collection_name=qdrant.collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )

        aliases = await client.get_aliases()
        matching = [alias for alias in aliases.aliases if alias.alias_name == qdrant.alias_name]

        if not matching:
            await client.update_collection_aliases(
                change_aliases_operations=[
                    models.CreateAliasOperation(
                        create_alias=models.CreateAlias(
                            collection_name=qdrant.collection_name,
                            alias_name=qdrant.alias_name,
                        )
                    )
                ]
            )
        elif len(matching) != 1 or matching[0].collection_name != qdrant.collection_name:
            targets = ", ".join(alias.collection_name for alias in matching)
            raise RuntimeError(
                f"Qdrant alias {qdrant.alias_name} points to unexpected collection(s): {targets}"
            )

        _LOGGER.info(
            "Managed-source Qdrant corpus initialized",
            extra={
                "event": "retrieval_qdrant_initialized",
                "collection": qdrant.collection_name,
                "alias": qdrant.alias_name,
                "vector_size": qdrant.vector_size,
            },
        )
    finally:
        await client.close()


def main() -> None:
    """Настраивает logging и запускает one-shot Qdrant initializer."""
    settings = load_retrieval_settings()
    configure_logging(
        service_name="retrieval-init",
        level=settings.log_level.value,
        log_root_dir=settings.log_root_dir,
        log_to_file=settings.log_to_file,
        file_max_bytes=settings.log_file_max_bytes,
        file_backup_count=settings.log_file_backup_count,
        retention_days=settings.log_retention_days,
    )
    asyncio.run(initialize_qdrant(settings))


if __name__ == "__main__":
    main()
