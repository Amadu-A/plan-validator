# tests/unit/context_service/test_vector_store_contract.py

"""Unit tests deterministic per-context Qdrant naming contract."""

from uuid import UUID

from context_service.domain.models import ContextSourceKind
from context_service.infrastructure.vector_store.qdrant import (
    build_context_collection_name,
    build_context_point_id,
)


def test_t_and_pz_use_different_collections_for_same_context() -> None:
    """Не позволяет typed T/PZ retrieval смешивать collections."""
    context_id = UUID("11111111-2222-3333-4444-555555555555")

    t_name = build_context_collection_name(
        prefix="plan_validator",
        context_id=context_id,
        kind=ContextSourceKind.TECHNICAL_ASSIGNMENT,
    )
    pz_name = build_context_collection_name(
        prefix="plan_validator",
        context_id=context_id,
        kind=ContextSourceKind.PROJECT_NOTE,
    )

    assert t_name == "plan_validator_t_11111111222233334444555555555555"
    assert pz_name == "plan_validator_pz_11111111222233334444555555555555"
    assert t_name != pz_name


def test_point_id_is_deterministic_per_generation_and_chunk() -> None:
    """Повторный candidate upsert адресует тот же Qdrant point."""
    source_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    first = build_context_point_id(
        source_id=source_id,
        fingerprint="f" * 64,
        chunk_id="p1-0",
    )
    second = build_context_point_id(
        source_id=source_id,
        fingerprint="f" * 64,
        chunk_id="p1-0",
    )

    assert first == second
