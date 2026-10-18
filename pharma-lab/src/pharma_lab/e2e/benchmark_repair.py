"""Repairs of the rule-built benchmark questions (eval data v3 design §3.1).

The rule-built generator makes four kinds of wrong row: questions that paste section text
instead of asking, questions that name a section heading, general questions attached to a
section that cannot answer them (regulatory note, incompatibility, trade-name list, ADR
management), pregnancy-and-lactation questions with one of the two sections, and leaflet
questions whose product name is cut in the middle of the title. These rows lower every
configuration alike and hide the difference between layers, so they are dropped or fixed
before the benchmark is assembled. A row no rule touches is returned unchanged.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence

from pharma_lab.e2e.corpus_text import (
    CorpusText,
    normalize_space,
    null_statement,
    section_slug,
)
from pharma_lab.e2e.golden_generate import brand_name

PASTED_MIN_WORDS = 11
_HEADING_LEAK = re.compile(r"\b(của|trong) mục\b", re.IGNORECASE)
_GENERAL = re.compile(
    r"là thuốc gì|là thuốc như thế nào|tìm thông tin|thông tin về|thông tin dược thư|"
    r"cần xem chuyên luận nào|thông tin dược thư tổng quát",
    re.IGNORECASE,
)
_ADR = re.compile(
    r"tác dụng (phụ|không mong muốn)|biểu hiện không mong muốn|phản ứng bất lợi|"
    r"nghĩ tới adr|có thể bị vấn đề gì",
    re.IGNORECASE,
)
# Matched on the question without diacritics, so noisy questions count too.
_PREGNANCY = re.compile(r"co thai|mang thai|ba bau|co bau|dang bau|thai ky|thai phu")
_LACTATION = re.compile(r"cho con bu|cho bu|nuoi con")
# Sections that cannot answer a general or ADR question.
UNANSWERING = {
    "thong-tin-qui-che",
    "tuong-ky",
    "ten-thuong-mai",
    "huong-dan-cach-xu-tri-adr",
}
GENERAL_TARGET = ("thong-tin-chung",)
ADR_TARGET = ("tac-dung-khong-mong-muon-adr", "tac-dung-phu")
PREGNANCY_SLUGS = ("thoi-ky-mang-thai", "thai-ky-va-cho-con-bu")
LACTATION_SLUGS = ("thoi-ky-cho-con-bu", "thai-ky-va-cho-con-bu")
_NAME_BREAK = re.compile(r"[,.;:)]$")


def repair_rows(
    rows: Sequence[dict], corpus: CorpusText
) -> tuple[list[dict], Counter[str]]:
    """The repaired rows, in order, and how many rows each rule changed or dropped."""
    sections = _sections_by_document(corpus)
    counts: Counter[str] = Counter()
    out: list[dict] = []
    for row in rows:
        fixed = _repair(dict(row), corpus, sections, counts)
        if fixed is not None:
            out.append(fixed)
    return out, counts


def _repair(
    row: dict,
    corpus: CorpusText,
    sections: Mapping[str, Mapping[str, str]],
    counts: Counter[str],
) -> dict | None:
    query = normalize_space(str(row["query"]))
    gold = [str(s) for s in row.get("expected_section_ids") or []]
    if not gold:
        return row
    if "?" not in query and len(query.split()) >= PASTED_MIN_WORDS:
        counts["pasted_text"] += 1
        return None
    if _HEADING_LEAK.search(query):
        counts["heading_leak"] += 1
        return None
    answering = [s for s in gold if not null_statement(corpus.sections.get(s, "x"))]
    if not answering or (
        len(answering) < len(gold) and row.get("answer_mode") != ("any_acceptable")
    ):
        counts["null_gold"] += 1
        return None
    if len(answering) < len(gold):
        counts["null_alternative"] += 1
        row = _with_gold(
            row, answering, "any_acceptable" if len(answering) > 1 else ("single")
        )
        gold = answering
    document = corpus.section_documents.get(gold[0], "")
    slugs = sections.get(document, {})
    if len(gold) == 1 and section_slug(gold[0]) in UNANSWERING:
        target, rule = _regold(query, str(row.get("intent_category")), gold[0], corpus)
        if rule:
            found = next((slugs[s] for s in target if s in slugs), None)
            if found is None:
                counts["dropped_no_target"] += 1
                return None
            counts[rule] += 1
            row = _with_gold(row, [found], "single")
            gold = [found]
    if len(gold) == 1 and section_slug(gold[0]) in {*PREGNANCY_SLUGS, *LACTATION_SLUGS}:
        row = _pregnancy_lactation(row, query, gold[0], slugs, counts)
    if document.startswith("leaflet:"):
        restored = _restore_name(query, corpus.titles.get(document, ""))
        if restored is not None:
            counts["truncated_name"] += 1
            row = {**row, "query": restored}
    return row


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()


def _pregnancy_lactation(
    row: dict,
    query: str,
    section_id: str,
    slugs: Mapping[str, str],
    counts: Counter[str],
) -> dict:
    """A pregnancy or lactation question gets the section of what it asks: both
    sections when it asks both, the other section when it was attached to the wrong
    one."""
    folded = _fold(query)
    pregnancy, lactation = (
        bool(_PREGNANCY.search(folded)),
        bool(_LACTATION.search(folded)),
    )
    preg = next((slugs[s] for s in PREGNANCY_SLUGS if s in slugs), None)
    lact = next((slugs[s] for s in LACTATION_SLUGS if s in slugs), None)
    if pregnancy and lactation:
        pair = [s for s in dict.fromkeys([preg, lact]) if s is not None]
        if len(pair) == 2:
            counts["pregnancy_lactation"] += 1
            return _with_gold(row, pair, "multi_required")
        return row
    wanted = preg if pregnancy else lact if lactation else None
    if wanted is not None and wanted != section_id:
        counts["pregnancy_lactation_regold"] += 1
        return _with_gold(row, [wanted], "single")
    return row


def _restore_name(query: str, title: str) -> str | None:
    """The question with its product name cut back to the brand when the generator
    cut the title in the middle of a phrase: "Tamiflu 75 mg phòng và dùng liều thế
    nào?" from "Tamiflu 75 mg phòng và trị cúm …" becomes "Tamiflu 75 mg dùng liều
    thế nào?". A name that stops at a phrase break is left as it is."""
    brand = brand_name(title)
    if not brand or not query.casefold().startswith(brand.casefold()):
        return None
    at = title.casefold().find(brand.casefold())
    if at < 0:
        return None
    asked = query[len(brand) :].split()
    rest = title[at + len(brand) :].split()
    common = 0
    while (
        common < min(len(asked), len(rest))
        and asked[common].casefold() == rest[common].casefold()
        and not _NAME_BREAK.search(rest[common])
    ):
        common += 1
    if common == 0 or common >= len(asked) or common >= len(rest):
        return None
    if asked[common].casefold() == rest[common].casefold():
        return None  # the question copies the title up to a phrase break
    return f"{brand} {' '.join(asked[common:])}"


