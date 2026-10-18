"""The conversational layer of the retrieval benchmark (spec v2 §3.1).

Each item is a short conversation built by rules from benchmark questions. The last user
turn is the one scored, and it inherits the gold sections of a parent benchmark question,
so no new labels are needed. Earlier assistant turns are fixed: the first sentences of the
gold section of the turn they answer. Every item carries one of eight phenomena that a
query rewriter must resolve:

- `pronoun`: the drug is referred to as "thuốc này";
- `ellipsis`: the subject is dropped altogether;
- `intent_shift`: "còn … thì sao?" asks another intent of the same drug;
- `drug_shift`: "còn <drug> thì sao?" asks the same intent of another drug;
- `answer_entity`: the drug is the active ingredient the previous answer named;
- `topic_switch`: the last turn is a full question about another drug, so the history
  must be ignored;
- `multi_intent`: the last turn asks two intents of the drug at once, without naming it;
- `noisy_followup`: an ellipsis follow-up typed without diacritics.
"""

from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pharma_lab.e2e.corpus_text import CorpusText, section_slug
from pharma_lab.e2e.golden_generate import (
    COMPOSITION,
    MonographNames,
    brand_name,
    drug_name,
    single_active,
)
from pharma_lab.e2e.one_round import MIN_SECTION_TOKENS, UNINFORMATIVE_SLUGS

PHENOMENA = (
    "pronoun",
    "ellipsis",
    "intent_shift",
    "drug_shift",
    "answer_entity",
    "topic_switch",
    "multi_intent",
    "noisy_followup",
)

# intent -> (noun phrase, question about "thuốc này", question without a subject)
INTENT_PHRASES: dict[str, tuple[str, str, str]] = {
    "dosage": ("liều dùng", "Thuốc này dùng liều thế nào?", "Dùng liều thế nào?"),
    "indication": ("công dụng", "Thuốc này dùng để chữa gì?", "Dùng để chữa gì?"),
    "contraindication": (
        "chống chỉ định",
        "Ai không được dùng thuốc này?",
        "Những ai không được dùng?",
    ),
    "adr": (
        "tác dụng phụ",
        "Thuốc này có tác dụng phụ gì?",
        "Có tác dụng phụ gì không?",
    ),
    "precaution": (
        "thận trọng",
        "Dùng thuốc này cần thận trọng gì?",
        "Cần thận trọng gì khi dùng?",
    ),
    "interaction": (
        "tương tác thuốc",
        "Thuốc này có tương tác với thuốc nào không?",
        "Có tương tác với thuốc nào không?",
    ),
    # Pregnancy only: the gold of a single-section parent is the pregnancy section.
    "pregnancy_lactation": (
        "dùng cho bà bầu",
        "Bà bầu có dùng thuốc này được không?",
        "Bà bầu có dùng được không?",
    ),
    "overdose": (
        "xử trí quá liều",
        "Lỡ dùng quá liều thuốc này thì xử trí sao?",
        "Quá liều thì xử trí thế nào?",
    ),
    "storage": ("bảo quản", "Thuốc này bảo quản thế nào?", "Bảo quản ra sao?"),
    "pharmacology": (
        "cơ chế tác dụng",
        "Thuốc này tác dụng theo cơ chế nào?",
        "Cơ chế tác dụng là gì?",
    ),
    "ingredient": (
        "thành phần",
        "Thuốc này có thành phần gì?",
        "Thành phần gồm những gì?",
    ),
    "manufacturer": (
        "nhà sản xuất",
        "Thuốc này của hãng nào?",
        "Của hãng nào sản xuất?",
    ),
    "general_info": (
        "thông tin chung",
        "Thuốc này là thuốc gì?",
        "Là thuốc gì vậy?",
    ),
}
# Section slug -> intent, for the sections of a multi-intent parent.
SLUG_INTENTS: dict[str, str] = {
    "lieu-luong-va-cach-dung": "dosage",
    "cach-dung-lieu-dung": "dosage",
    "chi-dinh": "indication",
    "cong-dung-chi-dinh": "indication",
    "chong-chi-dinh": "contraindication",
    "tac-dung-khong-mong-muon-adr": "adr",
    "tac-dung-phu": "adr",
    "than-trong": "precaution",
    "than-trong-khi-su-dung": "precaution",
    "tuong-tac-thuoc": "interaction",
    "thoi-ky-mang-thai": "pregnancy_lactation",
    "thai-ky-va-cho-con-bu": "pregnancy_lactation",
    "qua-lieu-va-xu-tri": "overdose",
    "qua-lieu": "overdose",
    "do-on-dinh-va-bao-quan": "storage",
    "duoc-ly-va-co-che-tac-dung": "pharmacology",
    "duoc-luc-hoc-tac-dong-cua-thuoc-len-co-the": "pharmacology",
    "thanh-phan": "ingredient",
    "thong-tin-chung": "general_info",
}
# Intents whose noun phrase is a heading, not something a user says ("còn thông tin
# chung thì sao?"); they are asked only as full questions.
HEADING_INTENTS = frozenset({"general_info"})
ANSWER_SENTENCES = 2
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Item:
    query_id: str
    phenomenon: str
    turns: tuple[tuple[str, str], ...]
    parent: Mapping[str, object]
    expected_section_ids: tuple[str, ...]

    def row(self) -> dict[str, object]:
        """The item in the benchmark's row format, with its turns."""
        parent = self.parent
        tags = parent.get("eval_tags")
        return {
            "query_id": self.query_id,
            "query": self.turns[-1][1],
            "turns": [{"role": role, "text": text} for role, text in self.turns],
            "eval_group": "conversational",
            "source_family": parent.get("source_family"),
            "query_form": self.phenomenon,
            "intent_category": parent.get("intent_category"),
            "expected_section_id": self.expected_section_ids[0],
            "expected_section_ids": list(self.expected_section_ids),
            "query_intent_count": len(self.expected_section_ids),
            "answer_mode": parent.get("answer_mode"),
            "parent_query_id": parent["query_id"],
            "parent_eval_group": parent.get("eval_group"),
            "eval_tags": [
                "conversational",
                self.phenomenon,
                # The last turn is a full question: the control for the history.
                *(["control"] if self.phenomenon == "topic_switch" else []),
                *(tags if isinstance(tags, list) else []),
            ],
        }


