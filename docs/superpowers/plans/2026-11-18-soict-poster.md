# SoICT 2026 A0 poster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SoICT 2026 poster as one A0 portrait page, delivered as an editable PPTX and a print-ready PDF, in style A (soft pastel, pill mascot), with every number taken from the paper.

**Architecture:** Same pipeline as the deck. `make_template.py` turns `docs/presentation/template.pptx` into an A0-portrait one-slide template. ppt-master's `pptx_to_svg.py --roundtrip` turns that template into a workspace. `build_poster.py` writes one SVG page into the workspace, reusing `docs/presentation/build/lib.py` and a new `poster_lib.py` for style A. ppt-master exports the native PPTX, and `render_pdf.py` prints the same SVG to an A0 PDF with Chromium. `check_poster.py` checks the SVG, PPTX and PDF against the spec.

**Render dir:** `<render_dir>` is any scratch folder outside the repo, e.g. the session scratchpad.

**Tech Stack:** Python 3.12 at `/usr/bin/python3` (deps in `~/.local`: python-pptx 1.0.2, pymupdf, pypdf, playwright, Pillow), ppt-master scripts in `.claude/skills/ppt-master/scripts`, LibreOffice `soffice` for PNG previews.

**Spec:** `docs/superpowers/specs/2026-11-18-soict-poster-design.md`. The deck spec it inherits rules from is `docs/superpowers/specs/2026-11-04-soict-presentation-design.md`.

## Global Constraints

