# SoICT 2026 poster: design

Date: 2026-11-18 · Paper 1360, *Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical Documents* (Van-An Doan, Tuan Quoc Nguyen ✉, HUST) · Conference December 2026, Ho Chi Minh City. **Submission deadline: 2026-11-23**, PPTX and PDF through the organisers' form (the author submits).

## 1. Intent

The paper was accepted for an oral talk, and the organisers also invite a poster. They print it for free at **A0 portrait (841 × 1189 mm)** and hang it in the exhibition room for the whole day of the talk. The author will **not stand beside it**, so the poster must tell the story on its own. Many people will see it through photos.

The author's angle is **practical usefulness**. Without documents a model gives wrong and dangerous drug answers; grounded in official labelling it gets them right. Real people also never use full drug names: they say "Panadol đỏ" (red Panadol) or "thuốc bao tử chữ Y" (the "letter Y" stomach medicine), and the system understands them. It runs on a small open model, which makes it deployable.

The author wants a **full research poster** (all the evidence of the paper) with a **soft, friendly, cute look**, not a dump of the paper.

## 2. Goals, non-goals, anti-goals

**Goals**
- A passer-by, or someone looking at a photo, gets the message from the title, the hook block and the block headings alone.
- A reader standing close can follow the whole study without the author, reading blocks in numbered order.
- One A0 portrait page delivered as an editable **PPTX** and a print-ready **PDF**, both exactly 841 × 1189 mm (±1 mm).

**Non-goals**
- No new experiments or numbers that are not in the paper.
- Not a copy of all 16 slides: the poster carries the subset in §5.

