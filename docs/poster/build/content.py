"""Every string and number on the poster (spec §5).

Numbers come from docs/report/; quotes come from the released runs under
pharma-lab/data/evaluation/e2e/runs/ and from the corpus under
pharma-lab/data/corpus/rag-final/. Vietnamese strings are verbatim, cut with "…".
"""

HEADER = {
    "title": [
        "Agentic Retrieval-Augmented Generation",
        "for Vietnamese Pharmaceutical Documents",
    ],
    "authors": "Van-An Doan · Tuan Quoc Nguyen ✉",
    "affiliation": [
        "School of Information and Communication Technology",
        "Hanoi University of Science and Technology",
    ],
    "venue": "SoICT 2026 · Paper 1360",
}

HOOK = {
    "heading": "Without documents, the model answers from memory. Grounded in "
    "official labelling, it follows the formulary.",
    # golden item e2e-ans-0260; answers from e2e-gemini-cr/{closed-book,full}
    "question_en": "Is metformin OK while breastfeeding?",
    "question_vi": "Đang cho con bú dùng metformin có sao không?",
    "bad": {
        "label": "✗  Gemini 3.8 Flash, no documents",
        "en": "“Breastfeeding women CAN USE metformin, … rated safe and "
        "compatible with breastfeeding, if prescribed by a doctor.”",
        "vi": "“Phụ nữ đang cho con bú CÓ THỂ DÙNG ĐƯỢC Metformin, … đánh giá là "
        "an toàn và tương thích với việc nuôi con bằng sữa mẹ, nếu có chỉ định "
        "của bác sĩ.”",
        "verdict": "Contradicts the formulary",
    },
    "good": {
        "label": "✓  Same model in our pipeline",
        "en": "“Metformin passes into breast milk [2, 3]… there is still a "
        "potential risk of hypoglycaemia… in infants [3]. Consider… stopping "
        "breastfeeding or stopping metformin…”",
        "vi": "“Metformin có bài tiết vào sữa mẹ [2, 3]… vẫn có nguy cơ tiềm ẩn "
        "gây hạ đường huyết… ở trẻ nhỏ [3]. Cần cân nhắc… ngừng cho con bú hoặc "
        "ngừng dùng thuốc Metformin…”",
        "verdict": "Matches the formulary, with citations",
    },
    "nick_heading": "It also understands drug nicknames",
    "nick_question_en": "Should I take the “letter Y” stomach medicine "
    "before or after meals?",
    "nick_question_vi": "Thuốc bao tử chữ Y uống trước hay sau ăn?",
    "nick_map": "nickname  →  Yumangel",
    # Yumangel leaflet, section 3 (rag-final/sections.jsonl). Leaflet text, not a model answer.
    "leaflet_label": "Yumangel leaflet · §3 Dosage",
    "leaflet_en": "“Adults: 1 sachet per dose, 4 times a day, 1–2 hours after "
    "meals and at bedtime.”",
    "leaflet_vi": "“Người lớn: uống 1 gói hỗn dịch/ lần x 4 lần/ ngày, sau khi ăn "
    "1 - 2 giờ và trước khi đi ngủ.”",
    "minis": [
        ("“Panadol đỏ”", "red Panadol", "Panadol Extra", "panadol"),
        ("“chữ P”", "the “P” one", "Phosphalugel", "phosphalugel"),
    ],
}

# Header cards, one per contribution (paper §1): (tag, value, two label lines)
CONTRIBUTIONS = [
    (
        "Resource",
        "10,000",
        ("benchmark questions on a", "released Vietnamese corpus"),
    ),
    (
        "Retrieval",
        "97.5%",
        ("relevant passage in top 10,", "retrieval vs cost compared"),
    ),
    (
        "Agentic RAG",
        "18× / 25×",
        ("fewer hallucinated answers,", "Gemini / open Qwen3.5-9B"),
    ),
]

RESOURCES = {
    "heading": "A Vietnamese drug-information corpus and benchmark, all released",
    "corpus": (
        "Corpus",
        "National Drug Formulary (689 monographs, 25 chapters) + 2,406 "
        "package leaflets → 24,946 chunks",
    ),
    "enrichment": (
        "Enrichment, no model call at query time",
        "Context header · 71-term glossary on 11,031 chunks · 2,409 nickname "
        "mappings on 13,790 leaflet chunks",
    ),
    "benchmark": (
        "Benchmark",
        "10,000 questions with known answer locations",
    ),
    "groups": [
        ("Formulary", 5000, "5,000"),
        ("Brand name", 2500, "2,500"),
        ("Chunk", 1000, "1,000"),
        ("Patient", 500, "500"),
        ("Noisy", 500, "500"),
        ("Multi-intent", 500, "500"),
    ],
    "groups_note": "Noisy: no diacritics or look-alike drug names",
    "golden": (
        "Golden set, 500 items",
        (
            "420 answerable · 50 multi-turn · 10 unanswerable",
            "10 out-of-scope · 10 prompt-injection",
        ),
    ),
}

