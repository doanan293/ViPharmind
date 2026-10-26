"""Tables of docs/research/paper-v2/08-phase-d-results.md from per-query metrics.

usage (from pharma-lab/): uv run python <this>
"""

import json
from collections import defaultdict
from pathlib import Path

from pharma_lab.evaluation.statistics import holm, paired_test

RUNS = Path("data/evaluation/runs")
groups: dict[str, str] = {}
slices: dict[str, list[str]] = defaultdict(list)
for line in (
    Path("data/evaluation/gold/section_retrieval_eval.jsonl")
    .read_text("utf-8")
    .splitlines()
):
    row = json.loads(line)
    groups[row["query_id"]] = row["eval_group"]
    for name in row.get("slices") or []:
        slices[name].append(row["query_id"])
SELECT = sorted(q for q, g in groups.items() if g not in ("conversational", "safety"))
CONV = sorted(q for q, g in groups.items() if g == "conversational")
RERANK = "qwen3_reranker_4b_q8_0"


def load(run: str, model: str | None = None, gold_only: bool = False):
    name = "top20-gold" if gold_only else "top20"
    sub = f"rerank/{model}/{name}" if model else f"baseline/{name}"
    path = RUNS / run / "reports" / sub / "metrics.jsonl"
    if not path.is_file():
        return None
    return {
        r["query_id"]: r for r in map(json.loads, path.read_text("utf-8").splitlines())
    }


def mean(rows, metric, queries):
    return 100 * sum(rows[q][metric] for q in queries) / len(queries)


def table(title, configs, metrics, queries, note=""):
    out = [f"### {title}", ""]
    if note:
        out += [note, ""]
    out.append("| Cấu hình | " + " | ".join(metrics) + " |")
    out.append("| --- | " + " | ".join("---:" for _ in metrics) + " |")
    for label, rows in configs:
        if rows is None:
            out.append(f"| {label} | " + " | ".join("chưa có" for _ in metrics) + " |")
            continue
        out.append(
            f"| {label} | "
            + " | ".join(f"{mean(rows, m, queries):.2f}" for m in metrics)
            + " |"
        )
    return [*out, ""]


def tests(title, pairs, metric, queries):
    """Paired sign-flip with Holm over the rows of one table; difference in points."""
    entries = [
        (a, b, ra, rb) for a, b, ra, rb in pairs if ra is not None and rb is not None
    ]
    results = [
        paired_test([100 * (ra[q][metric] - rb[q][metric]) for q in queries])
        for _, _, ra, rb in entries
    ]
    adjusted = holm([r.p_value for r in results])
    out = [
        f"Kiểm định ({title}, {metric}, {len(queries)} câu; KTC bootstrap 95 %, p sign-flip, Holm trong bảng):",
        "",
    ]
    out.append("| So sánh | Δ (điểm) | KTC 95 % | p Holm |")
    out.append("| --- | ---: | --- | ---: |")
    for (a, b, _, _), r, p in zip(entries, results, adjusted, strict=True):
        s = r.summary
        out.append(
            f"| {a} − {b} | {s.mean:+.2f} | [{s.ci_low:+.2f}; {s.ci_high:+.2f}] | {p:.4f} |"
        )
    return [*out, ""]


def by_group(configs, metric):
    names = sorted({g for g in groups.values() if g != "safety"})
    out = ["| Nhóm (n) | " + " | ".join(label for label, _ in configs) + " |"]
    out.append("| --- | " + " | ".join("---:" for _ in configs) + " |")
    for g in names:
        qs = [q for q, gg in groups.items() if gg == g]
        out.append(
            f"| {g} ({len(qs)}) | "
            + " | ".join(f"{mean(r, metric, qs):.2f}" if r else "—" for _, r in configs)
            + " |"
        )
    for s, qs in sorted(slices.items()):
        qs = [q for q in qs if groups[q] not in ("safety",)]
        out.append(
            f"| lát {s} ({len(qs)}) | "
            + " | ".join(f"{mean(r, metric, qs):.2f}" if r else "—" for _, r in configs)
            + " |"
        )
    return [*out, ""]