def _regold(
    query: str, intent: str, section_id: str, corpus: CorpusText
) -> tuple[tuple[str, ...], str]:
    """Where a question attached to an unanswering section belongs, and the rule name;
    no rule when the attachment is right (a brand question naming a listed brand)."""
    slug = section_slug(section_id)
    if slug == "ten-thuong-mai" and _names_a_listed_brand(query, section_id, corpus):
        return (), ""
    if intent == "adr" or _ADR.search(query):
        return ADR_TARGET, "adr_regold"
    if intent in {"general_info", "brand_lookup"} or _GENERAL.search(query):
        return GENERAL_TARGET, "generic_regold"
    return (), ""


def _names_a_listed_brand(query: str, section_id: str, corpus: CorpusText) -> bool:
    """A capitalised word of the question, other than the drug's own name, appears in
    the trade-name list."""
    text = corpus.sections.get(section_id, "").casefold()
    document = corpus.section_documents.get(section_id, "")
    own = set(corpus.titles.get(document, "").casefold().split())
    words = re.findall(r"[^\W\d_][\w-]{2,}", query)
    return any(
        word.casefold() in text and word.casefold() not in own
        for word in words
        if word[0].isupper()
    )


def _with_gold(row: dict, gold: list[str], mode: str) -> dict:
    return {
        **row,
        "expected_section_id": gold[0],
        "expected_section_ids": gold,
        "query_intent_count": len(gold),
        "answer_mode": mode,
    }


def _sections_by_document(corpus: CorpusText) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for section_id, document in corpus.section_documents.items():
        index.setdefault(document, {})[section_slug(section_id)] = section_id
    return index