PIPELINE = {
    "heading": "Code controls the flow, and each model call makes one small decision",
    "nodes": [
        ("User turn", "question + history", "user"),
        ("Guard", "attack? medicine?", "shield-check"),
        ("Rephrase", "standalone query", "pencil-simple"),
        ("Hybrid search", ("BM25 + dense,", "RRF k = 2"), "magnifying-glass"),
        ("Rerank", "top 5 + context", "funnel"),
        ("Judge", "enough evidence?", "scales"),
        ("Answer", "with citations", "chat-circle-text"),
    ],
    "loop_label": "not enough evidence: refine the query, ≤ 3 rounds",
    "principle": [
        "One narrow question per model call",
        "Code runs the flow: ≤ 3 search rounds",
        "Qwen3.5-9B runs every step",
    ],
    "exits": "Attacks are blocked and off-topic requests redirected by the guard",
}

RETRIEVAL_HEADING = (
    "Hybrid search with a self-hosted 4B reranker puts a relevant passage "
    "in the top 10 for 97.5% of questions"
)
RETRIEVAL_COLUMNS = ["Method", "Cost", "Hit@10", "Hit@30", "nDCG@10"]
# tables/retrieval.tex; last field marks the pipeline rows
RETRIEVAL_ROWS = [
    ("BM25", "sparse", "81.3", "92.6", "0.621", False),
    ("Qwen3-Emb-4B", "2,560", "95.4", "98.6", "0.820", False),
    ("OpenAI text-emb-3-large", "3,072", "95.0", "98.1", "0.800", False),
    ("Hybrid RRF, k = 60", "2,560", "93.7", "98.9", "0.747", False),
    ("Hybrid RRF, k = 2", "2,560", "95.9", "99.2", "0.784", True),
    ("+ Qwen3-Reranker-4B", "4.0/s", "97.5", "99.2", "0.859", True),
    ("+ Qwen3-Reranker-8B", "1.5/s", "97.7", "99.2", "0.880", False),
]
RETRIEVAL_NOTE = "Cost: embedding dimension, or query–chunk pairs reranked per second"
RETRIEVAL_LESSONS = [
    "Self-hosted Qwen3-Emb-4B beats OpenAI (nDCG@10 0.820 vs 0.800).",
    "The common default RRF k = 60 falls below dense alone (nDCG@10 0.747 vs "
    "0.820). k = 2 gives the best Hit@10 (95.9) and Hit@30 (99.2) before reranking.",
]

GROUNDING = {
    "heading": "Grounding gives most of the gain, and the open 9B model reaches "
    "0.913 against Gemini's 0.923",
    "categories": ["Closed-book", "One-step RAG", "Full agent"],
    "series": [
        ("Gemini 3.8 Flash", [0.268, 0.816, 0.923]),
        ("Qwen3.5-9B", [-0.060, 0.792, 0.913]),
    ],
    "axis_label": "Truthfulness on the 500-item golden set",
    "scoring": "Each answer scores perfect +1, acceptable +½, missing 0, wrong −1, "
    "so below zero means more wrong than right.",
    "hallucination": (
        "Hallucinated answers, closed-book → full agent:",
        "18.3% → 1.0% (Gemini) · 30.6% → 1.2% (Qwen3.5-9B)",
    ),
}

STEPS = {
    "heading": "Each step pays off on the questions it targets",
    "note": "Gemini agent, truthfulness",
    "legend": ("without", "with"),
    # tables/e2e-layers.tex: (step, targeted questions, without, with, without label, with label, extra)
    "rows": [
        ("Rephrase", "50 follow-up questions", 0.020, 0.920, "0.020", "0.920", ""),
        (
            "Judge–refine",
            "70 patient-phrased questions",
            0.657,
            1.000,
            "0.657",
            "1.000",
            "",
        ),
        (
            "Reranker",
            "70 single-chunk answers",
            0.607,
            0.771,
            "0.607",
            "0.771",
            "p = 0.056, borderline",
        ),
        (
            "Guard",
            "10 out-of-scope requests",
            0.0,
            1.0,
            "0/10",
            "10/10",
            "redirect rate, no reranker",
        ),
    ],
    "concat": "Rephrasing also beats concatenating earlier questions "
    "(0.920 vs 0.750 on follow-ups).",
}

FUTURE = {
    "heading": "Future work",
    "items": [
        "Cross-check answers with specialist sources and linear-algebraic "
        "logic programming",
        "A decision model that skips unneeded steps, to cut cost and latency",
        "A comparison with a ReAct agent",
    ],
}

LINKS = {
    "qr": [
        (
            "Code",
            "qr-github.png",
            "https://github.com/doanan293/ViPharmind/tree/v1.1.0",
        ),
        (
            "Data",
            "qr-kaggle.png",
            "https://www.kaggle.com/datasets/doanvanan0209/vipharma-rag",
        ),
    ],
    "emails": [
        "an.dv252778m@sis.hust.edu.vn",
        "tuannq@soict.hust.edu.vn",
    ],
    "funding": "Funded by Hanoi University of Science and Technology, "
    "project T2025-PC-019",
}


def all_texts() -> list[str]:
    """Every visible string, for the number and style checks."""
    out: list[str] = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    for v in (
        HEADER,
        HOOK,
        CONTRIBUTIONS,
        RESOURCES,
        PIPELINE,
        RETRIEVAL_HEADING,
        RETRIEVAL_COLUMNS,
        RETRIEVAL_ROWS,
        RETRIEVAL_NOTE,
        RETRIEVAL_LESSONS,
        GROUNDING,
        STEPS,
        FUTURE,
        LINKS["emails"],
        LINKS["funding"],
    ):
        walk(v)
    return out
