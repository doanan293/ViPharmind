from __future__ import annotations

import builtins
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pharma_lab import hashing as _query_hash
from pharma_lab.cache.jsonl_records import (
    CacheRecordError,
    ValidatedSubset,
    append_record,
    load_records,
    rewrite_records,
)
from pharma_lab.cache.jsonl_records import (
    subset_sha256 as record_subset_sha256,
)

model_slug = _query_hash.model_slug
normalize_query_for_hash = _query_hash.normalize_query_for_hash
query_hash = _query_hash.query_hash


class QueryEmbeddingCacheError(RuntimeError):
    pass


def validate_embedding(
    value, path: Path | None = None, line_number: int | None = None
) -> list[float]:
    location = ""
    if path is not None and line_number is not None:
        location = f" at {path}:{line_number}"
    if not isinstance(value, list) or not value:
        raise QueryEmbeddingCacheError(f"embedding must be a non-empty list{location}")
    vector: list[float] = []
    for item in value:
        if not isinstance(item, int | float):
            raise QueryEmbeddingCacheError(
                f"embedding values must be numeric{location}"
            )
        vector.append(float(item))
    return vector


@dataclass
class QueryEmbeddingCache:
    path: Path
    vector_dim: int | None = None
    model_sha256: str = ""

    def __post_init__(self):
        self.path = Path(self.path)
        self.model_sha256 = self.model_sha256
        self.records: dict[tuple[str, str, str], list[float]] = {}
        self.record_metadata: dict[tuple[str, str, str], dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            records = load_records(self.path)
        except CacheRecordError as exc:
            raise QueryEmbeddingCacheError(str(exc)) from exc
        for line_number, record in enumerate(records, start=1):
            self._load_record(self._normalize_record(record, line_number), line_number)

    def _normalize_record(self, record: dict, line_number: int) -> dict:
        for field in ("model", "query_id", "embedding"):
            if field not in record:
                raise QueryEmbeddingCacheError(
                    f"Cache record missing required field '{field}' in {self.path}:{line_number}"
                )
        query = str(record.get("query") or "")
        if not query.strip():
            raise QueryEmbeddingCacheError(
                f"Cache record requires query text in {self.path}:{line_number}"
            )
        vector = validate_embedding(record["embedding"], self.path, line_number)
        dimension = int(record.get("vector_dim") or len(vector))
        if self.vector_dim is None:
            self.vector_dim = dimension
        if dimension != self.vector_dim or len(vector) != self.vector_dim:
            raise QueryEmbeddingCacheError(
                f"Query embedding dimension mismatch at {self.path}:{line_number}: "
                f"{len(vector)} != {self.vector_dim}"
            )
        record_model_sha = str(record.get("model_sha256") or "")
        if self.model_sha256 and record_model_sha not in ("", self.model_sha256):
            raise QueryEmbeddingCacheError(
                f"Model digest mismatch in {self.path}:{line_number}"
            )
        normalized = {
            **record,
            "model": str(record["model"]),
            "model_sha256": self.model_sha256 or record_model_sha,
            "query_id": str(record["query_id"]),
            "query_hash": query_hash(query),
            "query": query,
            "vector_dim": self.vector_dim,
            "embedding": vector,
        }
        return normalized

    def _load_record(self, record: dict, line_number: int) -> None:
        if record.get("query_hash") != query_hash(str(record.get("query") or "")):
            raise QueryEmbeddingCacheError(
                f"Query hash mismatch in {self.path}:{line_number}"
            )
        vector = validate_embedding(record["embedding"], self.path, line_number)
        key = (str(record["model"]), str(record["query_id"]), str(record["query_hash"]))
        # Append-only checkpoints may contain a newer replacement for a key;
        # the last validated record is authoritative.
        self.records[key] = vector
        self.record_metadata[key] = dict(record)

    def get(self, model: str, query_id: str, query_text: str) -> list[float] | None:
        key = (model, query_id, query_hash(query_text))
        vector = self.records.get(key)
        if vector is None:
            return None
        return list(vector)

    def set(
        self, model: str, query_id: str, query_text: str, embedding: list[float]
    ) -> list[float]:
        vector = validate_embedding(embedding)
        if self.vector_dim is None:
            self.vector_dim = len(vector)
        if len(vector) != self.vector_dim:
            raise QueryEmbeddingCacheError(
                f"Query embedding dimension mismatch: {len(vector)} != {self.vector_dim}"
            )
        key = (model, query_id, query_hash(query_text))
        record = {
            "model": model,
            "model_sha256": self.model_sha256,
            "query_id": query_id,
            "query_hash": key[2],
            "query": query_text,
            "vector_dim": self.vector_dim,
            "embedding": vector,
            "created_at": datetime.now(UTC).isoformat(),
        }
        record = append_record(self.path, record, schema="query-embedding-v2")
        self.records[key] = vector
        self.record_metadata[key] = record
        return list(vector)

    def replace_keys(self, keys: builtins.set[tuple[str, str, str]]) -> None:
        kept = [
            key_record
            for key, key_record in self.record_metadata.items()
            if key not in keys
        ]
        rewrite_records(
            self.path, sorted(kept, key=lambda item: json.dumps(item, sort_keys=True))
        )
        self.records.clear()
        self.record_metadata.clear()
        self._load()

    def validate_subset(self, rows: list[dict], model: str) -> ValidatedSubset:
        expected = {
            (
                model,
                str(row.get("query_id") or ""),
                query_hash(str(row.get("query") or "")),
            )
            for row in rows
        }
        found = [
            self.record_metadata[key]
            for key in sorted(expected)
            if key in self.record_metadata
        ]
        for record in found:
            if record.get("model") != model:
                raise QueryEmbeddingCacheError(
                    "Query cache contains an unexpected model"
                )
        missing = len(expected) - len(found)
        return ValidatedSubset(
            total=len(expected),
            complete=len(found),
            missing=missing,
            sha256=record_subset_sha256(found) if not missing else None,
        )

    def subset_sha256(self, rows: list[dict], model: str) -> str:
        subset = self.validate_subset(rows, model)
        if not subset.is_complete:
            raise QueryEmbeddingCacheError(
                f"Query embedding cache is missing {subset.missing} records"
            )
        return str(subset.sha256)
