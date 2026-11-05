# SoICT 2026 oral presentation: design

Date: 2026-11-04 · Paper 1360, *Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical Documents* (Van-An Doan, Tuan Quoc Nguyen ✉, HUST) · Conference 4–5/12/2026, Ho Chi Minh City.

## 1. Intent

A 15-minute oral slot **including Q&A** at SoICT 2026 (Springer CCIS proceedings). The author called it a very important conference. The audience must leave remembering **the interesting insights and what the system can do**. The author named the Vietnamese drug corpus built from real package leaflets as the first thing to remember, and later added the colloquial-name / abbreviation enrichment ("Panadol xanh/đỏ", "thuốc bao tử chữ Y", TKTW…) as something that must be shown.

The deck must look like a scientific-conference talk: clean, evidence-first, high-quality diagrams, charts and tables, readable from the back of a room on a projector.

## 2. Goals, non-goals, anti-goals

**Goals**
- About 11 minutes of talk, about 4 minutes of Q&A.
- Every one of the 20 insights listed in §6 appears in the deck: the starred ones as their own main slides, the rest as supporting numbers or callouts on main slides, or on backup slides.
- Backup slides after "Thank you" answer the likely questions with full tables.
- Slides in **English**.

**Non-goals**
- No live demo and no screenshot of a running ViPharmInd app (none exists).
- No new experiments or numbers that are not in the paper.

**Anti-goals: fail even if the deck looks good**
- **Any number, model name, drug name or claim that does not match the paper exactly.** The author's words: "ta phải chuẩn chỉ đừng làm sai" (we must be exactly right, no mistakes). This is the top rule.
- Section labels like "WHY / WHAT WE BUILT / WHAT WE FOUND". The author found these not academic enough.
- Text-heavy slides; charts that are screenshots of the PDF.

## 3. Source of truth

All numbers come from `report/` (camera-ready manuscript). Priority:
1. `report/tables/{corpus,retrieval,e2e-main,e2e-ablation,e2e-layers}.tex`
2. `report/figures/{retrieval-cost,e2e-groups,pipeline}.tex` (data coordinates inside the TikZ)
3. `report/sections/{methodology,results,introduction,conclusion}.tex` for numbers stated only in prose (e.g. 2.2×, 1.4×, 295/480, 25.7%, 10.8%, 96.5%, κ/AC1/ρ, held-out 96.1 vs 93.8, 0.761→0.804)
4. Raw data under `pharma-lab/data/` only for **examples** (aliases, glossary terms, example questions and answers), never for metrics.

Exact wording of model names: Gemini 3.8 Flash (answer model; guard/rephrase use gemini-3.1-flash-lite, judge/refine/answer use gemini-3.8-flash-high), Qwen3.5-9B, Qwen3-Embedding-4B, Qwen3-Reranker-4B, BGE-M3, BGE-reranker-v2-m3, BGE-reranker-v2-gemma, EmbeddingGemma-300M, OpenAI text-embedding-3-large, BM25, RRF.

## 4. Visual style (decided)

- **Template:** `presentation/template.pptx` (Slidesgo "Introduction to Coding Workshop", 16:9, 9144000×5143500 EMU, 51 example slides, 30 layouts). Keep its look: white/very light lavender background, indigo monospace headings, orange accent, small decorative line/dot motifs. Replace all placeholder text and remove all template example slides that are not used, including the "Contents of this template" and credits slides. (Slidesgo's license asks for attribution; keeping a small credit line on the final slide is the builder's call.)
- **Result slides use "chart + headline numbers"** (author picked option C in the visual companion): chart on the left as the evidence, 1–2 big numbers on the right as the takeaway.
- **Section labels** follow the paper: *Introduction · Resources · Method · Experiments & Results · Conclusion*, shown as a small tag in a corner of each slide (e.g. `Results · Retrieval`). **No separate outline slide** (my call, author accepted).
- Charts are **rebuilt from the paper's numbers**, preferably as native editable PowerPoint charts, or as crisp vector graphics if native is not possible. Never screenshots of the PDF.
- The pipeline diagram is redrawn large and clean in template colours, faithful to `report/figures/pipeline.tex`: guard → rephrase → search (hybrid RRF top 30) → rerank (top 5 + context) → judge → answer, refine loop ≤3 rounds back to search, guard exits (blocked / redirect), small-talk exit, dashed = ablated steps, per-turn budget 10 calls / 40,000 tokens / 24,000 chars of evidence.
- Output: an **editable .pptx** in `presentation/`, with **English speaker notes** on every main slide including target time (my call).

