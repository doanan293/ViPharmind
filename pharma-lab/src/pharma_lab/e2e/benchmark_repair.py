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
from pharma_lab.e2e.golden_generate import (
    COMPOSITION,
    MonographNames,
    brand_name,
    names_a_product,
)

PASTED_MIN_WORDS = 11
_HEADING_LEAK = re.compile(r"\b(của|trong) mục\b|tên chung quốc tế", re.IGNORECASE)
# A rule-built multi-intent template no user says, and its rewording.
_MERGED_TEMPLATE = re.compile(
    r"^Người có thai hoặc có chống chỉ định thì dùng (?P<drug>.+) thế nào\?$"
)
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
# A question that asks for the trade names themselves: the trade-name list answers it.
_ASKS_BRANDS = re.compile(
    r"(tên|những|các) (biệt dược|tên thương mại|thương mại)|biệt dược (nào|gì)|"
    r"tên thương mại (nào|gì|là)",
    re.IGNORECASE,
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
_NAME_BREAK = re.compile(r"[,.;:)]$")


def repair_rows(
    rows: Sequence[dict], corpus: CorpusText, aliases: Sequence[str] = ()
) -> tuple[list[dict], Counter[str]]:
    """The repaired rows, in order, and how many rows each rule changed or dropped.
    `aliases` are the colloquial names of the corpus, to judge the alias rows."""
    sections = _sections_by_document(corpus)
    actives = _leaflet_actives(corpus)
    names = sorted({a.casefold() for a in aliases}, key=len, reverse=True)
    counts: Counter[str] = Counter()
    out: list[dict] = []
    for row in rows:
        if _vague_alias(row, corpus, names):
            counts["vague_alias"] += 1
            continue
        fixed = _repair(dict(row), corpus, sections, actives, counts)
        if fixed is not None:
            out.append(fixed)
    return out, counts


def _vague_alias(
    row: Mapping[str, object], corpus: CorpusText, names: Sequence[str]
) -> bool:
    """An alias question whose alias names a kind of product, not a product
    ("viên xanh xám cầm tiêu chảy"), so a user could mean many products."""
    if row.get("query_form") != "colloquial_alias":
        return False
    query = str(row["query"]).casefold()
    alias = next((name for name in names if name in query), None)
    gold = row.get("expected_section_ids")
    if alias is None or not isinstance(gold, list) or not gold:
        return False
    titles = [
        corpus.titles.get(corpus.section_documents.get(str(s), ""), "") for s in gold
    ]
    return not names_a_product(alias, titles)


def _repair(
    row: dict,
    corpus: CorpusText,
    sections: Mapping[str, Mapping[str, str]],
    actives: Mapping[str, frozenset[str]],
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
    if row.get("answer_mode") == "any_acceptable" and len(answering) > 1:
        kept = _answering_alternatives(query, answering, corpus, actives)
        if len(kept) < len(answering):
            counts["alternative_mismatch"] += 1
            answering = kept
    if len(answering) < len(gold):
        counts["null_alternative"] += 1
        row = _with_gold(
            row, answering, "any_acceptable" if len(answering) > 1 else ("single")
        )
        gold = answering
    merged = _MERGED_TEMPLATE.match(query)
    if merged:
        counts["merged_template"] += 1
        row = {
            **row,
            "query": f"{merged['drug']} có dùng được cho người có thai không, và những "
            "ai chống chỉ định?",
        }
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


_DOSE_QUESTION = re.compile(r"\blieu\b")
_CAUTION_QUESTION = re.compile(r"luu y|than trong")


def _answering_alternatives(
    query: str,
    alternatives: Sequence[str],
    corpus: CorpusText,
    actives: Mapping[str, frozenset[str]],
) -> list[str]:
    """The alternatives that answer alone: of the same product as the first one (the
    same monograph, or a leaflet of the same brand and active ingredients in another
    strength or pack, never another brand whose section happens to read alike), and,
    for a dose question, a dose section rather than one with only the route and
    timing, and, for a caution question, the precautions."""
    first = corpus.section_documents.get(alternatives[0], "")
    kept = [
        s
        for s in alternatives
        if _same_drug(first, corpus.section_documents.get(s, ""), corpus, actives)
    ]
    if _CAUTION_QUESTION.search(_fold(query)):
        # "Cần lưu ý gì?" is answered by the precautions, not by the pregnancy or
        # driving section of the same leaflet.
        caution = [s for s in kept if "than-trong" in section_slug(s)]
        kept = caution or kept
    if _DOSE_QUESTION.search(_fold(query)):
        dose = [s for s in kept if "lieu" in section_slug(s)]
        with_figures = [s for s in dose or kept if re.search(r"\d", corpus.sections[s])]
        kept = with_figures or dose or kept
    return kept


def _same_drug(
    first: str,
    other: str,
    corpus: CorpusText,
    actives: Mapping[str, frozenset[str]],
) -> bool:
    if other == first:
        return True
    if not (first.startswith("leaflet:") and other.startswith("leaflet:")):
        return False
    if first in actives and actives.get(other) not in (None, actives[first]):
        return False
    brands = [brand_name(corpus.titles.get(d, "")).split()[:1] for d in (first, other)]
    return bool(brands[0]) and _bare(brands[0][0]) == _bare(
        brands[1][0] if brands[1] else ""
    )


def _leaflet_actives(corpus: CorpusText) -> dict[str, frozenset[str]]:
    """Leaflet -> the monographs its composition names before the excipients."""
    names = MonographNames(corpus)
    out: dict[str, frozenset[str]] = {}
    for section_id, document in corpus.section_documents.items():
        if document.startswith("leaflet:") and section_slug(section_id) == COMPOSITION:
            text = corpus.sections[section_id][:600]
            head = re.split(r"tá dược", text, maxsplit=1, flags=re.IGNORECASE)[0]
            found = frozenset(names.named_in(head))
            if found:
                out[document] = found
    return out


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
    thế nào?". The copied title may keep its dosage form ("Siro …") and sit anywhere
    in the question. A name that stops at a phrase break is left as it is."""
    brand = brand_name(title)
    words = title.split()
    at = title.casefold().find(brand.casefold()) if brand else -1
    if at < 0:
        return None
    named = len(title[: at + len(brand)].split())
    asked = query.split()
    for size in range(len(words) - 1, named, -1):
        # A break after one word ("phòng,") ends no phrase; after two or more it does.
        if _NAME_BREAK.search(words[size - 1]) and size - named >= 2:
            continue
        cut = [_bare(w) for w in words[:size]]
        for start in range(len(asked) - size + 1):
            window = [_bare(w) for w in asked[start : start + size]]
            if window != cut or start + size == len(asked):
                continue
            if _bare(asked[start + size]) == _bare(words[size]):
                return None  # the question goes on with the title
            if size - named >= 2 and _NAME_BREAK.search(words[size - 1]):
                return None
            kept = [*asked[:start], *words[:named], *asked[start + size :]]
            return " ".join(kept)
    return None


def _bare(word: str) -> str:
    return word.casefold().strip(",.;:")


def _regold(
    query: str, intent: str, section_id: str, corpus: CorpusText
) -> tuple[tuple[str, ...], str]:
    """Where a question attached to an unanswering section belongs, and the rule name;
    no rule when the attachment is right (a brand question naming a listed brand)."""
    slug = section_slug(section_id)
    if slug == "ten-thuong-mai" and (
        _ASKS_BRANDS.search(query) or _names_a_listed_brand(query, section_id, corpus)
    ):
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
