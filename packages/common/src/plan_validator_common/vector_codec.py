# packages/common/src/plan_validator_common/vector_codec.py

"""Компактный transport codec dense float32 embedding vectors."""

import base64
import sys
from array import array
from collections.abc import Sequence

FLOAT32_BASE64_ENCODING = "float32-le-base64"


def encode_float32_vectors(
    vectors: Sequence[Sequence[float]],
    *,
    dimension: int,
) -> str:
    """Кодирует rectangular vectors в little-endian float32 Base64 payload."""
    if dimension <= 0:
        raise ValueError("Vector dimension must be positive")

    values = array("f")

    for vector in vectors:
        if len(vector) != dimension:
            raise ValueError("Vector dimension mismatch")

        values.extend(float(value) for value in vector)

    if sys.byteorder != "little":
        values.byteswap()

    return base64.b64encode(values.tobytes()).decode("ascii")


def decode_float32_vectors(
    payload: str,
    *,
    vector_count: int,
    dimension: int,
) -> tuple[tuple[float, ...], ...]:
    """Декодирует little-endian float32 Base64 в immutable vector batch."""
    if vector_count < 0:
        raise ValueError("Vector count must not be negative")

    if dimension <= 0:
        raise ValueError("Vector dimension must be positive")

    try:
        raw = base64.b64decode(
            payload.encode("ascii"),
            validate=True,
        )
    except (UnicodeEncodeError, ValueError) as exc:
        raise ValueError("Embedding vector payload is not valid Base64") from exc

    expected_bytes = vector_count * dimension * 4

    if len(raw) != expected_bytes:
        raise ValueError(
            f"Embedding vector payload size mismatch: expected={expected_bytes}, actual={len(raw)}"
        )

    values = array("f")
    values.frombytes(raw)

    if sys.byteorder != "little":
        values.byteswap()

    return tuple(
        tuple(float(value) for value in values[offset : offset + dimension])
        for offset in range(
            0,
            len(values),
            dimension,
        )
    )
