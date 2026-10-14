# Advisor-assigned papers: deep read and implications for the ViPharmind paper

Date: 2026-10-14. Sources are the full PDFs saved under
`scratchpad/external/papers/` (Ma et al. 13 pp., Mo et al. 16 pp., Fensore et al. 33 pp.),
the CHIQ GitHub repository (`chiq_repo/`: README, `generation/enhancement_generation.py`,
`generation/adhoc_query_rewriting.py`, `dense/fusion.py`), and the citation pages listed in
Section 6. Everything in the paper sections below is taken from the PDFs; page numbers refer to
the printed proceedings pages. Verification status of every citation is stated explicitly.

Our paper, for reference (from `report/sections/*.tex`): Vietnamese drug-information corpus
(689 formulary monographs, 2,406 leaflets), 10,000-question retrieval benchmark with gold
sections known by construction (six groups, 17 intents), 500-item end-to-end golden set
(420 answerable, 50 multi-turn, 10 unanswerable, 10 out-of-scope, 10 injection), pipeline
guard -> rephrase (standalone query from rolling summary + last four turns) -> hybrid RRF
(k=2, 50 dense + 50 BM25) -> Qwen3-Reranker-4B -> judge -> refine loop -> answer, run with
Gemini 3.8 Flash and Qwen3.5-9B. Reranked hybrid retrieval reaches Hit@10 97.5%; one-step
RAG (last turn as typed) leaves 96% of the 50 multi-turn items unanswered with Gemini and
88% with Qwen3.5-9B; removing the rephrase step costs 0.114 truthfulness and 0.110 nugget
recall; closed-book Gemini truthfulness is 0.268 against 0.923 for the full agent.

---

## 1. Ma et al. 2023, "Query Rewriting in Retrieval-Augmented Large Language Models"

### 1.1 Citation (verified on the ACL Anthology page)

Xinbei Ma, Yeyun Gong, Pengcheng He, Hai Zhao, Nan Duan. 2023. Query Rewriting in
Retrieval-Augmented Large Language Models. In *Proceedings of the 2023 Conference on
Empirical Methods in Natural Language Processing (EMNLP 2023)*, pages 5303–5315, Singapore.
Association for Computational Linguistics. DOI 10.18653/v1/2023.emnlp-main.322.
Code: https://github.com/xbmxb/RAG-query-rewriting. Note that the advisor's wording
"Query Rewriting in ..." matches the Anthology title; the PDF header prints
"Query Rewriting for Retrieval-Augmented Large Language Models".

### 1.2 Problem framing

- Retrieve-then-read pipelines with black-box LLM readers keep the retrieval query fixed:
  it is "either original from datasets or directly determined by the black-box generation"
  (p. 5305). "There is inevitably a gap between the input text and the knowledge that is
  really needed to query" (p. 5305).
- Prior LLM-oriented adaptation tunes the retriever (RePlug) or the interaction prompts
  (ReAct, DSP, Self-Ask); nobody adapts the query itself.
- Proposal: Rewrite-Retrieve-Read. Insert a rewriting step in front of a frozen retriever
  (Bing web search) and a frozen reader; optionally make the rewriter a small trainable
  model aligned to the frozen modules with RL on the reader's reward (Figure 1, p. 5305).
- Scope note: this is single-turn open-domain QA and MMLU. There is no conversation
  history anywhere in the paper. The relevance to our rephrase step is the frozen-LLM
  rewriter baseline and the "retrieval gain is larger than reader gain" finding.

### 1.3 Method in detail

Pipeline (Section 3.1, p. 5306): (i) query rewrite x -> x~; (ii) retrieve doc; (iii) read
[doc, x] -> y^. The rewrite prompt is few-shot and "the output can be none, one or more
queries to search" (p. 5306).

**Frozen-rewriter variant (LLM rewriter).** A frozen LLM (ChatGPT, gpt-3.5-turbo) is
prompted with [instruction, 1–3 demonstrations fixed across runs, input]. Exact prompts
(Table 1, p. 5308):

- Open-domain QA rewriter: "Think step by step to answer this question, and provide search
  engine queries for knowledge that you need. Split the queries with ';' and end the queries
  with '**'. {demonstration} Question: {x} Answer:"
- Multiple-choice rewriter: "Provide a better search query for web search engine to answer
  the given question, end the queries with '**'. {demonstration} Question: {x} Answer:"
- Direct prompt (no retrieval): "Answer the question in the following format, end the
  answer with '**'. {demonstration} Question: {x} Answer:"
- Reader prompt with retrieval: same, but "Question: {doc} {x} Answer:".

On PopQA the rewriter may output "None", meaning no retrieval (p. 5309).

**Trainable-rewriter variant.** T5-large (770M) as rewriter G_theta, trained in two stages
(Section 3.2, pp. 5306–5307):

1. *Warm-up by distillation.* Prompt the LLM to rewrite training questions; keep only
   rewrites for which the reader then answers correctly, D_train = {(x, x~) | y^ = y};
   fine-tune T5 with log-likelihood (Eq. 1). Warm-up data sizes (Table 5, p. 5314):
   HotpotQA 90.4k train -> 37.5k warm-up; AmbigNQ 19.4k -> 8.6k; PopQA 13.0k -> 6.0k;
   MMLU Humanities 3.8k -> 1.5k, STEM 2.4k -> 0.9k, Other 2.6k -> 1.3k, Social 2.4k -> 1.3k.
2. *Reinforcement learning with PPO* (Eqs. 2–5). MDP over tokens; policy = T5 after warm-up;
   value network initialised from the policy; GAE advantages; KL regularisation to the
   warm-up policy with an adaptive beta (target KL 0.2, K_beta 0.1, beta_0 0.001;
   Appendix B). Reward (Eq. 4): R = R_lm(x~, y) − beta KL(pi_theta || pi_0).
   - Open-domain QA (Eq. 6): R_lm = EM + lambda_f F1 + lambda_h Hit, with Hit = +1 if the
     gold answer string appears in the retrieved context and −1 otherwise; lambda_f =
     lambda_h = 1.0.
   - MMLU (Eq. 7): R_lm = EM.
   Training: warm-up lr 3e-5, batch {16, 20}, {6, 8, 12} epochs; RL sampling 5120 steps,
   10 threads, policy trained {2,3,4} epochs at lr 2e-6; 4-beam decoding.

**Retriever.** Bing search API, two settings (p. 5307): (i) concatenate Bing snippets;
(ii) fetch page text and keep paragraphs with the highest BM25 score against the query up to
a length cap (scikit-learn BM25). RL used BM25 selection for AmbigNQ and snippets elsewhere.

**Readers.** Frozen ChatGPT (gpt-3.5-turbo) and Vicuna-13B, few-shot, same reader prompt
across configurations. The authors explicitly do not tune prompts (p. 5307).

### 1.4 Datasets, metrics, baselines

- HotpotQA full test set (7.4k, multi-hop), AmbigNQ first 1,000 test samples, PopQA split
  13k train / 714 test by stratified sampling over 16 question types, MMLU four categories
  split 80/20 with contaminated documents removed. Metrics EM and F1 (open-domain), EM (MMLU).
- Baselines (Section 5.2, p. 5308): (i) Direct (no retrieval, few-shot); (ii)
  Retrieve-then-read (question used as the query); (iii) LLM as frozen rewriter; (iv)
  trainable rewriter.

### 1.5 Main numbers

Table 2 (open-domain QA, ChatGPT reader; EM / F1), p. 5308:

| Setting | HotpotQA | AmbigNQ | PopQA |
|---|---|---|---|
| Direct | 32.36 / 43.05 | 42.10 / 53.05 | 41.94 / 44.61 |
| Retrieve-then-read | 30.47 / 41.34 | 45.80 / 58.50 | 43.20 / 47.53 |
| LLM rewriter | 32.80 / 43.85 | 46.40 / 58.74 | 46.00 / 49.74 |
| Trainable rewriter | 34.38 / 45.97 | 47.80 / 60.71 | 45.72 / 49.51 |

Table 3 (MMLU EM; Humanities / STEM / Other / Social), p. 5308:

| Reader, setting | Hum. | STEM | Other | Social |
|---|---|---|---|---|
| ChatGPT Direct | 75.6 | 58.8 | 69.0 | 71.6 |
| ChatGPT Retrieve-then-read | 76.7 | 63.3 | 70.0 | 78.2 |
| ChatGPT LLM rewriter | 77.0 | 63.5 | 72.6 | 76.4 |
| Vicuna-13B Direct | 39.8 | 34.9 | 50.2 | 46.6 |
| Vicuna-13B Retrieve-then-read | 40.2 | 39.8 | 55.2 | 50.6 |
| Vicuna-13B LLM rewriter | 42.0 | 41.5 | 57.1 | 52.2 |
| Vicuna-13B Trainable rewriter | 43.2 | 40.9 | 59.3 | 51.2 |

Table 4 (retrieval analysis on AmbigNQ; EM / F1 / Hit ratio), p. 5310:

| Setting | EM | F1 | Hit ratio |
|---|---|---|---|
| No retrieval | 42.10 | 53.05 | – |
| Upper bound (only samples whose context hits the answer) | 58.40 | 69.45 | 100 |
| Retrieve-then-read, snippets | 38.70 | 50.50 | 61.1 |
| Retrieve-then-read, BM25 selection | 45.80 | 58.50 | 76.4 |
| LLM rewriter, snippets | 39.80 | 52.64 | 63.5 |
| LLM rewriter, BM25 | 46.40 | 58.74 | 77.5 |
| Trainable rewriter, BM25 | 47.80 | 60.71 | 82.2 |

Other findings worth citing:
- "On HotpotQA, the standard retrieval hurts the reader" (30.47 vs 32.36 EM); rewriting
  recovers and surpasses it (p. 5308). Multi-hop questions are poor search queries.
- "the improvement in the hit rate of the retriever is more significant than the improvement
  in the reader" (p. 5310), consistent with Mallen et al. 2022 and Liu et al. 2023.
- With snippets alone (no BM25 re-selection), retrieval *hurts* AmbigNQ (38.70 < 42.10 EM)
  even with the rewriter: a retrieval-quality threshold below which RAG loses to closed-book.
- Vicuna gains more from rewriting than ChatGPT: "a more powerful reader has more parametric
  memories, thus more difficult to compensate with external knowledge" (p. 5309).
- Trainable rewriter stays below the LLM rewriter on PopQA because "None" (no retrieval) is a
  valid query and the LLM "knows better when the retrieval is needed for itself as a reader"
  (p. 5309). F1 of the retrieval-free decision: LLM rewriter 71.9%, T5 67.1%.
- Case study (Figure 3): rewrites front-load the key entity and strip the question frame;
  T5 kept "2000 movie" together where ChatGPT split it.

### 1.6 Stated limitations (p. 5311, Appendix C)

