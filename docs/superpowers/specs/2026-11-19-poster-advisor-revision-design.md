# Poster revision after the advisor's review: design

Date: 2026-11-19 · Revises `2026-11-18-soict-poster-design.md` · Deadline unchanged: **2026-11-23**.

## 1. Intent

The advisor reviewed the A0 poster and asked for three things:

1. "Phần 3" (the pipeline block) should get more weight, and the main contributions must be clear.
2. Add some future work.
3. Be careful with the first block: a RAG answer can follow the documents and still differ from more reliable specialist knowledge. The advisor only asked us to consider this, so the author wants caution, not a rework.

Point 3 hits the metformin example directly. The closed-book Gemini answer ("can use metformin while breastfeeding", citing AAP) matches what specialist lactation sources commonly say. The National Drug Formulary is more cautious, and our judge grades against the formulary. So the poster must not call that answer "dangerous" or say the pipeline "gets it right" in a clinical sense. What the pipeline does is follow the formulary and cite it.

## 2. Goals, non-goals, anti-goals

**Goals**
- A reader sees the three contributions in the header row, and the pipeline block is the widest, most prominent block right after the hook.
- The hook keeps the metformin example (author's decision) with wording that claims agreement with the formulary, not clinical correctness.
- Future work appears on the poster, including the advisor's concern.

**Non-goals**
- No new example, experiment or number. Every number stays from `docs/report/`.
- No limits line (author's earlier decision). The advisor's concern goes in as future work.

**Anti-goals**
- Presenting the pipeline as a new RAG architecture. The paper says it combines established techniques. The contribution is the design principle for small models and the step-by-step evaluation.
- Naming outside sources (LactMed, AAP) on the poster. The paper does not cite them.
- All anti-goals of the original spec §2 still apply (exact numbers, no AI-sounding text, no semicolons joining claims, no em dashes as connectors).

## 3. Approaches

| Approach | Trade-off |
|---|---|
| **A. Contributions strip + full-width pipeline (chosen by the author)** | The contributions come right after the hook, and the pipeline is promoted to full width. Needs a reshuffle: block 2 and the hook lose some height to make room. |
| B. Keep the layout, rewrite content only | Least work, but the contributions sit at the bottom in block 7 and the pipeline stays half-width, which does not answer "ưu tiên hơn". |

## 4. Changes

**Space (found while planning, 2026-11-19).** The current poster has no free height. The new content (contributions, principle panel, future work) and a full-width pipeline need about 15–20 cm more than the page has, so the author approved four cuts: contributions replace the three header number cards, the takeaways list goes, the pipeline becomes one row of nodes with the principle panel beside it, and blocks 3 and 4 get more compact.

**New layout (top to bottom)**
```
│ Title · authors │ Contributions ① ② ③ (replace the 3 number cards) · mascot │
│ 1  Hook: metformin before/after │ nicknames                                │
│ 2  Pipeline, full width: 7 nodes in one row │ design-principle panel        │
│ 3  Resources (compact)     │ 5  Grounding & models                         │
│ 4  Retrieval (compact)     │ 6  Each step                                  │
│                            │ 7  Future work · QR · emails · funding        │
```
The numbered circles follow the new reading order (my call).

**Header: contributions replace the three number cards.** Three cards with the same fills as today's number cards. Each card has a small purple tag "Contribution 1/2/3" at the top, then a big value and a two-line label (each line at most about 28 characters, so it fits the card), using only numbers from the paper:
1. **10,000** · "benchmark questions on a" / "released Vietnamese corpus"
2. **97.5%** · "relevant passage in top 10," / "retrieval vs cost compared"
3. **18× / 25×** · "fewer hallucinated answers," / "Gemini / open Qwen3.5-9B"

The cards grow about 40 px taller to fit the tag. A caption above the cards would collide with the second title line.

2,409 nicknames stays in block 3 and the hallucination rates stay in block 5. The 0.913 vs 0.923 score moves into the block 5 heading: "Grounding gives most of the gain, and the open 9B model reaches 0.913 against Gemini's 0.923" (author's decision, 2026-11-19, to keep both highlights).

**Block 1, hook**
- Heading: "Without documents, the model answers from memory. Grounded in official labelling, it follows the national formulary and cites it."
- Red card verdict: "Contradicts the formulary" (drop "judged severe harm").
- Everything else unchanged.

**Block 2, pipeline (full width)**
- Heading unchanged: "Code controls the flow, and each model call makes one small decision".
- The seven nodes in one row on the left (about two thirds of the width), refine loop under the row from Judge back to Hybrid search, exits line under it.
- Design-principle panel on the right (lavender rounded box), three lines:
  - "Each model call answers one narrow question: Is this an attack? Is the evidence enough?"
  - "Code runs the flow, caps the refine loop at 3 rounds and can switch any step off."
  - "Narrow decisions suit small models: the open Qwen3.5-9B runs every step, like Gemini 3.8 Flash."

**Block 3, resources (compact)**: same facts, tighter spacing; the "Noisy: …" note goes.

**Block 4, retrieval (compact)**: same table; the two lessons share one lavender box.

**Block 5**: new heading as above, content unchanged. **Block 6**: unchanged.

**Block 7, future work** (right column under block 6), heading "Future work", exactly three short one-line items (author's decision, 2026-11-19: future work matters less than the results, so it takes little space):
1. "Cross-check answers with specialist sources and linear-algebraic logic rules" (the advisor's concern plus the paper's own future work, which cites the advisor's work `nguyen2022sparse`)
2. "A decision model that skips unneeded steps, to cut cost and latency" (author's idea. Refine calls go almost entirely to the 39% of questions whose first search is incomplete.)
3. "A comparison with a ReAct agent" (author's idea. ReAct is already cited in related work.)

QR codes, emails and funding stay in this block. The takeaways list is removed. "Real user questions, graded by several experts" is dropped to keep three items.

**Fit rule.** Every card ends at least 90 px (the page margin) above the page bottom. If the first build overflows, cut in this order until it fits, and report each cut used (my calls, delegated by the author): (a) GAP 40 → 30 and PAD 50 → 44; (b) the pipeline exits line moves into the principle panel as a fourth line; (c) QR codes 165 → 150 px; (d) drop the Qwen3-Reranker-8B row from the retrieval table. Never shrink text below the checker's minimum.

## 5. Left to the builder

Exact geometry, the panel's position in the pipeline block, how much the hook and resources shrink, final English wording within the meaning above (checked against the AI-text rules).

## 6. Verification

Same as the original spec §10: `make.sh` rebuilds PPTX and PDF, the number check and text-fit check pass, the poster is rendered to PNG and inspected at full size and at about 10%, PPTX and PDF stay 841 × 1189 mm. The author approves the PDF before submitting.