## 5. Slide plan (main deck, ~11 min)

Times are targets; the builder may rebalance as long as the total stays at about 11 minutes.

| # | Section tag | Title (working) | Main visual | Insights | Time |
|---|---|---|---|---|---|
| 1 | – | Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical Documents | Title, authors exactly as in the paper: **Van-An Doan** (presenter, underlined or marked) and **Tuan Quoc Nguyen** (✉ corresponding), HUST, SoICT 2026, paper 1360 | – | 0:20 |
| 2 | Introduction | A real question, a real risk | Chat-style mockup with a real colloquial / no-diacritic question from the golden set and the closed-book answer vs the grounded answer (both taken from actual run outputs, see §7). Three gaps: no Vietnamese drug resource; retrieval ranked without cost; agentic RAG opaque and reliant on strong models | – | 1:00 |
| 3 | Introduction | Contributions | 3 cards: Resource · Retrieval study with cost · Low-cost agentic pipeline + evaluation protocol; "all released" with 2 QR codes | 6 | 0:40 |
| 4 | Resources | A corpus from official drug labelling | Side by side: National Drug Formulary page (Paracetamol monograph) and a real package leaflet (Panadol Extra box text). Stat blocks from Table corpus: 689 monographs + 25 chapters, 2,406 leaflets, 3,120 docs, 24,946 chunks; page numbers kept for citation | 1 | 0:40 |
| 5 | Resources | Search the way patients talk | Panadol xanh vs Panadol đỏ product images → each maps to its own product; query "thuốc bao tử chữ Y …" → Yumangel chunk with context header + alias highlighted; chips of glossary expansions (TKTW, NSAID, ADR…). Counts: 2,409 colloquial mappings on 13,790 leaflet chunks; 71-term glossary on 11,031 chunks; footer line: deterministic, reproducible, zero LLM calls at query time | 4 | 1:00 |
| 6 | Resources | Two evaluation sets | 10,000-question benchmark as a 6-group chart (5,000 formulary · 2,500 brand · 1,000 chunk-level · 500 patient · 500 noisy · 500 multi-intent), 17 intents, 3 difficulty levels, "answer location known by construction"; 500-item golden set bar (420 answerable · 50 multi-turn · 10 unanswerable · 10 out-of-scope · 10 injection), written with a pharmacist, key facts with verbatim evidence quotes | 2, 3 | 1:00 |
| 7 | Method | Code drives, the LLM makes small decisions | Full-width pipeline diagram (§4); retrieval detail (Qwen3-Embedding-4B + BM25, RRF k=2, Qwen3-Reranker-4B); two model settings (Gemini vs all-Qwen3.5-9B on 2× T4) | 5 | 1:20 |
| 8 | Experiments & Results | Retrieval: 97.5% Hit@10, fully self-hosted | Two scatter plots from `retrieval-cost.tex` (dense: nDCG@10 vs embedding dim; rerankers: Hit@5 vs pairs/s, log x, dashed "hybrid, no reranker" line), chosen Qwen3-Reranker-4B highlighted. Big numbers: 97.5% Hit@10; 99.2% Hit@30 for hybrid. Callouts: Qwen3-Emb-4B 0.820 vs OpenAI 0.800 nDCG@10; RRF k=60 → 0.747 vs k=2 wins (held-out Hit@10 96.1 vs 93.8); 4B within 0.8 of 8B at 2.7× throughput; BGE-gemma no gain | 7, 8, 9, 10, (11 in notes) | 1:20 |
| 9 | Experiments & Results | Grounding is the big lever | Truthfulness bars: closed-book vs full agent for both models (0.268 → 0.923; −0.060 → 0.913). Big numbers: 18× fewer hallucinations (18.3% → 1.0%) Gemini; 25× (30.6% → 1.2%) Qwen3.5-9B; open 9B within 0.010 of Gemini | 12, 13 | 1:20 |
| 10 | Experiments & Results | Averages hide what each step does | Four paired with/without bars on the targeted groups (Table e2e-layers): rephrase on follow-ups 0.920 → 0.020; judge–refine on patient phrasing 1.000 → 0.657; reranker on single-chunk 0.771 → 0.607 (p = 0.056, mark as borderline); guard redirect 10/10 → 0/10. Note: one-step RAG leaves 96% / 88% of follow-ups unanswered | 14, 15 | 1:20 |
| 11 | Experiments & Results | Cheaper alternative: Concat RAG | Truthfulness vs LLM calls/turn for the configurations of Table e2e-main; follow-up numbers (Gemini: 0.920 vs 0.750, 84% vs 64% perfect; Qwen: nugget recall 0.948 vs 0.830; Concat hallucination 4.0% with Qwen). Judge accepts first search for 295/480 items | 16, 17 | 0:40 |
| 12 | Experiments & Results | Can we trust the judge? | Agreement tiles: κ 0.848 / 0.864, AC1 0.904 / 0.876, ρ 0.905 / 0.944 (Gemini / open-weight); PPI: judge slightly strict, favours no system. Citation: 96.5% of cited sentences supported; 25.7% of sentences uncited, 10.8% untraceable facts | 18, 19 | 0:40 |
| 13 | Conclusion | Limitations | Template-generated questions (99.2% Hit@30 likely optimistic); one pharmacist for golden set and calibration; 10 items per safety case (Wilson [0.722, 1.000]) | 20 | 0:30 |
| 14 | Conclusion | Takeaways | 3 lines + QR codes (GitHub `https://github.com/doanan293/ViPharmind/tree/v1.1.0`, Kaggle `https://www.kaggle.com/datasets/doanvanan0209/vipharma-rag`) | – | 0:30 |
| 15 | – | Thank you · Questions? | Contact: Van-An Doan, `an.dv252778m@sis.hust.edu.vn`; QR | – | – |