def answer_text(corpus: CorpusText, section_id: str) -> str:
    """The fixed assistant turn: the first sentences of a gold section."""
    text = " ".join(corpus.sections.get(section_id, "").split())
    text = re.sub(r"[#*|]+", " ", text)
    sentences = [s for s in _SENTENCE.split(" ".join(text.split())) if s]
    return " ".join(sentences[:ANSWER_SENTENCES])[:400]


def strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()


def informative_gold(row: Mapping[str, object], corpus: CorpusText) -> bool:
    """Every gold section can answer a question: not a trade-name list, regulatory
    note, incompatibility line or closing note, and long enough to quote."""
    return all(
        section_slug(section_id) not in UNINFORMATIVE_SLUGS
        and len(corpus.sections.get(section_id, "").split()) >= MIN_SECTION_TOKENS
        for section_id in _gold(row)
    )


def subject_name(corpus: CorpusText, document: str) -> str:
    title = corpus.titles.get(document, "")
    return drug_name(title) if document.startswith("drug:") else brand_name(title)


def _document(section_id: str) -> str:
    parts = section_id.split(":")
    return ":".join(parts[:3] if parts[0] == "leaflet" else parts[:2])


class _Index:
    """Benchmark questions by document and by intent, single-section ones only."""

    def __init__(
        self, rows: Sequence[Mapping[str, object]], corpus: CorpusText
    ) -> None:
        self.by_document: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        self.by_intent: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for row in rows:
            sections = row.get("expected_section_ids")
            if not isinstance(sections, list) or len(sections) != 1:
                continue
            if not _usable(row, corpus):
                continue
            self.by_document[_document(str(sections[0]))].append(row)
            self.by_intent[str(row.get("intent_category"))].append(row)

    def sibling(
        self, document: str, asked: set[str], seen: set[str], rng: random.Random
    ) -> Mapping[str, object] | None:
        """A question about the same document, of an intent not asked yet and with a
        gold section no turn has used yet."""
        options = [
            row
            for row in self.by_document.get(document, [])
            if str(row.get("intent_category")) not in asked
            and not set(_gold(row)) & seen
        ]
        return rng.choice(options) if options else None

    def other_drug(
        self, document: str, intent: str | None, rng: random.Random
    ) -> Mapping[str, object] | None:
        """A question about another document, of `intent` or of any intent."""
        pool = self.by_intent.get(intent, []) if intent else []
        if not pool:
            pool = [row for rows in self.by_intent.values() for row in rows]
        for _ in range(20):
            row = rng.choice(pool)
            if _document(_gold(row)[0]) != document:
                return row
        return None


def _usable(row: Mapping[str, object], corpus: CorpusText) -> bool:
    """A benchmark row that can open or end a conversation: a question (not pasted
    text), not noisy, with informative gold."""
    return (
        row.get("eval_group") != "noisy"
        and "?" in str(row.get("query", ""))
        and informative_gold(row, corpus)
    )


