import hashlib

import pytest

from pharma_lab.hashing import (
    canonical_sha256,
    document_hash,
    model_slug,
    query_hash,
    sha256_file,
)


def test_sha256_file_matches_hashlib_for_a_multi_block_file(tmp_path):
    data = b"x" * 3_000_000
    path = tmp_path / "a.bin"
    path.write_bytes(data)

    assert sha256_file(path) == hashlib.sha256(data).hexdigest()


def test_sha256_file_raises_os_error_for_a_missing_file(tmp_path):
    with pytest.raises(OSError):
        sha256_file(tmp_path / "missing.bin")


def test_canonical_sha256_ignores_key_order_and_whitespace():
    assert canonical_sha256({"b": 1, "a": [1, 2]}) == canonical_sha256(
        {"a": [1, 2], "b": 1}
    )
    assert canonical_sha256({"a": 1}) == hashlib.sha256(b'{"a":1}').hexdigest()


def test_query_hash_strips_surrounding_whitespace_only():
    assert query_hash("  paracetamol ") == query_hash("paracetamol")
    assert query_hash("Paracetamol") != query_hash("paracetamol")


def test_model_slug_replaces_separators_with_underscores():
    assert model_slug("qwen3-embedding:0.6b-q8_0") == "qwen3_embedding_0_6b_q8_0"


def test_document_hash_is_sha256_of_utf8_text():
    assert document_hash("thuốc") == hashlib.sha256("thuốc".encode()).hexdigest()