**Backup (after slide 15):** B1 full retrieval table (14 rows); B2 full end-to-end table (Table e2e-main); B3 ablation table (Table e2e-ablation); B4 nugget recall by question type (`e2e-groups.tex`: single-turn / multi-turn / noisy × 4 systems × 2 models); B5 retrieval slices (BM25 2.2× on 3,657 rare-word questions; reranker 1.4× on 846 sibling-product questions; dense vs BM25 by group) and metric definitions (truthfulness scoring 1 / ½ / 0 / −1, CRAG labels); B6 safety cases + example transcripts (a follow-up question rephrased; an unanswerable refusal; an injection blocked), from actual run outputs.

## 6. The 20 insights (approved by the author)

A. What it does: (1) first Vietnamese drug corpus from the National Formulary + 2,406 real leaflets ★; (2) 10,000-question benchmark with answer location known by construction ★; (3) 500-item golden set incl. multi-turn and safety cases; (4) deterministic enrichment, context header + 71-term glossary + 2,409 colloquial mappings; (5) agentic pipeline for low-cost models with small structured decisions and hard budgets ★; (6) everything released.
B. Retrieval: (7) 97.5% Hit@10, hybrid 99.2% Hit@30 ★; (8) self-hosted Qwen3-Emb-4B beats OpenAI-3-large ★; (9) RRF k=60 hurts, k=2 wins, holds on held-out; (10) 4B reranker ≈ 8B at 2.7× speed, BGE-gemma no gain; (11) BM25 for rare words (2.2×), reranker for sibling products (1.4×).
C. End-to-end: (12) grounding: 18× / 25× fewer hallucinations, closed-book Qwen negative ★; (13) open 9B within 0.010 of Gemini on 2× T4 ★; (14) per-step effect on targeted groups ★; (15) one-step RAG leaves 96% of follow-ups unanswered; (16) Concat RAG cheap but rephrase better, Qwen Concat hallucination 4.0%; (17) judge–refine acts as conditional refinement (61% accepted at first search); (18) judge agrees with blind pharmacist; (19) citation precision high, uncited sentences the weakness.
D. (20) Limitations.

