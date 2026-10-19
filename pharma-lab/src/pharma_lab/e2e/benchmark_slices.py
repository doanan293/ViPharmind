"""Construction-defined slices of the benchmark (eval data v3 design §3.4).

A slice is a property of the question and the corpus, never of a system's result, so a
layer's gain inside its slice is not selected by that layer. Each row gets the slices it
belongs to:

- `header_dependent`: the question names the drug or product but no gold section does;
  only the chunk header carries the name, so the header enrichment is what lets
  retrieval find it. A question that names nothing (a follow-up turn) gains nothing
  from a header.
- `name_variant`: a standalone question refers to the drug or product, but no word of
  its name occurs as written (misspelt or without diacritics, within two edits of a
  name word); lexical search cannot match the name, the dense half of hybrid search
  can. Follow-up turns, which do not name the drug at all, are left out.
- `rare_term`: a standalone question carries a word that occurs in at most
  RARE_TERM_SECTIONS sections of the corpus and in the gold section as written (a
  brand in a trade-name list, a product in its "thông tin thêm"); the dense model
  barely knows such a word, the lexical half of hybrid search matches it.
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
from pharma_lab.evaluation.section_eval_schema import BENCHMARK_SLICES

SLICES = BENCHMARK_SLICES
RARE_TERM_SECTIONS = 10
NAME_EDITS = 2
CONVERSATIONAL = "conversational"


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w{2,}", _fold(text)))


def _terms(text: str) -> set[str]:
    """Words of four characters or more that start with a letter."""
    return set(re.findall(r"[^\W\d_][\w-]{3,}", _fold(text)))


def _ascii(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()


def _edits(a: str, b: str, limit: int) -> int:
    """Levenshtein distance, cut off above `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        current = [i]
        for j, y in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y))
            )
        previous = current
    return previous[-1]


def refers_to(question: str, name: str) -> bool:
    """Whether a word of the question is within NAME_EDITS edits of a word of `name`,
    diacritics aside."""
    asked = re.findall(r"\w{3,}", _ascii(question))
    named = re.findall(r"\w{3,}", _ascii(name))
    return any(_edits(a, n, NAME_EDITS) <= NAME_EDITS for a in asked for n in named)


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
        # Sections each term occurs in, to tell a rare term from a common one.
        self.section_counts: dict[str, int] = defaultdict(int)
        for text in corpus.sections.values():
            for term in _terms(text):
                self.section_counts[term] += 1
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

    def full_name(self, document: str) -> str:
        """The name a user would write: the monograph name, or the product name with
        its strength."""
        title = self.corpus.titles.get(document, "")
        return drug_name(title) if document.startswith("drug:") else brand_name(title)

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
        question = str(row.get("query", ""))
        standalone = row.get("eval_group") != CONVERSATIONAL
        full = self.full_name(document)
        written = bool(_words(full) & _words(question))
        name = self.name(document)
        if name and name not in _fold(text) and (written or refers_to(question, full)):
            found.append("header_dependent")
        if standalone and full and not written and refers_to(question, full):
            found.append("name_variant")
        gold_terms = _terms(text)
        if standalone and any(
            self.section_counts.get(term, 0) <= RARE_TERM_SECTIONS
            for term in _terms(question) & gold_terms
        ):
            found.append("rare_term")
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