def _gold(row: Mapping[str, object]) -> list[str]:
    sections = row.get("expected_section_ids")
    return [str(s) for s in sections] if isinstance(sections, list) else []


def _turn(row: Mapping[str, object], corpus: CorpusText) -> list[tuple[str, str]]:
    return [
        ("user", str(row["query"])),
        ("assistant", answer_text(corpus, _gold(row)[0])),
    ]


def _history(
    document: str,
    intent: str,
    index: _Index,
    corpus: CorpusText,
    rng: random.Random,
    depth: int,
    gold: Sequence[str],
) -> list[tuple[str, str]] | None:
    """`depth - 1` earlier exchanges about `document`, the first naming it, none
    answered from a section of `gold` or of another earlier exchange (the last turn
    would re-ask what was just answered)."""
    turns: list[tuple[str, str]] = []
    asked = {intent}
    seen = set(gold)
    for _ in range(depth - 1):
        sibling = index.sibling(document, asked, seen, rng)
        if sibling is None:
            break
        asked.add(str(sibling.get("intent_category")))
        seen |= set(_gold(sibling))
        turns += _turn(sibling, corpus)
    return turns or None


def build_item(
    phenomenon: str,
    parent: Mapping[str, object],
    index: _Index,
    corpus: CorpusText,
    ingredients: Mapping[str, list[str]],
    rng: random.Random,
    depth: int,
) -> Item | None:
    """One conversation of `phenomenon` ending in a question with `parent`'s gold, or
    None when the parent does not fit the phenomenon."""
    gold = _gold(parent)
    if not gold:
        return None
    document = _document(gold[0])
    intent = str(parent.get("intent_category"))
    phrases = INTENT_PHRASES.get(intent)
    multi = parent.get("answer_mode") == "multi_required"
    if phenomenon == "multi_intent":
        if not multi:
            return None
        intents = [SLUG_INTENTS.get(section_slug(s)) for s in gold]
        if None in intents or len(set(intents)) < 2 or HEADING_INTENTS & set(intents):
            return None
        nouns = [INTENT_PHRASES[i][0] for i in intents if i is not None]
        history = _history(document, "multi_intent", index, corpus, rng, depth, gold)
        if history is None:
            return None
        last = f"Cho mình hỏi luôn {' và '.join(nouns)}?"
        return Item("", phenomenon, (*history, ("user", last)), parent, tuple(gold))
    # A templated question must ask what the gold section holds.
    if multi or len(gold) != 1 or phrases is None:
        return None
    if (
        phenomenon != "topic_switch"
        and SLUG_INTENTS.get(section_slug(gold[0])) != intent
    ):
        return None
    noun, pronoun_question, ellipsis_question = phrases
    if phenomenon in {"intent_shift", "noisy_followup"} and intent in HEADING_INTENTS:
        return None
    if phenomenon in {"pronoun", "ellipsis", "intent_shift", "noisy_followup"}:
        history = _history(document, intent, index, corpus, rng, depth, gold)
        if history is None:
            return None
        last = {
            "pronoun": pronoun_question,
            "ellipsis": ellipsis_question,
            "intent_shift": f"Còn {noun} thì sao?",
            "noisy_followup": strip_diacritics(f"Còn {noun} thì sao?"),
        }[phenomenon]
        return Item("", phenomenon, (*history, ("user", last)), parent, tuple(gold))
    if phenomenon == "drug_shift":
        other = index.other_drug(document, intent, rng)
        if other is None or other.get("intent_category") != intent:
            return None
        last = f"Còn {subject_name(corpus, document)} thì sao?"
        turns = (*_turn(other, corpus), ("user", last))
        return Item("", phenomenon, turns, parent, tuple(gold))
    if phenomenon == "topic_switch":
        other = index.other_drug(document, None, rng)
        if other is None:
            return None
        turns = (*_turn(other, corpus), ("user", str(parent["query"])))
        return Item("", phenomenon, turns, parent, tuple(gold))
    if phenomenon == "answer_entity":
        leaflets = ingredients.get(document)
        if not document.startswith("drug:") or not leaflets:
            return None
        leaflet = rng.choice(leaflets)
        composition = f"{leaflet}:{_composition_slug(corpus, leaflet)}"
        brand = subject_name(corpus, leaflet)
        first = (
            ("user", f"{brand} có thành phần gì?"),
            ("assistant", answer_text(corpus, composition)),
        )
        last = pronoun_question.replace("Thuốc này", "Hoạt chất đó").replace(
            "thuốc này", "hoạt chất đó"
        )
        return Item("", phenomenon, (*first, ("user", last)), parent, tuple(gold))
    raise ValueError(f"unknown phenomenon {phenomenon}")


