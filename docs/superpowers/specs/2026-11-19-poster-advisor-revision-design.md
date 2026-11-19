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
- A reader sees the three contributions right after the hook, and the pipeline block is the widest, most prominent block after it.
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

**New layout (top to bottom)**
```
│ Header (unchanged)                                  │
│ 1  Hook: metformin before/after │ nicknames         │
│ Contributions strip (three items, full width)       │
│ 2  Pipeline, full width: diagram + design principle │
│ 3  Resources        │ 5  Grounding & models         │
│ 4  Retrieval        │ 6  Each step                  │
│ 7  Takeaways · Future work · QR · funding           │
```
The numbered circles follow the new reading order, so the pipeline becomes 2 and resources becomes 3 (my call; the numbers mark reading order).

**Block 1, hook**
- Heading: "Without documents, the model answers from memory. Grounded in official labelling, it follows the national formulary and cites it."
- Red card verdict: "Contradicts the formulary" (drop "judged severe harm").
- Green card verdict unchanged: "Matches the formulary, with citations".
- Everything else unchanged. The hook may lose some height if the reshuffle needs it.

**Contributions strip (new)**, heading "Contributions", three numbered items taken from the paper's introduction:
1. A Vietnamese drug-information corpus and a 10,000-question benchmark with known answer locations, all released.
2. A comparison of sparse, dense, hybrid and reranked retrieval that weighs effectiveness against deployment cost.
3. An agentic pipeline that a small open model can run, evaluated step by step with ablations and safety cases.

Each item may carry a small pointer to its block (→ 3, → 4, → 2 · 5 · 6).

**Block 2, pipeline (full width)**
- Heading unchanged: "Code controls the flow, and each model call makes one small decision".
- The existing icon diagram, laid out wider.
- A design-principle panel beside or below the diagram, roughly:
  - "Each model call answers one narrow question: Is this an attack? Is the evidence enough?"
  - "Code runs the flow, caps the refine loop at 3 rounds and can switch any step off for ablation."
  - "Narrow decisions suit small models: the open Qwen3.5-9B runs every step, as does Gemini 3.8 Flash."

**Block 3, resources** (was 2): content unchanged, made more compact to free height (tighter spacing, smaller benchmark bar; the noisy-group note may go if space is short).

**Blocks 4, 5, 6**: content unchanged.

**Block 7, takeaways and future work**
- Takeaways unchanged.
- New "Future work" list, exactly three items (author's decision, 2026-11-19):
  1. Check answers against specialist sources and against explicit rules in linear-algebraic logic programming, and flag conflicts with the formulary. (Merges the advisor's concern with the paper's own future work, which cites the advisor's work `nguyen2022sparse`.)
  2. A decision model that picks the steps each question needs, to cut cost and latency. (Author's idea. The paper shows refine calls go almost entirely to the 39% of questions whose first search is incomplete.)
  3. A comparison with a ReAct agent that plans its own tool calls. (Author's idea. ReAct is already cited in related work.)
- "Real user questions, graded by several experts" is dropped to keep three items.
- QR codes, emails and funding unchanged.

## 5. Left to the builder

Exact geometry, the panel's position in the pipeline block, how much the hook and resources shrink, final English wording within the meaning above (checked against the AI-text rules).

## 6. Verification

Same as the original spec §10: `make.sh` rebuilds PPTX and PDF, the number check and text-fit check pass, the poster is rendered to PNG and inspected at full size and at about 10%, PPTX and PDF stay 841 × 1189 mm. The author approves the PDF before submitting.