## 7. Assets found (recon)

- Leaflet pages: `pharma-lab/data/sources/leaflets/html/<category>/<slug>.html` (2,434 files, crawled 2026-07-24 from nhathuocankhang.com; manifest in `leaflets/manifest.json`). Pages render with images in headless Chromium (Playwright is in `~/.local`; run with `/usr/bin/python3`). Panadol Extra page: `thuoc-dau-dau-ha-sot/panadol-extra.html`. Its box-side photo with "CHỈ ĐỊNH / LIỀU LƯỢNG VÀ CÁCH DÙNG": `https://cdn.tgdd.vn/Products/Images/10244/129157/panadol-extra-hop180v-7.jpg` (also `-6.jpg`). Product thumbnails for Panadol (blue) and Yumangel can be found the same way from their leaflet HTML.
- Formulary PDF: `pharma-lab/data/sources/duoc-thu-quoc-gia-viet-nam.pdf`, 1,668 pages; **page 1118** starts the PARACETAMOL monograph (`pdftoppm -f 1118 -l 1118`).
- Colloquial mappings: `pharma-lab/data/sources/colloquial_mappings.json`, e.g. `panadol-extra-gsk-150-vien-11440` → "Panadol đỏ / Panadol vỉ đỏ / Panadol hộp đỏ" (visual sign "Hộp màu đỏ, vỉ thuốc màu đỏ"); `panadol-gsk-150-vien-11439` → "Panadol xanh / xanh dương / thường"; `yumangel` → "thuốc bao tử chữ Y"; `phosphalugel` → "thuốc bao tử chữ P"; also Decolgen đỏ/xanh, Hapacol sủi, Loperamide xanh xám.
- Glossary: `pharma-lab/data/sources/term_glossary.json`, 71 terms (ADR, NSAID, TKTW, CYP3A4, G6PD, HbA1c…), each with Vietnamese and English expansions.
- Golden set: `pharma-lab/data/evaluation/e2e/golden_e2e.jsonl`; run outputs under `pharma-lab/data/evaluation/e2e/runs/<run>/<config>/answers.jsonl`.
- **The paper is the only source of truth for results (author's decision: "paper mới đúng").** All numbers shown on slides or in notes come from the paper. Do not compute or quote aggregates from run directories.
- **Example answers (slide 2, B6)** may be taken from any run directory (author's permission). They are qualitative illustrations only: show the question and answer texts, never a run's aggregate metrics. Label which model produced each answer.
- Real Vietnamese text shown on slides (questions, chunks, leaflet text) stays in Vietnamese with a short English gloss next to it.
- Every third-party image carries a small source line ("Source: nhathuocankhang.com", "Dược thư Quốc gia Việt Nam, 2nd ed., 2018, p. 1118").

## 8. Tools

The author invoked the `ppt-master` skill and the `pptx` skill and gave the template. Memory: ppt-master's Python deps are in `~/.local`; run it with `/usr/bin/python3` and create no extra virtualenvs. The work goes in `presentation/` (currently untracked) on branch `camera-ready`.

## 9. Verification (required before handing over)


- A number check: every number on every slide and in the notes is listed with its source location in the `.tex` files and checked to match. Rounding must match the paper (e.g. 0.923, not 0.92; 18.3%, not 18%), except for the headline "18×/25×", which the paper itself uses.
- Render every slide to an image (LibreOffice → PDF → PNG) and inspect for overflow, clipped text, overlaps, leftover template placeholders, and readability at projector size (no body text below ~14 pt equivalent on main slides).
- Rehearsal-time check: the speaker notes for the main slides read aloud in about 11 minutes (≈1,500–1,650 words in total).

## 10. Left to the builder

Exact slide wording, chart styling details, which template layouts to reuse for which slide, the icon choices, the QR generation method, how to split the ppt-master vs pptx skill work, and minor time rebalancing.

Calls I made that the author has not explicitly confirmed:  no outline slide (author accepted); English speaker notes with timings; editable PPTX output; native charts preferred; Vietnamese example text kept with English gloss; source lines on third-party images.