(i) Training trades generalisation for specialisation versus few-shot prompting. (ii) The
method keeps a one-turn retrieve-then-read loop rather than multi-call agents. (iii) Web
search is uncontrolled: "Neural dense retrievers that are based on professional, filtered
knowledge bases may potentially achieve better and controllable retrieval"; web APIs cost
money and return context that "can be occasionally inconsistent, redundant, and toxic".

### 1.7 What it means for us

- Our rephrase step is exactly their "LLM as a frozen rewriter" configuration, but applied
  to conversation history. Their Table 2 pattern (rewrite > retrieve-then-read > direct, with
  retrieve-then-read sometimes < direct) is the same qualitative pattern as our Table 2 and
  ablation (full agent > one-step RAG > closed-book).
- Their Hit ratio is our Hit@k; they show retrieval metrics move more than answer metrics.
  We can make the same point with Hit@10 97.5% versus the end-to-end gain.
- A trainable rewriter is not needed for our paper, but Section 1.3's "Hit" reward is a
  ready-made recipe if a reviewer asks how a 0.6B rewriter could replace the LLM call.

---

## 2. Mo et al. 2024, "CHIQ: Contextual History Enhancement for Improving Query Rewriting in Conversational Search"

### 2.1 Citation (verified on the ACL Anthology page)

Fengran Mo, Abbas Ghaddar, Kelong Mao, Mehdi Rezagholizadeh, Boxing Chen, Qun Liu,
Jian-Yun Nie. 2024. CHIQ: Contextual History Enhancement for Improving Query Rewriting in
Conversational Search. In *Proceedings of the 2024 Conference on Empirical Methods in
Natural Language Processing (EMNLP 2024)*, pages 2253–2268, Miami, Florida, USA. Association
for Computational Linguistics. DOI 10.18653/v1/2024.emnlp-main.135.
Code: https://github.com/fengranMark/CHIQ (README calls the repo "ConvCHIQ").

### 2.2 Problem framing

- Conversational search must "compose adequate search queries for each context-dependent
  utterance" (p. 2253). The dominant recipe is to prompt a closed-source LLM (ChatGPT) with
  the raw history and the current turn, Eq. 1: q_{n+1} <- LLM(I^CQR + H + u_{n+1}).
- Open-source 7B models do worse at this one-shot rewrite, but they do possess the basic NLP
  skills needed to clean the history (coreference, expansion, topic detection, summary).
- Proposal: two-step method. First enhance the history H into H' with five targeted
  prompts, then rewrite from H'. "instead of simply ask an LLM to generate a search query, it
  is critical to design strategies to generate different facets of enhancement" (p. 2261).
- Contrast with ours: our rephrase step is Eq. 1 applied to a rolling summary plus the last
  four turns. CHIQ is the natural "enhanced-history" baseline the advisor is pointing at.

### 2.3 Method in detail

**Task formulation (Section 3.1).** History H = {u_k, r_k}_{k=1..n} of user questions and
system responses; given u_{n+1}, produce q_{n+1} for an off-the-shelf retriever that returns
passages P_{n+1}.

**Five history-enhancement prompts (Section 3.2, Appendix A, pp. 2255–2256, 2265).** Each
is mapped to a basic NLP task. The paper states that the instruction text was tuned by trial
and error so that both LLaMA-2-7B-chat and Mistral-7B-Instruct-v0.2 follow the format, and
that "We observed no benefits from using in-context examples for any model" (p. 2265). The
exact prompts, quoted from Appendix A (the appendix headings are slightly mis-ordered in the
PDF; the mapping below follows the code names in `enhancement_generation.py`, which are
unambiguous):

1. **Question Disambiguation (QD)**, code `explain_question`, produces u'_{n+1}, a
   self-contained version of the current question that can replace u_{n+1} in Eq. 1.
   Prompt: "You are given a set of question-answers pairs and a new question that is
   ambiguous. Your goal is to rewrite the question so it becomes clear. Write the new
   question without any introduction." (Code wording: "re-write the question so it became
   clear. Just write the new question without any introduction.")
   Input format (code): `### Context` followed by one line per past turn "q a", then
   `### Ambiguous Question` and the current question.

2. **Response Expansion (RE)**, code `explain_response`, rewrites the last system response
   r_n into a self-contained r'_n. Prompt: "You are given a question-and-answer pair, where
   the answer is not clear. Your goal is to write a long version of the answer based on its
   given context. The generated answer should be one sentence only and less than 20 words."
   Input: `### Context` + past turns, then `### Question and Answer to explain` + "q_n r_n".

3. **Pseudo Response (PR)**, code `single_response`, speculates an answer r'_{n+1} to the
   current question from the LLM's own knowledge; it is concatenated to the input of Eq. 1
   (the HyDE/Query2doc idea inside a conversation). Prompt: "Given a series of
   question-and-answer pairs, along with a new question, your task is to give a one-sentence
   response to the new question." Input: `### Context` + past turns, `### Question` + u_{n+1}.

4. **Topic Switch (TS)**, code `new_topic`, decides whether u_{n+1} starts a new topic; if
   yes, H' keeps only the last turn {u'_n, r'_n}. Prompt: "Given a series of
   question-and-answer pairs, along with a new question, your task is to determine whether
   the new question continues the discussion on an existing topic or introduces a new topic.
   Please respond with either "new_topic" or "old_topic" as appropriate."

5. **History Summary (HS)**, code `summarize_context`, replaces H by a paragraph summary.
   Prompt: "You are given a context in the form of question-answer pairs. Your goal is to
   write a paragraph that summarizes the information in the context. The summary should be
   short with one sentence for each question answer pair."

Plus the rewrite prompt itself:

6. **Query Rewriting (A.6)**, code `search_query`: "Given a series of question-and-answer
   pairs as context, along with a new question, your task is to convert the new question into
   a search engine query that can be used to retrieve relevant documents. The output should
   be placed in a JSON dictionary as follows: {"query": ""}". The code parses the JSON and
   falls back to the raw current turn if parsing fails (`check_query` in
   `adhoc_query_rewriting.py`).

7. **Pseudo Supervision Signals (A.7)**, for CHIQ-FT training only: "You are given a
   relevant passage, a series of question-and-answer pairs as context along with a new
   question, your task is to generate a set of search queries based on the relevancy between
   the new question and the relevant passage and also rely on the given context. The output
   format should be in a list with indexes e.g., 1. 2. 3."

The code also contains an unused `multi_response` prompt (answer every past question in one
sentence without pronouns) and a `keyword_alias` extraction prompt; neither appears in the
paper.

Generation settings from the code: LLaMA `[INST] <<SYS>> ... <</SYS>>` / Mistral
`<s>[INST] ... [/INST]` chat templates, prompt truncated to the last 2,048 tokens,
`top_k=50, top_p=0.9, temperature=0.6, repetition_penalty=1.15`, `max_new_tokens=512`
(768 for summaries). The paper says temperature 0.7 (p. 2265); the code says 0.6. Output
cleaning drops QD outputs that do not end in "?" or that contain "context", "given",
"mentioned", and maps TS to yes/no.

**Default combination (Section 3.3, p. 2256).** "+QD" replaces u_{n+1} with u_{n+1} ⊕
u'_{n+1}; "+RE" replaces r_n with r'_n; "+PR" appends r'_{n+1} to the Eq. 1 input; "+TS"
truncates H to the last turn when a switch is detected; "+HS" overwrites H with the summary.
Default: run TS first. If a new topic is detected, apply QD+RE+PR on the truncated history.
Otherwise apply QD+RE+PR on the original history and then HS on top of the enhanced history.
HS is never activated after a detected topic switch (p. 2260).

**Three ways to use the enhanced history (Sections 3.3–3.4, 4.2).**

- **CHIQ-AD (ad-hoc).** Run the rewrite prompt on H' and send the query straight to the
  retriever. No training. Cost: five LLM generations per turn (QD, RE, PR, TS, HS) plus the
  rewrite.
