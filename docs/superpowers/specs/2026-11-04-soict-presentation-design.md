# SoICT 2026 oral presentation: design

Date: 2026-11-04, revised 2026-11-05 to match the delivered deck · Paper 1360, *Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical Documents* (Van-An Doan, Tuan Quoc Nguyen ✉, HUST) · Conference 4–5/12/2026, Ho Chi Minh City.

## 1. Intent

A 15-minute oral slot **including Q&A** at SoICT 2026 (Springer CCIS proceedings), presented by Van-An Doan. The author called it a very important conference. The audience must leave remembering **the interesting insights and what the system can do**. The author named the Vietnamese drug corpus built from real package leaflets as the first thing to remember, and the colloquial-name / abbreviation enrichment ("Panadol đỏ", "thuốc bao tử chữ Y", TKTW…) as something that must be shown. After the first build the author found the results section too thin and asked for the measured retrieval table and the "self-host the embedding model" lesson to be shown in full.

The deck must look like a scientific-conference talk: clean, evidence-first, high-quality diagrams, charts and tables, readable from the back of a room on a projector.

## 2. Goals, non-goals, anti-goals

**Goals**
- About 11:30 of talk and about 3:30 of Q&A.
- About 16 content slides (author's limit) plus a Thank-you slide; backup slides after it answer likely questions with full tables.
- Every one of the 20 insights in §6 appears in the deck, the important ones as their own slides.
- Slides and speaker notes in **English**.

**Non-goals**
- No live demo and no screenshot of a running ViPharmInd app (none exists).
- No new experiments or numbers that are not in the paper.

**Anti-goals: fail even if the deck looks good**
- **Any number, model name, drug name or claim that does not match the paper exactly.** The author's words: "ta phải chuẩn chỉ đừng làm sai" (we must be exactly right, no mistakes). This is the top rule.
- Section labels like "WHY / WHAT WE BUILT / WHAT WE FOUND". The author found these not academic enough.
- Text-heavy slides; charts that are screenshots of the PDF.
- Filler text (see §4, "Editorial rules").

## 3. Source of truth

All numbers come from `report/` (camera-ready manuscript). The author's decision: the paper is the only correct source of results, and no run-vs-paper discrepancy is mentioned anywhere. Priority:
1. `report/tables/{corpus,retrieval,e2e-main,e2e-ablation,e2e-layers}.tex`
2. `report/figures/{retrieval-cost,e2e-groups,pipeline}.tex` (data coordinates inside the TikZ)
3. `report/sections/{methodology,results,introduction,conclusion}.tex` for numbers stated only in prose (e.g. 2.2×, 1.4×, 295/480, 4.8 calls, 25.7%, 10.8%, 96.5%, κ/AC1/ρ, held-out 96.1 vs 93.8, 0.761→0.804, ">40% fewer calls and tokens")
4. Raw data under `pharma-lab/data/` only for **examples** (aliases, glossary terms, questions and answers), never for metrics. Example answers may come from any run directory (author's permission).

Exact wording of model names: Gemini 3.8 Flash (guard/rephrase use gemini-3.1-flash-lite, judge/refine/answer use gemini-3.8-flash-high), Qwen3.5-9B, Qwen3-Embedding-4B, Qwen3-Reranker-4B, BGE-M3, BGE-reranker-v2-m3, BGE-reranker-v2-gemma, EmbeddingGemma-300M, OpenAI text-embedding-3-large, BM25, RRF.

## 4. Visual style and editorial rules

- **Template:** `presentation/template.pptx` (Slidesgo "Introduction to Coding Workshop", 16:9). White / light lavender background, IBM Plex Mono indigo headings, Poppins body, orange accent, small line and dot motifs. All template example slides are removed.
- **Result slides use "chart + headline numbers"**: the chart or table is the evidence, one or two big numbers on the right are the takeaway.
- **Section tags** follow the paper (*Introduction · Resources · Method · Results · Conclusion · Backup*) as a small tag above each title. No outline slide.
- Charts and tables are **rebuilt from the paper's numbers**. The grounding chart, the question-type charts and all large tables are native, editable PowerPoint objects.
- The pipeline diagram is redrawn from `report/figures/pipeline.tex`: guard → rephrase → search (hybrid RRF top 30) → rerank (top 5 + context) → judge → answer, refine loop ≤ 3 rounds, guard and small-talk exits, dashed = ablated steps, per-turn budget.

**Editorial rules from the author's review**
- No infrastructure details: no "2× T4", "llama.cpp" or "thinking disabled" on slides, in notes or in backup.
- No filler captions: no item ids, "taken verbatim" notes, "Paper Table N" source lines, subtitles that restate the title, or implementation lines (Qdrant, LangGraph). A short line stays only where a chart or table cannot be read without it (the Cost column of slide 8, the closed-book / one-step definitions of slide 11, the 480-item denominator of slide 14).
- No credit lines: no product-photo credit and no Slidesgo template credit (author's decision; the free Slidesgo licence asks for one, so this assumes the author's own licence covers it).
- The QR codes appear once, on the Thank-you slide.
- Vietnamese questions are shown in sentence case with full diacritics, each with an English gloss for the international audience. Answers are quoted verbatim, with "…" for cuts.

## 5. Slide plan (as delivered)

| # | Tag | Title | Content |
|---|---|---|---|
| 1 | – | Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical Documents | Van-An Doan (presenter, underlined) · Tuan Quoc Nguyen ✉, HUST, SoICT 2026 · paper 1360 |
| 2 | Introduction | A real question, a real risk | "Đang cho con bú dùng metformin có sao không?" (golden item e2e-ans-0260, gloss "Is metformin OK while breastfeeding?"). Gemini 3.8 Flash closed-book says it is safe, which contradicts the formulary (judged severe harm); the same model in the pipeline says metformin passes into milk, may cause infant hypoglycaemia, and stopping breastfeeding or the drug should be considered, with citations. Three research gaps |
| 3 | Introduction | Contributions | Resource · retrieval study with cost · low-cost agentic RAG with evaluation; "Everything is released" band |
| 4 | Resources | A corpus from official drug labelling | Formulary p. 1118 (Paracetamol) and the Yumangel leaflet; 689 monographs + 25 chapters, 2,406 leaflets, 24,946 chunks; page numbers kept for citation |
| 5 | Resources | Search the way patients talk | Panadol đỏ → Panadol Extra, "thuốc bao tử chữ Y" → Yumangel, "chữ P" → Phosphalugel with product photos; the real Yumangel chunk with header and colloquial mapping; glossary TKTW / ADR / GFR; 2,409 mappings on 13,790 leaflet chunks, 71-term glossary on 11,031 chunks, no LLM call at query time |
| 6 | Resources | Two evaluation sets | 10,000-question benchmark by group; 500-item golden set (420 / 50 / 10 / 10 / 10) |
| 7 | Method | Code drives, the LLM makes small decisions | Pipeline diagram; three boxes: code owns control and budgets, Gemini setting, open-weight setting (Qwen3.5-9B, Apache 2.0, self-hosted) |
| 8 | Results | Retrieval: 14 methods on 10,000 questions | Native table (Method, Cost, Hit@5, Hit@10, Hit@30, nDCG@10, MRR@10), pipeline rows highlighted, best values bold; 97.5% Hit@10, 99.2% Hit@30; "Three lessons" |
| 9 | Results | Self-hosted embeddings match a commercial API | Dense scatter; head-to-head Qwen3-Emb-4B vs OpenAI-3-large (2,560 vs 3,072 dims, Hit@10 95.4 vs 95.0, nDCG@10 0.820 vs 0.800, MRR@10 0.779 vs 0.754, CER@10 98.4 vs 97.8), matches the 8B in Hit@10; fusion block: k = 60 gives 0.747 nDCG@10, below dense alone, k = 2 best Hit@10 / Hit@30 before reranking, held-out 96.1% vs 93.8% |
| 10 | Results | Rerankers: the 4B model is the sweet spot | Reranker scatter; +3.7 Hit@5, 2.7× the 8B's throughput at 0.8 lower Hit@5, BGE-v2-m3 eight times faster with Hit@10 unchanged, BGE-v2-gemma no gain, Vietnamese instruction 0.761 → 0.804; band: BM25 2.2× on 3,657 rare-word questions, reranker 1.4× on 846 sibling-product questions |
| 11 | Results | Grounding is the big lever | Native truthfulness chart (closed-book / one-step / full × two models); 18× and 25× fewer hallucinations; nugget recall and severe harm, closed-book → full agent |
| 12 | Results | One open 9B model can run every step | Native table of the two full agents (12 metrics incl. safety and cost); 0.010 truthfulness gap; −0.060 → 0.913 for the same Qwen3.5-9B; why a small model copes |
| 13 | Results | Averages hide what each step does | Per-step effect on targeted groups (rephrase 0.920 → 0.020, judge–refine 1.000 → 0.657, reranker 0.771 → 0.607 borderline, guard 10/10 → 0/10); one-step RAG leaves 96% / 88% of follow-ups unanswered |
| 14 | Results | What the extra LLM calls buy | Truthfulness dot plot by system (Gemini circle, Qwen square, LLM calls per turn under each name); follow-up comparison full agent vs Concat RAG; Concat 2.0 vs 5.3 calls, >40% fewer calls and tokens, 4.0% hallucination with Qwen3.5-9B; judge–refine bar 295 accepted / 185 refined (+4.8 calls each) |
| 15 | Results | Can we trust the automatic judge? | κ / AC1 / ρ tiles for both settings; PPI: slightly strict, favours no system; citations: 96.5% supported, 25.7% uncited, 10.8% untraceable |
| 16 | Conclusion | Takeaways | Five takeaways (resource; self-hosted retrieval is enough; grounding; small decisions suit small models; judge each step where needed) and a two-line Limits strip |
| 17 | – | Thank you! Questions? | Contacts and the two QR codes (GitHub v1.1.0, Kaggle); stays on screen during Q&A. Built on the title-slide layout, because the template's thank-you layout carries a locked Slidesgo credit |

**Backup (18–25):** divider; full limitations (template questions, one pharmacist, Wilson [0.722, 1.000]); full retrieval table; full end-to-end table; ablation table; nugget recall by question type; retrieval slices and metric definitions; three example transcripts (follow-up rephrased, unanswerable declined, injection blocked) with English glosses.

## 6. The 20 insights (approved by the author)

A. What it does: (1) first Vietnamese drug corpus from the National Formulary + 2,406 real leaflets; (2) 10,000-question benchmark with answer location known by construction; (3) 500-item golden set incl. multi-turn and safety cases; (4) deterministic enrichment, context header + 71-term glossary + 2,409 colloquial mappings; (5) agentic pipeline for low-cost models with small structured decisions and hard budgets; (6) everything released.
B. Retrieval: (7) 97.5% Hit@10, hybrid 99.2% Hit@30; (8) self-hosted Qwen3-Emb-4B beats OpenAI-3-large; (9) RRF k=60 hurts, k=2 wins, holds on held-out; (10) 4B reranker ≈ 8B at 2.7× speed, BGE-gemma no gain; (11) BM25 for rare words (2.2×), reranker for sibling products (1.4×).
C. End-to-end: (12) grounding: 18× / 25× fewer hallucinations, closed-book Qwen negative; (13) open 9B within 0.010 of Gemini; (14) per-step effect on targeted groups; (15) one-step RAG leaves 96% of follow-ups unanswered; (16) Concat RAG cheap but rephrase better, Qwen Concat hallucination 4.0%; (17) judge–refine acts as conditional refinement (295 of 480 accepted at first search); (18) judge agrees with blind pharmacist; (19) citation precision high, uncited sentences the weakness.
D. (20) Limitations: on slide 16 as one strip, in full in backup.

## 7. Assets

- Formulary PDF: `pharma-lab/data/sources/duoc-thu-quoc-gia-viet-nam.pdf`, page 1118 starts the PARACETAMOL monograph.
- Leaflet pages and product photos: `pharma-lab/data/sources/leaflets/html/` (crawled 2026-07-24 from nhathuocankhang.com). Copies used in the deck are in `presentation/assets-src/`.
- Colloquial mappings: `pharma-lab/data/sources/colloquial_mappings.json`. Panadol xanh is not shown, because its key has no leaflet in the corpus.
- Glossary: `pharma-lab/data/sources/term_glossary.json` (71 terms).
- Golden set: `pharma-lab/data/evaluation/e2e/golden_e2e.jsonl`; run outputs under `pharma-lab/data/evaluation/e2e/runs/<run>/<config>/answers.jsonl`.
- QR codes: GitHub `https://github.com/doanan293/ViPharmind/tree/v1.1.0`, Kaggle `https://www.kaggle.com/datasets/doanvanan0209/vipharma-rag`.

## 8. Build

- `presentation/build/make.sh` builds everything: it regenerates the ppt-master round-trip workspace from `template.pptx` when `presentation/projects/` is missing (the workspace is about 145 MB and not versioned), writes the slide SVGs and notes (`build_deck.py`, `notes.py`), runs the quality checker and exports the native PPTX to `presentation/SoICT2026_ViPharmInd_talk.pptx`. `render_pdf.py` writes the PDF backup.
- Run Python with `/usr/bin/python3` (ppt-master dependencies are in `~/.local`); no extra virtualenvs.
- The presenting machine needs Poppins and IBM Plex Mono (`presentation/fonts/`); otherwise use the PDF backup.
- `presentation/rehearsal.md` holds per-slide timings and the backup index.

## 9. Verification

- Every number on every slide is matched against the `.tex` sources; the only unmatched tokens are axis ticks, page numbers, model-name digits, row counts and percentages converted from table fractions.
- Every slide is rendered (LibreOffice and Chromium) and inspected for overflow, clipping and overlaps. LibreOffice shifts some auto-fit text boxes sideways; PowerPoint is the reference renderer.
- The quality gate and the delivery check pass. Speaker notes total about 1,570 words, about 11:30 at 130 words per minute.