- Page: A0 portrait, 841 × 1189 mm (±1 mm), in both files. SVG viewBox `0 0 3179 4494` (1 px = 1/96 in = 9,525 EMU). PPTX slide size 30,276,000 × 42,804,000 EMU. PDF page 2383.9 × 3370.4 pt.
- Numbers only from `docs/report/` (tables, then figure coordinates, then prose). Examples only from `pharma-lab/data/`. No new numbers.
- Every quoted model answer comes from a released run, and every leaflet quote is verbatim from the corpus. The Yumangel card is labelled as leaflet text, never as a model answer.
- English everywhere. Vietnamese only as a small italic line under each Vietnamese question or quote.
- Type sizes (px; pt = px × 0.75): title about 133, authors about 53, hook question and big numbers 67–80, block headings about 64, body, table cells and chart labels ≥ 37, Vietnamese lines and footnotes ≥ 29. **No text below 29 px.**
- Text style: no semicolon in any poster string, no em dash (—) used as a connector, no emoji (✓ ✗ ✉ → ↓ ↺ ≤ × are allowed symbols), none of the phrases "big lever", "heavy lifting", "k = 2 works".
- Deck editorial rules: no T4, llama.cpp, "thinking", Qdrant, LangGraph, item ids, "Paper Table N", photo or template credit.
- Author line "Van-An Doan · Tuan Quoc Nguyen ✉" (paper spelling). Header ends "SoICT 2026 · Paper 1360". No logos.
- Style A palette: background gradient `#F3EFFF` → `#FFF6EC`; cards white with large rounded corners and a faint indigo shadow; headings `#0C0A9E`; tags and number badges `#8208D5`; fills lavender `#E6E4FD`, peach `#FFE9CF`, mint `#DFF3EA`, coral `#FFE3DE`; Gemini bars periwinkle `#8F8CF0`, Qwen bars `#FFB27A`; with / without bars `#7FD1AE` / `#E3E1EE`. Body font Poppins.
- Each file ≤ 10 MB. Photos downscaled to about 150 dpi at printed size.
- Run Python with `/usr/bin/python3`. No virtualenvs, no pytest (not installed): tests are plain scripts with `assert`, exit code 0 on success.
- Generated workspace `docs/poster/projects/` and the outputs `docs/poster/SoICT2026_ViPharmInd_poster.pptx` / `.pdf` are not versioned (`docs/poster/.gitignore`), as for the deck.
- Commits carry no Claude attribution line (author's rule).

## Review Focus

1. **Text overflowing its card at A0.** A reader expects every line inside its card, also in PowerPoint where line breaks may differ. `check_poster.py` checks that each text's estimated width fits its group's `data-pptx-bounds` (Task 4), and Task 8 opens the PPTX render to compare with the PDF.
2. **Fonts missing on the organisers' machine.** A reader expects the same look whichever file is printed. Task 2 asserts Poppins is embedded in the PPTX and the PDF.
3. **The negative bar (−0.060) drawn above the axis or clipped.** Task 7 asserts the bar's y range lies below the zero line in the SVG and checks the native chart's value is −0.06.
4. **A number that drifts from the paper while editing.** Task 3's number check runs in every later task's verification.
5. **Vietnamese diacritics broken in PPTX or PDF** (e.g. "ữ", "ỏ" rendered as boxes). Task 5 asserts the extracted PDF text contains "Thuốc bao tử chữ Y" and "Panadol đỏ" exactly.

---

### Task 1: A0 template and pipeline spike

**Files:**
- Create: `docs/poster/.gitignore`, `docs/poster/build/make_template.py`, `docs/poster/build/build_poster.py`, `docs/poster/build/make.sh`, `docs/poster/build/check_poster.py`, `docs/poster/build/test_check_poster.py`

**Interfaces:**
- Consumes: `docs/presentation/build/lib.py` (`text`, `mtext`, `rect`, `group`, `table_marker`, `chart_marker`, colour constants), via `sys.path.insert(0, <repo>/docs/presentation/build)`.
- Produces:
  - `make_template.py`: writes `docs/poster/build/template-a0.pptx` (not versioned) with one slide, size 30,276,000 × 42,804,000 EMU, theme and embedded fonts kept from the deck template, and no visible layout or master decoration on the slide.
  - `build_poster.py`: constants `W = 3179`, `H = 4494`, `WS = docs/poster/projects/poster_a0`, `SVG_DIR = WS / "authoring-svg-flat"`; `page(groups: list[str], defs: str = "") -> None` writes `SVG_DIR / "poster.svg"` from the template slide SVG, as `page()` does in `docs/presentation/build/build_deck.py:75`, and writes `WS / "page_plan.json"` with one page; `main()`.
  - `make.sh [render_dir]`: builds the template if missing, the workspace if missing, runs `build_poster.py`, the stamp / authoring-view / quality-checker / `svg_to_pptx.py --roundtrip --native-charts-and-tables` steps exactly as `docs/presentation/build/make.sh`, copies the export to `docs/poster/SoICT2026_ViPharmInd_poster.pptx`, and with `render_dir` renders a PNG with `soffice` + `pdftoppm -r 20`. Resolve the skill path from the repo root (`$PRES/../..`), not from `docs/`.
  - `check_poster.py`: `check_svg(path) -> list[str]`, `check_pptx(path) -> list[str]`, `check_pdf(path) -> list[str]`, each returning problem messages (empty list = pass); CLI `check_poster.py svg|pptx|pdf <path>` prints problems and exits 1 if any.

- [ ] **Step 1: Write `test_check_poster.py` with failing checks**

Build tiny fixtures in a temp dir and assert:
```python
assert check_svg(svg_ok) == []  # viewBox 0 0 3179 4494, one 40 px text
assert any("viewBox" in p for p in check_svg(svg_169))  # viewBox 0 0 960 540
assert any("29" in p for p in check_svg(svg_small))  # a 20 px text
assert any(";" in p for p in check_svg(svg_semicolon))  # text "a; b"
assert any("emoji" in p for p in check_svg(svg_emoji))  # text "💡 tip"
assert check_svg(svg_symbols) == []  # text "✓ ✗ ✉ → ↓ ≤ ×"
assert any("slide size" in p for p in check_pptx(pptx_169))  # python-pptx default deck
```
`check_pptx` also checks one slide, `ppt/fonts/` contains a Poppins part, file ≤ 10 MB. `check_pdf` checks one page of 2383.9 × 3370.4 pt (±3), Poppins among embedded fonts (pymupdf `get_fonts`), file ≤ 10 MB.

- [ ] **Step 2: Run it and see it fail**

Run: `/usr/bin/python3 docs/poster/build/test_check_poster.py`
Expected: ImportError or AssertionError.

- [ ] **Step 3: Implement `check_poster.py`**

Emoji test: any code point in U+1F000–U+1FAFF or U+2600–U+27BF except ✓ (U+2713), ✗ (U+2717), ✉ (U+2709). Banned phrases from Global Constraints are reported by `check_svg` too.

- [ ] **Step 4: Run the test and see it pass**

Run: `/usr/bin/python3 docs/poster/build/test_check_poster.py`
Expected: exit 0.

- [ ] **Step 5: Implement `make_template.py`, `build_poster.py` (spike page) and `make.sh`**

The spike page has: the style A gradient background (`linearGradient` in `defs`), one rounded white card with a soft shadow, the title text at 133 px, one native table via `table_marker` (3 × 3, any spike values) and one native bar chart via `chart_marker` with a negative value, both following `build_deck.py` `p08()` and `g_grounding()` payloads. If the deck template's layouts carry decoration that cannot be removed in the SVG with the `drop`/`keep` logic of `page()`, strip it in `make_template.py`.

- [ ] **Step 6: Run the spike and check it**

Run: `bash docs/poster/build/make.sh <render_dir> && /usr/bin/python3 docs/poster/build/check_poster.py pptx docs/poster/SoICT2026_ViPharmInd_poster.pptx`
Expected: `[POSTFLIGHT] status=passed` (or `passed-with-warnings` with `quality_gate=passed`), the check prints nothing and exits 0, and the rendered PNG shows gradient, card, title, table and chart at full width with nothing left over from the template. **If the slide size or native objects are wrong and cannot be fixed in this task, stop and report: the spec's fallback (approach C) needs the author's go-ahead.**

- [ ] **Step 7: Commit**

```bash
git add docs/poster/.gitignore docs/poster/build/
git commit -m "feat(poster): A0 template and build pipeline spike"
```

### Task 2: Fonts embedded in PPTX and PDF

**Files:**
- Create: `docs/poster/build/render_pdf.py`
- Modify: `docs/poster/build/make.sh`, and `make_template.py` if fonts do not travel

**Interfaces:**
- Consumes: `check_pptx`, `check_pdf` (Task 1), `WS`, `SVG_DIR` (Task 1).
- Produces: `render_pdf.py` writes `docs/poster/SoICT2026_ViPharmInd_poster.pdf` from `SVG_DIR / "poster.svg"` with Playwright Chromium, page size 841 × 1189 mm, background printed, fonts from `docs/presentation/fonts/` loaded with `@font-face` so they embed; `make.sh` runs it after the export.

- [ ] **Step 1: Run the checks on the spike outputs and record which fail**

Run: `/usr/bin/python3 docs/poster/build/check_poster.py pptx docs/poster/SoICT2026_ViPharmInd_poster.pptx`
Expected now: a Poppins problem only if ppt-master dropped the template's embedded fonts (the template has `ppt/fonts/Poppins-regular.fntdata`).

- [ ] **Step 2: Implement `render_pdf.py` and, if needed, carry the template's `ppt/fonts/*.fntdata` parts (Poppins regular and bold) into the export through ppt-master's embedded-font sidecar (`pptx_embedded_fonts.py`, manifest `native-payloads/embedded-fonts/manifest.json`)**

- [ ] **Step 3: Verify both files**

Run: `bash docs/poster/build/make.sh && /usr/bin/python3 docs/poster/build/check_poster.py pptx docs/poster/SoICT2026_ViPharmInd_poster.pptx && /usr/bin/python3 docs/poster/build/check_poster.py pdf docs/poster/SoICT2026_ViPharmInd_poster.pdf`
Expected: both exit 0. If the PPTX cannot embed Poppins, stop and report (spec §7 makes this a spike failure).

- [ ] **Step 4: Commit**

```bash
git add docs/poster/build/
git commit -m "feat(poster): A0 PDF render and embedded fonts"
```

### Task 3: Poster content and number check

**Files:**
- Create: `docs/poster/build/content.py`, `docs/poster/build/check_numbers.py`, `docs/poster/build/test_check_numbers.py`

**Interfaces:**
- Produces:
  - `content.py`: every string and number shown on the poster, as module constants grouped by block (`HEADER`, `HOOK`, `RESOURCES`, `PIPELINE`, `RETRIEVAL_ROWS`, `GROUNDING`, `STEPS`, `TAKEAWAYS`, `LINKS`). Values and wording exactly as spec §5. Quoted answers copied from `pharma-lab/data/evaluation/e2e/runs/*-cr/{closed-book,full}/answers.jsonl` (item `e2e-ans-0260`, and `e2e-ans-0072` if used), the leaflet quote from the Yumangel section of `pharma-lab/data/corpus/rag-final/sections.jsonl`.
  - `check_numbers.py`: `numbers_in(texts: list[str]) -> set[str]`; `unmatched(numbers: set[str], sources: list[Path], allow: set[str]) -> set[str]`; CLI `check_numbers.py <poster.svg>` reads all `<text>` strings and fails on any number not found in `docs/report/{tables,figures,sections}/*.tex`. `ALLOW` lists each exception with a comment (block badges 1–7, "1360", "2026", "841", "1189", model-name digits such as "3.8", "9B", "4B", "8B", "3.5", drug doses in the quoted leaflet / answers, "−1", "+½", "0", axis ticks).

- [ ] **Step 1: Write `test_check_numbers.py`**

```python
assert numbers_in(["0.923 vs 0.913", "18× fewer", "97.5%"]) == {
    "0.923",
    "0.913",
    "18",
    "97.5",
}
assert unmatched({"0.923", "0.999"}, REPORT_TEX, set()) == {"0.999"}
assert unmatched({"24,946"}, REPORT_TEX, set()) == set()  # LaTeX writes 24{,}946
assert unmatched({"−0.060"}, REPORT_TEX, set()) == set()  # LaTeX writes $-$0.060
```

- [ ] **Step 2: Run it and see it fail**

Run: `/usr/bin/python3 docs/poster/build/test_check_numbers.py`
Expected: ImportError.

- [ ] **Step 3: Implement `check_numbers.py` and `content.py`**

Normalise LaTeX before matching (`{,}` → `,`, `$-$` and `−` → `-`, drop `\%`). For "18×" and "25×" the source is the prose "eighteen- to twenty-five-fold" plus 18.3% → 1.0% and 30.6% → 1.2%: allow-list them with that comment.

- [ ] **Step 4: Run the tests and check `content.py` against the paper**

Run: `/usr/bin/python3 docs/poster/build/test_check_numbers.py && /usr/bin/python3 -c "import sys; sys.path.insert(0,'docs/poster/build'); import content"`
Expected: exit 0 for both.

- [ ] **Step 5: Commit**

```bash
git add docs/poster/build/content.py docs/poster/build/check_numbers.py docs/poster/build/test_check_numbers.py
git commit -m "feat(poster): poster content and number check against the paper"
```

### Task 4: Style A kit

**Files:**
- Create: `docs/poster/build/poster_lib.py`
- Modify: `docs/poster/build/check_poster.py` (text-fit check), `docs/poster/build/test_check_poster.py`

**Interfaces:**
- Consumes: `lib.py` primitives.
- Produces in `poster_lib.py` (all return SVG strings, coordinates in poster px):
  - palette constants from Global Constraints; `GRAD_DEFS: str` (background gradient and card shadow filter)
  - `background() -> str`
  - `soft_card(x, y, w, h, fill="#FFFFFF", r=48) -> str`
  - `badge(cx, cy, n: int) -> str` (purple circle with the block number)
  - `block_heading(x, y, w, n: int, text: str) -> tuple[str, float]` (badge + wrapped heading at 64 px; returns SVG and the y below it)
  - `bubble(x, y, w, en: str, vi: str, fill, tail: str = "left") -> tuple[str, float]`
  - `verdict_card(x, y, w, kind: str, label: str, en: str, vi: str, verdict: str) -> tuple[str, float]` (`kind` is "bad" with coral fill and red text or "good" with mint fill and green text)
  - `stat_card(x, y, w, h, value: str, label: str, fill) -> str`
  - `mascot(x, y, w, pose: str = "wave") -> str` (pill: white and lavender halves, indigo outline, eyes, smile, pink cheeks; the mockup in `.superpowers/brainstorm/288287-1794985632/content/full-content-v3.html` is the reference)
  - `wrap(text: str, size: float, width: float) -> list[str]` (greedy wrap using a Poppins average-width estimate; used by every multi-line text)
- `check_svg` gains a fit check: for each `<g data-pptx-bounds>`, every `<text>` inside has estimated width ≤ the group width.

- [ ] **Step 1: Add a failing fit test to `test_check_poster.py`**

```python
assert any("overflow" in p for p in check_svg(svg_long_text_in_narrow_group))
assert check_svg(svg_short_text_in_wide_group) == []
```

- [ ] **Step 2: Run it and see it fail**

Run: `/usr/bin/python3 docs/poster/build/test_check_poster.py`
Expected: AssertionError on the overflow case.

- [ ] **Step 3: Implement the fit check and `poster_lib.py`; make the spike page in `build_poster.py` a style sheet that shows every component once**

- [ ] **Step 4: Verify**

Run: `/usr/bin/python3 docs/poster/build/test_check_poster.py && bash docs/poster/build/make.sh <render_dir> && /usr/bin/python3 docs/poster/build/check_poster.py svg docs/poster/projects/poster_a0/authoring-svg-flat/poster.svg`
Expected: exit 0, and the PNG shows the components in style A, matching the mockup's look.

- [ ] **Step 5: Commit**

```bash
git add docs/poster/build/
git commit -m "feat(poster): style A components and text-fit check"
```

### Task 5: Header and hook (block 1)

**Files:**
- Modify: `docs/poster/build/build_poster.py`
- Modify: `docs/poster/build/test_check_poster.py` (diacritics test)

**Interfaces:**
- Consumes: `content.HEADER`, `content.HOOK`, `poster_lib.*`, images copied into `WS / "images"` (Panadol Extra, Yumangel, Phosphalugel thumbnails from `docs/presentation/assets-src/`, downscaled per Global Constraints).
- Produces: `header_block() -> tuple[str, float]`, `hook_block(y: float) -> tuple[str, float]` (SVG and bottom y). Layout per spec §5.1: left half before/after metformin, right half nickname → Yumangel leaflet card plus two small cards, three stat cards across the full width.

- [ ] **Step 1: Add a failing PDF text test**

```python
text = pdf_text(POSTER_PDF)  # pymupdf page.get_text()
for s in [
    "Thuốc bao tử chữ Y uống trước hay sau ăn?",
    "Đang cho con bú dùng metformin có sao không?",
    "Yumangel leaflet",
    "Contradicts the formulary",
    "2,409",
    "0.913 vs 0.923",
]:
    assert s in text, s
assert (
    "Qwen3.5-9B" not in hook_leaflet_card_text
)  # the leaflet card is not a model answer
```

- [ ] **Step 2: Run it and see it fail**

Expected: AssertionError on the first missing string.

- [ ] **Step 3: Implement `header_block` and `hook_block`**

- [ ] **Step 4: Verify**

Run: `bash docs/poster/build/make.sh <render_dir> && /usr/bin/python3 docs/poster/build/test_check_poster.py && /usr/bin/python3 docs/poster/build/check_poster.py svg docs/poster/projects/poster_a0/authoring-svg-flat/poster.svg && /usr/bin/python3 docs/poster/build/check_numbers.py docs/poster/projects/poster_a0/authoring-svg-flat/poster.svg`
Expected: all exit 0; the PNG shows the title as the largest text and the hook directly under it.

- [ ] **Step 5: Commit**

```bash
git add docs/poster/build/
git commit -m "feat(poster): header and before/after hook"
```

### Task 6: Resources and pipeline (blocks 2 and 3)

**Files:**
- Modify: `docs/poster/build/build_poster.py`

**Interfaces:**
- Consumes: `content.RESOURCES`, `content.PIPELINE`, `poster_lib.*`, `lib.icon` (Phosphor duotone icons, as deck slide 7).
- Produces: `resources_block(x, y, w) -> tuple[str, float]`, `pipeline_block(x, y, w) -> tuple[str, float]`. Resources: corpus, enrichment, a stacked bar of the six benchmark groups with widths proportional to 5,000 / 2,500 / 1,000 / 500 / 500 / 500, golden set. Pipeline: icon nodes user → guard → rephrase → hybrid search → rerank → judge → answer, the refine loop (≤ 3 rounds) and the guard exits, the two-setting line.

- [ ] **Step 1: Add assertions to the PDF text test**

```python
for s in [
    "24,946",
    "13,790",
    "11,031",
    "5,000",
    "2,500",
    "420",
    "≤ 3",
    "RRF k = 2",
    "Code controls the flow, and each model call makes one small decision",
]:
    assert s in text, s
```

- [ ] **Step 2: Run it and see it fail**
- [ ] **Step 3: Implement both blocks**
- [ ] **Step 4: Verify** with the same command as Task 5 Step 4. Expected: all exit 0; blocks 2 and 3 sit side by side under the hook.
- [ ] **Step 5: Commit**

```bash
git add docs/poster/build/build_poster.py docs/poster/build/test_check_poster.py
git commit -m "feat(poster): resources and pipeline blocks"
```

### Task 7: Retrieval, grounding and per-step results (blocks 4, 5, 6)

**Files:**
- Modify: `docs/poster/build/build_poster.py`, `docs/poster/build/test_check_poster.py`

**Interfaces:**
- Consumes: `content.RETRIEVAL_ROWS`, `content.GROUNDING`, `content.STEPS`, `lib.table_marker`, `lib.chart_marker`, `poster_lib.*`.
- Produces: `retrieval_block(x, y, w)`, `grounding_block(x, y, w)`, `steps_block(x, y, w)`, each `-> tuple[str, float]`.
  - Retrieval: native table (7 rows × Method, Cost, Hit@10, Hit@30, nDCG@10), pipeline rows (Hybrid RRF k = 2, + Qwen3-Reranker-4B) in peach; the two lessons from spec §5.4 verbatim in meaning.
  - Grounding: native clustered bar chart, categories Closed-book / One-step RAG / Full agent, series Gemini 3.8 Flash (0.268, 0.816, 0.923) and Qwen3.5-9B (−0.060, 0.792, 0.913), axis −0.2 to 1.0; the scoring note; the hallucination line.
  - Steps: four rows of paired bars (without in `#E3E1EE`, with in `#7FD1AE`), values and labels from spec §5.6, the p = 0.056 row marked borderline; the Concat line.

- [ ] **Step 1: Add failing tests**

```python
chart = native_chart_values(
    POSTER_PPTX
)  # python-pptx: slide.shapes → chart.plots[0].series
assert chart["Qwen3.5-9B"] == [-0.06, 0.792, 0.913]
assert chart["Gemini 3.8 Flash"] == [0.268, 0.816, 0.923]
table = native_table_cells(POSTER_PPTX)
assert ["+ Qwen3-Reranker-4B", "4.0/s", "97.5", "99.2", "0.859"] in table
assert "k = 2 gives the best Hit@10 (95.9) and Hit@30 (99.2) before reranking" in text
assert "wrong −1" in text
```
Also assert in the SVG fallback that the −0.060 bar's top y equals the zero line's y (it hangs below the axis).

- [ ] **Step 2: Run them and see them fail**
- [ ] **Step 3: Implement the three blocks**, following `build_deck.py` `g_grounding()` (line 1218) for the chart payload and `p08()` (line 1041) for the table payload.
- [ ] **Step 4: Verify** with the Task 5 Step 4 command. Expected: all exit 0; the two columns end at about the same height.
- [ ] **Step 5: Commit**

```bash
git add docs/poster/build/build_poster.py docs/poster/build/test_check_poster.py
git commit -m "feat(poster): retrieval table, grounding chart and per-step bars"
```

### Task 8: Takeaways, final layout and delivery check

**Files:**
- Modify: `docs/poster/build/build_poster.py`, `docs/poster/build/make.sh`

**Interfaces:**
- Consumes: `content.TAKEAWAYS`, `content.LINKS`, QR images (`qr-github.png`, `qr-kaggle.png`), everything above.
- Produces: `takeaways_block(y) -> tuple[str, float]`; the final `poster.svg`; both deliverables in `docs/poster/`; `make.sh` ends by running all checks (`test_check_poster.py`, `test_check_numbers.py`, `check_poster.py svg|pptx|pdf`, `check_numbers.py`) and fails if any fails.

- [ ] **Step 1: Add failing tests**

```python
for s in [
    "T2025-PC-019",
    "an.dv252778m@sis.hust.edu.vn",
    "tuannq@soict.hust.edu.vn",
    "template-generated questions",
    "a single pharmacist",
]:
    assert s in text, s
assert qr_decodes(POSTER_PDF) == {
    "https://github.com/doanan293/ViPharmind/tree/v1.1.0",
    "https://www.kaggle.com/datasets/doanvanan0209/vipharma-rag",
}
```
`qr_decodes` renders the PDF at 100 dpi with pymupdf and decodes with `cv2.QRCodeDetector` if OpenCV is in `~/.local`; if not, compare the embedded images byte-for-byte with `docs/presentation/assets-src/qr-*.png` instead.

- [ ] **Step 2: Run them and see them fail**
- [ ] **Step 3: Implement `takeaways_block`, balance the layout so the page has no large empty band, and add the check chain to `make.sh`**
- [ ] **Step 4: Full build and visual check**

Run: `bash docs/poster/build/make.sh <render_dir>`
Expected: every check passes; `ls -l docs/poster/*.pptx docs/poster/*.pdf` shows both ≤ 10 MB. Open three images and inspect: the PDF rendered at 20 dpi (photo view: title, hook and headings readable), at 100 dpi (no overlap, clipping or overflow), and the PPTX rendered by `soffice` (same layout as the PDF, allowing LibreOffice's known sideways shift of auto-fit boxes).

- [ ] **Step 5: Commit**

```bash
git add docs/poster/build/
git commit -m "feat(poster): takeaways, links and delivery checks"
```

- [ ] **Step 6: Hand the two files to the author for approval** (PDF is the reference). The author submits them through the organisers' form before 2026-11-23.
