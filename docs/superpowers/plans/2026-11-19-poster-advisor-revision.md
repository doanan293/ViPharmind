# Poster Revision After the Advisor's Review: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revise the SoICT 2026 A0 poster so that the contributions are in the header, the pipeline is a full-width block right after the hook, the hook wording is cautious, and block 7 lists future work, all on one A0 page.

**Architecture:** All poster strings live in `docs/poster/build/content.py`. Layout lives in `build_poster.py`, helpers in `poster_lib.py`. `make.sh` builds the SVG, exports the PPTX and PDF, then runs every check and `test_poster_output.py` against the built files. Tests here are output tests: change the test, run `make.sh`, see it fail, change the build, run again.

**Tech Stack:** Python 3 at `/usr/bin/python3` (deps in `~/.local`), ppt-master round-trip scripts, pymupdf, python-pptx.

**Spec:** `docs/superpowers/specs/2026-11-19-poster-advisor-revision-design.md` (revises `docs/superpowers/specs/2026-11-18-soict-poster-design.md`)

## Global Constraints

- Every number on the poster comes from `docs/report/`. `check_numbers.py` must pass. No new numbers beyond those in the spec.
- Text rules (`check_poster.py`): no `;`, no `—`, no emoji, no banned phrases, no text below 29.33 px, no text wider than its group's `data-pptx-bounds`.
- Vietnamese text uses Montserrat (`P.VI_FAMILY`). English uses Poppins.
- Page is 3178.58 × 4493.86 px (841 × 1189 mm). Page margin `M = 90`.
- Do not name LactMed or AAP anywhere on the poster.
- Future work has exactly three items, with the wording from spec §4.
- Run everything with `/usr/bin/python3`. Build with `docs/poster/build/make.sh` from the repo root. It must end with `all checks passed`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Cards running past the page bottom.** The page has no slack. Every `*-card` group must end at least 90 px above the page bottom. Pinned by `test_cards_inside_page` (Task 4).
2. **Contribution labels too wide for the header cards.** `stat_card` does not wrap tuple labels. The fit check in `check_poster.py svg` catches this. Re-break lines if it fires, keeping the words.
3. **One-row pipeline node labels overflowing their slot** ("Hybrid search", "question + history"). The fit check catches this. Widen the diagram share (0.66 → 0.70) before changing text.
4. **Stale references to the removed content** (`HOOK["stats"]`, `TAKEAWAYS`, `pipeline-arrows` bent path, `resources-note`). `make.sh` fails on any of these. Task 1 and Task 3 update tests and `all_texts()`.
5. **Badge numbers out of reading order.** Pinned by `test_badges_follow_reading_order` (Task 2).

---

### Task 1: Contributions in the header and cautious hook wording

**Files:**
- Modify: `docs/poster/build/content.py` (`HOOK`, new `CONTRIBUTIONS`, `all_texts`)
- Modify: `docs/poster/build/poster_lib.py:170` (`stat_card`)
- Modify: `docs/poster/build/build_poster.py:94-131` (`header_block`)
- Test: `docs/poster/build/test_poster_output.py`

**Interfaces:**
- Produces: `content.CONTRIBUTIONS: list[tuple[str, str, tuple[str, str]]]`, one `(tag, value, (line1, line2))` per card. `poster_lib.stat_card(x, y, w, h, value, label, fill, tag: str | None = None) -> str`. `header_block()` still returns `(groups, bottom)`. Group ids become `contribution-0..2` (were `stat-0..2`).

- [ ] **Step 1: Update the tests**

In `test_hook_strings_in_pdf`, remove `"2,409"` from the list. That number now only appears in block 3, where `test_resources_and_pipeline_in_pdf` checks it. Add these tests:

```python
def test_contributions_in_header():
    text = pdf_text()
    for s in [
        "Contribution 1",
        "Contribution 2",
        "Contribution 3",
        "10,000",
        "97.5%",
        "0.913 vs 0.923",
        "open Qwen3.5-9B pipeline",
    ]:
        assert s in text, s
    assert "18× / 25×" not in text


def test_hook_wording_is_cautious():
    text = pdf_text()
    assert "it follows the national formulary and cites it" in text
    assert "dangerous" not in text
    assert "gets them right" not in text
    assert "judged severe harm" not in text
    assert "Contradicts the formulary" in text
```

- [ ] **Step 2: Run `docs/poster/build/make.sh`**

Expected: FAIL in `test_poster_output.py` on `test_contributions_in_header` (no "Contribution 1").

- [ ] **Step 3: Change `content.py`**

- `HOOK["heading"]` = `"Without documents, the model answers from memory. Grounded in official labelling, it follows the national formulary and cites it."`
- `HOOK["bad"]["verdict"]` = `"Contradicts the formulary"`
- Delete `HOOK["stats"]`.
- Add:

```python
CONTRIBUTIONS = [
    (
        "Contribution 1",
        "10,000",
        ("benchmark questions on a", "released Vietnamese corpus"),
    ),
    (
        "Contribution 2",
        "97.5%",
        ("relevant passage in top 10,", "retrieval vs cost compared"),
    ),
    (
        "Contribution 3",
        "0.913 vs 0.923",
        ("open Qwen3.5-9B pipeline", "vs Gemini 3.8 Flash"),
    ),
]
```

- Add `CONTRIBUTIONS` to the tuple walked in `all_texts()`.

- [ ] **Step 4: Add the `tag` parameter to `stat_card`**

When `tag` is set, draw it in `PUR`, bold, `T_SMALL`, centred, about 24 px below the card top. Centre the value-and-label block in the space under the tag. With `tag=None` the output is unchanged.

- [ ] **Step 5: Change `header_block`**

Loop over `C.CONTRIBUTIONS` instead of `C.HOOK["stats"]`. Use group ids `contribution-{i}`. Raise the card height `sh` from 225 to 265 so the tag fits. Return `sy + sh` as before.

- [ ] **Step 6: Run `docs/poster/build/make.sh`**

Expected: `all checks passed`. If `check_poster.py svg` reports text overflow in a `contribution-*` group, re-break that label's two lines without changing the words, then run again.

- [ ] **Step 7: Commit**

```bash
git add docs/poster/build/content.py docs/poster/build/poster_lib.py docs/poster/build/build_poster.py docs/poster/build/test_poster_output.py
git commit -m "feat(poster): contributions in the header, cautious hook wording"
```

---

### Task 2: Full-width pipeline in one row, with the design-principle panel

**Files:**
- Modify: `docs/poster/build/content.py` (`PIPELINE`)
- Modify: `docs/poster/build/build_poster.py:307-400` (`pipeline_block`), `:670-693` (`build`), and the `n` argument of every `block_heading` call
- Test: `docs/poster/build/test_poster_output.py`

**Interfaces:**
- Consumes: `header_block`, `hook_block` (unchanged signatures).
- Produces: `pipeline_block(x, y0, w) -> (groups, bottom)`, called with `w = CW`. Group ids: `pipeline-card`, `pipeline-heading`, `pipeline-node-{i}` for i in 0..6, `pipeline-arrows`, `pipeline-loop`, `pipeline-exits`, `pipeline-principle`. Badge numbers: hook 1, pipeline 2, resources 3, retrieval 4, grounding 5, steps 6, takeaways/future 7.

- [ ] **Step 1: Update the tests**

In `test_bent_arrows_leave_room_for_the_head`, check only `"pipeline-loop"`. In a single row, `pipeline-arrows` has no bent path. Add these helpers and tests:

```python
def bounds(gid: str) -> tuple[float, float, float, float]:
    root = ET.parse(SVG).getroot()
    for g in root.iter():
        if g.attrib.get("id") == gid:
            return tuple(float(v) for v in g.attrib["data-pptx-bounds"].split())
    raise AssertionError(f"no group {gid}")


def test_pipeline_is_full_width_after_hook():
    px, py, pw, ph = bounds("pipeline-card")
    _, hy, _, hh = bounds("hook-card")
    _, ry, _, _ = bounds("resources-card")
    assert pw > 2990, pw
    assert hy + hh < py < ry, (hy + hh, py, ry)
    tops = {round(bounds(f"pipeline-node-{i}")[1]) for i in range(7)}
    assert len(tops) == 1, tops  # one row


def test_pipeline_principle_panel():
    t = " ".join(group_text("pipeline-principle").split())
    assert "Is the evidence enough?" in t, t
    assert "Qwen3.5-9B runs every step" in t, t


def test_badges_follow_reading_order():
    for gid, n in [
        ("hook-heading", "1"),
        ("pipeline-heading", "2"),
        ("resources-heading", "3"),
        ("retrieval-heading", "4"),
        ("grounding-heading", "5"),
        ("steps-heading", "6"),
    ]:
        assert group_text(gid).split()[0] == n, (gid, group_text(gid)[:20])
```

- [ ] **Step 2: Run `docs/poster/build/make.sh`**

Expected: FAIL in `test_poster_output.py` on `test_pipeline_is_full_width_after_hook`.

- [ ] **Step 3: Add `PIPELINE["principle"]` to `content.py`**

Copy these three strings exactly as the spec gives them:

```python
"principle": [
    "Each model call answers one narrow question: Is this an attack? Is the evidence enough?",
    "Code runs the flow, caps the refine loop at 3 rounds and can switch any step off.",
    "Narrow decisions suit small models: the open Qwen3.5-9B runs every step, like Gemini 3.8 Flash.",
],
```

