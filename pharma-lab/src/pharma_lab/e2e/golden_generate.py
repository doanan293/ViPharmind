"""Multi-hop candidates generated from the corpus (spec §3.0b), for `golden draft`.

The benchmark has no question whose evidence sits in two different drugs' documents, so
the two kinds that need it are built from the corpus itself:

- `two_drug`: the interaction section of monograph A names drug B, and the question asks
  about taking both and about one more thing on B (dose, contraindications or adverse
  effects). Gold is A's interaction section and B's section for that intent.
- `brand_to_ingredient`: a leaflet names exactly one monograph ingredient in its
  composition section and lacks a section (interactions, precautions, pregnancy or
  overdose) that the monograph has. Gold is the leaflet's composition section and the
  monograph section.

The question is templated; the draft step rewrites it in a user's words and keeps the
drug names, and the review decides whether every gold section is needed.
"""

from __future__ import annotations

import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pharma_lab.e2e.corpus_text import CorpusText, section_slug

# Monograph section slugs and the leaflet slugs that hold the same information.
INTERACTIONS = "tuong-tac-thuoc"
TWO_DRUG_INTENTS: tuple[tuple[str, str], ...] = (
    (
        "lieu-luong-va-cach-dung",
        "Tôi đang dùng {a}, bác sĩ kê thêm {b}. Hai thuốc này có tương tác với nhau "
        "không, và liều {b} thường dùng là bao nhiêu?",
    ),
    (
        "chong-chi-dinh",
        "Tôi đang dùng {a} và định dùng thêm {b}. Dùng chung có tương tác gì không, "
        "và {b} chống chỉ định với những ai?",
    ),
    (
        "tac-dung-khong-mong-muon-adr",
        "Tôi đang dùng {a}, giờ được kê thêm {b}. Hai thuốc có tương tác không, và "
        "{b} có tác dụng không mong muốn nào cần theo dõi?",
    ),
)
BRAND_INTENTS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        INTERACTIONS,
        (INTERACTIONS,),
        "{brand} có tương tác với thuốc nào không?",
    ),
    (
        "than-trong",
        ("than-trong-khi-su-dung", "than-trong"),
        "Dùng {brand} cần thận trọng những gì?",
    ),
    (
        "thoi-ky-mang-thai",
        ("thai-ky-va-cho-con-bu", "thai-ky", "phu-nu-co-thai-va-cho-con-bu"),
        "Phụ nữ có thai dùng {brand} được không?",
    ),
    (
        "qua-lieu-va-xu-tri",
        ("qua-lieu",),
        "Lỡ uống quá liều {brand} thì xử trí thế nào?",
    ),
)
COMPOSITION = "thanh-phan"
# Three intents of one monograph whose sections must fall in two or more chunks, so one
# chunk cannot answer the question (spec §3.0c merges neighbouring sections).
THREE_INTENT_TRIPLES: tuple[tuple[tuple[str, str, str], str], ...] = (
    (
        ("chi-dinh", "lieu-luong-va-cach-dung", "tac-dung-khong-mong-muon-adr"),
        "{a} chỉ định cho bệnh gì, dùng liều bao nhiêu và có tác dụng phụ nào?",
    ),
    (
        ("lieu-luong-va-cach-dung", "chong-chi-dinh", "tuong-tac-thuoc"),
        "{a} dùng liều thế nào, ai không được dùng và có tương tác với thuốc gì?",
    ),
    (
        ("chi-dinh", "than-trong", "thoi-ky-mang-thai"),
        "{a} chữa bệnh gì, cần thận trọng gì và phụ nữ có thai dùng được không?",
    ),
)
# Monograph names that appear in interaction or composition sections without being the
# drug asked about (excipients, vehicles and alcohol).
EXCIPIENTS = frozenset(
    {
        "ethanol",
        "glucose",
        "glycerol",
        "glycerin",
        "sorbitol",
        "manitol",
        "natri clorid",
        "kali clorid",
        "calci clorid",
        "natri bicarbonat",
        "acid citric",
        "nước cất",
        "oxygen",
        "magnesi sulfat",
        "calci carbonat",
        "than hoạt",
    }
)
# Title words before the brand name, and the words that end it.
_FORM_PREFIX = re.compile(
    r"^(thuốc|viên|dung dịch|siro|si-rô|hỗn dịch|gel|kem|cao lỏng|mỡ|bột|cốm|kẹo|"
    r"nhũ tương|miếng dán|dầu|tuýp|ống|bơm|lọ|chai|nén|nang|sủi|bao phim|bao tan|"
    r"uống|tiêm|xịt|nhỏ|ngậm|mũi|mắt|bôi|da|đặt|trực tràng|phóng thích|kéo dài|"
    r"âm đạo|truyền|tĩnh mạch)\s+",
    re.IGNORECASE,
)
_NAME_END = re.compile(
    r"\s+(trị|điều trị|chỉ định|ngừa|phòng|bổ sung|hỗ trợ|giảm|cầm|tuần hoàn|giúp|"
    r"kháng|chống|cải thiện|kiểm soát|điều hòa|ổn định|sát khuẩn|dùng|cho|bôi|làm|"
    r"tăng|hạ|chữa|thuốc tránh thai|hộp|chai|lọ|tuýp|vỉ|ống|gói)\b.*$|\s*\(.*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Candidate:
    query_id: str
    query: str
    kind: str
    expected_section_ids: tuple[str, ...]
    subjects: tuple[str, ...]

    def row(self) -> dict[str, object]:
        return {
            "query_id": self.query_id,
            "query": self.query,
            "kind": self.kind,
            "eval_group": None,
            "expected_section_ids": list(self.expected_section_ids),
            "missing": [],
            "generated": True,
            "subjects": list(self.subjects),
        }


def drug_name(title: str) -> str:
    """A monograph title the way a user writes it: `ACID FOLIC` -> `acid folic`."""
    name = " ".join(title.split()).lower()
    return name[:1].upper() + name[1:]


def brand_name(title: str) -> str:
    """The product name with its strength, without dosage form, use and packaging."""
    name = " ".join(title.split())
    while (shorter := _FORM_PREFIX.sub("", name, count=1)) != name:
        name = shorter
    name = _NAME_END.sub("", name, count=1).strip(" ,.-")
    return name or " ".join(title.split())


_DOSE = re.compile(r"\d[\d.,]*\s*(mg|g|mcg|µg|iu|ui|%)(?!\w)", re.IGNORECASE)
_PARENTHESES = re.compile(r"\([^)]*\)")


def single_active(composition: str) -> bool:
    """Whether a composition section lists one active ingredient: one dose figure
    before the excipients, parenthetical salt equivalents aside. A combination product
    cannot be answered from one ingredient's monograph."""
    actives = re.split(r"tá dược", composition, maxsplit=1, flags=re.IGNORECASE)[0]
    return len(_DOSE.findall(_PARENTHESES.sub("", actives))) == 1


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _ngrams(tokens: Sequence[str], longest: int) -> set[str]:
    return {
        " ".join(tokens[start : start + size])
        for size in range(1, longest + 1)
        for start in range(len(tokens) - size + 1)
    }


class MonographNames:
    """Which monographs a text names, by whole-word match on the monograph title."""

    def __init__(self, corpus: CorpusText) -> None:
        self.by_name: dict[str, str] = {}
        for document, title in corpus.titles.items():
            name = " ".join(_tokens(title))
            if document.startswith("drug:") and name and name not in EXCIPIENTS:
                self.by_name[name] = document
        self.longest = max((len(name.split()) for name in self.by_name), default=1)

    def named_in(self, text: str) -> list[str]:
        """Monograph document keys named in `text`, in order of first appearance."""
        grams = _ngrams(_tokens(text), self.longest)
        found = [name for name in self.by_name if name in grams]
        folded = text.casefold()
        found.sort(key=lambda name: folded.find(name.split()[0]))
        return [self.by_name[name] for name in found]


def _sections_by_document(corpus: CorpusText) -> dict[str, dict[str, str]]:
    """document key -> section slug -> section id."""
    index: dict[str, dict[str, str]] = {}
    for section_id, document in corpus.section_documents.items():
        index.setdefault(document, {})[section_slug(section_id)] = section_id
    return index


def two_drug_candidates(
    corpus: CorpusText, *, count: int, seed: int
) -> list[Candidate]:
    """`count` pairs (A, B), one per A and at most two per B, where A's interaction
    section names B; the asked intent on B cycles through TWO_DRUG_INTENTS."""
    names = MonographNames(corpus)
    sections = _sections_by_document(corpus)
    monographs = sorted(
        document
        for document in corpus.titles
        if document.startswith("drug:") and INTERACTIONS in sections.get(document, {})
    )
    random.Random(seed).shuffle(monographs)
    out: list[Candidate] = []
    partners: dict[str, int] = {}
    for a in monographs:
        if len(out) == count:
            break
        if a not in names.by_name.values():
            continue
        a_section = sections[a][INTERACTIONS]
        pair = next(
            (
                (b, intent, template)
                for b in names.named_in(corpus.sections[a_section])
                if b != a and partners.get(b, 0) < 2
                for intent, template in _rotate(TWO_DRUG_INTENTS, len(out))
                if intent in sections.get(b, {})
            ),
            None,
        )
        if pair is None:
            continue
        b, intent, template = pair
        partners[b] = partners.get(b, 0) + 1
        a_name, b_name = drug_name(corpus.titles[a]), drug_name(corpus.titles[b])
        out.append(
            Candidate(
                f"gen-two-drug-{len(out) + 1:04d}",
                template.format(a=a_name, b=b_name),
                "two_drug",
                (a_section, sections[b][intent]),
                (a_name, b_name),
            )
        )
    return out


def brand_candidates(corpus: CorpusText, *, count: int, seed: int) -> list[Candidate]:
    """`count` leaflets, one per ingredient, whose composition names exactly one
    monograph and which lack a section the monograph has; the intent cycles through
    BRAND_INTENTS."""
    names = MonographNames(corpus)
    sections = _sections_by_document(corpus)
    leaflets = sorted(
        document
        for document in corpus.titles
        if document.startswith("leaflet:") and COMPOSITION in sections.get(document, {})
    )
    random.Random(seed).shuffle(leaflets)
    out: list[Candidate] = []
    used_ingredients: set[str] = set()
    for leaflet in leaflets:
        if len(out) == count:
            break
        composition = sections[leaflet][COMPOSITION]
        text = corpus.sections[composition][:600]
        named = names.named_in(text)
        if len(named) != 1 or named[0] in used_ingredients or not single_active(text):
            continue
        ingredient = named[0]
        for intent, leaflet_slugs, template in _rotate(BRAND_INTENTS, len(out)):
            if intent not in sections.get(ingredient, {}):
                continue
            if any(slug in sections[leaflet] for slug in leaflet_slugs):
                continue
            used_ingredients.add(ingredient)
            brand = brand_name(corpus.titles[leaflet])
            out.append(
                Candidate(
                    f"gen-brand-{len(out) + 1:04d}",
                    template.format(brand=brand),
                    "brand_to_ingredient",
                    (composition, sections[ingredient][intent]),
                    (brand,),
                )
            )
            break
    return out


def three_intent_candidates(
    corpus: CorpusText,
    chunks: Mapping[str, str],
    *,
    count: int,
    seed: int,
    exclude_documents: Sequence[str] = (),
) -> list[Candidate]:
    """`count` monographs, one each and none of `exclude_documents`, asked three intents
    whose sections sit in at least two chunks; the triple cycles through
    THREE_INTENT_TRIPLES."""
    sections = _sections_by_document(corpus)
    monographs = sorted(
        document
        for document in corpus.titles
        if document.startswith("drug:") and document not in set(exclude_documents)
    )
    random.Random(seed).shuffle(monographs)
    out: list[Candidate] = []
    for document in monographs:
        if len(out) == count:
            break
        for slugs, template in _rotate(THREE_INTENT_TRIPLES, len(out)):
            ids = [sections[document].get(slug) for slug in slugs]
            if None in ids:
                continue
            gold = [section_id for section_id in ids if section_id is not None]
            if len({chunks.get(section_id) for section_id in gold}) < 2:
                continue
            name = drug_name(corpus.titles[document])
            out.append(
                Candidate(
                    f"gen-three-intent-{len(out) + 1:04d}",
                    template.format(a=name),
                    "three_intent",
                    tuple(gold),
                    (name,),
                )
            )
            break
    return out


def _rotate[T](items: Sequence[T], offset: int) -> list[T]:
    """`items` starting from `offset`, so each candidate tries another intent first."""
    offset %= len(items)
    return [*items[offset:], *items[:offset]]


def generate(
    corpus: CorpusText,
    counts: Mapping[str, int],
    *,
    seed: int,
    chunks: Mapping[str, str] | None = None,
    exclude_documents: Sequence[str] = (),
) -> list[dict[str, object]]:
    """Candidate rows for the generated kinds, in the row format of `hard-candidates`.
    Three-intent rows need `chunks` (section id to chunk label)."""
    rows: list[Candidate] = []
    if counts.get("three_intent", 0) > 0:
        if chunks is None:
            raise ValueError("three_intent candidates need the section to chunk map")
        rows += three_intent_candidates(
            corpus,
            chunks,
            count=counts["three_intent"],
            seed=seed,
            exclude_documents=exclude_documents,
        )
    if counts.get("two_drug", 0) > 0:
        rows += two_drug_candidates(corpus, count=counts["two_drug"], seed=seed)
    if counts.get("brand_to_ingredient", 0) > 0:
        rows += brand_candidates(corpus, count=counts["brand_to_ingredient"], seed=seed)
    return [candidate.row() for candidate in rows]
