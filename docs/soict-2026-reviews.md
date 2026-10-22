# SoICT 2026 reviews, paper 1360

Nguyên văn bốn review trong thư chấp nhận (oral). Camera-ready hạn 30/10/2026, 12–15 trang, phải có permission statement.

```text
----------------------- REVIEW 1 ---------------------

SUBMISSION: 1360
TITLE: Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical Documents

----------- Overall evaluation -----------
The paper presents a useful Vietnamese pharmaceutical corpus, a 10,000-question retrieval benchmark, and a carefully evaluated agentic RAG pipeline. The experimental design is a clear strength, particularly the retrieval comparison, ablation studies, statistical testing, judge calibration, and evaluation with both commercial and open-weight models.

However, the methodological novelty of the agentic RAG pipeline is limited. Most components—query rewriting, hybrid retrieval, reranking, evidence judging, iterative refinement, and citation-based generation—are established techniques, so the contribution is stronger as a resource and system evaluation paper than as a new RAG methodology.

Areas for Improvement
- Clarify the novelty and position the main contribution more explicitly around the Vietnamese pharmaceutical benchmark, reproducible system design, and comprehensive evaluation rather than a fundamentally new agentic RAG architecture.
- The retrieval benchmark is largely rule/template-generated, which may make it more regular than real patient questions. This limitation should be emphasized more clearly.
- The ablation results suggest that much of the gain over one-step RAG comes from query rephrasing, especially for multi-turn questions, while the judge–refine loop provides a smaller improvement. This should be discussed more explicitly.
- A simpler conversational retrieval baseline, such as directly appending previous turns to the search query, would strengthen the analysis because the paper currently leaves this alternative untested.
- The safety evaluation is based on only 10 examples for each of the unanswerable, out-of-scope, and prompt-injection categories, so strong robustness claims should be avoided.
- The golden set and blind evaluation rely on a single pharmacist, which limits the reliability of the medical evaluation. This should be stated more prominently as a limitation.


----------------------- REVIEW 2 ---------------------

SUBMISSION: 1360
TITLE: Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical Documents

----------- Overall evaluation -----------
The paper builds a Vietnamese drug-information corpus, a 10,000-question template-generated retrieval benchmark and a 500-item end-to-end set, compares sparse, dense, hybrid and reranked retrieval with cost reported alongside effectiveness, and proposes an agentic RAG pipeline that keeps control flow in code and limits each LLM call to one small structured decision, evaluated with Gemini 3.8 Flash and Qwen3.5-9B. Below i list out some of the strengths and weaknesses for the paper.

Strengths.

- Dedicated Vietnamese drug-information benchmark, with corpus, golden set and all run outputs released.
- The retrieval study is useful, and the evaluation protocol is rigorous

Weaknesses.

- Even though i vote for accept, the methodological novelty is modest. Guard, rewrite, hybrid search, rerank, judge, refine is a standard agentic RAG recipe; the contribution is the resource and the evaluation, and the framing should say so.
- The one-step RAG baseline is weak by construction on multi-turn items (it searches the last turn as typed), so the headline advantage on follow-ups is against a strawman. The authors name the obvious remedy (appending history to the query) but do not run it, although the rephrase ablation accounts for most of the one-step gap.
- The judge-refine loop yields small performance for about 40% more tokens and nearly double the LLM calls, and removing the reranker changes no end-to-end metric, which weakens the practical relevance of the reranker comparison.
- Benchmark and the 420 single-turn golden items are template-generated from the same corpus whose chunks are enriched with the same colloquial mappings, so near-saturated scores (Hit@30 99.2%) likely overstate performance on real patient questions. The fusion constant and the reranker instruction are tuned on the same benchmark.
- Citation recall of 0.70 to 0.72 means over a quarter of content sentences are not supported by the passage they cite, a serious issue in a domain motivated by traceability, and it is not analysed.
- Safety cases use 10 items each, too few to support "resists all injections" claims


----------------------- REVIEW 3 ---------------------

SUBMISSION: 1360
TITLE: Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical Documents

----------- Overall evaluation -----------
The paper is carefully executed and provides a potentially useful Vietnamese pharmaceutical retrieval benchmark. The retrieval study, cost analysis, ablations, paired statistical tests, and human calibration of the automatic judge are stronger than average. However, the methodological novelty of the agentic pipeline is limited: it combines standard components including query rewriting, hybrid retrieval, reranking, evidence judging, refinement, and guarded generation. More importantly, the main advantage over one-step RAG is heavily driven by multi-turn questions where the baseline searches only the final user utterance without resolving pronouns. The authors report that one-step RAG leaves 96% of Gemini multi-turn questions unanswered, while query rewriting restores the referenced drug name. A much stronger and cheaper baseline—e.g., retrieval using conversational context or concatenated previous turns—is not tested.
The evaluation data are also relatively controlled: the 10,000 retrieval questions are template-generated, the 500-item golden set is created by the first author with one pharmacist, and only one pharmacist provides blind grading. The safety subsets contain only ten examples each, producing very wide confidence intervals. The paper itself also notes that the RRF fusion constant is selected on the same benchmark.
I find the dataset and evaluation valuable, but the claimed agentic advantage needs a stronger conversational-RAG baseline and more independent clinical evaluation.


----------------------- REVIEW 4 ---------------------

SUBMISSION: 1360
TITLE: Agentic Retrieval-Augmented Generation for Vietnamese Pharmaceutical Documents

----------- Overall evaluation -----------
The paper builds a Vietnamese drug-information corpus (the 2018 National Drug Formulary plus 2,406 package leaflets) and a 10,000-question rule-generated retrieval benchmark with answer locations known by construction. It systematically compares BM25, dense, hybrid RRF and reranked retrieval, then proposes an agentic pipeline that keeps control flow in code and restricts every LLM call to one small structured decision. The pipeline is evaluated end to end on a 500-item golden set.

Strengths: The paper contributes a resource that fills a real gap, since no benchmark exists for Vietnamese drug labelling. The evaluation protocol is unusually complete: CRAG-style answer classes that penalise hallucination more than abstention, nugget recall, faithfulness, citation recall, safety cases, paired randomization tests with Holm correction, Wilson and bootstrap intervals, and judge calibration via prediction-powered inference against blind pharmacist grades.

Limitations:
1. The one-step RAG baseline is too weak for multi-turn questions. Most of the agent's advantage comes from rephrasing on the 50 follow-up questions, where one-step RAG leaves 96% unanswered;
2.      Tuning on the test set. The fusion constant k = 2 is selected on the same benchmark used for reporting, and it is unclear whether the 1,000-question reranker-instruction pilot is disjoint from the benchmark. A dev/test split, or results with k fixed in advance, should be provided.
```
