"""Plain text of every section and document title in a knowledge bundle."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from pharma_agent.domain.corpus.bundle import KnowledgeBundle, read_bundle

from pharma_lab.bundle.chunks import gold_chunk_label, iter_document_chunks


def normalize_space(text: str) -> str:
    return " ".join(text.split())


# A section that says there is nothing to say: "Không có.", "Chưa có báo cáo.", or the
# leaflet line that only tells the reader to call the emergency number.
NULL_STATEMENT_CHARS = 200
_NULL_OPENER = re.compile(
    r"^(hiện( nay)? |cho đến nay |hiện tại )?(không|chưa) (có|thấy|ghi nhận|được)",
    re.IGNORECASE,
)
_ADVICE = re.compile(
    r"không (nên )?(dùng|sử dụng|khuyến)|thận trọng|tránh|ngừng|điều trị|xử trí|"
    r"theo dõi|chỉ (khi|nên|dùng)|cân nhắc",
    re.IGNORECASE,
)
_EMERGENCY_ONLY = re.compile(r"cấp cứu 115", re.IGNORECASE)


def null_statement(text: str) -> bool:
    """A short section that answers nothing: it only says there is no information,
    no report or nothing to note, without advice, or only points to emergency care."""
    flat = normalize_space(text)
    if len(flat) >= NULL_STATEMENT_CHARS:
        return False
    if len(flat) < 15 or _EMERGENCY_ONLY.search(flat):
        return True
    return bool(_NULL_OPENER.search(flat)) and not _ADVICE.search(flat)


def section_slug(section_id: str) -> str:
    """`drug:x:tuong-tac-thuoc` -> `tuong-tac-thuoc`; leaflets drop the `NN-` prefix."""
    slug = section_id.rsplit(":", 1)[1]
    return re.sub(r"^\d+-", "", slug)


@dataclass(frozen=True)
class CorpusText:
    # section key -> section markdown (blocks joined by blank lines)
    sections: dict[str, str]
    # section key -> document key
    section_documents: dict[str, str]
    # document key -> title
    titles: dict[str, str]

    def normalized_section(self, section_id: str) -> str | None:
        text = self.sections.get(section_id)
        return None if text is None else normalize_space(text)

    @cached_property
    def _folded(self) -> str:
        texts = [*self.sections.values(), *self.titles.values()]
        return "\n".join(normalize_space(text).casefold() for text in texts)

    def contains(self, term: str) -> bool:
        """Whether `term` occurs, case-insensitively, in any section or title."""
        needle = normalize_space(term).casefold()
        return bool(needle) and needle in self._folded


def load_corpus_text(bundle_dir: Path) -> CorpusText:
    return corpus_text(read_bundle(bundle_dir))


def chunk_texts(bundle: KnowledgeBundle, section_ids: Iterable[str]) -> dict[str, str]:
    """Chunk text by gold chunk label for the chunks that hold the given sections."""
    wanted = set(section_ids)
    texts: dict[str, str] = {}
    for item in iter_document_chunks(bundle):
        for draft in item.drafts:
            if wanted & set(draft.section_keys):
                label = gold_chunk_label(draft.document_key, draft.ordinal)
                texts[label] = draft.chunk_text
    return texts


def section_chunks(bundle: KnowledgeBundle) -> dict[str, str]:
    """The gold chunk label that holds each section."""
    chunks: dict[str, str] = {}
    for item in iter_document_chunks(bundle):
        for draft in item.drafts:
            label = gold_chunk_label(draft.document_key, draft.ordinal)
            for section_key in draft.section_keys:
                chunks[section_key] = label
    return chunks


def corpus_text(bundle: KnowledgeBundle) -> CorpusText:
    return CorpusText(
        sections={
            section.key: "\n\n".join(block.markdown for block in section.blocks)
            for section in bundle.sections
        },
        section_documents={
            section.key: section.document_key for section in bundle.sections
        },
        titles={document.key: document.title for document in bundle.documents},
    )