- **CHIQ-FT (search-oriented fine-tuning).** Build pseudo labels offline: Eq. 2,
  Q'_{n+1} <- LLM(Î^CQR ⊕ H' ⊕ u_{n+1} ⊕ p*_{n+1}), i.e. the LLM sees the enhanced history
  *and the gold passage* and emits several candidate queries in one pass; Eq. 3 keeps the
  candidate with the highest retrieval score S against the qrels (NDCG@3 is the selection
  metric, p. 2266). A small model M(H' ⊕ u_{n+1}) = q'_{n+1} is fine-tuned by MLE on these
  labels. Backbone FlanT5-base (large also tried), 10 epochs, lr 1e-5, batch 8, max query
  length 32. At inference no LLM is called, "so that the latency is not much affected"
  (p. 2257). Note that the README's step 3.3 fine-tunes on the raw history; the paper's
  Eq. 3 says M takes H'.
- **CHIQ-Fusion.** Rank-list fusion of the CHIQ-AD and CHIQ-FT result lists using the
  result-level fusion of Lin et al. 2021b (CQE), balance factor alpha = 1 (p. 2266). The code
  (`dense/fusion.py`) implements `CQE_hybrid` (score = s_0 + alpha·s_1 with the other list's
  minimum score filled in for missing documents), plus `combine_max`, `combine_sum` and an
  RRF variant marked "bug". Default alpha in the script is 0.4 with a comment giving
  per-dataset values; the paper reports alpha = 1.

### 2.4 Experimental setup

**Open-source LLMs.** `meta-llama/Llama-2-7b-chat-hf` (main tables) and
`mistralai/Mistral-7B-Instruct-v0.2` (Appendix C). ChatGPT-3.5 only in Table 3 to isolate
the effect of history enhancement.

**Datasets (Table 6, p. 2265).**

| Dataset | Split | #Conv. | #Turns (queries) | Collection |
|---|---|---|---|---|
| TopiOCQA | train | 3,509 | 45,450 | 25M passages |
| TopiOCQA | test | 205 | 2,514 | |
| QReCC | train | 10,823 | 29,596 | 54M |
| QReCC | test | 2,775 | 8,124 | |
| CAsT-19 | test | 50 | 479 | 38M |
| CAsT-20 | test | 25 | 208 | 38M |
| CAsT-21 | test | 26 | 239 | 40M |

Samples without gold passages are discarded. Human rewrites exist for all datasets except
TopiOCQA. CAsT qrels are graded; relevance thresholds 1, 2, 2 for CAsT-19/20/21. CAsT is
test-only (zero-shot transfer of models trained on TopiOCQA).

**Retrievers.** Sparse BM25 via Pyserini (k1 = 0.9, b = 0.4 on TopiOCQA; k1 = 0.82, b = 0.68
on QReCC) and dense ANCE via Faiss. Query / concatenated input / passage truncated to 32 /
512 / 384 tokens.

**Metrics.** MRR, NDCG@3, Recall@10 through pytrec_eval (the code also computes
Recall@100 and MAP). Significance: paired t-test at p < 0.05 against all compared baselines.
Main tables use LLaMA-2-7B.

**Baselines (Section 4.2, Appendix B.3).** Three families:
1. Fine-tuned small CQR models: QuReTeC (term-selection tagger), T5QR (T5-base on human
   rewrites), CONQRR (T5 + RL with ranking signal), ConvGQR (rewrite + expansion, two T5s),
   EDIRCS (text editing with ranking signal).
2. LLM-based: IterCQR (iterative rewriting seeded by ChatGPT), RETPO (LLaMA-2-7B fine-tuned
   on GPT-4-generated rewrites with retriever preference), LLM-Aided IQR (ChatGPT as rewriter
   and editor, two passes), LLM4CS (ChatGPT/LLaMA prompting with five calls per query and
   aggregation of rewrites and pseudo responses, run without chain-of-thought), HyDE and
   Query2doc (ChatGPT pseudo-document expansion), LLM-based ad-hoc retrievers RepLLaMA,
   E5-Mistral, LLM-Embedder.
3. Conversational dense retrievers (not directly comparable): ConvDR (ANCE distilled from
   human rewrites) and InstructorR (FlanT5-XL instruction-tuned retriever).

### 2.5 Main numbers

Table 1 (TopiOCQA and QReCC; MRR / NDCG@3 / Recall@10), p. 2258. Dagger = significant at
p < 0.05 over all baselines except CONQRR, RETPO, IterCQR.

Dense (ANCE):

| System | TopiOCQA | QReCC |
|---|---|---|
| ConvDR | 27.2 / 26.4 / 43.5 | 38.5 / 35.7 / 58.2 |
| InstructorR | 25.3 / 23.7 / 45.1 | 43.5 / 40.5 / 66.7 |
| QuReTeC | 11.2 / 10.5 / 20.2 | 35.0 / 32.6 / 55.0 |
| T5QR | 23.0 / 22.2 / 37.6 | 34.5 / 31.8 / 53.1 |
| CONQRR | – | 41.8 / – / 65.1 |
| ConvGQR | 25.6 / 24.3 / 41.8 | 42.0 / 39.1 / 63.5 |
| EDIRCS | – | 42.1 / – / 65.6 |
| IterCQR | 26.3 / 25.1 / 42.6 | 42.9 / 40.2 / 65.5 |
| RETPO | 30.0 / 28.9 / 49.6 | 44.0 / 41.1 / 66.7 |
| LLM-Aided | – | 43.9 / 41.3 / 65.6 |
| LLM4CS (LLaMA-2-7B) | 27.7 / 26.7 / 43.3 | 44.8 / 42.1 / 66.4 |
| CHIQ-FT | 30.0 / 28.9 / 51.0 | 36.9 / 34.0 / 57.6 |
| CHIQ-AD | 33.2 / 32.2 / 53.0 | 47.0 / 44.6 / 70.8 |
| CHIQ-Fusion | 38.0 / 37.0 / 61.6 | 47.2 / 44.2 / 70.7 |

Sparse (BM25):

| System | TopiOCQA | QReCC |
|---|---|---|
| QuReTeC | 8.5 / 7.3 / 16.0 | 34.0 / 30.5 / 55.5 |
| T5QR | 11.3 / 9.8 / 22.1 | 33.4 / 30.2 / 53.8 |
| CONQRR | – | 38.3 / – / 60.1 |
| ConvGQR | 12.4 / 10.7 / 23.8 | 45.6 / 44.1 / 41.0 |
| EDIRCS | – | 41.2 / – / 62.7 |
| IterCQR | 16.5 / 14.9 / 29.3 | 46.7 / 44.1 / 64.4 |
| LLM-Aided | – | 48.9 / 46.3 / 66.4 |
| LLM4CS (LLaMA-2-7B) | 18.9 / 17.7 / 33.7 | 47.8 / 45.0 / 69.1 |
| CHIQ-FT | 17.0 / 15.4 / 32.3 | 37.8 / 35.0 / 57.1 |
| CHIQ-AD | 22.5 / 20.5 / 40.4 | 53.1 / 50.7 / 77.2 |
| CHIQ-Fusion | 25.6 / 23.5 / 44.7 | 54.3 / 51.9 / 78.5 |

Headline deltas the authors state (p. 2259): dense CHIQ-AD beats LLM4CS by 5.5 (TopiOCQA)
and 2.2 (QReCC) MRR; CHIQ-FT beats T5QR by 7.0 and 1.9 MRR; CHIQ-Fusion adds 4.8 and 0.2
MRR over the best single component. CHIQ-FT loses to ConvGQR/IterCQR on QReCC because
those are trained on QReCC's human rewrites; "enhancing the history is crucial for
performance when no QR-supervised annotations exist" (p. 2259).

Table 2 (zero-shot, dense ANCE, CAsT; MRR / NDCG@3 / Recall@10), p. 2258:

| System (LLM) | CAsT-19 | CAsT-20 | CAsT-21 |
|---|---|---|---|
| RepLLaMA (LLaMA-2-7B) | 62.4 / 31.6 / 10.6 | 26.8 / 18.3 / 10.4 | 47.4 / 32.7 / 19.6 |
| E5-Mistral (Mistral-7B) | 62.2 / 31.3 / 9.5 | 22.0 / 15.4 / 8.4 | 48.2 / 32.5 / 20.5 |
| LLM-Embedder (LLaMA-2-7B) | 63.3 / 36.6 / 11.4 | 25.2 / 15.4 / 8.7 | 46.8 / 31.2 / 17.3 |
| HyDE (ChatGPT) | 55.6 / 39.2 / 10.0 | 44.8 / 29.3 / 16.9 | – |
| Query2doc (ChatGPT) | 58.8 / 42.4 / 11.6 | 48.6 / 32.5 / 17.3 | – |
| InstructorR (ChatGPT) | 61.2 / 46.6 / 10.4 | 43.7 / 29.6 / 8.3 | 46.7 / 32.5 / 18.4 |
| LLM4CS (LLaMA-2-7B) | 68.4 / 45.9 / 11.2 | 52.3 / 37.2 / 17.9 | 57.0 / 41.5 / 20.2 |
| LLM4CS (Mistral-7B) | 67.6 / 44.5 / 10.9 | 48.3 / 33.5 / 17.0 | 53.0 / 35.3 / 19.6 |
| LLM4CS (ChatGPT) | 70.4 / 46.8 / 11.7 | 58.6 / 41.5 / 19.3 | 66.1 / 46.9 / 24.4 |
| CHIQ-FT (LLaMA-2-7B) | 68.5 / 45.1 / 11.9 | 46.3 / 31.6 / 15.9 | 53.9 / 36.0 / 20.4 |
| CHIQ-AD (LLaMA-2-7B) | 70.8 / 47.6 / 11.9 | 51.0 / 34.4 / 17.9 | 57.7 / 42.0 / 22.6 |
| CHIQ-Fusion (LLaMA-2-7B) | 73.3 / 50.5 / 12.9 | 54.0 / 38.0 / 19.3 | 62.9 / 46.5 / 25.2 |

Table 3 (open vs closed LLM, CHIQ-AD, dense; MRR / NDCG@3), p. 2259:

| LLM | History | CAsT-19 | CAsT-20 | CAsT-21 |
|---|---|---|---|---|
| LLaMA-2-7B | original | 67.4 / 42.5 | 40.9 / 27.9 | 52.7 / 37.2 |
| Mistral-7B | original | 67.9 / 42.0 | 44.2 / 30.4 | 59.5 / 41.6 |
| ChatGPT-3.5 | original | 69.3 / 40.8 | 53.0 / 36.2 | 60.3 / 41.9 |
| LLaMA-2-7B | enhanced | 70.8 / 47.6 | 51.0 / 34.4 | 57.7 / 42.0 |
| Mistral-7B | enhanced | 71.4 / 47.2 | 49.2 / 34.4 | 67.0 / 47.2 |
| ChatGPT-3.5 | enhanced | 71.7 / 46.4 | 55.7 / 40.5 | 62.2 / 42.8 |

ChatGPT also gains from enhanced history (NDCG@3 +5.4, +4.3, +0.9); the LLaMA-to-ChatGPT
MRR gap shrinks from 1.9 / 12.1 / 7.6 to 0.9 / 4.7 / 4.5 (p. 2260).

Table 4 (supervision signal ablation for CHIQ-FT, dense; MRR / NDCG@3), p. 2260:

| Signal | TopiOCQA | QReCC |
|---|---|---|
| Manual (human rewrites) | – | 34.7 / 31.9 |
| CHIQ-FT (full) | 30.0 / 28.9 | 36.9 / 34.0 |
| w/o enhanced history H' | 27.6 / 26.7 | 35.4 / 33.8 |
| w/o multiple candidates Q' | 24.2 / 23.4 | 33.4 / 31.7 |
| w/o gold passage p* | 18.2 / 17.2 | 26.8 / 23.9 |

LLM-generated supervision beats human rewrites (36.9 vs 34.7 MRR on QReCC), "consistent with
previous studies that have identified human-written queries as sub-optimal" (p. 2260).

Table 5 (history-enhancement ablation for CHIQ-AD; MRR / NDCG@3), p. 2260:

| Setting | Dense TopiOCQA | Dense QReCC | Sparse TopiOCQA | Sparse QReCC |
|---|---|---|---|---|
| CHIQ-AD full | 33.2 / 32.2 | 47.0 / 44.6 | 22.5 / 20.5 | 53.1 / 50.7 |
| w/o QD | 32.5 / 31.4 | 44.6 / 41.9 | 22.1 / 20.1 | 47.3 / 44.6 |
| w/o RE | 28.3 / 27.0 | 46.6 / 44.0 | 19.0 / 16.8 | 50.1 / 47.3 |
| w/o PR | 26.4 / 25.2 | 43.5 / 40.8 | 16.9 / 15.3 | 46.9 / 44.5 |
| w/o TS | 20.0 / 18.7 | 46.9 / 44.4 | 17.8 / 16.5 | 51.7 / 48.8 |

Topic-switch detection matters most on TopiOCQA (+13.2 dense, +5.2 sparse MRR) because the
dataset is built around topic shifts; on QReCC QD matters most for sparse retrieval. "while
question disambiguation (QD) improves performance, it is less critical compared to
predicting a pseudo response (PR) or enhancing the quality of the last system response
(RE)" (p. 2260).

Appendix C (Mistral-7B-Instruct-v0.2): same trends, systematically lower than LLaMA except
on CAsT-21; dense TopiOCQA CHIQ-FT 26.2 / 25.4 / 45.3, CHIQ-AD 28.9 / 28.3 / 46.8,
CHIQ-Fusion 36.3 / 35.0 / 59.6; QReCC CHIQ-AD 46.7 / 44.2 / 70.7. When the gap between AD
and FT is large, fusion helps little or hurts; when it is small, fusion gains clearly.

Case analysis (Section 5.6, Appendix D): QD and RE resolve coreference and expand acronyms,
TS removes noise, PR adds likely answer terms, HS keeps key terms in plain text. PR and RE
"may also introduce noisy terms due to the wrong fact generated by LLMs that hurt the
ranking results" (p. 2261). AD queries are expansion-heavy, FT queries concise. Table 9
example: "What is the emotional response due to the third one?" -> raw rewrite ranks the
gold passage 41st, CHIQ-AD 4th, CHIQ-FT ("How does adrenaline impact mood?") 3rd, fusion 1st.
Table 10 shows an enhancement failure where the LLM hallucinated an unrelated topic
(Kenneth Anger) into the history of a Cal Tjader conversation.

### 2.6 Stated limitations (p. 2261)

No larger open models (Mixtral 56B, LLaMA 70B, Gemma) and no GPT-4 or Claude for cost
reasons; no back-off filter to detect noisy enhancement outputs; no interpolation between
human and pseudo queries for FT; only five enhancement facets.

### 2.7 What it means for us

- CHIQ's "original history" baseline *is* our rephrase step (one rewrite prompt over the
  raw history). CHIQ-AD is the obvious stronger variant to add: QD, RE, PR, TS, HS with a 9B
  open model, which is larger than their 7B models.