def _composition_slug(corpus: CorpusText, leaflet: str) -> str:
    for section_id, owner in corpus.section_documents.items():
        if owner == leaflet and section_slug(section_id) == COMPOSITION:
            return section_id.rsplit(":", 1)[1]
    raise KeyError(f"{leaflet} has no composition section")


def single_ingredient_leaflets(corpus: CorpusText) -> dict[str, list[str]]:
    """Monograph document -> leaflets whose composition names it as the only active
    ingredient, so an answer about the leaflet names the monograph's drug."""
    names = MonographNames(corpus)
    out: dict[str, list[str]] = defaultdict(list)
    for section_id, document in sorted(corpus.section_documents.items()):
        if (
            not document.startswith("leaflet:")
            or section_slug(section_id) != COMPOSITION
        ):
            continue
        text = corpus.sections[section_id][:600]
        # Only what comes before the excipients: "Tá dược: glycin" names no active.
        actives = re.split(r"tá dược", text, maxsplit=1, flags=re.IGNORECASE)[0]
        named = names.named_in(actives)
        if len(named) == 1 and single_active(text):
            out[named[0]].append(document)
    return dict(out)


def build_conversational(
    rows: Sequence[Mapping[str, object]],
    corpus: CorpusText,
    *,
    total: int,
    seed: int,
    covered: Mapping[str, bool] | None = None,
) -> list[dict[str, object]]:
    """`total` items spread evenly over PHENOMENA. Parents are drawn in a seeded order,
    alternating between questions one retrieval round covers and questions it misses
    when `covered` is given, and keeping leaflet (brand-name) parents in every
    phenomenon. User turns run from two to four.

    Each item is named by its phenomenon and parent and drawn with its own seed, and
    parents are ordered by a seeded hash of their id, so a change to one row changes
    only the items built from it, not every item after it."""
    index = _Index(rows, corpus)
    ingredients = single_ingredient_leaflets(corpus)
    parents = [row for row in rows if _usable(row, corpus)]
    per_phenomenon = total // len(PHENOMENA)
    extra = total - per_phenomenon * len(PHENOMENA)
    items: list[Item] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for position, phenomenon in enumerate(PHENOMENA):
        need = per_phenomenon + (1 if position < extra else 0)
        order = _parent_order(parents, phenomenon, seed, covered)
        made: list[Item] = []
        used: set[str] = set()
        for parent in order:
            if len(made) == need:
                break
            query_id = str(parent["query_id"])
            if query_id in used:
                continue
            rng = random.Random(_key(seed, phenomenon, query_id))
            depth = rng.choice((2, 2, 3, 4))
            item = build_item(
                phenomenon, parent, index, corpus, ingredients, rng, depth
            )
            if item is None:
                continue
            # Two items ending in the same turn with the same gold test one thing.
            key = (item.turns[-1][1], item.expected_section_ids)
            if key in seen:
                continue
            seen.add(key)
            used.add(query_id)
            made.append(item)
        items += made
    return [
        {
            **item.row(),
            "query_id": f"conv-{item.phenomenon}-{item.parent['query_id']}",
        }
        for item in items
    ]


def _key(seed: int, *parts: str) -> str:
    return hashlib.sha1(":".join((str(seed), *parts)).encode()).hexdigest()


def _parent_order(
    parents: Sequence[Mapping[str, object]],
    phenomenon: str,
    seed: int,
    covered: Mapping[str, bool] | None,
) -> list[Mapping[str, object]]:
    """Leaflet and formulary parents interleaved, and, given `covered`, covered and
    missed parents interleaved, each stream ordered by a seeded hash of the parent id."""
    streams: dict[tuple[bool, bool], list[Mapping[str, object]]] = defaultdict(list)
    for row in parents:
        leaflet = str(row.get("eval_group", "")).startswith("leaflet")
        hit = covered.get(str(row["query_id"]), True) if covered else True
        streams[(leaflet, hit)].append(row)
    for stream in streams.values():
        stream.sort(key=lambda row: _key(seed, phenomenon, str(row["query_id"])))
    keys = sorted(streams)
    out: list[Mapping[str, object]] = []
    position = 0
    while any(position < len(streams[key]) for key in keys):
        for key in keys:
            if position < len(streams[key]):
                out.append(streams[key][position])
        position += 1
    return out
