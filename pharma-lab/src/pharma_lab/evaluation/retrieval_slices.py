"""Benchmark slices that show where a retrieval layer helps (camera-ready spec §2 E4).

A slice is a property of the question and the corpus, never of a system's result, so a
layer's gain inside its slice is not selected by that layer. The definitions follow the
eval data v3 design (branch `v2.0.0`, `e2e/benchmark_slices.py`), adapted to the v1
corpus, where a leaflet is one section:

- `rare_term`: the question carries a word that occurs in at most `max_sections` sections
  of the corpus and in a gold section as written; the dense model barely knows such a
  word, the lexical half of hybrid search matches it.
- `sibling_products`: another leaflet of the same brand word has the same active
  ingredients (another strength or form); the candidates look alike and the reranker
  decides the order.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pharma_lab.artifacts.jsonl import iter_jsonl_objects
from pharma_lab.e2e.corpus_text import CorpusText, load_corpus_text
from pharma_lab.evaluation.artifact_contracts import write_json
from pharma_lab.evaluation.metric_comparison import load_query_metric

RARE_TERM_SECTIONS = 10
COMPOSITION_CHARS = 600
# Monograph names that appear in composition sections without being an active
# ingredient (excipients, vehicles and alcohol).
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
    r"\s+(trị|điều trị|chỉ định|ngừa|phòng|dự phòng|ngăn ngừa|ngăn|kết hợp|phối hợp|"
    r"bổ sung|hỗ trợ|giảm|cầm|tuần hoàn|giúp|"
    r"kháng|chống|cải thiện|kiểm soát|điều hòa|ổn định|sát khuẩn|dùng|cho|bôi|làm|"
    r"tăng|hạ|chữa|thuốc tránh thai|hộp|chai|lọ|tuýp|vỉ|ống|gói)\b.*$|\s*\(.*$",
    re.IGNORECASE,
)
_COMPOSITION = re.compile(r"thành phần", re.IGNORECASE)
_EXCIPIENT_START = re.compile(r"tá dược", re.IGNORECASE)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _terms(text: str) -> set[str]:
    """Words of four characters or more that start with a letter."""
    return set(re.findall(r"[^\W\d_][\w-]{3,}", _fold(text)))


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def brand_name(title: str) -> str:
    """The product name with its strength, without dosage form, use and packaging."""
    name = " ".join(title.split())
    while (shorter := _FORM_PREFIX.sub("", name, count=1)) != name:
        name = shorter
    name = _NAME_END.sub("", name, count=1).strip(" ,.-")
    return name or " ".join(title.split())


class MonographNames:
    """Which monographs a text names, by whole-word match on the monograph title."""

    def __init__(self, corpus: CorpusText) -> None:
        self.by_name: dict[str, str] = {}
        for document, title in corpus.titles.items():
            name = " ".join(_tokens(title))
            if document.startswith("drug:") and name and name not in EXCIPIENTS:
                self.by_name[name] = document
        self.longest = max((len(name.split()) for name in self.by_name), default=1)

    def named_in(self, text: str) -> frozenset[str]:
        tokens = _tokens(text)
        grams = {
            " ".join(tokens[start : start + size])
            for size in range(1, self.longest + 1)
            for start in range(len(tokens) - size + 1)
        }
        return frozenset(self.by_name[name] for name in self.by_name if name in grams)


def _gold(row: Mapping[str, Any]) -> list[str]:
    gold = row.get("expected_section_ids")
    return [str(section) for section in gold] if isinstance(gold, list) else []


def rare_terms(
    rows: Sequence[Mapping[str, Any]],
    corpus: CorpusText,
    *,
    max_sections: int = RARE_TERM_SECTIONS,
) -> set[str]:
    counts: dict[str, int] = defaultdict(int)
    for text in corpus.sections.values():
        for term in _terms(text):
            counts[term] += 1
    found: set[str] = set()
    for row in rows:
        gold_terms = _terms(" ".join(corpus.sections.get(s, "") for s in _gold(row)))
        shared = _terms(str(row.get("query", ""))) & gold_terms
        if any(counts.get(term, 0) <= max_sections for term in shared):
            found.add(str(row["query_id"]))
    return found


def _actives(text: str, names: MonographNames) -> frozenset[str]:
    match = _COMPOSITION.search(text)
    head = text[match.start() :] if match else text
    head = _EXCIPIENT_START.split(head[:COMPOSITION_CHARS], maxsplit=1)[0]
    return names.named_in(head)


def sibling_products(rows: Sequence[Mapping[str, Any]], corpus: CorpusText) -> set[str]:
    names = MonographNames(corpus)
    families: dict[tuple[frozenset[str], str], set[str]] = defaultdict(set)
    for section_id, document in corpus.section_documents.items():
        if not document.startswith("leaflet:"):
            continue
        actives = _actives(corpus.sections[section_id], names)
        words = _fold(brand_name(corpus.titles.get(document, ""))).split()
        if actives and words:
            families[(actives, words[0])].add(document)
    siblings = {doc for docs in families.values() if len(docs) > 1 for doc in docs}
    found: set[str] = set()
    for row in rows:
        gold = _gold(row)
        if gold and corpus.section_documents.get(gold[0]) in siblings:
            found.add(str(row["query_id"]))
    return found


def win_rate(
    better: Mapping[str, float], worse: Mapping[str, float], ids: Collection[str]
) -> float:
    """Share of `ids` where `better` scores strictly higher than `worse`."""
    if not ids:
        return 0.0
    return statistics.fmean(1.0 if better[i] > worse[i] else 0.0 for i in ids)


@dataclass(frozen=True)
class SlicesRequest:
    runs_root: Path
    evaluation_path: Path
    bundle_dir: Path
    output_dir: Path


REPORT_NAME = "top30-window3"
BASELINE = Path("reports") / "baseline" / REPORT_NAME
RUNS = {
    "bm25": "bm25-qwen4b-k30",
    "dense": "dense-qwen4b-k30",
    "hybrid": "hybrid-qwen4b-p50-k30-rrf2",
}
RERANK = Path("reports") / "rerank" / "qwen3_reranker_4b_fp16" / REPORT_NAME


def _comparison(
    better: Mapping[str, float],
    worse: Mapping[str, float],
    inside: Collection[str],
    outside: Collection[str],
) -> dict[str, float]:
    win_in, win_out = win_rate(better, worse, inside), win_rate(better, worse, outside)
    return {
        "win_inside": win_in,
        "win_outside": win_out,
        "ratio": win_in / win_out if win_out else float("inf"),
    }


def run_slices(request: SlicesRequest) -> dict[str, Any]:
    rows = list(iter_jsonl_objects(request.evaluation_path))
    corpus = load_corpus_text(request.bundle_dir)
    ids = {str(row["query_id"]) for row in rows}
    leaflets = {
        str(row["query_id"])
        for row in rows
        if (corpus.section_documents.get((_gold(row) or [""])[0]) or "").startswith(
            "leaflet:"
        )
    }
    rare = rare_terms(rows, corpus)
    sibling = sibling_products(rows, corpus)

    def metric(path: Path, name: str) -> dict[str, float]:
        return load_query_metric(path, name)[1]

    hit10 = {
        name: metric(request.runs_root / run / BASELINE, "hit@10")
        for name, run in RUNS.items()
    }
    hybrid_dir = request.runs_root / RUNS["hybrid"]
    hybrid5 = metric(hybrid_dir / BASELINE, "hit@5")
    rerank5 = metric(hybrid_dir / RERANK, "hit@5")
    top1 = {
        "hybrid": {
            k: float(v == 1.0) for k, v in metric(hybrid_dir / BASELINE, "mrr").items()
        },
        "rerank": {
            k: float(v == 1.0) for k, v in metric(hybrid_dir / RERANK, "mrr").items()
        },
    }
    report = {
        "rows": len(ids),
        "rare_term": {
            "size": len(rare),
            "bm25_over_dense_hit10": _comparison(
                hit10["bm25"], hit10["dense"], rare, ids - rare
            ),
            "hybrid_over_dense_hit10": _comparison(
                hit10["hybrid"], hit10["dense"], rare, ids - rare
            ),
        },
        "sibling_products": {
            "size": len(sibling),
            "rerank_over_hybrid_hit5": _comparison(
                rerank5, hybrid5, sibling, ids - sibling
            ),
            "rerank_over_hybrid_hit5_leaflets": _comparison(
                rerank5, hybrid5, sibling, leaflets - sibling
            ),
            "rerank_over_hybrid_top1": _comparison(
                top1["rerank"], top1["hybrid"], sibling, ids - sibling
            ),
        },
    }
    request.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(request.output_dir / "report.json", report)
    (request.output_dir / "report.md").write_text(markdown(report), encoding="utf-8")
    return report


def markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Retrieval slices",
        "",
        "| Slice | Size | Comparison | Win inside | Win outside | Ratio |",
        "| --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for slice_name in ("rare_term", "sibling_products"):
        entry = report[slice_name]
        for name, value in entry.items():
            if name == "size":
                continue
            lines.append(
                f"| {slice_name} | {entry['size']} | {name} | {value['win_inside']:.3f} "
                f"| {value['win_outside']:.3f} | {value['ratio']:.1f}x |"
            )
    return "\n".join(lines) + "\n"