- The two enhancements that mattered most (PR, i.e. a pseudo answer, and RE, i.e. expanding
  the last system answer) are cheap in our setting because our answer step already produces a
  grounded, self-contained answer: the previous *grounded* answer is a better RE than an LLM
  guess, and a PR drawn from a 9B model on Vietnamese drug facts risks exactly the noise
  they warn about.
- Their metric set (MRR, NDCG@3, Recall@10, paired t-test) maps directly onto our
  MRR@10, nDCG@10, Hit@10 with Holm-adjusted paired tests.
- Fusion of two rewrites via rank-list fusion is a one-line addition to our RRF step.

---

## 3. Fensore et al. 2025, "Does Domain-Specific Retrieval Augmented Generation Help LLMs Answer Consumer Health Questions?"

### 3.1 Citation (verified on the PMLR page and the PDF header)

Chase M. Fensore, Rodrigo M. Carrillo-Larco, Megha K. Shah, Joyce C. Ho. 2025. Does
Domain-Specific Retrieval Augmented Generation Help LLMs Answer Consumer Health Questions?
In *Proceedings of the 10th Machine Learning for Healthcare Conference (MLHC 2025)*,
Proceedings of Machine Learning Research 298:1–33. PMLR. No DOI is issued by PMLR for this
volume; cite the URL https://proceedings.mlr.press/v298/fensore25a.html. Code:
https://github.com/fensorechase/rag-patient-metabolic-qa. The PDF header reads
"Proceedings of Machine Learning Research 298:1–33, 2025 / Machine Learning for Healthcare
2025".

### 3.2 Problem framing

- LLMs score well on medical exams, but "many of these datasets still focus on
  multiple-choice formats that may not reflect the complexity and variability of real
  patient questions" (p. 1–2). They quote Raji et al. 2025 on moving "beyond medical exams".
- RAG is widely assumed to help, "yet ... it remains unclear whether RAG truly aids the
  process of medical QA without extensive setup and configuration" (p. 2). MIRAGE (Xiong et
  al. 2024) is multiple-choice only and "can only assess retrieval capability on less than
  half of the questions" (p. 2).
- Question: can off-the-shelf open LLMs plus targeted retrieval from authoritative NIDDK pages
  answer open-ended consumer health questions better than the same LLMs closed-book, with no
  fine-tuning? Closed-domain assumption: the ground-truth answer is present in the corpus D.

### 3.3 Corpus and dataset

- NIDDK subset of MedQuAD: 1,192 QA pairs, 828 unique questions, 12 template categories
  (information, susceptibility, causes, symptoms, exams/tests, treatment, prevention,
  considerations, complications, frequency, research, outlook). Questions average 9.08 words
  (sd 3.39, range 4–27); reference answers average 268.59 words (sd 289.64, range 6–2,024).
  Each question carries its source NIDDK URL, used as retrieval ground truth.
- Corpus: 151 unique NIDDK web pages (dead links recovered from the Wayback Machine), HTML
  stripped while keeping headers. After cleaning, pages have mean 698.66 words, median 455,
  max 2,782, min 432 (Appendix D).
- Chunking tuned on a 12-question development set: 300 tokens with 50-token overlap, min
  100, max 500, sentence boundaries preserved, section titles and document focus kept as
  metadata. Result: 240 chunks in total (p. 6).

### 3.4 Retriever

- Embeddings BAAI/bge-large-en-v1.5 indexed in ChromaDB with metadata.
- Hybrid scoring of three signals: dense cosine similarity, BM25, and "a domain-specific
  re-ranking based on medical term overlap"; hybrid weight 0.5, MMR lambda 0.5, initial
  k = 10, final k = 5, cross-encoder/ms-marco-MiniLM-L-6-v2 as reranker (Appendix C).
- Corpus-aware query expansion: PMI over a 5-token window, threshold theta = 0.5, global
  TF-IDF-variance weight above the 75th percentile, expanded terms repeated 1–4 times
  (Appendix B). The authors note that this only works because MedQuAD questions contain the
  corpus's key terms and would not transfer to patients who lack the terminology.
- Retrieval metrics: precision, recall, nDCG and MRR at k = 5, where a chunk is relevant if it
  comes from the ground-truth URL.

Table 1 (retrieval ablation on all 828 questions), p. 9:

| Configuration | Precision | Recall | nDCG | MRR |
|---|---|---|---|---|
| Full | 0.153 | 0.333 | 0.319 | 0.314 |
| w/o query expansion | 0.158 | 0.333 | 0.320 | 0.316 |
| w/o reranking | 0.134 | 0.327 | 0.287 | 0.274 |
| w/o BM25 | 0.153 | 0.333 | 0.319 | 0.314 |
| Dense only (w/o QE, BM25, reranking) | 0.156 | 0.319 | 0.300 | 0.294 |
| BM25 only | 0.134 | 0.329 | 0.291 | 0.279 |

Table 5/6 (varying k): initial k 5–50 moves precision only 0.152–0.155; final k = 1 gives
precision 0.302 and MRR 0.302, k = 5 precision 0.153 and MRR 0.314, k = 10 precision 0.108
and MRR 0.315. Table 7: medical embedder abhinand/MedEmbed-large-v0.1 gives precision 0.154
versus 0.153 for bge-large, so the general model was kept; ms-marco-electra-base reranker is
worse (0.121 precision).

"The relatively low precision scores (0.134–0.153) indicate that only about 15% of the top-5
retrieved chunks contain information from the ground-truth document" (p. 9). Because MRR
is 0.31, the first relevant chunk is on average around rank 3 when it appears at all, and
recall@5 of 0.33 means two thirds of the relevant chunks are missed.

### 3.5 The four LLMs and generation

Llama 3.1 70B-Instruct, Llama 3.1 8B-Instruct, Mixtral 8x7B-Instruct-v0.1 (MoE, 46.7B),
Meditron-70B (LLaMA-2 fine-tuned on medical text). All 4-bit NF4, temperature 0.1, max 512
new tokens, one H100, Hugging Face Transformers. Retrieved context is trimmed to fit the
window.

Prompts (Appendix B.4):
- Vanilla (used in the main results): "You are a helpful doctor answering patient
  questions. Your responses should be informative, concise, and clear. {question_text}"
- RAG: "You are a medical professional answering patient questions. Answer the following
  {question_type} question using ONLY the provided medical reference documents. Reference
  Documents: {context_str} Question: question Instructions: 1. Use ONLY information from the
  provided reference documents 2. Be clear, concise, and accurate 3. If the documents don't
  contain enough information to answer the question completely, acknowledge this 4.
  Structure complex answers with appropriate formatting 5. Include relevant medical
  terminology when present in the source documents Answer:"
- A vanilla prompt matching the RAG format was tested on an 83-question subset (Table 10)
  and gave similar automatic scores, so the authors attribute the vanilla-vs-RAG gap to
  retrieval rather than prompt wording.

### 3.6 Answer metrics, LLM judge and clinical validation

- Automatic: BLEU-1, BLEU-4, ROUGE-1, ROUGE-L, BERTScore against the MedQuAD reference.
- LLM-as-judge: Llama 3.1 70B-Instruct scores eight categorical criteria (scientific
  consensus 1/0/−1; inappropriate content 0/−1/−2; missing content 0/−1/−2; harm extent
  0/−1/−2; harm likelihood 0/−1/−2; bias 0/−1; empathy 2/1/0; grammaticality 1/0), returned
  as JSON, normalised to a 0–10 composite. 6,624 responses were judged; GPT-4 judging was
  estimated at $700–900 and rejected for reproducibility.
- Calibration: the judge gives the MedQuAD reference answers a composite of 8.66 (sd 0.89,
  750/828 valid), slightly below the best vanilla system (8.58 is Llama-70B vanilla; the text
  says reference answers scored 0.56 lower than the best approach on average), which they
  read as the judge being "generally well calibrated at categorizing ground truth answers as
  acceptable" (p. 28).
- Clinical validation: 22 questions stratified over the 12 categories and three LLMs
  (Meditron excluded), 66 vanilla-vs-RAG pairs, one clinician blinded to model, approach and
  judge score, head-to-head A / B / Tie with reference answers available. Agreement between
  the judge's sign of the composite difference and the clinician: 59% (n = 66); 69% if judge
  ties are credited to vanilla; 51% if ties are credited to RAG. Two diabetes clinicians
  oversaw the evaluation process.

### 3.7 Main numbers: where vanilla beat RAG

Table 2 (n = 828; BLEU-1 / BLEU-4 / ROUGE-1 / ROUGE-L / BERTScore), p. 10:

| Model | LLM-only | RAG |
|---|---|---|
| Llama 3.1 8B | 0.2035 / 0.0263 / 0.3047 / 0.1527 / 0.8181 | 0.1628 / 0.0177 / 0.2246 / 0.1234 / 0.7967 |
| Llama 3.1 70B | 0.2044 / 0.0291 / 0.3065 / 0.1529 / 0.8178 | 0.1500 / 0.0204 / 0.2345 / 0.1376 / 0.8206 |
| Mixtral 8x7B | 0.2091 / 0.0314 / 0.3135 / 0.1674 / 0.8312 | 0.1236 / 0.0204 / 0.2171 / 0.1302 / 0.8196 |
| Meditron-70B | 0.1551 / 0.0110 / 0.2100 / 0.0971 / 0.7870 | 0.1516 / 0.0193 / 0.2082 / 0.1297 / 0.8062 |

Vanilla wins every column for the three general models except BERTScore for Llama-70B
(0.8206 RAG vs 0.8178 vanilla). Meditron-70B is the exception: RAG wins BLEU-4, ROUGE-L and
BERTScore, vanilla wins BLEU-1 and ROUGE-1.

Table 3 / Table 12 (judge composite, 0–10, mean and sd, n = 828), pp. 11, 28:

