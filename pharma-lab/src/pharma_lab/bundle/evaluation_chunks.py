"""Chunk rows for the evaluation dataset builders, derived from the backend chunker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pharma_agent.domain.corpus.bundle import BlockKind, DocumentKind, KnowledgeBundle

from pharma_lab.bundle.chunks import gold_chunk_label, iter_document_chunks

CONTENT_TYPES: dict[DocumentKind, str] = {
    DocumentKind.DRUG_MONOGRAPH: "drug_monograph",
    DocumentKind.GENERAL_MONOGRAPH: "general_monograph",
    DocumentKind.LEAFLET: "brand_page",
}
LIST_KINDS = {BlockKind.LIST, BlockKind.INDEX_ENTRIES}


def evaluation_chunk_rows(bundle: KnowledgeBundle) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in iter_document_chunks(bundle):
        kinds = {
            section.key: {block.kind for block in section.blocks}
            for section in item.sections
        }
        for draft in item.drafts:
            held: set[BlockKind] = set().union(*(kinds[k] for k in draft.section_keys))
            rows.append(
                {
                    "chunk_id": gold_chunk_label(draft.document_key, draft.ordinal),
                    "document_id": draft.document_key,
                    "ordinal": draft.ordinal,
                    "section_ids": list(draft.section_keys),
                    "headings": list(draft.headings),
                    "title": item.document.title,
                    "source": item.document.source.title,
                    "content_type": CONTENT_TYPES[item.document.kind],
                    "context_header": draft.context_header,
                    "chunk_text": draft.chunk_text,
                    "embedding_text": draft.embedding_text,
                    "has_table": BlockKind.TABLE in held,
                    "has_list": bool(held & LIST_KINDS),
                    "colloquial_mapping": {}
                    if draft.colloquial is None
                    else {
                        "key": draft.colloquial.key,
                        "aliases": list(draft.colloquial.aliases),
                        "visual_sign": draft.colloquial.visual_sign,
                        "product_names": list(draft.colloquial.product_names),
                    },
                    "term_annotations": [
                        term.model_dump() for term in draft.term_annotations
                    ],
                }
            )
    return rows


def write_evaluation_chunks(bundle: KnowledgeBundle, path: Path) -> int:
    rows = evaluation_chunk_rows(bundle)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows)
