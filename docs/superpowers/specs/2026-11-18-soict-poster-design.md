# SoICT 2026 poster: design

Date: 2026-11-18 · Paper 1360, *Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical Documents* (Van-An Doan, Tuan Quoc Nguyen ✉, HUST) · Conference December 2026, Ho Chi Minh City. **Submission deadline: 2026-11-23**, PPTX and PDF through the organisers' form (the author submits).

## 1. Intent

The paper was accepted for an oral talk; the organisers also invite a poster. They print it for free at **A0 portrait (841 × 1189 mm)** and hang it in the exhibition room for the whole day of the talk. The author will **not stand beside it**, so the poster must tell the story on its own.

The author's angle is **practical usefulness**: real people never use full drug names. They say "Panadol đỏ" (red Panadol) or "thuốc bao tử chữ Y" (the "letter Y" stomach medicine). The poster must show that the system understands how people actually talk about drugs and answers from the official leaflet, and that it can run cheaply on a small open model, which is what makes it deployable.

## 2. Goals, non-goals, anti-goals

**Goals**
- A passer-by gets the message in about 30 seconds from the title, the hook block and the block headings alone.
- A reader standing close can follow the whole study without the author, reading blocks in numbered order.
- One A0 portrait page delivered as an editable **PPTX** and a print-ready **PDF**, both exactly 841 × 1189 mm (±1 mm).

**Non-goals**
- No new experiments or numbers that are not in the paper.
- Not a copy of all 16 slides: the poster carries a subset (§5), and the full tables stay in the paper.

**Anti-goals: fail even if it looks good**
- **Any number, model name, drug name or claim that does not match the paper exactly.** Same top rule as the deck ("ta phải chuẩn chỉ đừng làm sai").
- Invented examples. The hook question and answer are a real golden item and a real run answer.
- A wall of text: a block that cannot be understood from its heading plus its figure.
- The editorial rules of the deck spec (`2026-11-04-soict-presentation-design.md` §4) apply: no infrastructure details (T4, llama.cpp, thinking disabled), no filler captions, no item ids, no "Paper Table N" lines, no implementation names (Qdrant, LangGraph), no product-photo or template credit.

## 3. Source of truth

Identical to the deck spec §3: numbers come only from `docs/report/` (tables, then figure coordinates, then prose); raw data under `pharma-lab/data/` only for examples. Model names exactly as written there (Gemini 3.8 Flash, Qwen3.5-9B, Qwen3-Embedding-4B / Qwen3-Emb-4B in tables, Qwen3-Reranker-4B, OpenAI text-embedding-3-large, BM25, RRF). The author line follows the paper ("Tuan Quoc Nguyen"), not the acceptance email ("Quoc-Tuan Nguyen").

## 4. Language and type

- **Everything in English** (author's decision). Vietnamese appears only as a **small line under** each Vietnamese user question or quoted answer, giving the original text (author's decision).
- Type hierarchy, readable at print scale (1 SVG px = 1/96 in, so pt = px × 0.75):
  - Title, the largest text on the poster: about 100 pt, readable from 5–6 m.
  - Authors / affiliation: about 40 pt.
  - Hook question and the three big numbers: about 50–60 pt (numbers may be larger).
  - Block headings: about 48 pt. Each heading is a **one-sentence finding**, not a section name.
  - Body, table cells, chart labels: at least 28 pt. Small Vietnamese lines and footnote-level text: at least 22 pt.
- Visual identity reused from the deck: palette and fonts in `docs/presentation/build/lib.py` (indigo `#0C0A9E`, orange `#EB9109`, purple, lavender; IBM Plex Mono headings, Poppins body), the deck's icon style and the product photos and QR codes in `docs/presentation/assets-src/`.

## 5. Layout and content

Portrait, read top to bottom, two columns below the hook, blocks numbered 1–7 with a visible reading order.

```
┌──────────────────────────────────────────────┐
│ Title (2 lines) · authors · HUST · SoICT 2026 │
├──────────────────────────────────────────────┤
│ 1  Hook: real question → real answer          │
│    + nickname strip + three big numbers       │
├─────────────────────┬────────────────────────┤
│ 2  Resources        │ 3  Pipeline             │
├─────────────────────┼────────────────────────┤
│ 4  Retrieval        │ 5  Grounding & models   │
├─────────────────────┴────────────────────────┤
│ 6  Each step pays off where it is aimed       │
├──────────────────────────────────────────────┤
│ 7  Takeaways · limitations · QR · funding     │
└──────────────────────────────────────────────┘
```

Proportions and exact block positions are left to the builder; the hook band must sit directly under the title and be the most eye-catching content block.