| Model | LLM-only | RAG |
|---|---|---|
| Llama 3.1 8B | 8.44 (1.23) | 7.07 (1.60) |
| Llama 3.1 70B | 8.58 (1.03) | 7.60 (1.58) |
| Mixtral 8x7B | 7.81 (1.58) | 7.70 (1.64) |
| Meditron-70B | 6.27 (2.87) | 5.88 (3.00) |

The same ordering holds on the 582-question intersection with complete judge output
(8.62 / 7.06, 8.87 / 7.55, 7.94 / 7.63, 6.31 / 5.64). Mixtral has the smallest gap.

Per-criterion observations (Section 3.3.1, Figure 2, Figure 4):
- Scientific consensus: vanilla produced fewer "opposed" or "no consensus" answers; vanilla
  Llama-70B highest aligned rate; Llama-8B with RAG lowest; Meditron-70B with RAG the most
  "opposed".
- Inappropriate content: rare for both; Meditron produced it over 20% of the time and RAG
  made Meditron worse.
- Missing content: "Across all models, RAG responses were more judged to have more omissions
  with great clinical significance", most extreme for Llama 3.1. Yet Mixtral with RAG had
  the highest rate of answers with no omission at all (10%), and RAG "did slightly boost the
  rate of responses with complete content, despite increasing the number of responses with
  major omissions" (p. 14).
- Harm: general models under 20% severe-harm potential in both settings; Meditron 20–30%;
  vanilla marginally lower overall. RAG "showed competitive performance in specific areas
  like scientific consensus and harm reduction" for some models (abstract, p. 14).
- Length (Table 8): RAG answers are shorter, mean 188.4 words (sd 125.2, min 0) versus
  vanilla 237.7 (sd 78.3) and reference 264.8 (sd 287.7). The min of 0 words shows some RAG
  runs returned nothing; the "ONLY the provided documents" instruction also produced
  refusals such as "The provided reference documents do not contain comprehensive
  information on the treatments for ..." (Figure 7).
- Retrieval-to-answer coupling (Appendix E.3, Figures 5–6): Pearson correlation between
  precision@5 and composite judge score is 0.28 for Llama-8B and 0.08 for Llama-70B. Large
  models produced high-scoring answers even at precision@5 = 0; Meditron collapsed when
  retrieval failed. When context was partially relevant (low precision, high MRR) all four
  RAG systems "consistently produced poor quality answers", which the authors read as the
  LLM being "consistently distracted by irrelevant information in the retrieved context when
  part but not all of the context was relevant" (p. 28).

### 3.8 The authors' explanation

1. Retrieval was poor even for templated questions: "the relatively low retrieval
   performance of the full retrieval system applied (Precision@5 = 0.15) highlights a
   fundamental challenge in applying RAG to popular medical question-answering tasks, even in
   a simplified setting with templated questions like in MedQuAD" (p. 13).
2. A two-sided semantic gap: answer content is spread over several sections of interlinked
   pages, and even verbatim question text duplicated across pages was not reliably surfaced.
3. The questions favour parametric knowledge: "the consistency in question formats helps
   models leverage patterns in their pre-trained medical knowledge" and the NIDDK subset
   covers "a limited set of medical conditions, which may favor the general medical knowledge
   already present in current LLMs" (p. 13).
4. Metric artefacts: reference-overlap metrics penalise RAG's shorter answers (BLEU brevity
   penalty) and "valid alternative phrasings"; the judge appears "overly conservative in
   their assessment of retrieval-augmented approaches" (p. 12).
5. Configuration sensitivity (citing Simon et al. 2024, Agrawal et al. 2024): "even with
   careful tuning of retrieval components for the medical domain and question types,
   achieving reliable performance remains difficult" (p. 14).

### 3.9 The authors' recommendations and stated limitations

Recommendations (Sections 4.2–4.3): do not deploy RAG as a complete replacement; build "a
system for selective applications based on the characteristics of the question or the
confidence metrics"; invest in medical-specific RAG infrastructure, adaptive retrieval
(FLARE), multi-hop reasoning (RAPTOR), systematic configuration studies and "more
benchmarks for validating RAG system configurations in medical settings". Future datasets
should "better reflect the variability and contextual nature of real-world patient
queries", explicitly naming "multiple turns of dialogue" as something their study did not
cover (p. 13).

Limitations they state (Section 4.3): single NIDDK subset; LLM judge only moderately aligned
with the clinician and biased toward vanilla; clinical validation on 22 questions and one
annotator; question templates far simpler than real patient language.

### 3.10 What it means for us

- Their negative result is conditional on retrieval quality (P@5 = 0.15, MRR 0.31, Recall@5
  0.33 on a 240-chunk corpus) and on answers that live inside the model's parametric memory
  (English NIDDK content). Our retrieval places a relevant chunk in the top ten for 97.5% of
  10,000 questions on a corpus of tens of thousands of chunks, and our closed-book baseline
  reaches truthfulness 0.268 (Gemini) and −0.060 (Qwen3.5-9B) with 18–31% hallucinated
  answers, so the two preconditions for their result are both absent in our setting.
- Several of their recommendations are already components of our pipeline: a judge that
  checks sufficiency and triggers refinement (their "confidence metrics"), guard-based
  selective retrieval (small talk bypasses retrieval), abstention on unanswerable items, a
  calibrated judge with blind pharmacist labels and PPI rather than raw judge means.
- Their "partially relevant context distracts the LLM" finding is a direct motivation for
  reranking plus the judge-refine loop, and their 0.08–0.28 correlation between retrieval
  precision and answer quality is the reason to report retrieval and answer metrics side by
  side rather than infer one from the other.

---

## 4. Cross-paper synthesis

1. **Query adaptation is the cheapest lever in RAG.** Ma et al. show that a frozen-LLM
   rewrite recovers cases where retrieval hurts (HotpotQA) and raises the retrieval hit ratio
   more than the answer score (AmbigNQ 76.4 -> 77.5 -> 82.2). CHIQ shows that for
   conversational input the *history* fed to the rewriter matters as much as the rewriter:
   enhancing it closes most of the open-vs-closed-model gap (CAsT-20 MRR gap 12.1 -> 4.7).
   Our ablation (rephrase worth 0.114 truthfulness, 96% of follow-ups unanswered without it)
   is the end-to-end counterpart; what we lack is the retrieval-level ablation over rewrite
   variants that these two papers run.
2. **Retrieval quality thresholds decide whether RAG helps.** Ma et al.'s snippet setting
   (hit 61–64%) loses to closed-book while BM25 selection (hit 76–82%) wins. Fensore's
   P@5 = 0.15 loses. Kim et al. 2025 (22% relevant passages in the top 16) report RAG
   degrading factuality by up to 6%. Gilson et al. 2024 (ophthalmology, 70k documents) gain
   on reference factuality but lose slightly on accuracy. Our Hit@10 of 97.5% sits far above
   every one of these, which is the cleanest framing for why our RAG gain is large.
3. **Partial relevance is worse than no retrieval.** Fensore (Appendix E.3), Gilson
   (irrelevant documents "downgrade response accuracy and completeness") and Ma et al.
   (HotpotQA noise) all describe the same failure; our reranker and judge-refine loop are
   the mechanisms that address it, and the ablation shows the loop's effect.
4. **Evaluation must separate retrieval from reading.** Ma et al. use hit ratio plus EM;
   CHIQ uses MRR / NDCG@3 / Recall@10 with t-tests; Fensore uses P / R / nDCG / MRR plus a
   judge plus a blinded clinician. Our paper already follows this split, but the
   conversational part is only evaluated end to end on 50 items; a retrieval-level
   conversational benchmark is the missing piece.

---

## 5. Implications for our paper

### 5.1 Rewriting baselines and variants to add at the retrieval level

The paper currently evaluates rephrasing only end to end (ablation "w/o rephrase" and the
one-step RAG baseline on 50 multi-turn items). Both Ma et al. and CHIQ evaluate rewriting
*at the retriever*, with the same index, the same retriever and relevance labels, and that is
what the advisor is asking for. Recommended configurations, in increasing strength, each run
through our hybrid RRF (k = 2) + Qwen3-Reranker-4B stack on the same index:

| ID | Query fed to the retriever | Source / precedent | LLM calls per turn |
|---|---|---|---|
| Q0 | Last user turn as typed | our one-step RAG; CHIQ "default" fallback; Fensore | 0 |
| Q1 | Concatenation of all turns (questions and answers) as one query | ConvDR-style raw session input; TopiOCQA "AllHistory" baseline | 0 |
| Q1b | Concatenation of the last k = 2 turns + current turn | same, cheaper and the common dense-retrieval input | 0 |
| Q2 | Standalone rewrite from raw history (our current rephrase step) | Ma et al. "LLM as frozen rewriter"; CHIQ Eq. 1 on original history; T5QR analogue | 1 |
| Q3 | Standalone rewrite from CHIQ-enhanced history (QD + RE + PR + TS + HS by default) | CHIQ-AD | 5–6 |
| Q3a | Q3 without PR (no speculative answer) | our cheap-LLM constraint; CHIQ Table 5 shows PR is the riskiest facet | 4–5 |
| Q3b | Q2 where RE is replaced by the pipeline's own previous grounded answer and HS by our rolling summary | our pipeline already has both artefacts, so this costs 1 call | 1 |
| Q4 | Rewrite + pseudo answer concatenated (rewrite ⊕ PR) | CHIQ "+PR"; LLM4CS RAR; HyDE / Query2doc inside a conversation | 2 |
| Q5 | Multi-rewrite fusion: retrieve with Q2 and Q3 (or Q2 and Q4) separately and fuse the two rank lists | CHIQ-Fusion (CQE score fusion, alpha = 1); we would use RRF since the step already exists | 2–7 |
| Q6 | Oracle: the parent single-turn benchmark question as typed | human-rewrite upper bound in QReCC / CANARD evaluation; our benchmark gives it for free | 0 |

Why each is worth having: Q0 and Q6 bound the problem (what one-step RAG sees versus the
best possible rewrite). Q1 is the baseline reviewers from the IR side will ask for first,
and it tests whether the reranker alone can cope with history noise. Q2 is the current
pipeline. Q3 is the advisor's CHIQ request; Q3a/Q3b are the versions that respect our
"cheap LLM, one small structured decision per call" design and are the ones we would keep
if they match Q3. Q4 and Q5 test the expansion-and-fusion direction that CHIQ and LLM4CS
report as the strongest. Running Q2–Q5 with both Gemini (gemini-3.1-flash-lite, the model
our rephrase step uses) and Qwen3.5-9B reproduces CHIQ's open-vs-closed comparison (their
Table 3) in our domain.

How CHIQ evaluates them, mapped onto our protocol:
- Same off-the-shelf retriever for every query variant (they use BM25 and ANCE; we use
  hybrid RRF with and without the reranker so that the reranker's contribution to
  history-noise robustness is visible).
- Metrics MRR, NDCG@3, Recall@10 via pytrec_eval; we report Hit@3/5/10, MRR@10, nDCG@10
  with the same binary gains as the main benchmark, and CER@10 where the multi-turn item
  accumulates intents.
