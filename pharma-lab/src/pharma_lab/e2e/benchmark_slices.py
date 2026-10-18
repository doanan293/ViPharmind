"""Construction-defined slices of the benchmark (eval data v3 design §3.4).

A slice is a property of the question and the corpus, never of a system's result, so a
layer's gain inside its slice is not selected by that layer. Each row gets the slices it
belongs to:

- `header_dependent`: no gold section names the drug or product; only the chunk header
  carries the name, so the header enrichment is what lets retrieval find it.
- `low_overlap`: under 35% of the question's content words occur in the gold sections
  and the title; lexical search alone misses it, dense search in hybrid finds it.
- `sibling_products`: another leaflet of the same brand with the same active
  ingredients has the asked section (another strength or form); the candidates look
  alike and the reranker decides the order.
- `multi_chunk`: the required gold sections sit in two or more chunks.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping

from pharma_lab.e2e.corpus_text import CorpusText, section_slug
from pharma_lab.e2e.golden_generate import (
    COMPOSITION,
    MonographNames,
    brand_name,
    drug_name,
)

SLICES = ("header_dependent", "low_overlap", "sibling_products", "multi_chunk")
LOW_OVERLAP = 0.35
_STOP = frozenset(
    [
        "thuốc",
        "dùng",
        "như",
        "thế",
        "nào",
        "những",
        "không",
        "được",
        "có",
        "gì",
        "bao",
        "nhiêu",
        "cần",
        "khi",
        "các",
        "của",
        "cho",
        "với",
        "này",
        "người",
    ]
)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _content_words(text: str) -> set[str]:
    return set(re.findall(r"\w{3,}", _fold(text))) - _STOP


def _document(section_id: str) -> str:
    parts = section_id.split(":")
    return ":".join(parts[:3] if parts[0] == "leaflet" else parts[:2])


class SliceIndex:
    """What the slices need from the corpus, built once for the benchmark."""

    def __init__(self, corpus: CorpusText, chunks: Mapping[str, str]) -> None:
        self.corpus = corpus
        self.chunks = chunks
        names = MonographNames(corpus)
        self.slugs: dict[str, set[str]] = defaultdict(set)
        self.actives: dict[str, frozenset[str]] = {}
        for section_id, document in corpus.section_documents.items():
            self.slugs[document].add(section_slug(section_id))
            if document.startswith("leaflet:") and section_slug(section_id) == (
                COMPOSITION
            ):
                text = corpus.sections[section_id][:600]
                actives = re.split(r"tá dược", text, maxsplit=1, flags=re.IGNORECASE)[0]
                found = frozenset(names.named_in(actives))
                if found:
                    self.actives[document] = found
        self.families: dict[tuple[frozenset[str], str], list[str]] = defaultdict(list)
        for document, actives in self.actives.items():
            self.families[(actives, self.brand(document))].append(document)

    def name(self, document: str) -> str:
        """The name a section would carry: the monograph name, or the product's
        brand word."""
        title = self.corpus.titles.get(document, "")
        if document.startswith("drug:"):
            return _fold(drug_name(title))
        return self.brand(document)

    def brand(self, document: str) -> str:
        words = _fold(brand_name(self.corpus.titles.get(document, ""))).split()
        return words[0] if words else ""

    def slices(self, row: Mapping[str, object]) -> list[str]:
        """The slices of one benchmark row, in SLICES order."""
        gold = row.get("expected_section_ids")
        sections = [str(s) for s in gold] if isinstance(gold, list) else []
        if not sections:
            return []
        document = _document(sections[0])
        text = " ".join(self.corpus.sections.get(s, "") for s in sections)
        found: list[str] = []
        name = self.name(document)
        if name and name not in _fold(text):
            found.append("header_dependent")
        words = _content_words(str(row.get("query", "")))
        title = self.corpus.titles.get(document, "")
        if words and len(words & _content_words(f"{text} {title}")) / len(words) < (
            LOW_OVERLAP
        ):
            found.append("low_overlap")
        if self._has_sibling(document, section_slug(sections[0])):
            found.append("sibling_products")
        if row.get("answer_mode") == "multi_required" and (
            len({self.chunks.get(s, s) for s in sections}) >= 2
        ):
            found.append("multi_chunk")
        return found

    def _has_sibling(self, document: str, slug: str) -> bool:
        actives = self.actives.get(document)
        if actives is None:
            return False
        family = self.families[(actives, self.brand(document))]
        return any(other != document and slug in self.slugs[other] for other in family)