- [ ] **Step 4: Rewrite the layout of `pipeline_block`**

- **Nodes.** The diagram takes the left 66% of the inner width. The seven nodes sit in one row, `slot = diagram_w / 7`. Keep the existing node drawing (circle, icon, name, wrapped sub-label), with the last node in `P.PEACH`. Use group ids `pipeline-node-{i}`.
- **Arrows.** Draw a straight arrow between each pair of neighbouring nodes (marker `pa`).
- **Refine loop.** Keep the existing bent path from Judge (node 5) down, across and up to Hybrid search (node 3), plus the loop label. The last leg must be at least 50 px.
- **Exits line.** Put it under the loop, within the diagram width.
- **Principle panel.** It sits right of the diagram, 50 px gap, filling the remaining inner width. Draw a `P.LAV` rounded rect (radius 36) with the three `principle` lines as `P.para` at `T_BODY`, 18 px between items. Group id `pipeline-principle`.
- **Card height.** The card bottom is the lower of the diagram and the panel, plus `PAD`.

- [ ] **Step 5: Reflow `build()` and renumber the badges**

- **Order.** Header → hook → `pipeline_block(M, y, CW)` → `GAP` → two columns.
  - Left column: `resources_block`, `retrieval_block`.
  - Right column: `grounding_block`, `steps_block`.
- **Block 7.** Takeaways stays for now, under steps in the right column. Pass `bottom = max(left_bottom, its own content bottom)`. Task 3 replaces it.
- **Badges.** Set the `block_heading` numbers to: resources 3, retrieval 4, grounding 5, steps 6, takeaways 7.

- [ ] **Step 6: Run `docs/poster/build/make.sh`**

Expected: `all checks passed`. No page-fit check exists until Task 4, so the bottom may run off the page for now. If ppt-master's quality checker rejects elements outside the page, apply fallback (a) from Task 4 Step 5 now. The new tests pass, and `check_poster.py svg` reports no text overflow in `pipeline-*` groups.

- [ ] **Step 7: Commit**

```bash
git add docs/poster/build/content.py docs/poster/build/build_poster.py docs/poster/build/test_poster_output.py
git commit -m "feat(poster): full-width one-row pipeline with the design principle"
```

---

### Task 3: Future work replaces the takeaways list

**Files:**
- Modify: `docs/poster/build/content.py` (`TAKEAWAYS` → `FUTURE`, `all_texts`)
- Modify: `docs/poster/build/build_poster.py:622-667` (`takeaways_block` → `future_block`), `build`
- Test: `docs/poster/build/test_poster_output.py`

**Interfaces:**
- Consumes: column bottoms from `build()` (Task 2).
- Produces: `future_block(x, y0, w, min_bottom) -> (groups, bottom)`, where `bottom = max(content bottom, min_bottom)`. Group ids: `future-card`, `future-heading`, `future-{i}`, `future-footer`, `future-qr`. The badge is 7.

- [ ] **Step 1: Update the tests**

Rename `test_takeaways_and_links_in_pdf` to `test_future_work_and_links_in_pdf`. Replace `"Self-hosted retrieval is enough."` with the three checks below, and keep the funding and email checks:

```python
("linear-algebraic logic programming",)
("to cut cost and latency",)
("ReAct agent",)
```

Then add:

```python
def test_takeaways_list_removed():
    text = pdf_text()
    assert "Takeaways" not in text
    assert "Self-hosted retrieval is enough." not in text
    assert "Real user questions" not in text


def test_future_badge_is_seven():
    assert group_text("future-heading").split()[0] == "7"
```

- [ ] **Step 2: Run `docs/poster/build/make.sh`**

Expected: FAIL in `test_poster_output.py` on `test_future_work_and_links_in_pdf`.

- [ ] **Step 3: Replace `TAKEAWAYS` with `FUTURE` in `content.py`**

Use the exact copy from the spec. Update `all_texts()` to walk `FUTURE` instead of `TAKEAWAYS`.

```python
FUTURE = {
    "heading": "Future work",
    "items": [
        "Check answers against specialist sources and against explicit rules in "
        "linear-algebraic logic programming, and flag conflicts with the formulary.",
        "A decision model that picks the steps each question needs, to cut cost and latency.",
        "A comparison with a ReAct agent that plans its own tool calls.",
    ],
}
```

- [ ] **Step 4: Write `future_block`**

Base it on `takeaways_block`, with these changes:
- **Markers.** Each item gets a purple bold number marker (`"1"`, `"2"`, `"3"`) instead of the ✓.
- **Layout.** Keep the QR stack on the right and the email and funding footer under the items.
- **Bottom.** Return `max(content bottom, min_bottom)`, and drop the overflow assert.
- **In `build()`.** Call it under `steps_block` in the right column, with `min_bottom = left column bottom`.
- **Cleanup.** Delete `takeaways_block`.