- Paired significance against every baseline (they use a t-test at p < 0.05; we keep the
  Holm-adjusted randomization test already used in Table 3 of the paper).
- Cost next to effectiveness: CHIQ argues CHIQ-FT is worth having because it removes LLM
  calls at inference; we should report LLM calls and tokens per rewrite for Q2–Q5 as we do
  for the end-to-end configurations.
- Error analysis by phenomenon (their Section 5.6 and Tables 9–10): rank of the gold section
  under each variant for a handful of items, including a case where enhancement hurts.

### 5.2 A fair conversational retrieval benchmark derived from the template benchmark

The 10,000-question benchmark already has what CHIQ's datasets have and Fensore's lacks:
every question is labelled with its gold section by construction. A conversational layer can
therefore be generated with rules, inherit the parent question's qrels unchanged, and need no
new relevance annotation. Design:

**Turn structure.** Each item is a short dialogue of two to four user turns with the
system's answers in between, and only the final turn is evaluated (as in TopiOCQA, QReCC and
CAsT). The system answers in the history must be fixed and identical for every variant
(the paper already does this for the 50 golden-set items); take them from the gold section
text (first one or two sentences of the gold section, or the reference answer where one
exists) so that the history is grounded and does not leak the final answer. Sample parent
questions from all six benchmark groups and all 17 intents, stratified by difficulty, so the
conversational set is a controlled transform of a known-difficulty single-turn set. A size of
1,000–2,000 items keeps the paired tests powerful at the 0.01–0.02 MRR level that CHIQ's
deltas live at.

**Phenomena (one label per item, so results can be broken down).** These correspond to the
ambiguity types CHIQ's five prompts target and to what Vietnamese users actually type:

