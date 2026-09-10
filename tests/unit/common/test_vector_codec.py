# tests/unit/common/test_vector_codec.py

"""Unit tests compact dense embedding vector transport codec."""

import math

import pytest
from plan_validator_common.vector_codec import (
    FLOAT32_BASE64_ENCODING,
    decode_float32_vectors,
    encode_float32_vectors,
)


def test_float32_base64_vectors_round_trip() -> None:
    """Проверяет compact round-trip нескольких vectors с float32 tolerance."""
    vectors = (
        (0.1, 0.2, 0.3, 0.4),
        (-0.5, 0.0, 0.5, 1.0),
    )

    payload = encode_float32_vectors(vectors, dimension=4)
    restored = decode_float32_vectors(
        payload,
        vector_count=2,
        dimension=4,
    )

    assert FLOAT32_BASE64_ENCODING == "float32-le-base64"
    assert len(restored) == 2

    for expected, actual in zip(vectors, restored, strict=True):
        assert all(
            math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-6)
            for left, right in zip(expected, actual, strict=True)
        )


def test_float32_base64_codec_rejects_wrong_shape() -> None:
    """Не допускает silent vector dimension/byte-length corruption."""
    with pytest.raises(ValueError, match="dimension mismatch"):
        encode_float32_vectors(((1.0, 2.0),), dimension=3)

    payload = encode_float32_vectors(((1.0, 2.0),), dimension=2)

    with pytest.raises(ValueError, match="payload size mismatch"):
        decode_float32_vectors(payload, vector_count=2, dimension=2)