- [ ] **Step 5: Run `/usr/bin/python3 docs/poster/build/build_poster.py`, then `docs/poster/build/make.sh`**

Expected: `build_poster.py` prints the column bottoms, and `make.sh` ends with `all checks passed`.

- [ ] **Step 6: Commit**

```bash
git add docs/poster/build/content.py docs/poster/build/build_poster.py docs/poster/build/test_poster_output.py
git commit -m "feat(poster): future work replaces the takeaways list"
```

---

### Task 4: Compact blocks 3 and 4, fit the page, deliver

**Files:**
- Modify: `docs/poster/build/content.py` (`RESOURCES["groups_note"]` removed)
- Modify: `docs/poster/build/build_poster.py` (`resources_block`, `retrieval_block`, and the fallback constants if needed)
- Test: `docs/poster/build/test_poster_output.py`
- Outputs: `docs/poster/SoICT2026_ViPharmInd_poster.pptx`, `docs/poster/SoICT2026_ViPharmInd_poster.pdf`

**Interfaces:**
- Consumes: everything above. The group ids `resources-note` and `retrieval-lesson-1` disappear, and `retrieval-lessons` replaces `retrieval-lesson-{i}`.

- [ ] **Step 1: Add the fit test**

```python
def test_cards_inside_page():
    root = ET.parse(SVG).getroot()
    page_h = float(root.attrib["viewBox"].split()[3])
    for g in root.iter():
        gid = g.attrib.get("id", "")
        if gid.endswith("-card"):
            _, y, _, h = (float(v) for v in g.attrib["data-pptx-bounds"].split())
            assert y + h <= page_h - 90 + 0.5, (gid, round(y + h), round(page_h - 90))
```

- [ ] **Step 2: Run `docs/poster/build/make.sh`**

Expected: FAIL on `test_cards_inside_page` or earlier on the page overflow, naming the lowest card. If it already passes, keep the compaction steps anyway: the spec asks for them.

- [ ] **Step 3: Compact block 3 (resources)**

- Delete `RESOURCES["groups_note"]` and its drawing.
- Reduce the spacing between key-value groups from 24 to 14 px.

- [ ] **Step 4: Compact block 4 (retrieval)**

Draw both `RETRIEVAL_LESSONS` inside one `P.LAV` box, as two paragraphs with 14 px between them. Group id `retrieval-lessons`.

- [ ] **Step 5: Fit loop**

Run `/usr/bin/python3 docs/poster/build/build_poster.py` and read the printed bottoms. While the lowest card ends above `page_h - 90`, apply the spec's fallback cuts in order, one at a time, re-running after each:
- (a) `GAP` 40 → 30 and `PAD` 50 → 44.
- (b) Move the pipeline exits line into the principle panel as a fourth line.
- (c) QR codes 165 → 150 px.
- (d) Drop the `+ Qwen3-Reranker-8B` row from `RETRIEVAL_ROWS`. Also change `test_retrieval_table_row` to expect `len(rows) == 7`.

Note each cut used for the final report. If all four are used and the page still overflows, stop and report the remaining overflow in px. Do not shrink text.

- [ ] **Step 6: Run `docs/poster/build/make.sh /tmp/claude-1000/-home-andv-personal-vipharmind-camera-ready/2901d07e-c145-48de-9f25-d69856841928/scratchpad/lo`**

Expected: `all checks passed`, then `rendered: …`. The LibreOffice render of the PPTX lands in that folder.

- [ ] **Step 7: Look at the result**

```bash
pdftoppm -r 18 -png docs/poster/SoICT2026_ViPharmInd_poster.pdf /tmp/claude-1000/-home-andv-personal-vipharmind-camera-ready/2901d07e-c145-48de-9f25-d69856841928/scratchpad/small
pdftoppm -r 60 -png docs/poster/SoICT2026_ViPharmInd_poster.pdf /tmp/claude-1000/-home-andv-personal-vipharmind-camera-ready/2901d07e-c145-48de-9f25-d69856841928/scratchpad/big
```

Open both PNGs and `lo-1.png`. Check for:
- overlaps or clipping, especially the contribution cards against the title and mascot, the one-row pipeline labels, and the loop arrow
- an empty band at the bottom of either column
- reading order 1 → 7

Fix what you find and re-run Step 6.

- [ ] **Step 8: Commit**

```bash
git add docs/poster/build/ docs/poster/SoICT2026_ViPharmInd_poster.pptx docs/poster/SoICT2026_ViPharmInd_poster.pdf
git commit -m "feat(poster): compact resources and retrieval, fit the revised layout"
```