1. *Drug pronoun / demonstrative*: the final turn refers to the drug of the previous turn by
   "thuốc này", "nó", "loại này" (our 50 golden-set items; CHIQ's QD target).
   Example: Q1 "Paracetamol có dùng được cho phụ nữ có thai không?" -> Q2 "Vậy thuốc này
   bảo quản ở nhiệt độ bao nhiêu?"
2. *Ellipsis / zero anaphora*: the subject is dropped entirely, which is the normal
   Vietnamese follow-up form. Example: "Còn liều cho trẻ em?" or "Có tương tác với rượu
   không?"
3. *Intent switch, same drug*: a new intent on the same drug with no reference at all,
   e.g. dosage then contraindication ("Chống chỉ định gồm những gì?").
4. *Drug switch, same intent*: the intent is inherited and only the drug changes ("Còn
   ibuprofen thì sao?"); the gold section is the new drug's section for the inherited intent.
5. *Reference to an entity introduced in the system answer*: the follow-up refers to a
   term that appears only in the previous answer, e.g. a side effect or an interacting drug
   named in the answer ("Tác dụng phụ đó có nguy hiểm không?", "Thuốc đó là thuốc gì?").
   This is the case CHIQ's RE prompt exists for, and the one where using our own grounded
   previous answer (Q3b) should shine.
6. *Topic switch*: the final turn names a new drug and a new intent; the correct behaviour
   is to ignore the history (CHIQ's TS; their largest effect on TopiOCQA). Include it so that
   rewrites that over-condition on history are penalised.
7. *Accumulated multi-intent*: the final turn asks for two intents, one inherited and one
   new ("và liều dùng nữa"), evaluated with CER@10 like the multi-intent group.
8. *Noisy follow-up*: phenomena 1–2 with missing diacritics or look-alike drug names, since
   noisy questions are our hardest group (Hit@10 54–83% before reranking).

Keep a *brand-name* subset (leaflet questions) in every phenomenon so that the
colloquial-name mapping is tested in context ("Panadol đỏ" in turn one, "thuốc này" in
turn two).

**Metrics.** Hit@3/5/10, MRR@10, nDCG@10 on the inherited qrels, CER@10 for phenomenon 7,
all with paired Holm-adjusted tests, broken down by phenomenon and by turn depth (2, 3, 4).
Two extra measures that CHIQ-style papers report and that we can compute for free: the
oracle gap (each variant minus Q6, the parent question as typed) and a rewrite-fidelity
score between the generated standalone query and the parent question (ROUGE-L or token
F1), which CANARD/QReCC use because human rewrites exist; here the parent question *is* the
human-quality rewrite. Report LLM calls and tokens per rewrite next to the metrics.

**Fairness rules.** Same index, retriever, reranker and fusion constant for every variant;
history fixed and identical; the rewriter never sees the gold section; the rewrite prompt
and its model fixed across variants (only the history preparation changes); results for
both the Gemini rewriter and Qwen3.5-9B; no fine-tuning on the benchmark (CHIQ-FT would be
future work and needs a train split).

**Naming.** Phrase it as the conversational layer of the existing benchmark (e.g. "the
conversational split") rather than a new dataset, because it reuses the templates and gold
labels; this also answers Fensore's call for datasets that include "multiple turns of
dialogue" while keeping answer locations known.

### 5.3 Framing our results against Fensore et al.

The point to make in the paper is not that Fensore is wrong but that their negative result
sits below a retrieval-quality threshold and above a parametric-knowledge threshold, and
our setting is on the other side of both.

Retrieval-quality threshold, with the evidence line:
- Fensore: P@5 = 0.15, MRR 0.31, Recall@5 0.33 -> vanilla wins on every metric.
- Ma et al.: hit ratio 61–64% (snippets) -> retrieval loses to closed-book on AmbigNQ
  (38.7 vs 42.1 EM); hit ratio 76–82% (BM25 selection) -> retrieval wins (45.8–47.8 EM).
- Kim et al. 2025: 22% of top-16 passages relevant, evidence selection precision 41–43% ->
  RAG lowers factuality by up to 6% and completeness by up to 5%; query reformulation and
  evidence filtering recover up to 12 points.
- Gilson et al. 2024: dense retrieval over 70k ophthalmology documents -> reference
  correctness 20.6% -> 54.5%, attribution 1.85 -> 2.49 / 5, but accuracy 3.52 -> 3.23 and
  completeness 3.47 -> 3.27 because irrelevant documents are passed to the model.
- Ours: Hit@10 97.5%, MRR@10 0.855 after reranking -> truthfulness 0.268 -> 0.923 and
  hallucinated answers 18.3% -> 1.0% (Gemini); 30.6% -> 1.2% (Qwen3.5-9B).

Parametric-knowledge threshold: Fensore's questions are English NIDDK templates about
common conditions, which Llama 3.1 70B answers well closed-book (judge 8.58, near the
reference answers' 8.66). Vietnamese formulary and leaflet content is long-tail for both
Gemini and Qwen3.5-9B, as our closed-book baselines show (truthfulness 0.268 and −0.060,
no abstention on unknown drugs). Soudani et al. 2024 and Mallen et al. 2023 make the same
point in general: retrieval helps most for low-popularity knowledge.

What they lacked that we have (each a sentence the paper can use):
1. A retrieval benchmark with answer locations known by construction (10,000 questions over
   the full corpus, versus 828 questions and 240 chunks with a 12-question tuning set).
2. A rephrase step with conversation history and a judge-refine loop, i.e. the "selective
   applications based on ... confidence metrics" they recommend (their RAG used a single
   fixed top-5 retrieval and a prompt that forbids outside knowledge).
3. A reranker that moves precision (they found reranking the only component that mattered,
   nDCG 0.287 -> 0.319; ours raises Hit@5 by 3.8 points and is run with a 4B model).
4. Abstention and safety cases (unanswerable, out-of-scope, injection), which they do not
   test; their RAG prompt's "acknowledge this" produced empty or refusing answers that were
   then penalised by BLEU and by the judge.
5. Nugget-level correctness and hallucination rates instead of BLEU / ROUGE, which they
   themselves say penalise RAG's shorter answers (188 vs 238 words).
6. A judge calibrated with 300 blind pharmacist labels and PPI, where they report 59%
   judge-clinician agreement on 66 pairs and a judge bias toward vanilla.
7. Multi-turn items, which they name as missing from their study.
8. An open-weight 9B model that matches the commercial one inside the pipeline, which
   speaks to their reproducibility concern.

Honest caveats to keep: our corpus is closed-domain and the questions are template-derived
with pharmacist-written golden items, so, like Fensore, we do not yet measure free-form
patient language at scale; the conversational split in 5.2 is the step toward that.

### 5.4 Further closely related works on "does RAG help medical / consumer health QA"

All verified as stated; the first two are already in `references.bib` (`xiong2024medrag`,
`nygren2026drug`) and are listed for completeness.

1. Guangzhi Xiong, Qiao Jin, Zhiyong Lu, Aidong Zhang. 2024. Benchmarking
   Retrieval-Augmented Generation for Medicine. *Findings of ACL 2024*, pages 6233–6251.
   DOI 10.18653/v1/2024.findings-acl.372. Verified on the ACL Anthology. MIRAGE: 7,663
   multiple-choice questions, 41 corpus / retriever / LLM combinations; MedRAG improves six
   LLMs "by up to 18% over chain-of-thought prompting"; a log-linear scaling with the
   number of snippets and a lost-in-the-middle effect. Use: the positive counterpart to
   Fensore, and the source of the "corpus and retriever choice matters" claim.
2. Aidan Gilson, Xuguang Ai, Thilaka Arunachalam, Ziyou Chen, Ki Xiong Cheong, Amisha
   Dave, Cameron Duic, Mercy Kibe, Annette Kaminaka, Minali Prasad, Fares Siddig, Maxwell
   Singer, Wendy Wong, Qiao Jin, Tiarnan D. L. Keenan, Xia Hu, Emily Y. Chew, Zhiyong Lu,
   Hua Xu, Ron A. Adelman, Yih-Chung Tham, Qingyu Chen. 2024. Enhancing Large Language
   Models with Domain-specific Retrieval Augment Generation: A Case Study on Long-form
   Consumer Health Question Answering in Ophthalmology. arXiv:2409.13902; PMC12478434;
   PMID 41031070. Verified through the Europe PMC record (PMC12478434 is the preprint
   deposit; no journal version was found on 2026-10-14, so cite the arXiv id). Study:
   ~70,000 documents (66,269 PubMed abstracts, 24 AAO Preferred Practice Patterns, 1,494
   EyeWiki articles), 1,024-token snippets, text-embedding-ada-002 dense retrieval, 100
   consumer questions, 10 healthcare professionals, 540 annotations per annotator on 30
   questions. Numbers: without RAG 252 references of which 45.3% hallucinated, 34.1% minor
   errors, 20.6% correct; with RAG 277 references, 54.5% correct, 26.7% minor errors, 18.8%
   hallucinated; only 62.5% of the top-10 retrieved documents were cited, mean rank 4.9;
   attribution 1.85 -> 2.49 (P < 0.001); accuracy 3.52 -> 3.23 (P = 0.03); completeness
   3.47 -> 3.27 (P = 0.17). Use: RAG fixes evidence hallucination but irrelevant documents
   cost accuracy; the model may ignore top-ranked documents.
3. Hyunjae Kim, Jiwoong Sohn, Aidan Gilson, ... , Hua Xu, Qingyu Chen (27 authors). 2025.
   Rethinking Retrieval-Augmented Generation for Medicine: A Large-Scale, Systematic Expert
   Evaluation and Practical Insights. arXiv:2511.06738 (v1, 10 November 2025). Verified on
   arXiv. 18 experts, 80,502 annotations, 800 outputs from GPT-4o and Llama-3.1-8B on 200
   patient and USMLE-style queries; "standard RAG often degraded performance"; 22% of the
   top-16 retrieved passages relevant; evidence-selection precision 41–43%, recall 27–49%;
   factuality down by up to 6% and completeness by up to 5% versus non-RAG; evidence
   filtering and query reformulation give up to +12 points on MedMCQA and +8.2 on
   MedXpertQA. Use: the strongest recent statement that retrieval and evidence selection are
   the failure points, and that query reformulation is the fix, which is our rephrase step.
4. Erfan Nourbakhsh, Rocky Slavin, Ke Yang, Anthony Rios. 2026. When Retrieval Doesn't
   Help: A Large-Scale Study of Biomedical RAG. *Proceedings of the 25th Workshop on
   Biomedical Natural Language Processing (BioNLP 2026)*, pages 890–910, San Diego.
   DOI 10.18653/v1/2026.bionlp-1.72. Verified on the ACL Anthology. Five open models
   (7B–72B), ten biomedical QA datasets, four retrievers, four corpora; retrieval gains
   "typically within 1–2 points"; the backbone matters far more than retriever or corpus;
   the bottleneck is the model's ability to use evidence. Use: the exam-style counterpart to
   Fensore; our gain is large precisely because the knowledge is absent from the model.
5. Cyril Zakka, Rohan Shad, Akash Chaurasia, Alex R. Dalal, Jennifer L. Kim, Michael Moor,
   Robyn Fong, Curran Phillips, Kevin Alexander, Euan Ashley, Jack Boyd, Kathleen Boyd,
   Karen Hirsch, Curt Langlotz, Rita Lee, Joanna Melia, Joanna Nelson, Karim Sallam, Stacey
   Tullis, Melissa Ann Vogelsong, John Patrick Cunningham, William Hiesinger. 2024.
   Almanac: Retrieval-Augmented Language Models for Clinical Medicine. *NEJM AI* 1(2).
   DOI 10.1056/AIoa2300068; PMID 38343631. Verified through Europe PMC (DOI and author
   list). 130 clinical scenarios judged by physicians; mean factuality gain of 18%. Use: a
   guideline-grounded clinical RAG with a positive expert evaluation.
6. Guangzhi Xiong, Qiao Jin, Xiao Wang, Minjia Zhang, Zhiyong Lu, Aidong Zhang. 2025.
   Improving Retrieval-Augmented Generation in Medicine with Iterative Follow-up Questions.
   *Pacific Symposium on Biocomputing* 30:199–214. DOI 10.1142/9789819807024_0015;
   PMID 39670371. Verified through Europe PMC. i-MedRAG lets the LLM ask follow-up queries
   over several rounds; zero-shot 69.68% on MedQA with GPT-3.5. Use: iterative retrieval in
   medicine, the closest published relative of our judge-refine loop.
7. Houman Kazemzadeh et al. (15 authors). 2025. DrugRAG: Enhancing Pharmacy LLM
   Performance Through A Novel Retrieval-Augmented Generation Pipeline. arXiv:2512.14896
   (v1 16 December 2025, v2 20 May 2026). Verified on arXiv; preprint only. 141 pharmacy
   licensure-style questions, ten LLMs at baseline (46–92%), five with RAG; gains of 7–21
   points (Llama 3.1 8B 46% -> 67%, Gemma 3 27B 61% -> 71%). Use: the only drug-information
   RAG result we found; multiple-choice and English, which leaves our open-ended Vietnamese
   setting uncovered.
8. Heydar Soudani, Evangelos Kanoulas, Faegheh Hasibi. 2024. Fine Tuning vs. Retrieval
   Augmented Generation for Less Popular Knowledge. *SIGIR-AP 2024*, pages 12–22. Citation
   taken from Fensore's reference list; confirm the DOI (ACM) before adding to the bib.
   Use: RAG helps most on low-popularity knowledge, which is our argument for why Vietnamese
   drug labelling differs from NIDDK content.
9. Nghia Trung Ngo, Chien Van Nguyen, Franck Dernoncourt, Thien Huu Nguyen. 2024.
   Comprehensive and Practical Evaluation of Retrieval-Augmented Generation Systems for
   Medical Question Answering. arXiv:2411.09213 (MedRGB). Verified on arXiv as a preprint;
   a retitled version appears at an AAAI 2026 workshop listing. Use only if a benchmark on
   noisy or insufficient retrieved context is needed; it finds current models handle noise
   and misinformation in retrieved documents poorly.
10. Haitao Li et al. 2025. LexRAG: Benchmarking Retrieval-Augmented Generation in
    Multi-Turn Legal Consultation Conversation. arXiv:2502.20640; reported as a SIGIR 2025
    resource paper (confirm the ACM DOI before citing). 1,013 expert-annotated five-round
    dialogues and 17,228 candidate legal articles, with conversational retrieval and
    generation tasks. Use: a template for a multi-turn RAG benchmark in a regulated domain;
    no medical equivalent was found, which strengthens the novelty of our conversational
    split.
11. Kelong Mao, Zhicheng Dou, Fengran Mo, Jiewen Hou, Haonan Chen, Hongjin Qian. 2023.
    Large Language Models Know Your Contextual Search Intent: A Prompting Framework for
    Conversational Search (LLM4CS). *Findings of EMNLP 2023*, pages 1211–1225.
    DOI 10.18653/v1/2023.findings-emnlp.86. Verified on the ACL Anthology. Use: the
    multi-rewrite plus pseudo-response aggregation baseline CHIQ compares against.
12. Conversational search datasets, as cited by CHIQ (bibliographic details from CHIQ's
    reference list): Adlakha et al. 2022, TopiOCQA, *TACL* 10:468–483; Anantha et al. 2021,
    QReCC, *NAACL 2021*, pages 520–534; Elgohary et al. 2019, CANARD, *EMNLP-IJCNLP 2019*,
    pages 5918–5924; Dalton et al. 2020/2021/2022, TREC CAsT overviews. Use: to say which
    turn structure and metrics our conversational split follows.

### 5.5 Exact sentences from the three papers for the related-work section

Ma et al. 2023 (EMNLP):
- "there is inevitably a gap between the input text and the knowledge that is really needed
  to query" (p. 5305).
- "The retrieval query is either original from datasets or directly determined by the
  black-box generation, thus is always fixed." (p. 5305)
- "On HotpotQA, the standard retrieval hurts the reader. This shows that using complex
  questions as queries cannot compensate for the parametric knowledge, but bring noises
  instead" (p. 5308).
- "We also observed that the improvement in the hit rate of the retriever is more
  significant than the improvement in the reader." (p. 5310)
- "a more powerful reader has more parametric memories, thus more difficult to compensate
  with external knowledge" (p. 5309).
- "Neural dense retrievers that are based on professional, filtered knowledge bases may
  potentially achieve better and controllable retrieval." (p. 5311)

Mo et al. 2024 (CHIQ):
- "One of the crucial steps is to compose adequate search queries for each context-dependent
  utterance." (p. 2253)
- "The key challenge is to unlock the full capabilities of open-source LLMs for
  conversational search. This requires carefully preparing the conversation history to
  enhance its quality, rather than directly using it to generate the search query."
  (p. 2253)
- "The contrasting observations between the two datasets suggest that enhancing the history
  is crucial for performance when no QR-supervised annotations exist." (p. 2259)
- "despite the superior reasoning abilities of closed-source LLM, enhancing the
  conversational history is deemed important for handling complex queries within
  conversational scenarios" (p. 2259).
- "conducting QR on enhanced conversational history helps to narrow the performance gap
  between open-source and closed-source LLMs" (p. 2259–2260).
- "we notice that while question disambiguation (QD) improves performance, it is less
  critical compared to predicting a pseudo response (PR) or enhancing the quality of the
  last system response (RE)" (p. 2260).
- "prompts such as PR and RE generation generally aid in retrieval, they may also introduce
  noisy terms due to the wrong fact generated by LLMs that hurt the ranking results"
  (p. 2260–2261).
- "instead of simply ask an LLM to generate a search query, it is critical to design
  strategies to generate different facets of enhancement in view of finding the target
  information" (p. 2261).

Fensore et al. 2025 (MLHC):
- "we find that vanilla LLM approaches consistently outperform RAG variants across both
  quantitative metrics (BLEU, ROUGE, BERTScore) and qualitative assessments" (abstract).
- "The relatively low retrieval performance (Precision@5 = 0.15) highlights fundamental
  challenges in implementing effective RAG systems for medical question-answering, even with
  carefully curated questions." (abstract)
- "successful implementation of RAG for consumer health question-answering requires more
  sophisticated approaches than simple retrieval and prompt engineering" (abstract).
- "only about 15% of the top-5 retrieved chunks contain information from the ground-truth
  document. This reveals a key challenge in consumer health QA: the semantic gap between how
  patients phrase questions and how medical information is presented in authoritative
  sources." (p. 9)
- "While real-world patient questions often involve colloquial language, multiple turns of
  dialogue, and complex personal context, our evaluation used the more structured MedQuAD
  format where questions follow 12 standard templates" (p. 13).
- "This aligns with recent work showing that naive RAG implementations can degrade LLM
  performance when retrieval quality is suboptimal (Agrawal et al., 2024), a problem likely
  to be exacerbated with more natural patient language." (p. 13)
- "a more practical approach might be to develop a system for selective applications based
  on the characteristics of the question or the confidence metrics" (p. 14).
- "LLMs were consistently distracted by irrelevant information in the retrieved context when
  part but not all of the context was relevant to answering the question" (p. 28).
- "it suggests that LLM-based judges may be overly conservative in their assessment of
  retrieval-augmented approaches" (p. 12).
- "Critically, there is a need for more benchmarks for validating RAG system configurations
  in medical settings, where errors can have serious consequences." (p. 14)

Gilson et al. 2024 (for the same paragraph):
- "irrelevant documents by RAG downgrade response accuracy and completeness, especially in
  challenging tasks such as long-form question answering" (abstract).
- "LLMs may not select top-ranked documents by RAG, which results in hallucinated evidence
  remaining" (abstract).

### 5.6 Concrete revision plan for the paper

Related work (one new paragraph, replaces nothing):
- Query rewriting for RAG: Ma et al. 2023 (rewrite-retrieve-read; frozen and trainable
  rewriter; retrieval gain exceeds reader gain); conversational query rewriting: T5QR /
  CONQRR lineage, LLM4CS, CHIQ (enhanced history closes the open-vs-closed gap). State that
  our rephrase step is the frozen-rewriter configuration over a rolling summary and that we
  add the CHIQ-style enhanced-history and fusion variants as retrieval-level baselines.
- "Does RAG help medical QA": Fensore 2025 (no, at P@5 0.15), Nourbakhsh 2026 (1–2 points
  on exam QA), Kim 2025 (degrades factuality when 22% of passages are relevant), Gilson
  2024 (fixes evidence, costs accuracy), Xiong 2024 and Zakka 2024 (yes, with good
  retrieval); conclude that the answer depends on retrieval precision and on whether the
  knowledge is parametric, and that Vietnamese drug labelling with Hit@10 97.5% is the
  favourable case. Mention DrugRAG as the only drug-information RAG result and that it is
  multiple-choice English.

Experiments (new retrieval-level table, two to four paragraphs):
- Build the conversational split (Section 5.2) from the template benchmark; report size and
  phenomenon distribution in the evaluation-sets subsection.
- Run Q0, Q1, Q2, Q3, Q3b, Q5 and Q6 with the hybrid + reranker stack; Gemini and
  Qwen3.5-9B rewriters; Hit@3/5/10, MRR@10, nDCG@10, CER@10, paired Holm tests, LLM calls
  and tokens per rewrite; breakdown by phenomenon and turn depth.
- Keep the 50 golden-set multi-turn items as the end-to-end check and cite the new table as
  the retrieval-level explanation of the 96% / 88% unanswered rate.

Discussion:
- One paragraph on the retrieval-quality threshold using the evidence line in Section 5.3.
- One sentence acknowledging that partially relevant context harms answers (Fensore,
  Gilson) and pointing to the judge-refine ablation (+0.028 truthfulness, −2.1 points
  missing) as the mitigation.

Bib entries to add (verified ones ready to paste):

```bibtex
@inproceedings{ma2023rewrite,
  title     = {Query Rewriting in Retrieval-Augmented Large Language Models},
  author    = {Ma, Xinbei and Gong, Yeyun and He, Pengcheng and Zhao, Hai and Duan, Nan},
  booktitle = {Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing},
  pages     = {5303--5315},
  year      = {2023},
  address   = {Singapore},
  publisher = {Association for Computational Linguistics},
  doi       = {10.18653/v1/2023.emnlp-main.322}
}

@inproceedings{mo2024chiq,
  title     = {{CHIQ}: Contextual History Enhancement for Improving Query Rewriting in Conversational Search},
  author    = {Mo, Fengran and Ghaddar, Abbas and Mao, Kelong and Rezagholizadeh, Mehdi and Chen, Boxing and Liu, Qun and Nie, Jian-Yun},
  booktitle = {Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing},
  pages     = {2253--2268},
  year      = {2024},
  address   = {Miami, Florida, USA},
  publisher = {Association for Computational Linguistics},
  doi       = {10.18653/v1/2024.emnlp-main.135}
}

@inproceedings{fensore2025rag,
  title     = {Does Domain-Specific Retrieval Augmented Generation Help {LLM}s Answer Consumer Health Questions?},
  author    = {Fensore, Chase M. and Carrillo-Larco, Rodrigo M. and Shah, Megha K. and Ho, Joyce C.},
  booktitle = {Proceedings of the 10th Machine Learning for Healthcare Conference},
  series    = {Proceedings of Machine Learning Research},
  volume    = {298},
  pages     = {1--33},
  year      = {2025},
  publisher = {PMLR},
  url       = {https://proceedings.mlr.press/v298/fensore25a.html}
}

@misc{gilson2024ophthalmology,
  title         = {Enhancing Large Language Models with Domain-specific Retrieval Augment Generation: A Case Study on Long-form Consumer Health Question Answering in Ophthalmology},
  author        = {Gilson, Aidan and Ai, Xuguang and Arunachalam, Thilaka and Chen, Ziyou and Cheong, Ki Xiong and Dave, Amisha and Duic, Cameron and Kibe, Mercy and Kaminaka, Annette and Prasad, Minali and Siddig, Fares and Singer, Maxwell and Wong, Wendy and Jin, Qiao and Keenan, Tiarnan D. L. and Hu, Xia and Chew, Emily Y. and Lu, Zhiyong and Xu, Hua and Adelman, Ron A. and Tham, Yih-Chung and Chen, Qingyu},
  year          = {2024},
  eprint        = {2409.13902},
  archivePrefix = {arXiv},
  note          = {PMC12478434}
}

@misc{kim2025rethinking,
  title         = {Rethinking Retrieval-Augmented Generation for Medicine: A Large-Scale, Systematic Expert Evaluation and Practical Insights},
  author        = {Kim, Hyunjae and Sohn, Jiwoong and Gilson, Aidan and Cochran-Caggiano, Nicholas and Applebaum, Serina and Jin, Heeju and Park, Seihee and Park, Yujin and Park, Jiyeong and Choi, Seoyoung and Herrera Contreras, Brittany Alexandra and Huang, Thomas and Yun, Jaehoon and Wei, Ethan F. and Jiang, Roy and Colucci, Leah and Lai, Eric and Dave, Amisha and Guo, Tuo and Singer, Maxwell B. and Koo, Yonghoe and Adelman, Ron A. and Zou, James and Taylor, Andrew and Cohan, Arman and Xu, Hua and Chen, Qingyu},
  year          = {2025},
  eprint        = {2511.06738},
  archivePrefix = {arXiv}
}

@inproceedings{nourbakhsh2026retrieval,
  title     = {When Retrieval Doesn't Help: A Large-Scale Study of Biomedical {RAG}},
  author    = {Nourbakhsh, Erfan and Slavin, Rocky and Yang, Ke and Rios, Anthony},
  booktitle = {Proceedings of the 25th Workshop on Biomedical Natural Language Processing (BioNLP 2026)},
  pages     = {890--910},
  year      = {2026},
  address   = {San Diego, California},
  publisher = {Association for Computational Linguistics},
  doi       = {10.18653/v1/2026.bionlp-1.72}
}

@article{zakka2024almanac,
  title   = {Almanac: Retrieval-Augmented Language Models for Clinical Medicine},
  author  = {Zakka, Cyril and Shad, Rohan and Chaurasia, Akash and Dalal, Alex R. and Kim, Jennifer L. and Moor, Michael and Fong, Robyn and Phillips, Curran and Alexander, Kevin and Ashley, Euan and Boyd, Jack and Boyd, Kathleen and Hirsch, Karen and Langlotz, Curt and Lee, Rita and Melia, Joanna and Nelson, Joanna and Sallam, Karim and Tullis, Stacey and Vogelsong, Melissa Ann and Cunningham, John Patrick and Hiesinger, William},
  journal = {NEJM AI},
  volume  = {1},
  number  = {2},
  year    = {2024},
  doi     = {10.1056/AIoa2300068}
}

@inproceedings{xiong2025imedrag,
  title     = {Improving Retrieval-Augmented Generation in Medicine with Iterative Follow-up Questions},
  author    = {Xiong, Guangzhi and Jin, Qiao and Wang, Xiao and Zhang, Minjia and Lu, Zhiyong and Zhang, Aidong},
  booktitle = {Pacific Symposium on Biocomputing},
  volume    = {30},
  pages     = {199--214},
  year      = {2025},
  doi       = {10.1142/9789819807024_0015}
}

@misc{kazemzadeh2025drugrag,
  title         = {{DrugRAG}: Enhancing Pharmacy {LLM} Performance Through A Novel Retrieval-Augmented Generation Pipeline},
  author        = {Kazemzadeh, Houman and Mokhtari Dizaji, Kiarash and Tavakoli, Seyed Reza and Davoodi, Farbod and KarimiNejad, MohammadReza and Abed Azad, Parham and Latifi, Fatemeh and Sabzi, Ali and Khosravi, Armin and Ahmadi, Siavash and Khalaj, Babak and Rohban, Mohammad Hossein and Aminian, Glolamali and Amoozgar, Zohreh and Javaheri, Tahereh},
  year          = {2025},
  eprint        = {2512.14896},
  archivePrefix = {arXiv}
}

@inproceedings{mao2023llm4cs,
  title     = {Large Language Models Know Your Contextual Search Intent: A Prompting Framework for Conversational Search},
  author    = {Mao, Kelong and Dou, Zhicheng and Mo, Fengran and Hou, Jiewen and Chen, Haonan and Qian, Hongjin},
  booktitle = {Findings of the Association for Computational Linguistics: EMNLP 2023},
  pages     = {1211--1225},
  year      = {2023},
  address   = {Singapore},
  publisher = {Association for Computational Linguistics},
  doi       = {10.18653/v1/2023.findings-emnlp.86}
}
```

Entries still to verify before use: Soudani et al. 2024 (SIGIR-AP, pages 12–22, DOI not
checked), LexRAG (SIGIR 2025 DOI not checked; arXiv 2502.20640 is safe), MedRGB
(arXiv 2411.09213 only), TopiOCQA / QReCC / CANARD (details copied from CHIQ's reference
list; the Anthology pages should be checked when the bib is edited).

## 6. Verification log

| Item | How verified | Status |
|---|---|---|
| Ma et al. 2023 citation | ACL Anthology page 2023.emnlp-main.322 | verified (pages 5303–5315, DOI) |
| Mo et al. 2024 citation | ACL Anthology page 2024.emnlp-main.135 | verified (pages 2253–2268, DOI) |
| Fensore et al. 2025 citation | PMLR v298 page and PDF header | verified (PMLR 298:1–33, no DOI) |
| CHIQ prompts | PDF Appendix A and `generation/enhancement_generation.py` | verified; code wording differs slightly from the appendix; code temperature 0.6 vs paper 0.7 |
| CHIQ fusion | `dense/fusion.py` | verified; CQE_hybrid default, alpha 0.4 in script vs 1 in paper |
| Xiong 2024 MIRAGE | ACL Anthology 2024.findings-acl.372 | verified |
| Gilson 2024 | Europe PMC record and full text for PMC12478434 | verified as arXiv preprint; no journal version found |
| Kim 2025 | arXiv abstract page 2511.06738 | verified (preprint) |
| Nourbakhsh 2026 | ACL Anthology 2026.bionlp-1.72 | verified |
| Zakka 2024 Almanac | Europe PMC DOI lookup | verified (NEJM AI 1(2), DOI, PMID) |
| Xiong 2025 i-MedRAG | Europe PMC title lookup | verified (PSB 30:199–214, DOI, PMID) |
| Kazemzadeh 2025 DrugRAG | arXiv abstract page 2512.14896 | verified (preprint) |
| Mao 2023 LLM4CS | ACL Anthology bib 2023.findings-emnlp.86 | verified |
| Soudani 2024, LexRAG 2025, MedRGB 2024, TopiOCQA, QReCC, CANARD | search results and the papers' own reference lists | partly verified; check DOIs before adding |