**Anti-goals: fail even if it looks good**
- **Any number, model name, drug name or claim that does not match the paper exactly.** Same top rule as the deck ("ta phải chuẩn chỉ đừng làm sai").
- Invented examples or answers. Every quoted model answer comes from a released run, and every leaflet quote is verbatim from the corpus. The author asked once for a hand-written answer in a chat bubble; it was declined and replaced by the leaflet quote in §5.1.
- A stiff paper look: dense grey text, square boxes, screenshots of PDF tables.
- The editorial rules of the deck spec (`2026-11-04-soict-presentation-design.md` §4): no infrastructure details (T4, llama.cpp, thinking disabled), no filler captions, no item ids, no "Paper Table N" lines, no implementation names (Qdrant, LangGraph), no product-photo or template credit.
- AI-sounding text (author's review): no semicolons joining two claims in headings or body lines, no metaphors such as "big lever" or "heavy lifting", no closers that repeat a heading, no em dashes as connectors, no decorative emoji bullets.

## 3. Source of truth

Identical to the deck spec §3: numbers come only from `docs/report/` (tables, then figure coordinates, then prose); raw data under `pharma-lab/data/` only for examples. Model names exactly as written there (Gemini 3.8 Flash, Qwen3.5-9B, Qwen3-Emb-4B, Qwen3-Reranker-4B, OpenAI text-embedding-3-large, BM25, RRF). The author line follows the paper ("Tuan Quoc Nguyen"), not the acceptance email ("Quoc-Tuan Nguyen").

## 4. Look, language and type

**Style A, "soft pastel"** (author's choice from the mockups in `.superpowers/brainstorm/`, file `full-content-v3.html`, left poster):
- Background: a soft vertical gradient from pale lavender (`#F3EFFF`) to pale peach (`#FFF6EC`).
- Content in white cards with large rounded corners and a faint indigo shadow; numbered purple circles (1–7) mark the reading order.
- Deck palette softened: indigo `#0C0A9E` for headings, purple `#8208D5` for tags, lavender `#E6E4FD`, peach `#FFE9CF`, mint `#DFF3EA`, coral `#FFE3DE` for fills. Charts use soft periwinkle (Gemini) and soft orange (Qwen3.5-9B); "with / without" bars use mint and pale grey.
- A **pill mascot** (white and lavender capsule with eyes, smile and pink cheeks) beside the title. Optionally one or two more small mascot poses elsewhere (e.g. pointing at the QR codes), never covering content.
- Icons in the deck's line-icon style for the pipeline steps, not emoji.
- Real product photos (Panadol Extra, Yumangel, Phosphalugel) from `docs/presentation/assets-src/`.
- Fonts: Poppins for body and headings (the mockup's heavy rounded weight). Poppins has no Vietnamese glyphs, so every Vietnamese line uses Montserrat (embedded in the PDF as static instances). The PPTX embeds only Poppins and IBM Plex Mono.

**Language**: everything in English (author's decision). Vietnamese appears only as a small italic line under each Vietnamese question or quoted answer, giving the original text (author's decision).

**Type** at print scale (1 SVG px = 1/96 in, so pt = px × 0.75):
- Title, the largest text: about 100 pt.
- Authors / affiliation: about 40 pt.
- Hook question and the three big numbers: about 50–60 pt (numbers may be larger).
- Block headings: about 48 pt, each a **one-sentence finding** in plain words.
- Body, table cells, chart labels: at least 28 pt. Vietnamese lines and footnotes: at least 22 pt.

## 5. Layout and content

Portrait, read top to bottom: title band, a full-width hook card, two columns, a full-width takeaways card. The mockup `full-content-v3.html` (left) shows the arrangement; proportions are the builder's.

```
┌──────────────────────────────────────────────┐
│ Title (2 lines) + mascot · authors · SoICT    │
├──────────────────────────────────────────────┤
│ 1  Before/after (metformin) │ nickname → leaflet│
│    three big numbers                          │
├─────────────────────┬────────────────────────┤
│ 2  Resources        │ 3  Pipeline             │
│ 4  Retrieval        │ 5  Grounding & models   │
│                     │ 6  Each step            │
├─────────────────────┴────────────────────────┤
│ 7  Takeaways · limits · QR · funding          │
└──────────────────────────────────────────────┘
```

**Header.** Title exactly as the paper. "Van-An Doan · Tuan Quoc Nguyen ✉", "School of Information and Communication Technology, Hanoi University of Science and Technology", "SoICT 2026 · Paper 1360". Emails go in block 7. No logos (none in the repo).

**1. Hook.** Heading: "Without documents, the model gives dangerous answers. Grounded in official labelling, it gets them right." (or a shorter wording with the same meaning).
- Left, before and after, as on deck slide 2 (golden item `e2e-ans-0260`, answers verbatim from the released runs, cut with "…"):
  - Question: "Is metformin OK while breastfeeding?" / *Đang cho con bú dùng metformin có sao không?*
  - Red card ✗ "Gemini 3.8 Flash, no documents": English rendering of "Phụ nữ đang cho con bú CÓ THỂ DÙNG ĐƯỢC Metformin, … đánh giá là an toàn và tương thích với việc nuôi con bằng sữa mẹ…" with the Vietnamese underneath; verdict line "Contradicts the formulary · judged severe harm".
  - Green card ✓ "Same model in our pipeline": English rendering of "Metformin có bài tiết vào sữa mẹ [2, 3]… vẫn có nguy cơ tiềm ẩn gây hạ đường huyết… ở trẻ nhỏ [3]. Cần cân nhắc… ngừng cho con bú hoặc ngừng dùng thuốc Metformin…" with the Vietnamese underneath; verdict line "Matches the formulary, with citations".
- Right, "It also understands drug nicknames":
  - Question: "Should I take the 'letter Y' stomach medicine before or after meals?" / *Thuốc bao tử chữ Y uống trước hay sau ăn?*
  - "nickname → Yumangel" (from `colloquial_mappings.json`).
  - Leaflet card with the Yumangel photo, labelled "Yumangel leaflet · §3 Dosage": "Adults: 1 sachet per dose, 4 times a day, 1–2 hours after meals and at bedtime." / *Người lớn: uống 1 gói hỗn dịch/ lần x 4 lần/ ngày, sau khi ăn 1 - 2 giờ và trước khi đi ngủ.* (verbatim from section `leaflet:thuoc-tri-viem-loet-da-day:yumangel` in `pharma-lab/data/corpus/rag-final/sections.jsonl`, the Yumangel 1 g leaflet that the "thuốc bao tử chữ Y" mapping points to; the "3 lần/ngày" text belongs to Yumangel F and must not be used). This card is the leaflet text, not a model answer, and must not be labelled as one.
  - Two small cards: "Panadol đỏ" → Panadol Extra, "chữ P" → Phosphalugel, with photos.
- Three big numbers: **2,409** everyday nicknames mapped to products · **18× / 25×** fewer hallucinated answers with grounding (Gemini 18.3% → 1.0%, Qwen3.5-9B 30.6% → 1.2%) · **0.913 vs 0.923** truthfulness, open Qwen3.5-9B vs Gemini 3.8 Flash.

**2. Resources.** Heading: "A Vietnamese drug-information corpus and benchmark, all released".
- Corpus: National Drug Formulary (689 monographs, 25 chapters) + 2,406 package leaflets → 24,946 chunks.
- Enrichment with no model call at query time: context header, 71-term glossary on 11,031 chunks, 2,409 nickname mappings on 13,790 leaflet chunks.
- Benchmark: 10,000 questions with known answer locations, a stacked bar of six groups (5,000 formulary, 2,500 brand-name, 1,000 chunk-level, 500 patient-phrased, 500 noisy, 500 multi-intent).
- Golden set: 500 items (420 answerable, 50 multi-turn, 10 unanswerable, 10 out-of-scope, 10 prompt-injection).
- Optional small example: the real Qwen3.5-9B answer to golden item `e2e-ans-0072` ("Panadol đỏ có thành phần gì?" → Panadol Extra, paracetamol 500 mg, caffeine 65 mg, from `runs/e2e-qwen35-9b-cr/full/answers.jsonl`), only if space allows.

**3. Pipeline.** Heading: "Code controls the flow, and each model call makes one small decision". Icon diagram as deck slide 7: user → guard → rephrase → hybrid search (BM25 + dense, RRF k = 2) → rerank → judge (enough evidence?) → answer with citations; refine loop ≤ 3 rounds; guard exits for attacks and off-topic requests. One line: run with Gemini 3.8 Flash and with the open-weight Qwen3.5-9B.

**4. Retrieval.** Heading: "Hybrid search with a self-hosted 4B reranker puts a relevant passage in the top 10 for 97.5% of questions".
- Table rows from `tables/retrieval.tex`: BM25, Qwen3-Emb-4B, OpenAI text-emb-3-large, Hybrid RRF k = 60, Hybrid RRF k = 2, + Qwen3-Reranker-4B, + Qwen3-Reranker-8B; columns Cost, Hit@10, Hit@30, nDCG@10. Pipeline rows highlighted in peach.
- Two lessons: "Self-hosted Qwen3-Emb-4B beats OpenAI (nDCG@10 0.820 vs 0.800)." "The common default RRF k = 60 falls below dense alone (nDCG@10 0.747 vs 0.820). k = 2 gives the best Hit@10 (95.9) and Hit@30 (99.2) before reranking." (k = 2 does not beat dense alone in nDCG@10, so the lesson must not say "k = 2 works".)

**5. Grounding and models.** Heading: "Grounding gives most of the gain, and the open 9B model comes within 0.010 of Gemini".
- Grouped bar chart of truthfulness, closed-book / one-step RAG / full agent × two models (Gemini 0.268 / 0.816 / 0.923; Qwen3.5-9B −0.060 / 0.792 / 0.913). The negative bar goes below the zero line.
- Scoring note under the chart: "Each answer scores perfect +1, acceptable +½, missing 0, wrong −1, so below zero means more wrong than right." (paper Eq. 1).
- Hallucination closed-book → full agent: 0.183 → 0.010 (Gemini), 0.306 → 0.012 (Qwen3.5-9B).

**6. Each step.** Heading: "Each step pays off on the questions it targets". Paired with/without bars from `tables/e2e-layers.tex` (Gemini agent): rephrase, 50 follow-ups, 0.020 → 0.920; judge–refine, 70 patient-phrased questions, 0.657 → 1.000; reranker, 70 single-chunk answers, 0.607 → 0.771 (p = 0.056, borderline); guard, 10 out-of-scope requests, 0/10 → 10/10 redirected. One line: "Rephrasing also beats concatenating earlier questions (0.920 vs 0.750)."

**7. Takeaways, limits, links.** Four takeaways: grounding in official labelling removes most hallucinations; self-hosted retrieval is enough; small structured decisions suit small open models; corpus, benchmark, code and every run are released. Limits line: template-generated questions, a single pharmacist. QR codes to GitHub v1.1.0 and Kaggle (labels "Code", "Data"), the two emails, and "Funded by Hanoi University of Science and Technology, project T2025-PC-019".

## 6. Approaches

| Approach | Trade-off |
|---|---|
| **A. Reuse the deck pipeline (chosen)** | New `build_poster.py` reuses `docs/presentation/build/lib.py`; one A0 SVG page → ppt-master → native editable PPTX; PDF from the same SVG. Same identity and verified numbers as the talk. Risk: ppt-master and the round-trip workflow have only been used at 16:9. |
| B. LaTeX poster (beamerposter / tikzposter) | Reuses the paper's TikZ figures and gives a crisp PDF, but the required PPTX would be a picture of the PDF, not editable. |
| C. Direct python-pptx at A0 | Native PPTX at any size, but every drawing helper must be rewritten, too slow for a five-day deadline. |

The author chose **A**. **Fallback:** if a spike shows ppt-master cannot produce a correct A0 portrait PPTX, switch to C, keeping the palette, fonts and assets, and tell the author.

## 7. Build decisions

- Files under `docs/poster/`: `build/` (scripts), the workspace under `docs/poster/projects/` (generated, not versioned, like the deck's), outputs `docs/poster/SoICT2026_ViPharmInd_poster.pptx` and `.pdf`.
- Canvas: SVG viewBox about 3179 × 4494 px (1 px = 1/96 in = 9,525 EMU), giving 841 × 1189 mm. The round-trip template is an A0-portrait copy of `docs/presentation/template.pptx` (same theme), or whatever ppt-master needs for a non-16:9 canvas.
- **First step is a spike**: one A0 SVG with a title, a gradient background, a rounded card, a native table and a native chart through the full pipeline, checking the PPTX slide size, fonts, gradient and chart scale, before the full poster is built.
- Fonts: it is unknown whether the organisers print the PDF or the PPTX, so both must be safe to print. The PDF embeds Poppins (and IBM Plex Mono if used). The PPTX embeds them too (`pptx_embedded_fonts.py` or equivalent); proving this works is part of the spike. Text boxes do not rely on auto-fit and leave some slack.
- The PDF is the reference file for the author's approval. Under approach A it is rendered from the SVG (as `docs/presentation/build/render_pdf.py` does, at A0 page size). Under fallback C it is exported from the PPTX with LibreOffice, with auto-fit off, and the PPTX is opened once in PowerPoint (by the author if none is reachable from WSL).
- Both files under 10 MB if possible (Google Form uploads are often capped): photos downscaled to about 150 dpi at printed size.
- Python is `/usr/bin/python3` (deps in `~/.local`), no extra virtualenvs.
- `docs/presentation/build/make.sh` resolved the ppt-master path relative to `docs/` after the move to `docs/` and was fixed on 2026-11-18; a poster `make.sh` must resolve it from the repo root.

## 8. Calls made without the author (check these)

- The "chữ Y" example shows the verbatim leaflet text, not a model answer, because no released run answers a "chữ Y" question.
- Answers and leaflet quotes are shown in English with the Vietnamese original underneath, extending the author's rule for questions.
- Hook numbers: 2,409 mappings, 18× / 25×, 0.913 vs 0.923.
- Retrieval shown as a seven-row table, not the cost scatter plots.
- Fonts embedded in both files; the PDF is the approval reference; files kept under 10 MB.
- "Paper 1360" in the header; no logos.

## 9. Left to the builder

Exact geometry, column split and spacing; extra mascot poses; icon choices within the deck's icon set; chart styling within style A; the English wording of headings within the meaning given here; how much of each quoted answer fits.

## 10. Verification

- Every number on the poster is matched against the `.tex` sources (same procedure as deck spec §9); quoted answers against `answers.jsonl`; the leaflet quote against the corpus.
- Every heading and body line is checked against the AI-text anti-goal in §2 (no semicolons joining claims, no metaphors, no repeated closers, no em dashes, no emoji bullets).
- PPTX slide size and PDF page size are 841 × 1189 mm.
- The poster is rendered to PNG and inspected at full size and at about 10% (a phone-photo view) for overflow, clipping, overlaps and type below the minimum sizes.
- The ppt-master quality gate and delivery check pass.
- Done when both files are in `docs/poster/` and the author has approved them; the author submits through the form before 2026-11-23.
