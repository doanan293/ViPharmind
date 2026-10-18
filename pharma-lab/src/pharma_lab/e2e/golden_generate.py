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
from dataclasses import dataclass, replace

from pharma_lab.e2e.corpus_text import CorpusText, null_statement, section_slug

# Monograph section slugs and the leaflet slugs that hold the same information.
INTERACTIONS = "tuong-tac-thuoc"
# Neutral wording: many interacting drugs are injected or used in hospital, so the user is
# not cast as the one taking them.
TWO_DRUG_INTENTS: tuple[tuple[str, str], ...] = (
    (
        "lieu-luong-va-cach-dung",
        "{a} và {b} dùng cùng nhau có tương tác không, và liều {b} thường dùng là "
        "bao nhiêu?",
    ),
    (
        "chong-chi-dinh",
        "{a} dùng chung với {b} có tương tác gì không, và {b} chống chỉ định với "
        "những ai?",
    ),
    (
        "tac-dung-khong-mong-muon-adr",
        "{a} và {b} dùng cùng lúc có tương tác không, và {b} có tác dụng không mong "
        "muốn nào cần theo dõi?",
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


def _name_tokens(text: str) -> set[str]:
    """Words and numbers apart, so `3g` and `3 g` are the same name."""
    return set(re.findall(r"\d+|[^\W\d_]+", text.casefold()))


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


# Words before a drug name that mean the text does not describe an interaction with it:
# a cross-reference ("Xem progesteron"), a likeness ("phản ứng giống disulfiram") or the
# drug's class ("các tetracyclin", "như tetracyclin nói chung").
_NOT_A_PARTNER = re.compile(r"(xem|giống|các|như|nhóm|họ)\s*$")


def named_as_partner(text: str, name: str) -> bool:
    """Whether `text` names the drug `name` at least once as a drug in its own right."""
    folded = " ".join(_tokens(text))
    target = " ".join(_tokens(name))
    for match in re.finditer(rf"(?<!\w){re.escape(target)}(?!\w)", folded):
        before = folded[max(0, match.start() - 12) : match.start()]
        if not _NOT_A_PARTNER.search(before):
            return True
    return False


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
                if b != a
                and partners.get(b, 0) < 2
                and named_as_partner(corpus.sections[a_section], corpus.titles[b])
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
        brand = brand_name(corpus.titles[leaflet])
        # A brand that spells out its ingredient needs no composition section.
        if " ".join(_tokens(corpus.titles[ingredient])) in " ".join(_tokens(brand)):
            continue
        for intent, leaflet_slugs, template in _rotate(BRAND_INTENTS, len(out)):
            if intent not in sections.get(ingredient, {}):
                continue
            if any(slug in sections[leaflet] for slug in leaflet_slugs):
                continue
            used_ingredients.add(ingredient)
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


# Leaflet sections a colloquial-name question asks for, with the question template.
COLLOQUIAL_INTENTS: tuple[tuple[str, str], ...] = (
    ("cach-dung-lieu-dung", "{alias} dùng thế nào, mỗi lần bao nhiêu?"),
    ("chong-chi-dinh", "Những ai không được dùng {alias}?"),
    ("tac-dung-phu", "Dùng {alias} có thể bị tác dụng phụ gì?"),
    ("cong-dung-chi-dinh", "{alias} dùng để chữa bệnh gì?"),
    ("thai-ky-va-cho-con-bu", "Bà bầu có dùng {alias} được không?"),
    ("tuong-tac-thuoc", "{alias} uống chung với thuốc khác có sao không?"),
    ("qua-lieu", "Lỡ dùng quá liều {alias} thì phải làm sao?"),
)


# The aliases asked per product (or per group of products sharing an alias), and the
# length below which a section is a null statement ("Không có thận trọng đặc biệt.")
# rather than an answer.
ALIASES_PER_PRODUCT = 2
MIN_GOLD_CHARS = 40


def quotable(text: str) -> bool:
    """A section long enough to answer a question by itself, not a null statement."""
    return len(" ".join(text.split())) >= MIN_GOLD_CHARS and not null_statement(text)


def names_a_product(alias: str, titles: Sequence[str]) -> bool:
    """The alias carries a proper name of one of the titles (a capitalised title word
    other than a dosage form, or a word it starts with: `Berberin` in `Berberine`).
    "nước muối sinh lý" or "viên xanh xám cầm tiêu chảy" name a kind of product,
    not a product."""
    words = re.findall(r"[^\W\d_][\w-]{2,}", alias.casefold())
    for title in titles:
        for proper in re.findall(r"[^\W\d_][\w-]{2,}", title):
            if not proper[0].isupper() or _FORM_PREFIX.match(f"{proper} "):
                continue
            folded = proper.casefold()
            if any(
                w == folded or (len(w) >= 5 and folded.startswith(w)) for w in words
            ):
                return True
    return False


def colloquial_groups(
    corpus: CorpusText, aliases: Sequence[tuple[str, Sequence[str]]]
) -> dict[tuple[str, ...], list[str]]:
    """Leaflets that share colloquial aliases -> the aliases asked for them, at most
    ALIASES_PER_PRODUCT, those sharing the fewest words with the titles first.

    An alias belongs to every leaflet it maps to. It is kept only when it occurs in none
    of their titles or sections and is not an official name (every word of it in one
    title), so retrieval reaches the product under it only through the colloquial
    enrichment of its chunks, and only when it carries a product's proper name
    (`names_a_product`), so a user could mean nothing else by it."""
    texts: dict[str, list[str]] = {}
    for section_id, document in corpus.section_documents.items():
        texts.setdefault(document, []).append(corpus.sections[section_id])
    spelling: dict[str, str] = {}
    documents: dict[str, set[str]] = {}
    for alias, section_ids in aliases:
        key = alias.casefold()
        spelling.setdefault(key, alias)
        documents.setdefault(key, set()).update(
            corpus.section_documents[s]
            for s in section_ids
            if s in corpus.section_documents
        )
    by_group: dict[tuple[str, ...], list[tuple[float, str]]] = {}
    for key, found in documents.items():
        if not found:
            continue
        words = _name_tokens(key)
        titles = [_name_tokens(corpus.titles.get(d, "")) for d in found]
        text = " ".join(
            " ".join([corpus.titles.get(d, ""), *texts.get(d, [])]) for d in found
        ).casefold()
        if key in text or any(words <= title for title in titles):
            continue
        if not names_a_product(key, [corpus.titles.get(d, "") for d in found]):
            continue
        overlap = len(words & set().union(*titles)) / len(words)
        by_group.setdefault(tuple(sorted(found)), []).append((overlap, spelling[key]))
    return {
        group: [alias for _, alias in sorted(ranked)[:ALIASES_PER_PRODUCT]]
        for group, ranked in sorted(by_group.items())
    }


def colloquial_benchmark(
    corpus: CorpusText, aliases: Sequence[tuple[str, Sequence[str]]]
) -> list[Candidate]:
    """Every alias of `colloquial_groups` asked for every COLLOQUIAL_INTENTS section its
    leaflets have that can answer alone: the colloquial group of the benchmark. An alias
    of several leaflets accepts that section of any of them."""
    sections = _sections_by_document(corpus)
    out: list[Candidate] = []
    for group, names in colloquial_groups(corpus, aliases).items():
        for alias in names:
            for slug, template in COLLOQUIAL_INTENTS:
                gold = tuple(
                    section_id
                    for document in group
                    if (section_id := sections.get(document, {}).get(slug))
                    and quotable(corpus.sections[section_id])
                )
                if gold:
                    out.append(
                        Candidate(
                            f"enrich-colloquial-{len(out) + 1:04d}",
                            template.format(alias=alias),
                            "colloquial",
                            gold,
                            (alias,),
                        )
                    )
    return out


# Plain-language phrases a user says for a term that the formulary writes only as its
# abbreviation, with the monograph section and the question template.
GLOSSARY_PHRASES: tuple[tuple[str, str, str, str], ...] = (
    (
        "NSAID",
        "thuốc kháng viêm không steroid",
        INTERACTIONS,
        "{drug} uống chung với thuốc kháng viêm không steroid có sao không?",
    ),
    (
        "PPI",
        "thuốc ức chế bơm proton",
        INTERACTIONS,
        "{drug} dùng cùng thuốc ức chế bơm proton có bị tương tác không?",
    ),
    (
        "SSRI",
        "thuốc ức chế tái hấp thu serotonin chọn lọc",
        INTERACTIONS,
        "{drug} có dùng chung được với thuốc ức chế tái hấp thu serotonin chọn lọc không?",
    ),
    (
        "ARV",
        "thuốc kháng HIV",
        INTERACTIONS,
        "Người đang uống thuốc kháng HIV dùng thêm {drug} có bị tương tác không?",
    ),
    (
        "MAO",
        "monoamin oxidase",
        INTERACTIONS,
        "{drug} có dùng được cùng thuốc ức chế monoamin oxidase không?",
    ),
    (
        "ACE",
        "enzym chuyển angiotensin",
        INTERACTIONS,
        "{drug} dùng cùng thuốc ức chế enzym chuyển angiotensin có tương tác không?",
    ),
    (
        "CYP",
        "cytochrom P450",
        INTERACTIONS,
        "{drug} có bị ảnh hưởng khi dùng cùng thuốc ức chế cytochrom P450 không?",
    ),
    (
        "INR",
        "tỷ số chuẩn hóa quốc tế",
        INTERACTIONS,
        "Dùng {drug} cùng thuốc chống đông có làm thay đổi tỷ số chuẩn hóa quốc tế không?",
    ),
    (
        "TKTW",
        "thần kinh trung ương",
        "tac-dung-khong-mong-muon-adr",
        "{drug} có gây tác dụng phụ trên thần kinh trung ương không?",
    ),
    (
        "HIV",
        "suy giảm miễn dịch",
        "chi-dinh",
        "{drug} có dùng để điều trị nhiễm virus gây suy giảm miễn dịch ở người không?",
    ),
    (
        "AIDS",
        "hội chứng suy giảm miễn dịch mắc phải",
        "chi-dinh",
        "{drug} có dùng cho người mắc hội chứng suy giảm miễn dịch mắc phải không?",
    ),
    (
        "HBV",
        "virus viêm gan B",
        "than-trong",
        "Người nhiễm virus viêm gan B dùng {drug} cần thận trọng gì?",
    ),
    (
        "HCV",
        "virus viêm gan C",
        "chi-dinh",
        "{drug} có dùng để điều trị viêm gan do virus viêm gan C không?",
    ),
    (
        "COPD",
        "bệnh phổi tắc nghẽn mạn tính",
        "chi-dinh",
        "{drug} có dùng cho người bệnh phổi tắc nghẽn mạn tính không?",
    ),
    (
        "ECG",
        "điện tâm đồ",
        "than-trong",
        "Dùng {drug} có cần theo dõi điện tâm đồ không?",
    ),
    (
        "SJS",
        "hội chứng Stevens-Johnson",
        "tac-dung-khong-mong-muon-adr",
        "{drug} có thể gây hội chứng Stevens-Johnson không?",
    ),
    (
        "GFR",
        "mức lọc cầu thận",
        "lieu-luong-va-cach-dung",
        "Người suy thận có mức lọc cầu thận thấp dùng {drug} liều thế nào?",
    ),
    (
        "HRT",
        "liệu pháp hormon thay thế",
        INTERACTIONS,
        "Phụ nữ đang dùng liệu pháp hormon thay thế có dùng {drug} được không?",
    ),
    (
        "TSH",
        "hormon kích thích tuyến giáp",
        "lieu-luong-va-cach-dung",
        "Liều {drug} được chỉnh theo hormon kích thích tuyến giáp thế nào?",
    ),
    (
        "LDL",
        "lipoprotein tỷ trọng thấp",
        "duoc-ly-va-co-che-tac-dung",
        "{drug} có làm giảm lipoprotein tỷ trọng thấp trong máu không?",
    ),
    (
        "HDL",
        "lipoprotein tỷ trọng cao",
        "duoc-ly-va-co-che-tac-dung",
        "{drug} ảnh hưởng thế nào đến lipoprotein tỷ trọng cao?",
    ),
    (
        "TEN",
        "hoại tử thượng bì nhiễm độc",
        "tac-dung-khong-mong-muon-adr",
        "{drug} có thể gây hoại tử thượng bì nhiễm độc không?",
    ),
    (
        "VTE",
        "huyết khối thuyên tắc tĩnh mạch",
        "than-trong",
        "Người có nguy cơ huyết khối thuyên tắc tĩnh mạch dùng {drug} cần lưu ý gì?",
    ),
    (
        "NYHA",
        "Hội Tim New York",
        "chong-chi-dinh",
        "Suy tim theo phân loại của Hội Tim New York có được dùng {drug} không?",
    ),
    (
        "NSAID",
        "thuốc kháng viêm không steroid",
        "than-trong",
        "Dùng {drug} cùng thuốc kháng viêm không steroid cần thận trọng gì?",
    ),
    (
        "MAO",
        "monoamin oxidase",
        "chong-chi-dinh",
        "Người đang dùng thuốc ức chế monoamin oxidase có được dùng {drug} không?",
    ),
    (
        "INR",
        "tỷ số chuẩn hóa quốc tế",
        "lieu-luong-va-cach-dung",
        "Liều {drug} được chỉnh theo tỷ số chuẩn hóa quốc tế thế nào?",
    ),
    (
        "TKTW",
        "thần kinh trung ương",
        INTERACTIONS,
        "{drug} uống cùng thuốc an thần gây ức chế thần kinh trung ương có sao không?",
    ),
    (
        "HIV",
        "suy giảm miễn dịch",
        "lieu-luong-va-cach-dung",
        "Người nhiễm virus gây suy giảm miễn dịch ở người dùng {drug} liều thế nào?",
    ),
    (
        "HIV",
        "suy giảm miễn dịch",
        "than-trong",
        "Người nhiễm virus gây suy giảm miễn dịch dùng {drug} cần thận trọng gì?",
    ),
    (
        "AIDS",
        "hội chứng suy giảm miễn dịch mắc phải",
        "lieu-luong-va-cach-dung",
        "Liều {drug} cho người mắc hội chứng suy giảm miễn dịch mắc phải là bao nhiêu?",
    ),
)
# No term holds more than this share of the glossary group.
GLOSSARY_TERM_SHARE = 0.25


def glossary_matches(corpus: CorpusText) -> dict[str, list[Candidate]]:
    """Term -> one question per monograph whose GLOSSARY_PHRASES section writes the term
    only as its abbreviation, in monograph key order."""
    sections = _sections_by_document(corpus)
    monographs = sorted(d for d in corpus.titles if d.startswith("drug:"))
    by_term: dict[str, list[Candidate]] = {}
    for term, phrase, slug, template in GLOSSARY_PHRASES:
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)")
        for document in monographs:
            section_id = sections.get(document, {}).get(slug)
            if section_id is None:
                continue
            text = corpus.sections[section_id]
            if not pattern.search(text) or phrase.casefold() in text.casefold():
                continue
            name = drug_name(corpus.titles[document])
            # A vaccine prevents; asking whether it treats the infection is not real.
            if "điều trị" in template and name.casefold().startswith("vắc xin"):
                continue
            by_term.setdefault(term, []).append(
                Candidate(
                    "",
                    template.format(drug=name),
                    "glossary",
                    (section_id,),
                    (name, phrase),
                )
            )
    return by_term


def glossary_benchmark(corpus: CorpusText, *, seed: int = 0) -> list[Candidate]:
    """The term and monograph pairs of `glossary_matches`, each term cut to
    GLOSSARY_TERM_SHARE of the group by a seeded draw: the glossary group of the
    benchmark, so no single abbreviation decides the glossary layer's score."""
    found = glossary_matches(corpus)
    caps = term_caps({term: len(pairs) for term, pairs in found.items()})
    rng = random.Random(seed)
    out: list[Candidate] = []
    for term, pairs in found.items():
        keep = sorted(rng.sample(range(len(pairs)), caps[term]))
        for position in keep:
            out.append(
                replace(pairs[position], query_id=f"enrich-glossary-{len(out) + 1:04d}")
            )
    return out


def term_caps(counts: Mapping[str, int]) -> dict[str, int]:
    """Rows kept per term: every term cut to the largest common cap that is at most
    GLOSSARY_TERM_SHARE of the rows kept, but never below the smallest term (with
    too few terms the share cannot hold)."""
    cap = max(counts.values(), default=0)
    floor = min(counts.values(), default=0)
    while cap > floor and cap > GLOSSARY_TERM_SHARE * sum(
        min(n, cap) for n in counts.values()
    ):
        cap -= 1
    return {term: min(n, cap) for term, n in counts.items()}


def benchmark_row(candidate: Candidate) -> dict[str, object]:
    """A probe question in the retrieval benchmark's row format; several sections are
    alternatives (the same section of products sharing an alias)."""
    sections = list(candidate.expected_section_ids)
    return {
        "query_id": candidate.query_id,
        "query": candidate.query,
        "eval_group": candidate.kind,
        "source_family": "enrichment_probe",
        "query_form": candidate.kind,
        "intent_category": section_slug(sections[0]),
        "expected_section_id": sections[0],
        "expected_section_ids": sections,
        "query_intent_count": 1,
        "answer_mode": "any_acceptable" if len(sections) > 1 else "single",
        "eval_tags": ["enrichment_probe", candidate.kind],
        "notes": f"enrichment probe; subjects: {', '.join(candidate.subjects)}",
    }


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
