"""Pure hash helpers shared by every layer, Kaggle workers included."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_query_for_hash(query: str) -> str:
    return query.strip()


def query_hash(query: str) -> str:
    normalized = normalize_query_for_hash(query)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def model_slug(model_name: str) -> str:
    return (
        model_name.replace(":", "_")
        .replace("-", "_")
        .replace(".", "_")
        .replace("/", "_")
    )


def document_hash(document_text: str) -> str:
    return hashlib.sha256(document_text.encode("utf-8")).hexdigest()