stage1 = [
    ("BM25", load("bm25-v3-k20")),
    ("dense gemma-300m", load("dense-gemma300m-v3-k20")),
    ("dense bge-m3", load("dense-bge-m3-v3-k20")),
    ("dense qwen 0,6B", load("dense-qwen06b-v3-k20")),
    ("dense qwen 4B", load("dense-qwen4b-v3-k20")),
    ("hybrid qwen 4B (rrf2)", load("hybrid-qwen4b-v3-p50-k20-rrf2")),
    ("dense qwen 8B", load("dense-qwen8b-v3-k20")),
    ("hybrid qwen 8B (rrf2)", load("hybrid-qwen8b-v3-p50-k20-rrf2")),
]
H4 = "hybrid-qwen4b-v3-p50-k20-rrf2"
stage2 = [
    ("không rerank", load(H4)),
    ("bge-reranker-v2-m3", load(H4, "bge_reranker_v2_m3_q8_0")),
    ("Qwen3-Reranker-0,6B", load(H4, "qwen3_reranker_0_6b_q8_0")),
    ("Qwen3-Reranker-4B", load(H4, RERANK)),
    ("Qwen3-Reranker-8B", load(H4, "qwen3_reranker_8b_q8_0")),
]
chosen = load(H4, RERANK)
d1 = load("dense-qwen4b-v3-k20", RERANK)
d2 = load("hybrid-qwen4b-v3-plain-p50-k20-rrf2", RERANK)
d6 = load("hybrid-qwen4b-v3-p50-k20-rrf60")
d7 = load("hybrid-qwen4b-v3-sections-p50-k20-rrf2", RERANK, gold_only=True)
d7_base = load(H4, RERANK, gold_only=True)
M4 = ["hit@3", "hit@5", "hit@10", "hit@20", "ndcg@5", "mrr@10"]

lines = ["## Bảng sinh tự động (`phase_d_tables.py`)", ""]
lines += table("Giai đoạn 1: tìm (chưa rerank), tập chọn 8.470 câu", stage1, M4, SELECT)
lines += table(
    "Giai đoạn 1 trên nhóm hội thoại (1.500 câu, câu cuối để nguyên = Q0)",
    stage1,
    M4,
    CONV,
)
lines += table("Giai đoạn 2: rerank trên hybrid qwen 4B, tập chọn", stage2, M4, SELECT)
lines += table(
    "D: ablation trên cặp đã chọn (hybrid qwen 4B + Qwen3-Reranker-4B), tập chọn",
    [
        ("cặp đã chọn", chosen),
        ("D1 dense qwen 4B + rerank 4B", d1),
        ("D2 không enrichment + rerank 4B", d2),
        ("D6 hybrid RRF k=60 (chưa rerank)", d6),
        ("hybrid RRF k=2 (chưa rerank)", load(H4)),
    ],
    M4,
    SELECT,
)
lines += tests(
    "D",
    [
        ("cặp đã chọn", "D1 dense", chosen, d1),
        ("cặp đã chọn", "D2 không enrichment", chosen, d2),
        ("RRF k=2", "RRF k=60", load(H4), d6),
    ],
    "hit@5",
    SELECT,
)
lines += table(
    "D7: đơn vị đọc, chấm theo mục gold, cả 9.970 câu",
    [("chunk gộp ~1.024 token", d7_base), ("một chunk mỗi mục", d7)],
    M4,
    sorted(q for q, g in groups.items() if g != "safety"),
)
lines += tests(
    "D7",
    [("chunk gộp", "chunk theo mục", d7_base, d7)],
    "hit@5",
    sorted(q for q, g in groups.items() if g != "safety"),
)
lines += ["### Theo nhóm và lát, Hit@5", ""]
lines += by_group(
    [
        ("chọn", chosen),
        ("không rerank", load(H4)),
        ("D1 dense", d1),
        ("D2 plain", d2),
        ("BM25", load("bm25-v3-k20")),
    ],
    "hit@5",
)
print("\n".join(lines))
