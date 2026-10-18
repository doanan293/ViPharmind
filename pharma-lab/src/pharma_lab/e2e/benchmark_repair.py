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
from collections import Counter
from collections.abc import Mapping, Sequence

from pharma_lab.e2e.corpus_text import CorpusText, normalize_space, section_slug
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
_PREGNANCY = re.compile(r"có thai|mang thai|bà bầu|thai kỳ", re.IGNORECASE)
_LACTATION = re.compile(r"cho con bú", re.IGNORECASE)
# The generator cut product names after the first use verb, sometimes keeping "và":
# "Tamiflu 75 mg phòng và dùng liều thế nào?" from "Tamiflu 75 mg phòng và trị cúm …".
_CUT_NAME = re.compile(
    r"^(?P<prefix>.+?\s(?:phòng|trị|điều trị|giảm|hỗ trợ|bổ sung|chống|ngừa|cầm|tăng|"
    r"giúp)(?:\svà)?)\s(?P<rest>(?:có|dùng|bảo|cần|là|thì|nên|chứa|uống|trong)\b.*)$"
)
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
    if (
        len(gold) == 1
        and _PREGNANCY.search(query)
        and _LACTATION.search(query)
        and section_slug(gold[0]) in {*PREGNANCY_SLUGS, *LACTATION_SLUGS}
    ):
        both = [
            next((slugs[s] for s in PREGNANCY_SLUGS if s in slugs), None),
            next((slugs[s] for s in LACTATION_SLUGS if s in slugs), None),
        ]
        pair = [s for s in dict.fromkeys(both) if s is not None]
        if len(pair) == 2:
            counts["pregnancy_lactation"] += 1
            row = _with_gold(row, pair, "multi_required")
    if document.startswith("leaflet:"):
        match = _CUT_NAME.match(query)
        title = corpus.titles.get(document, "")
        if match and title.casefold().startswith(match["prefix"].casefold()):
            counts["truncated_name"] += 1
            row = {**row, "query": f"{brand_name(title)} {match['rest']}"}
    return row


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
