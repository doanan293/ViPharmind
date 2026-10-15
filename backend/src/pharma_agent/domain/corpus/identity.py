"""Deterministic identities for chunk versions (spec C §6.1, v2 §3.0c).

Public API: pharma-lab uses ``sha256_hex`` to key precomputed embeddings.
"""

import hashlib
import json
import uuid
from collections.abc import Mapping

from pharma_agent.domain.shared.text import normalize_text

CORPUS_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "pharma-agent:corpus:v1")
_SEPARATOR = "\x1f"


def _normalized(value: object) -> object:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, Mapping):
        return {str(key): _normalized(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_normalized(item) for item in value]
    return value


def canonical_json(value: object) -> str:
    """Sorted keys, no insignificant whitespace, every string normalized."""
    return json.dumps(
        _normalized(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_version_id(
    document_key: str, chunk_text: str, embedding_text: str, chunker_version: str
) -> uuid.UUID:
    digest = sha256_hex(
        _SEPARATOR.join(
            (
                document_key,
                normalize_text(chunk_text),
                normalize_text(embedding_text),
                chunker_version,
            )
        )
    )
    return uuid.uuid5(CORPUS_NAMESPACE, "chunk" + _SEPARATOR + digest)