**Header.** Title exactly as the paper. "Van-An Doan · Tuan Quoc Nguyen ✉" with both emails (`an.dv252778m@sis.hust.edu.vn`, `tuannq@soict.hust.edu.vn`), "School of Information and Communication Technology, Hanoi University of Science and Technology", "SoICT 2026 · Paper 1360". No logos: none exist in the repo and none are downloaded. The acceptance email asks only for A0 portrait, PPTX and PDF ("feel free to use your own artwork"), so no other header element is required.

**1. Hook: patients ask by nickname.** Heading along the lines of "People ask about drugs by nickname; the system answers from the official leaflet".
- Chat exchange using golden item `e2e-ans-0072`: question "What is in 'red Panadol'?" with the small Vietnamese line "Panadol đỏ có thành phần gì?". Answer: the **Qwen3.5-9B full-agent** answer from `pharma-lab/data/evaluation/e2e/runs/e2e-qwen35-9b-cr/full/answers.jsonl` (recognises Panadol Extra; paracetamol 500 mg, caffeine 65 mg; cites the leaflet), shown as a faithful English rendering of an excerpt with the Vietnamese excerpt in a small line, "…" marking cuts. Label the answer with the model name. (Builder-chosen example, see §8: this item is real, uses the author's own example and shows the small open model; no golden item asks about "chữ Y".)
- Nickname strip with product photos: "Panadol đỏ" → Panadol Extra, "thuốc bao tử chữ Y" → Yumangel, "chữ P" → Phosphalugel (from `colloquial_mappings.json`; same three as deck slide 5), each nickname with a short English gloss.
- Three big numbers: **2,409** colloquial mappings · **18× / 25×** fewer hallucinated answers with grounding (Gemini 0.183 → 0.010, Qwen3.5-9B 0.306 → 0.012) · **0.913 vs 0.923** truthfulness, open Qwen3.5-9B vs Gemini 3.8 Flash.

**2. Resources.** Heading: a first Vietnamese drug-information corpus and benchmark, all released.
- Corpus: National Drug Formulary (689 monographs, 25 general chapters) + 2,406 package leaflets → 24,946 chunks.
- Deterministic enrichment, no model call at query time: context header, 71-term glossary on 11,031 chunks, 2,409 colloquial mappings on 13,790 leaflet chunks.
- Benchmark: 10,000 questions with known answer locations, six groups (5,000 formulary, 2,500 brand-name, 1,000 chunk-level, 500 patient, 500 noisy, 500 multi-intent).
- Golden set: 500 items (420 answerable, 50 multi-turn, 10 unanswerable, 10 out-of-scope, 10 prompt-injection).

**3. Pipeline.** Heading: code drives the flow; every model call makes one small decision. The icon diagram of deck slide 7, redrawn at poster scale: user → guard → rephrase → hybrid search (BM25 + dense, RRF k = 2) → rerank → judge, refine loop ≤ 3 rounds → answer, with guard and small-talk exits. One line naming the two settings (Gemini 3.8 Flash; open Qwen3.5-9B).

**4. Retrieval.** Heading: hybrid search with a self-hosted 4B reranker puts a correct passage in the top 10 for 97.5% of questions.
- A native table with a selection of `tables/retrieval.tex` rows: BM25, Qwen3-Emb-4B, OpenAI text-emb-3-large, Hybrid RRF k = 60, Hybrid RRF k = 2, + Qwen3-Reranker-4B, + Qwen3-Reranker-8B; columns Cost, Hit@10, Hit@30, nDCG@10. Pipeline rows highlighted.
- Two one-line lessons: the self-hosted Qwen3-Emb-4B beats OpenAI text-embedding-3-large (nDCG@10 0.820 vs 0.800); the usual RRF k = 60 falls below dense alone (0.747 vs 0.820), k = 2 works.

**5. Grounding and models.** Heading: grounding is the big lever, and an open 9B model comes within 0.010 of Gemini.
- Native grouped bar chart of truthfulness, closed-book / one-step RAG / full agent × two models (Gemini 0.268 / 0.816 / 0.923; Qwen3.5-9B −0.060 / 0.792 / 0.913). The negative value must render below the axis.
- Hallucination closed-book → full agent: 0.183 → 0.010 (Gemini), 0.306 → 0.012 (Qwen3.5-9B).

**6. Each step pays off where it is aimed.** Heading as given. Paired with/without bars from `tables/e2e-layers.tex` (Gemini agent): rephrase on 50 multi-turn follow-ups 0.020 → 0.920; judge–refine on 70 patient-phrased questions 0.657 → 1.000; reranker on 70 single-chunk questions 0.607 → 0.771 (p = 0.056, shown as borderline); guard on 10 out-of-scope requests 0/10 → 10/10 redirects. One line: rephrase also beats simply concatenating earlier questions (0.920 vs 0.750 with Gemini).

**7. Takeaways, limits, links.** Three to four short takeaways (grounding in official labelling; self-hosted retrieval is enough; small structured decisions suit small open models; everything released). Limits strip: template-generated questions, a single pharmacist. QR codes to GitHub v1.1.0 and Kaggle with short labels. Acknowledgement: funded by HUST under project T2025-PC-019.

## 6. Approaches

| Approach | Trade-off |
|---|---|
| **A. Reuse the deck pipeline (chosen)** | New `build_poster.py` reuses `docs/presentation/build/lib.py`; one A0 SVG page → ppt-master → native editable PPTX; PDF from the same SVG. Same identity and verified numbers as the talk. Risk: ppt-master and the round-trip workflow have only been used at 16:9. |
| B. LaTeX poster (beamerposter / tikzposter) | Reuses the paper's TikZ figures, crisp PDF; but the required PPTX would be a picture of the PDF, not editable. |
| C. Direct python-pptx at A0 | Guaranteed native PPTX at any size; all drawing helpers rewritten, too slow for a five-day deadline. |

The author chose **A**. **Fallback:** if a spike shows ppt-master cannot produce a correct A0 portrait PPTX, switch to C, keeping the palette, fonts and assets, and tell the author.

## 7. Build decisions

- Files under `docs/poster/`: `build/` (scripts), the workspace under `docs/poster/projects/` (generated, not versioned, like the deck's), outputs `docs/poster/SoICT2026_ViPharmInd_poster.pptx` and `.pdf`.
- Canvas: SVG viewBox about 3179 × 4494 px (1 px = 1/96 in = 9,525 EMU), giving 841 × 1189 mm. The template for the round-trip is an A0-portrait copy of `docs/presentation/template.pptx` (same theme), or whatever ppt-master needs for a non-16:9 canvas.
- **First step is a spike**: one A0 SVG with a title, a native table and a native chart through the full pipeline, checking the PPTX slide size, fonts and chart scale, before the full poster is built.
- Fonts: it is unknown whether the organisers print the PDF or the PPTX, so **both must be safe to print**. The PDF embeds Poppins and IBM Plex Mono. The PPTX embeds them too (`pptx_embedded_fonts.py` or equivalent); proving this works is part of the spike, and failure to embed counts as a spike failure. Text boxes do not rely on auto-fit, and each leaves some slack so a substitute font would not overflow.
- The PDF is the reference file for the author's approval. Under approach A it is rendered from the SVG (as `docs/presentation/build/render_pdf.py` does, at A0 page size). Under fallback C it is exported from the PPTX with LibreOffice, with auto-fit off everywhere, and the PPTX is opened once in PowerPoint (by the author if no PowerPoint is reachable from WSL) to confirm it matches.
- Both files stay under 10 MB if possible (Google Form uploads are often capped at 10 MB): photos are downscaled to what A0 print needs (about 150 dpi at their printed size).
- Python is `/usr/bin/python3` (deps in `~/.local`), no extra virtualenvs.

## 8. Calls made without the author (check these)

- Hook example is golden item `e2e-ans-0072` ("Panadol đỏ") with the Qwen3.5-9B answer, not a "chữ Y" question, because no real item asks about "chữ Y". "Chữ Y" still appears in the nickname strip.
- Answers are shown as English renderings with the Vietnamese original small underneath, extending the author's rule for questions.
- Hook numbers: 2,409 mappings, 18× / 25×, 0.913 vs 0.923. The judge–refine 0.657 → 1.000 result sits in block 6.
- Retrieval shown as a seven-row table, not the cost scatter plots.
- Outputs not versioned, matching the deck.
- Fonts embedded in both files, because it is unknown which file the organisers print; the PDF is the approval reference.
- "Paper 1360" in the header; no logos.
- Files kept under 10 MB in case the form caps uploads.

## 9. Left to the builder

Exact geometry, column split and spacing; icon choices; chart styling within the deck's look; English wording of headings within the meaning given here; how much of the answer excerpt fits.

## 10. Verification

- Every number on the poster is matched against the `.tex` sources (same procedure as deck spec §9); the hook answer is matched against `answers.jsonl`.
- PPTX slide size and PDF page size are checked to be 841 × 1189 mm.
- The poster is rendered to PNG and inspected at full size and at about 10% (the "from 5 m" view) for overflow, clipping, overlaps and type below the minimum sizes.
- The quality gate and delivery check of ppt-master pass.
- Done when both files are in `docs/poster/` and the author has approved them; the author submits through the form before 2026-11-23.
