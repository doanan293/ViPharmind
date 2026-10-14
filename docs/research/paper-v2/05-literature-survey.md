# Literature survey (2023-2026): quality, latency and cost of agentic RAG over Vietnamese drug information with cheap models

Compiled 2026-10-14 for the ViPharmind paper (report/). Scope: the six threads requested by the authors, plus the primary sources for the models the paper uses (Qwen3.5, Gemini 3.8 Flash, TypeSafe Jev).

## How to read this file

Every entry has the form

- **Status.** VERIFIED means the paper page (arXiv abstract page, ACL Anthology, publisher page, official blog) was opened during this survey and the authors, title, venue, year and identifier were read from it. PARTIAL means the page was opened but some field (venue, final author order, numbers) could not be confirmed from it. UNVERIFIED means the work is known only from secondary sources or from search snippets; cite it only after opening the page yourself.
- **Citation.** Authors, title, venue, year, arXiv id and/or DOI.
- **Summary.** One paragraph on method and findings, with numbers where the paper reports them.
- **Relation to ours.** What our paper adds or why we cite it.

Numbers quoted from abstracts are reproduced as the abstract states them. Where a number comes from the full text or from a third party, the entry says so.

## The paper's claims that this survey has to position

1. **Decision steps on a decision model, generation steps on a small LLM.** Guardrail, evidence-sufficiency judge and per-intent coverage are decision-only steps. They run on a tiny non-generative "decision model" (TypeSafe Jev or an open-weight equivalent) that returns a typed answer with a calibrated probability. Query rewrite, refine and answer run on a small generative LLM.
2. **Confidence-gated refinement.** The retrieve-more loop runs only when the judge's calibrated probability of "evidence sufficient" falls below a threshold. Sweeping the threshold gives a cost-versus-quality Pareto curve.
3. **Controlled workflow-versus-agent comparison across model sizes.** The same tools and corpus are run under a code-controlled workflow (fixed step order, every model call is one small structured decision) and under a ReAct-style autonomous tool-calling agent, with Qwen3.5 2B, 4B, 9B, 27B and Gemini 3.8 Flash, to find the model size at which autonomous planning catches up with the fixed workflow.
4. **Quality, latency and cost reported together** for every configuration, in a Vietnamese pharmaceutical setting with multi-turn conversational questions.

## Summary of what the literature already covers and what it does not

- The workflow-versus-agent distinction is now standard (Anthropic 2024) and has a few 2025-2026 empirical comparisons (Kumar et al. 2026 on 19 benchmarks with one large model; Gray et al. 2025 on code translation at three model scales; Zhang et al. 2026 on information extraction with one 7B model). None of them runs the comparison on a RAG task, with a ladder of small open-weight models, and reports quality, latency and cost together. AgentFloor (Karmakar and Chatterjee 2026) gives the closest capability ladder for small open-weight agents but on synthetic tool tasks, not RAG.
- Adaptive retrieval is a mature thread (FLARE, Self-RAG, Adaptive-RAG, DRAGIN, CRAG, SKR, SEAKR, Rowen, UAR). Training-free, threshold-based stopping for iterative retrieval appeared in 2025-2026 (TARG, TASR, HALT, Stop-RAG). All of these gate on the generator's own logits or on a trained controller; none gates on an external calibrated decision model, none reports a cost-quality Pareto curve by sweeping the gate threshold on a small-model pipeline, and none works in Vietnamese.
- Cost-aware evaluation of agents is argued for by Kapoor et al. (2024) and implemented in routing and cascade work (FrugalGPT, RouteLLM, AutoMix, UCCI 2026). Latency is rarely reported for RAG pipelines outside systems papers (RAGCache, RAGO) and a handful of medical works (Nygren et al. 2026). No work reports quality, latency and dollar cost per configuration for an agentic RAG pipeline on small models.
- "Decision models" became a product category in September-October 2026 (TypeSafe Jev, AWS Strands Decider 2B, Liquid AI d1, Microsoft Decision-1, plus community clones). Independent evaluations exist for annotation (Ibrahim and Zaki 2026), alignment-failure detection (Guo et al. 2026), crash-report coding (Rafe and Das 2026) and, negatively, for guardrails (Azizi et al. 2026). No published work uses a decision model inside a RAG control loop, as the evidence-sufficiency judge, or measures the effect of its calibration on a retrieve-more gate.
- Conversational RAG benchmarks (MTRAG, CORAL, ChatRAG-Bench) and conversational query rewriting (T5QR, ConvGQR, LLM4CS, InstructoR, CHIQ, IterCQR, AdaCQR) give the standard baselines for our rephrase comparison. None is Vietnamese or pharmaceutical.
- Vietnamese resources cover embeddings (VN-MTEB), general medical QA (ViMQ, ViHealthQA, ViMedAQA, UIT-ViCoQA) and legal retrieval. No Vietnamese drug-information RAG benchmark or agentic RAG evaluation exists.


## A. Workflows versus autonomous agents

### A.1 Foundations: the taxonomy, ReAct, the small-model position, and the agentic RAG survey

#### Anthropic 2024, "Building effective agents" — VERIFIED (https://www.anthropic.com/engineering/building-effective-agents)

- **Citation.** Erik Schluntz, Barry Zhang (Anthropic). "Building effective agents." Anthropic engineering blog, 19 December 2024. No arXiv id or DOI; cite the URL with an access date.
- **Summary.** Defines workflows as "systems where LLMs and tools are orchestrated through predefined code paths" and agents as systems where "LLMs dynamically direct their own processes and tool usage"; the dividing line is who decides the step sequence. The augmented LLM (retrieval, tools, memory) is the building block, and five workflow patterns are named: prompt chaining, routing, parallelization (sectioning and voting), orchestrator-workers and evaluator-optimizer, followed by autonomous agents. The advice is to find "the simplest solution possible, and only increasing complexity when needed", to prefer workflows for well-defined tasks where predictability matters, and to reserve agents for open-ended problems where the number of steps cannot be fixed in advance. The post is a practitioner essay without benchmarks.
- **Relation to ours.** This is the taxonomy the paper should adopt and name. Our "graph routing" condition is a routing plus evaluator-optimizer workflow with the loop gated by a calibrated judge, and our ReAct condition is their "agent". The post gives guidance without measurements; we give the measurement (quality, latency, cost) for both sides of the line across model sizes.

#### Yao et al. 2023, ReAct — VERIFIED (https://arxiv.org/abs/2210.03629)

- **Citation.** Shunyu Yao, Jeffrey Zhao, Dian Yu, Nan Du, Izhak Shafran, Karthik Narasimhan, Yuan Cao. "ReAct: Synergizing Reasoning and Acting in Language Models." ICLR 2023. arXiv:2210.03629.
- **Summary.** Interleaves free-form reasoning traces with actions so that reasoning plans and revises the action sequence while actions pull observations from the environment. On HotpotQA and FEVER with a Wikipedia API it reduces hallucination and error propagation relative to chain-of-thought, and on ALFWorld and WebShop it beats imitation and RL methods by 34 and 10 absolute success points with one or two in-context examples. The model chooses the number and order of tool calls, which is the autonomous end of the spectrum.
- **Relation to ours.** ReAct is our autonomous baseline, implemented with native tool calling. We ask at which model size a ReAct loop matches a fixed workflow on a Vietnamese drug-information task and what it costs in latency and tokens.

#### Belcak et al. 2025, "Small Language Models are the Future of Agentic AI" — VERIFIED (https://arxiv.org/abs/2506.02153)

- **Citation.** Peter Belcak, Greg Heinrich, Shizhe Diao, Yonggan Fu, Xin Dong, Saurav Muralidharan, Yingyan Celine Lin, Pavlo Molchanov (NVIDIA). "Small Language Models are the Future of Agentic AI." arXiv:2506.02153, v1 2 Jun 2025, v3 22 Sep 2026. Position paper, no venue.
- **Summary.** Argues that small language models are sufficiently capable, operationally better suited and far cheaper for the many narrow, repetitive sub-tasks inside agentic systems, that heterogeneous systems should route only open-ended conversation to large models, and gives an LLM-to-SLM conversion algorithm (log calls, cluster, fine-tune specialists). The abstract has no benchmark numbers; the contribution is the position and the economics argument, and the authors invite and publish critiques.
- **Relation to ours.** We implement the heterogeneous split they advocate, with a non-generative decision model for the decision steps and a small LLM for generation, and measure it end to end on a real domain with latency and cost, which the position paper does not.

#### Singh et al. 2025/2026, "Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG" — VERIFIED (https://arxiv.org/abs/2501.09136)

- **Citation.** Aditi Singh, Abul Ehtesham, Saket Kumar, Tala Talaei Khoei, Athanasios V. Vasilakos. "Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG." arXiv:2501.09136, v1 15 Jan 2025, v4 1 Apr 2026. No venue listed.
- **Summary.** Surveys systems that embed agents (reflection, planning, tool use, multi-agent collaboration) in the RAG pipeline and proposes a taxonomy along four axes: agent cardinality, control structure, degree of autonomy and knowledge representation. It compares design trade-offs across frameworks, reviews applications in healthcare, finance, education and enterprise documents, and lists open challenges in evaluation, coordination, memory management, efficiency and governance. No quantitative results.
- **Relation to ours.** The "control structure" and "degree of autonomy" axes are exactly the two conditions we compare, and "efficiency" and "evaluation" are the open challenges we address with a cost-and-latency-reporting evaluation. Cite it as the framing survey.


### A.2 Empirical comparisons of fixed workflows and autonomous agents (2025-2026)

These are the works that most directly bear on contribution 3. All were opened on arXiv during this survey.

#### Kumar et al. 2026, "Learning to Construct Practical Agentic Systems" — VERIFIED (https://arxiv.org/abs/2606.00189)

- **Citation.** Aditya Kumar, Zhihan Lei, Jerry Yan, Joshua W. Momo, Lauhitya Reddy, Rafael Enrique Cabrera Jimenez, Cassandra A. Cohen, Arthur Kajiyama, William W. Cohen. "Learning to Construct Practical Agentic Systems." arXiv:2606.00189, v1 29 May 2026, v2 6 Sep 2026. No venue listed.
- **Summary.** The paper builds agents from "pseudo-tools" (LLM calls on a restricted context) and compares hand-constructed fixed workflows with a dynamically planned ReAct loop that uses the same tools, on 19 benchmarks (BBH, FinQA, MedAgentBench, MuSR, NaturalPlan, RuleArena, tau-bench and others), all with DeepSeek-V3.1. Averaged over the 19 benchmarks (Table 1 of the full text), the fixed workflow reaches accuracy 0.64 at $0.70 per 100 instances, the ReAct loop 0.56 at $1.66, and a zero-shot prompt 0.47 at $0.44. Fixed workflows were more accurate on 12 of 19 benchmarks and cheaper on all 19, with an average cost gap above a factor of two that the authors call the "agentic tax". Dynamic workflows were fragile because tool and pseudo-tool calls failed on syntax or semantic errors, and "the flexibility of an agent loop comes at the price of unpredictability in cost and performance". The paper then learns the fixed workflows and applies NSGA-II multi-objective search to trade cost against quality, finding configurations with similar quality at about one seventh of the cost. Caveat stated in the paper: the fixed workflows were hand-tuned on validation data for about six weeks while the ReAct baseline was not tuned.
- **Relation to ours.** This is the strongest published evidence that a fixed workflow beats a ReAct loop in both accuracy and cost, and it also reports a cost-quality Pareto search, so it should be cited next to Anthropic's taxonomy. It uses one large model (DeepSeek-V3.1) and no retrieval task. Our comparison holds the task fixed (Vietnamese drug RAG), varies the model from 2B to 27B plus a commercial model, and adds latency, so it answers the question this paper leaves open, namely whether the "agentic tax" shrinks or grows as the model gets smaller.

#### Gray, Yotam and Udrea 2025, "Workflows vs Agents for Code Translation" — VERIFIED (https://arxiv.org/abs/2512.14762)

- **Citation.** Henry Gray, Tom Yotam, Octavian Udrea. "Workflows vs Agents for Code Translation." NeurIPS 2025 Fourth Workshop on Deep Learning for Code. arXiv:2512.14762, 15 Dec 2025.
- **Summary.** The paper repairs syntax errors in a MATLAB-to-HDL translation pipeline either with a fixed expert-written workflow or with an MCP-based agent that chooses its own tools, over 42 signal-processing functions and three model scales (8B, 30B, 235B). The agent fixes more initial syntax errors and so pushes more candidates downstream; the largest effect is at mid scale, where simulation reach rate rises by over 20 percentage points. The authors attribute the gain to short prompts, aggressive context management and conditional tool use, and note that naive inclusion of tools was harmful at small scale while on-demand tool use helped at 8B and 30B. At 235B the final-success gains were small and a naive RAG variant had the highest final success. They conclude that well-designed agentic frameworks are most useful for compensating the limited capacity of small and mid-sized models.
- **Relation to ours.** This is the main published result pointing the other way, namely that agency helps small and mid-sized models more than large ones, on a code task where tools can verify outputs. Our paper should cite it as the counter-case and state the difference: in RAG the tools (retrieval) do not verify the answer, and in our setting the fixed workflow wins at small scale and the agent only catches up at larger scale. Reporting at which size the crossover happens is what our comparison adds.

#### Zhang, Chen and Feng 2026, "Behavioral Controllability of Agentic Models for Information Extraction: From Fixed Workflows to Reflective Agents" — VERIFIED (https://arxiv.org/abs/2607.15715)

- **Citation.** Lujia Zhang, Xingzhou Chen, Hongwei Feng. "Behavioral Controllability of Agentic Models for Information Extraction: From Fixed Workflows to Reflective Agents." arXiv:2607.15715, v1 17 Jul 2026, v2 29 Jul 2026. No venue listed.
- **Summary.** The task is dataset-mention extraction from NeurIPS 2024 papers with a 7B model (openPangu-Embedded-7B via vLLM). The fixed workflow S0 (parse, metadata, dataset names, per-dataset details) is compared with ReAct-style agents that add rule-based reflection, quality-aware retry and memory (S1a) and LLM reflection (S1b). Over up to 50 papers, S0 yields 158 records (3.76 per paper), S1a 165 and S1b 168, with link grounding under 20% for all. The agent logs are seven times longer (50,189 versus 7,084 lines). The authors present the comparison as descriptive without statistical testing and conclude that the workflow "remains attractive for cheap, predictable batch extraction" while agents help on heterogeneous inputs and give an inspectable process trace.
- **Relation to ours.** A one-model, one-task comparison with small effects; it shows the question is open at the 7B scale. Our design adds the size ladder, the RAG task and the latency-cost axis, and uses paired statistical tests.

#### Karmakar and Chatterjee 2026, "AgentFloor: How Far Up the Tool-Use Ladder Can Small Open-Weight Models Go?" — VERIFIED (https://arxiv.org/abs/2605.00334)

- **Citation.** Ranit Karmakar, Jayita Chatterjee. "AgentFloor: How Far Up the tool use Ladder Can Small Open-Weight Models Go?" arXiv:2605.00334, 1 May 2026. No venue listed.
- **Summary.** AgentFloor is a 30-task, six-tier ladder (A0 instruction following, A single tool, B two-tool chain, C branching, D multi-source synthesis with recovery, E long-horizon planning) run on 16 open-weight models from 0.27B to 32B plus GPT-5, 16,542 scored runs. From Table 2 of the full text, Qwen3.5-2B scores 44/68/80/40/32/0 on A0 to E, Qwen3-8B 80/76/64/24/0/0, Gemma4-26B 100/96/72/59/32/0, Qwen3-32B 76/96/72/36/9/0 and GPT-5 80/98/82/51/42/10. The steepest drop for every model is from tier B (two-tool chain) to tier C (branching), and tier E stays near zero for all open-weight models. The authors state that "parameter count alone is a poor predictor of agentic capability across model families" and give examples where a 4B model beats a 26B one on tier D.
- **Relation to ours.** The closest existing capability ladder for small open-weight agents, including Qwen3.5-2B. Its tasks are synthetic and deterministic; ours is a real RAG task with a judge. We cite it to motivate the expectation that a fixed workflow (which removes branching and planning from the model) helps most below tier C, and our size sweep tests this expectation on RAG.

#### Albayaydh, Zhao and Flechais 2026, "Beyond the Leaderboard: A Synthesis of Tool-Use, Planning, and Reasoning Failures in LLM Agents" — VERIFIED (https://arxiv.org/abs/2607.05775)

- **Citation.** Wael Albayaydh, Rui Zhao, Ivan Flechais. "Beyond the Leaderboard: A Synthesis of Tool-Use, Planning, and Reasoning Failures in Large Language Model Agents." arXiv:2607.05775, 7 Jul 2026. No venue listed.
- **Summary.** A synthesis of 27 benchmark, taxonomy and audit papers (2023-2026) covering 19 benchmarks into six failure clusters: tool-invocation and parameter errors, planning and constraint-satisfaction failures, long-horizon degradation from context accumulation, multi-agent coordination failures, safety failures under adversarial or under-specified input, and measurement-validity problems. Failures compound nonlinearly with task length, strong sub-task performance does not predict end-to-end success, and extra scaffolding does not consistently improve reliability.
- **Relation to ours.** Useful for the related-work sentence that motivates removing planning from the model: the first three clusters are exactly what a code-controlled workflow with one structured decision per call avoids. The synthesis has no statement about model scale, which our study supplies for one task.

#### Srivastava et al. 2026, "EffGen: Enabling Small Language Models as Capable Autonomous Agents" — VERIFIED (https://arxiv.org/abs/2602.00887)

- **Citation.** Gaurav Srivastava, Aafiya Hussain, Chi Wang, Yingyan Celine Lin, Xuan Wang. "EffGen: Enabling Small Language Models as Capable Autonomous Agents." ICML 2026. arXiv:2602.00887, v1 31 Jan 2026, v2 14 Jun 2026.
- **Summary.** An agent framework for small models with prompt compression (57% average), dependency-based task decomposition, five-factor complexity routing and unified memory, evaluated on 13 benchmarks against LangChain, AutoGen and Smolagents. Prompt optimisation helps small models more (+11.2% at 1.5B versus +2.4% at 32B) while complexity routing helps larger models more (+3.6% at 1.5B versus +7.9% at 32B).
- **Relation to ours.** Shows that the interventions that help small-model agents are size-dependent, which supports reporting results per model size rather than for one model. EffGen is a framework paper; it does not compare a fixed workflow with an autonomous loop.

#### Patel et al. 2026, "The Bitter Lesson of Tool Calling" — VERIFIED (https://arxiv.org/abs/2608.06370)

- **Citation.** Ishan Patel, Sahil Sen, Elias Lumer, Vamse Kumar Subbiah. "The Bitter Lesson of Tool Calling." arXiv:2608.06370, 6 Aug 2026. No venue listed.
- **Summary.** Compares programmatic tool calling (tools exposed as typed Python stubs called from generated code) with native JSON tool calling across 14 models on BFCL v4. Programmatic calling matches or exceeds JSON calling on 11 of 14 models, is more robust to parallel fan-out (13 of 14) and to context rot (JSON baseline degrades 2.3% on average), and its advantage tracks model capability across release generations.
- **Relation to ours.** The tool-calling interface itself is a confound in workflow-versus-agent comparisons. We fix the interface (native structured output for every decision in the workflow, native tool calling for the agent) and report it, so the comparison is about control flow, not about the calling format.

#### Note on other 2026 search hits (UNVERIFIED, not opened)

Evoflux (arXiv 2606.12674, inference-time evolution of executable tool workflows for compact agents), "WorkBench Revisited: Workplace Agents Two Years On" (arXiv 2606.13715, which reports that moving from prompt-parsed ReAct to native tool calling removed the format-adherence failures of 2024) and "Beyond Generalist LLMs: Specialist Agentic Systems for Structured Code Workflow Execution" (arXiv 2607.14456) came up in search but were not opened. WorkBench Revisited is worth opening if the paper discusses format-adherence failures of small models.


### A.3 Agentic RAG with reasoning and reinforcement learning, multi-agent and automated-workflow designs

#### Li et al. 2025, "Towards Agentic RAG with Deep Reasoning: A Survey of RAG-Reasoning Systems in LLMs" — VERIFIED (https://arxiv.org/abs/2507.09477)

- **Citation.** Yangning Li, Weizhi Zhang, Yuyao Yang, et al. "Towards Agentic RAG with Deep Reasoning: A Survey of RAG-Reasoning Systems in LLMs." arXiv:2507.09477, Jul 2025 (submitted to ARR).
- **Summary.** Organises the field into reasoning-enhanced RAG, RAG-enhanced reasoning and synergised RAG-reasoning (agentic loops that interleave search and reasoning), catalogues methods, datasets and challenges, and points toward effective, multimodal, trustworthy and human-centred systems. No numbers.
- **Relation to ours.** Positions Search-R1-style learned loops as the frontier; we show that in the cheap-model regime a fixed, non-learned workflow with a calibrated gate is competitive and cheaper.

#### Gao et al. 2025, "Synergizing RAG and Reasoning: A Systematic Review" — VERIFIED (https://arxiv.org/abs/2504.15909)

- **Citation.** Yunfan Gao, Yun Xiong, Yijie Zhong, Yuxi Bi, Ming Xue, Haofen Wang. "Synergizing RAG and Reasoning: A Systematic Review." arXiv:2504.15909, Apr 2025.
- **Summary.** Defines reasoning in the RAG context, builds a taxonomy of collaborative objectives, paradigms and implementations, and criticises current evaluation for lacking intermediate supervision and for ignoring "cost-risk trade-offs in practice". Names hybrid model collaboration and RL-driven optimisation as directions.
- **Relation to ours.** Explicitly calls out the missing cost-risk axis; our joint quality, latency and cost reporting answers that call.

#### Jin et al. 2025, Search-R1 — VERIFIED (https://arxiv.org/abs/2503.09516)

- **Citation.** Bowen Jin, Hansi Zeng, Zhenrui Yue, Jinsung Yoon, Sercan Ö. Arık, Dong Wang, Hamed Zamani, Jiawei Han. "Search-R1: Training LLMs to Reason and Leverage Search Engines with Reinforcement Learning." COLM 2025. arXiv:2503.09516.
- **Summary.** PPO or GRPO teaches the model to emit search queries inside step-by-step reasoning, with retrieved-token masking and an outcome reward. The latest abstract reports +41% over RAG baselines with Qwen2.5-7B and +20% with Qwen2.5-3B on seven QA datasets (earlier versions quote lower 7B gains, so cite the version used). Also studies the RL algorithm, model choice and response-length dynamics.
- **Relation to ours.** Search-R1 needs RL training per model; we show a training-free workflow plus a calibrated gate for 2B-27B models and report the latency that learned loops hide.

#### Song et al. 2025, R1-Searcher — VERIFIED (https://arxiv.org/abs/2503.05592)

- **Citation.** Huatong Song, Jinhao Jiang, Yingqian Min, et al. "R1-Searcher: Incentivizing the Search Capability in LLMs via Reinforcement Learning." arXiv:2503.05592, Mar 2025. No venue found.
- **Summary.** Two-stage outcome-based RL that teaches the model to call external search during reasoning with no process rewards or distillation cold start; reports large gains over prior RAG methods on multi-hop QA, including over GPT-4o-mini under LLM-as-judge scoring. No numbers in the abstract.
- **Relation to ours.** Same family as Search-R1; cite together.

#### Li et al. 2025, Search-o1 — VERIFIED (https://arxiv.org/abs/2501.05366; ACL Anthology 2025.emnlp-main.276)

- **Citation.** Xiaoxi Li, Guanting Dong, Jiajie Jin, et al. "Search-o1: Agentic Search-Enhanced Large Reasoning Models." EMNLP 2025 (main). arXiv:2501.05366, DOI 10.18653/v1/2025.emnlp-main.276.
- **Summary.** Lets a large reasoning model trigger retrieval when it reaches an uncertain point and adds a Reason-in-Documents module that condenses retrieved text before injecting it into the chain; evaluated on science, maths and code reasoning and six open-domain QA sets. Retrieval is model-triggered and assumes a strong reasoning model.
- **Relation to ours.** Search-o1's trigger is the model's own uncertainty inside a long trace; ours is an external calibrated judge on a tiny model, which is what makes it cheap and portable.

#### Jiang et al. 2025, DeepRetrieval — VERIFIED (https://arxiv.org/abs/2503.00223)

- **Citation.** Pengcheng Jiang, Jiacheng Lin, Lang Cao, et al. "DeepRetrieval: Hacking Real Search Engines and Retrievers with Large Language Models via Reinforcement Learning." arXiv:2503.00223, 2025.
- **Summary.** RL with retrieval metrics as the reward teaches an LLM to write search queries without reference queries: 65.07% recall on publication search (prior best 24.68%), 63.18% on trial search (prior 32.11%), and a 3B model beating GPT-4o and Claude 3.5 Sonnet on 11 of 13 datasets.
- **Relation to ours.** A 3B model can be an excellent query writer when trained; we keep query rewriting as an untrained generation step and measure its contribution within the pipeline.

#### Nguyen, Chin and Tai 2025, MA-RAG — VERIFIED (https://arxiv.org/abs/2505.20096)

- **Citation.** Thang Nguyen, Peter Chin, Yu-Wing Tai. "MA-RAG: Multi-Agent Retrieval-Augmented Generation via Collaborative Chain-of-Thought Reasoning." arXiv:2505.20096, 2025.
- **Summary.** Planner, step-definer, extractor and QA agents each own one RAG stage and share chain-of-thought. LLaMA3-8B with MA-RAG beats larger standalone models on NQ, HotpotQA, 2WikiMultihopQA and TriviaQA; ablations find the planner and extractor matter most for multi-hop and the QA agent benefits most from a high-capacity model.
- **Relation to ours.** A stage-per-agent decomposition is a workflow in all but name; we make the workflow/agent distinction explicit and put each stage on the cheapest model that is calibrated for it.

#### Zhang et al. 2024, Chain of Agents — VERIFIED (https://arxiv.org/abs/2406.02818; NeurIPS 2024 proceedings)

- **Citation.** Yusen Zhang, Ruoxi Sun, Yanfei Chen, Tomas Pfister, Rui Zhang, Sercan Ö. Arık. "Chain of Agents: Large Language Models Collaborating on Long-Context Tasks." NeurIPS 2024. arXiv:2406.02818.
- **Summary.** Worker agents each read a segment of a long input and pass findings along a chain; a manager composes the answer. Gains of up to 10% over RAG, full-context and multi-agent baselines on QA, summarisation and code completion. The topology is fixed in code.
- **Relation to ours.** Another fixed-topology multi-LLM design; we study a different fixed topology (route, judge, refine) and make the cost of each node explicit.

#### Zhang et al. 2025, AFlow — VERIFIED (https://arxiv.org/abs/2410.10762; ICLR 2025 oral)

- **Citation.** Jiayi Zhang, Jinyu Xiang, Zhaoyang Yu, et al. "AFlow: Automating Agentic Workflow Generation." ICLR 2025 (oral). arXiv:2410.10762.
- **Summary.** Treats workflow design as search over code-represented graphs of LLM-invoking nodes with MCTS, code modification, tree-structured experience and execution feedback. Average +5.7% over the best baselines on six benchmarks, and lets smaller models beat GPT-4o on specific tasks at 4.55% of GPT-4o's dollar cost.
- **Relation to ours.** AFlow searches for a workflow automatically; we hand-design one and ask the prior question of whether a workflow beats autonomy at all for small models, and at what cost. The 4.55% cost figure is a useful precedent for reporting dollar cost.

#### Hu, Lu and Clune 2025, ADAS — VERIFIED (https://arxiv.org/abs/2408.08435; ICLR 2025)

- **Citation.** Shengran Hu, Cong Lu, Jeff Clune. "Automated Design of Agentic Systems." ICLR 2025. arXiv:2408.08435.
- **Summary.** Defines agents in code and lets a meta agent program new agents guided by an archive of past designs; discovered agents beat hand-designed ones on coding, science and maths and transfer across domains and models.
- **Relation to ours.** Same code-as-agent view; we fix the code and vary the model, which isolates the model-size effect ADAS does not study.

#### Zheng and Worring 2026, LatentRAG — VERIFIED (https://arxiv.org/abs/2605.06285)

- **Citation.** Yijia Zheng, Marcel Worring. "LatentRAG: Latent Reasoning and Retrieval for Efficient Agentic RAG." arXiv:2605.06285, May 2026.
- **Summary.** Observes that agentic RAG spends most of its latency generating intermediate thoughts and sub-queries token by token; emits them instead as latent tokens in one forward pass aligned to a dense retriever. Across seven benchmarks it matches explicit agentic RAG while cutting latency by about 90%; the body (via a search snippet, not read) puts Search-R1-style methods at roughly 15 times the latency of single-step RAG.
- **Relation to ours.** Independent evidence that agentic loops are latency-dominated; we attack the same cost with a different lever (gating the loop off when evidence is already sufficient) and without training.

#### Maharjan, Kaur and Molyet 2026, "Agent-Orchestrated Adaptive RAG: A Comparative Study" — VERIFIED (https://arxiv.org/abs/2606.05658)

- **Citation.** Anuj Maharjan, Devinder Kaur, Richard Molyet. "Agent-Orchestrated Adaptive RAG: A Comparative Study on Structured and Multi-Hop Retrieval." arXiv:2606.05658, Jun 2026.
- **Summary.** An agent with query decomposition, iterative retrieval and a bounded self-reflection loop on a DevOps knowledge base and MuSiQue. Decomposition helps DevOps (overall +0.04, MRR +0.17) but hurts ranking precision on MuSiQue; reflection improves citation accuracy at a large latency cost (a search snippet of the body reports 17 s to 104 s with the overall score falling 0.721 to 0.666 on MuSiQue). The authors recommend applying agentic steps selectively by query and domain.
- **Relation to ours.** Agrees that unconditional agentic steps can cost more than they return; our confidence gate is a principled rule for when to run them.

#### Bhatia et al. 2026, "From RAG to Agentic RAG for Faithful Islamic Question Answering" — VERIFIED (https://arxiv.org/abs/2601.07528)

- **Citation.** Gagan Bhatia, Hamdy Mubarak, Mustafa Jarrar, et al. "From RAG to Agentic RAG for Faithful Islamic Question Answering." arXiv:2601.07528, 2026.
- **Summary.** A 3,810-item bilingual benchmark with gold answers to measure hallucination and abstention, plus a verse corpus; an agentic RAG framework with structured tool calls gives the largest gains over standard RAG across Arabic-centric and multilingual LLMs including Qwen3-4B. A search snippet of the body reports that for Qwen3-4B the agentic setup raises tokens from 502 to 1,520 and latency from 0.52 s to 3.45 s with about six tool calls per query.
- **Relation to ours.** The closest domain-specific, small-model, non-English agentic RAG study with a latency number; we add the explicit workflow control condition and a size sweep instead of one 4B point.

#### Wu et al. 2026, Tiny-Critic RAG — VERIFIED (https://arxiv.org/abs/2603.00846)

- **Citation.** Yichao Wu, Penghao Liang, Yafei Xiang, et al. "Tiny-Critic RAG: Empowering Agentic Fallback with Parameter-Efficient Small Language Models." arXiv:2603.00846, Mar 2026.
- **Summary.** Replaces the LLM evaluator in a CRAG-style loop with a LoRA-tuned 1.7B binary gatekeeper (constrained decoding, non-thinking mode) that decides whether to route to agentic fallback; routing accuracy comparable to GPT-4o-mini with latency reduced by an order of magnitude (a search snippet of the body cites a 94.6% reduction in routing overhead versus a 785 ms heavy router).
- **Relation to ours.** The closest existing use of a tiny model as the gate of a RAG loop. It fine-tunes a generative model and measures routing only; we use an off-the-shelf calibrated decision model, gate on its probability, and report end-to-end quality, latency and cost.

#### Bhandari et al. 2026, Evoflux — VERIFIED (https://arxiv.org/abs/2606.12674)

- **Citation.** Kushal Raj Bhandari, Ling Yue, Ching-Yun Ko, et al. (IBM). "Evoflux: Inference-Time Evolution of Executable Tool Workflows for Compact Agents." arXiv:2606.12674, Jun 2026.
- **Summary.** For compact planners, repairs executable tool workflows with structured edits, execution feedback and diversity pruning. On held-out MCP-Bench tasks (250 live tools) execution feasibility rises from roughly 3% to 17-24% across small planners; SFT and SFT+DPO on the same data matched or fell below zero-shot; ReAct reached higher peaks with higher variance and token cost.
- **Relation to ours.** Confirms that free-running ReAct on small models is high-variance and token-hungry; we take the other route (fix the workflow in code) and measure the variance and cost it removes.

### A.4 Tool-use benchmarks and small-model tool calling

#### Patil et al. 2025, BFCL — VERIFIED (https://proceedings.mlr.press/v267/patil25a.html)

- **Citation.** Shishir G. Patil, Huanzhi Mao, Fanjia Yan, et al. "The Berkeley Function Calling Leaderboard (BFCL): From Tool Use to Agentic Evaluation of Large Language Models." ICML 2025, PMLR 267:48371-48392. No arXiv id found.
- **Summary.** A function-invocation benchmark covering serial and parallel calls in several languages scored by AST matching, mixing expert-curated and user-contributed functions and adding abstention and stateful multi-step agentic settings. The stated finding is that state-of-the-art models handle single-turn calls well while memory, dynamic decision-making and long-horizon reasoning remain open.
- **Relation to ours.** BFCL measures tool-call correctness in isolation; we measure what tool-calling autonomy buys in an end-to-end RAG task against a workflow that never asks the model to pick tools.

#### Yao et al. 2025, tau-bench — VERIFIED (https://arxiv.org/abs/2406.12045; ICLR 2025 proceedings)

- **Citation.** Shunyu Yao, Noah Shinn, Pedram Razavi, Karthik Narasimhan. "τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains." ICLR 2025. arXiv:2406.12045.
- **Summary.** Agents talk to a simulated user in retail and airline domains under a policy and are scored on the final database state; introduces pass^k for reliability over repeated trials. GPT-4o succeeds on under 50% of tasks and pass^8 is below 25% in retail.
- **Relation to ours.** Shows autonomous agents are unreliable even at frontier scale; we quantify the same unreliability for 2B-27B open models and show the fixed workflow as the alternative.

#### Qin et al. 2024, ToolLLM / ToolBench — VERIFIED (https://arxiv.org/abs/2307.16789; ICLR 2024 proceedings)

- **Citation.** Yujia Qin, Shihao Liang, Yining Ye, et al. "ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs." ICLR 2024. arXiv:2307.16789.
- **Summary.** Builds ToolBench from 16,464 RapidAPI endpoints with ChatGPT-generated instructions and DFS-based solution paths, an automatic evaluator and a LLaMA fine-tune that reaches performance comparable to ChatGPT. The point is that open models need targeted data to call tools well.
- **Relation to ours.** We do not fine-tune; we ask whether small off-the-shelf models can be trusted to plan tool use at all and show a workflow design that removes the need.

#### Kavathekar et al. 2025, "Small Models, Big Tasks" — VERIFIED (https://arxiv.org/abs/2504.19277)

- **Citation.** Ishan Kavathekar, Raghav Donakanti, Ponnurangam Kumaraguru, Karthik Vaidhyanathan. "Small Models, Big Tasks: An Exploratory Empirical Study on Small Language Models for Function Calling." EASE 2025. arXiv:2504.19277.
- **Summary.** Tests small models on function-call generation under zero-shot, few-shot and fine-tuning, with and without prompt injection, and measures latency and memory on an edge device. Few-shot beats zero-shot and fine-tuning is best, but the models "struggle significantly with adhering to the given output format".
- **Relation to ours.** The format-adherence failure is exactly the risk our workflow removes by giving small models only single typed decisions instead of free-form tool calls.

#### Jhandi et al. 2026, "Small Language Models for Efficient Agentic Tool Calling" — VERIFIED (https://arxiv.org/abs/2512.15943)

- **Citation.** Polaris Jhandi, Owais Kazi, Shreyas Subramanian, Neel Sendas. "Small Language Models for Efficient Agentic Tool Calling: Outperforming Large Models with Targeted Fine-tuning." AAAI 2026 Workshop on Agentic AI Benchmarks and Applications for Enterprise Tasks. arXiv:2512.15943.
- **Summary.** Fine-tunes a 350M model for one epoch and reports a 77.55% ToolBench pass rate versus 26.00% for ChatGPT-CoT and 30.18% for ToolLLaMA-DFS. Workshop paper on a single benchmark.
- **Relation to ours.** Supports the economics of small specialised models through fine-tuning; our decision model is used off the shelf.

#### Su et al. 2025, "Scaling Agents via Continual Pre-training" (AgentFounder) — VERIFIED (https://arxiv.org/abs/2509.13310)

- **Citation.** Liangcai Su, Zhen Zhang, Guangyu Li, et al. (Tongyi). "Scaling Agents via Continual Pre-training." arXiv:2509.13310, Sep 2025.
- **Summary.** Adds agentic continual pre-training before post-training; AgentFounder-30B reaches 39.9% BrowseComp-en, 43.3% BrowseComp-zh and 31.5% HLE pass@1. A search snippet of the body reports average accuracy rising from 20.4% (1B) to 32.7% (4B) to 48.9% (30B).
- **Relation to ours.** A size-versus-agentic-accuracy curve for one training recipe; we give the analogous curve for untrained open models and show the workflow alternative at the low end.

#### Taheri et al. 2026, "Small Reasoning Models are Instruction Followers in Function Calling" — VERIFIED (https://arxiv.org/abs/2608.22472)

- **Citation.** Yalda Taheri, et al. "Small Reasoning Models are Instruction Followers in Function Calling." arXiv:2608.22472, Aug 2026.
- **Summary.** Moves function calling to a small dedicated model in an instruction-following format; beats native function calling and is robust to quantisation.
- **Relation to ours.** Supports delegating narrow structured decisions to small dedicated models.

#### Not opened (do not cite without checking)

"Optimizing Agentic Workflows using Meta-tools" (arXiv 2601.22037), MCP-Bench (arXiv 2508.20453), ML-Tool-Bench (arXiv 2512.00672), ToolACE (ICLR 2025), "Scaffolded Language Models with Language Supervision for Mixed-Autonomy: A Survey" (arXiv 2410.16392, opened by the sub-survey but only useful as a framing citation).

**Thread A gap statement.** No paper reports a fixed-pipeline-versus-ReAct comparison on a RAG task across a ladder of small open-weight model sizes with quality, latency and cost together. The nearest are Kumar et al. 2026 (19 tasks, one large model), Gray et al. 2025 (code repair, three scales, agent wins at mid scale) and Zhang et al. 2026 (one 7B model, small differences).


## B. Adaptive and conditional retrieval, confidence gating

### B.1 Adaptive retrieval, 2023-2025: when to retrieve, and who decides

#### Mallen et al. 2023, "When Not to Trust Language Models" (PopQA) — VERIFIED (https://arxiv.org/abs/2212.10511)

- **Citation.** Alex Mallen, Akari Asai, Victor Zhong, Rajarshi Das, Daniel Khashabi, Hannaneh Hajishirzi. "When Not to Trust Language Models: Investigating Effectiveness of Parametric and Non-Parametric Memories." ACL 2023. arXiv:2212.10511.
- **Summary.** Introduces PopQA (14k questions) and probes ten models with four augmentation methods. Models fail on long-tail entities and scaling does not fix it, while retrieval-augmented models beat much larger unassisted ones; unassisted models stay competitive on popular entities. Proposes adaptive retrieval (retrieve only when entity popularity is low), which improves accuracy and cuts inference cost.
- **Relation to ours.** The origin of "retrieve only when needed"; our gate decides on evidence sufficiency after a first retrieval rather than on query popularity before it.

#### Trivedi et al. 2023, IRCoT — VERIFIED (https://arxiv.org/abs/2212.10509)

- **Citation.** Harsh Trivedi, Niranjan Balasubramanian, Tushar Khot, Ashish Sabharwal. "Interleaving Retrieval with Chain-of-Thought Reasoning for Knowledge-Intensive Multi-Step Questions." ACL 2023. arXiv:2212.10509.
- **Summary.** Alternates retrieval with chain-of-thought sentences so each step guides the next query; with GPT-3 it improves retrieval by up to 21 points and QA by up to 15 on HotpotQA, 2WikiMultihopQA, MuSiQue and IIRC, with similar gains for Flan-T5-large. The iteration count is a fixed step budget.
- **Relation to ours.** IRCoT always iterates; we iterate only when a calibrated judge says evidence is insufficient.

#### Jiang et al. 2023, FLARE — VERIFIED (https://arxiv.org/abs/2305.06983)

- **Citation.** Zhengbao Jiang, Frank F. Xu, Luyu Gao, Zhiqing Sun, Qian Liu, Jane Dwivedi-Yu, Yiming Yang, Jamie Callan, Graham Neubig. "Active Retrieval Augmented Generation." EMNLP 2023. arXiv:2305.06983.
- **Summary.** Predicts the next sentence, uses it as a query, and regenerates when the sentence contains low-probability tokens; beats or matches baselines on four long-form knowledge-intensive tasks. The trigger is the generator's raw token probability.
- **Relation to ours.** FLARE gates on the generator's own token confidence; we gate on a separate tiny model's calibrated probability of "evidence sufficient", which also works with generators whose logits we cannot read (Gemini Flash).

#### Wang et al. 2023, SKR — VERIFIED (https://arxiv.org/abs/2310.05002; ACL Anthology 2023.findings-emnlp.691)

- **Citation.** Yile Wang, Peng Li, Maosong Sun, Yang Liu. "Self-Knowledge Guided Retrieval Augmentation for Large Language Models." Findings of EMNLP 2023. arXiv:2310.05002, DOI 10.18653/v1/2023.findings-emnlp.691.
- **Summary.** Observes that retrieval sometimes hurts answers the model already knew; elicits the model's self-knowledge (and nearest previously seen questions) to call retrieval only for unfamiliar questions. Beats chain-of-thought and always-retrieve with InstructGPT and ChatGPT.
- **Relation to ours.** SKR's self-knowledge is the model's own; we externalise the judgment to a calibrated decision model and gate the second retrieval, not the first.

#### Asai et al. 2024, Self-RAG — VERIFIED (https://arxiv.org/abs/2310.11511; ICLR 2024 proceedings)

- **Citation.** Akari Asai, Zeqiu Wu, Yizhong Wang, Avirup Sil, Hannaneh Hajishirzi. "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection." ICLR 2024. arXiv:2310.11511.
- **Summary.** Trains one model to emit reflection tokens that decide when to retrieve and that critique passages and its own output, controllable at inference. 7B and 13B Self-RAG beat ChatGPT and retrieval-augmented Llama2-chat on open-domain QA, reasoning and fact verification, with better factuality and citation accuracy in long-form.
- **Relation to ours.** Self-RAG bakes the sufficiency judgment into a trained generator; we keep the generator untouched and move the judgment to a separate, cheaper calibrated model. Already cited in the paper.

#### Yan et al. 2024, CRAG — VERIFIED (https://arxiv.org/abs/2401.15884)

- **Citation.** Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling. "Corrective Retrieval Augmented Generation." arXiv:2401.15884, v3 Oct 2024. No peer-reviewed venue found.
- **Summary.** A lightweight retrieval evaluator (a fine-tuned T5-class model) scores retrieval quality and triggers Correct, Ambiguous or Incorrect actions, with web search as fallback and decompose-then-recompose filtering; plug-and-play on four short- and long-form datasets.
- **Relation to ours.** CRAG's evaluator is the direct ancestor of our evidence-sufficiency judge; we replace the fine-tuned evaluator with a calibrated typed-answer model and sweep its threshold to trace the cost curve. Already cited in the paper.

#### Jeong et al. 2024, Adaptive-RAG — VERIFIED (https://arxiv.org/abs/2403.14403)

- **Citation.** Soyeong Jeong, Jinheon Baek, Sukmin Cho, Sung Ju Hwang, Jong C. Park. "Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity." NAACL 2024. arXiv:2403.14403.
- **Summary.** A small classifier predicts query complexity and routes to no-retrieval, single-step or multi-step (IRCoT-style) retrieval, with labels derived automatically from model outcomes and dataset bias. Better accuracy-efficiency trade-off than fixed and prior adaptive baselines on open-domain QA.
- **Relation to ours.** Adaptive-RAG routes before seeing evidence using a complexity classifier; we decide after the first retrieval using a calibrated sufficiency judgment, and we add per-intent coverage checks. Already cited in the paper.

#### Su et al. 2024, DRAGIN — VERIFIED (https://arxiv.org/abs/2403.10081; ACL Anthology 2024.acl-long.702)

- **Citation.** Weihang Su, Yichen Tang, Qingyao Ai, Zhijing Wu, Yiqun Liu. "DRAGIN: Dynamic Retrieval Augmented Generation based on the Real-time Information Needs of Large Language Models." ACL 2024. arXiv:2403.10081.
- **Summary.** Decides when to retrieve from attention-weighted token uncertainty during generation and what to retrieve from attention over the whole context; outperforms prior dynamic RAG on four knowledge-intensive datasets.
- **Relation to ours.** DRAGIN needs white-box access to attention; our gate is black-box with respect to the generator.

#### Zhang, Fang and Chen 2024, RetrievalQA and TA-ARE — VERIFIED (https://arxiv.org/abs/2402.16457)

- **Citation.** Zihan Zhang, Meng Fang, Ling Chen. "RetrievalQA: Assessing Adaptive Retrieval-Augmented Generation for Short-form Open-Domain Question Answering." Findings of ACL 2024. arXiv:2402.16457.
- **Summary.** A 1,271-question benchmark of new-world and long-tail facts where retrieval is required. Finds that calibration-based triggers depend heavily on threshold tuning and that vanilla prompting does not reliably decide when to retrieve; proposes time-aware adaptive retrieval (TA-ARE) with no calibration (a search snippet of the body reports average match 31.1 versus 24.8).
- **Relation to ours.** Shows threshold sensitivity is a real problem; we turn it into a reported object by sweeping the threshold of a calibrated model and showing the whole Pareto curve.

#### Ding et al. 2025, Rowen — VERIFIED (https://arxiv.org/abs/2402.10612)

- **Citation.** Hanxing Ding, Liang Pang, Zihao Wei, Huawei Shen, Xueqi Cheng. "Rowen: Adaptive Retrieval-Augmented Generation for Hallucination Mitigation in LLMs." SIGIR-AP 2025. arXiv:2402.10612.
- **Summary.** Detects uncertainty by checking semantic consistency of answers generated across languages and across models, and retrieves only when they disagree; outperforms prior methods at detecting and mitigating hallucination.
- **Relation to ours.** Rowen's consistency check needs multiple full generations; our judge is a single call to a tiny model.

#### Liu et al. 2025, CtrlA — VERIFIED (https://arxiv.org/abs/2405.18727; ACL Anthology 2025.findings-acl.652)

- **Citation.** Huanshuo Liu, Hao Zhang, Zhijiang Guo, et al. "CtrlA: Adaptive Retrieval-Augmented Generation via Inherent Control." Findings of ACL 2025. arXiv:2405.18727.
- **Summary.** Extracts honesty and confidence directions from internal representations, steers toward honesty and monitors the confidence feature to decide when to retrieve; beats adaptive RAG baselines.
- **Relation to ours.** White-box probing of the generator; ours is black-box and portable across the Qwen and Gemini families.

#### Cheng et al. 2024, UAR — VERIFIED (https://arxiv.org/abs/2406.12534)

- **Citation.** Qinyuan Cheng, Xiaonan Li, Shimin Li, et al. "Unified Active Retrieval for Retrieval Augmented Generation." Findings of EMNLP 2024. arXiv:2406.12534.
- **Summary.** Frames four independent retrieval criteria (intent, knowledge, time-sensitivity, self-awareness) as plug-and-play classifiers with negligible cost plus a combination procedure; beats prior work on retrieval-timing judgment over four instruction types.
- **Relation to ours.** Multi-criterion classification on a shared backbone resembles our multi-question decision model; we add calibration, a threshold sweep and a cost axis.

#### Yao et al. 2025, SeaKR — VERIFIED (https://arxiv.org/abs/2406.19215; ACL 2025)

- **Citation.** Zijun Yao, Weijian Qi, Liangming Pan, et al. "SeaKR: Self-aware Knowledge Retrieval for Adaptive Retrieval Augmented Generation." ACL 2025. arXiv:2406.19215.
- **Summary.** Uses internal-state uncertainty to trigger retrieval, re-ranks snippets by how much they reduce that uncertainty, and chooses a reasoning strategy for multi-retrieval questions; beats adaptive RAG baselines on simple and complex QA.
- **Relation to ours.** White-box again; we show an external calibrated gate achieves the same control without model internals.

#### Wang et al. 2024, RAGate — VERIFIED (https://arxiv.org/abs/2407.21712)

- **Citation.** Xi Wang, Procheta Sen, Ruizhe Li, Emine Yilmaz. "Adaptive Retrieval-Augmented Generation for Conversational Systems." arXiv:2407.21712, Jul 2024.
- **Summary.** Trains a gating model on human judgments of whether each conversational turn needs augmentation, conditioned on context, and reports a correlation between generation confidence and retrieved-knowledge relevance.
- **Relation to ours.** Same gating idea for dialogue; ours gates a second retrieval in a QA workflow and reports cost.

#### Li et al. 2024, Self-Route — VERIFIED (https://arxiv.org/abs/2407.16833)

- **Citation.** Zhuowan Li, Cheng Li, Mingyang Zhang, Qiaozhu Mei, Michael Bendersky. "Retrieval Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid Approach." EMNLP 2024 Industry Track. arXiv:2407.16833.
- **Summary.** Long context beats RAG on average when resources allow but RAG is far cheaper; Self-Route asks the model whether the retrieved context is answerable and escalates to long context only when not, cutting cost while matching long-context quality.
- **Relation to ours.** Same "escalate only when insufficient" logic; we make the sufficiency question a calibrated probability from a tiny model and sweep it.

#### Baek et al. 2025, Probing-RAG — VERIFIED (https://arxiv.org/abs/2410.13339)

- **Citation.** Ingeol Baek, Hwan Chang, Byeongjeong Kim, Jimin Lee, Hwanhee Lee. "Probing-RAG: Self-Probing to Guide Language Models in Selective Document Retrieval." Findings of NAACL 2025. arXiv:2410.13339.
- **Summary.** A pre-trained prober on intermediate hidden states decides whether another retrieval round is needed; beats prior methods on five open-domain QA sets while reducing redundant retrieval steps.
- **Relation to ours.** Also gates the retrieve-more loop, but from hidden states; our gate is a separate model's calibrated typed answer.

#### Wang et al. 2025, Astute RAG — VERIFIED (https://arxiv.org/abs/2410.07176)

- **Citation.** Fei Wang, Xingchen Wan, Ruoxi Sun, Jiefeng Chen, Sercan Ö. Arık. "Astute RAG: Overcoming Imperfect Retrieval Augmentation and Knowledge Conflicts for Large Language Models." ACL 2025. arXiv:2410.07176.
- **Summary.** Shows imperfect retrieval is common and harmful; elicits internal knowledge, consolidates it with retrieved passages while tracking sources, and picks the most reliable answer. With Gemini and Claude it beats robustness-focused RAG and is the only method matching no-retrieval in the worst case.
- **Relation to ours.** Addresses evidence quality after retrieval; our judge decides whether to retrieve more, so the two are complementary.

#### Moskvoretskii et al. 2025, "Adaptive Retrieval Without Self-Knowledge?" — VERIFIED (https://arxiv.org/abs/2501.12835; ACL Anthology 2025.acl-long.319)

- **Citation.** Viktor Moskvoretskii, Maria Lysyuk, Mikhail Salnikov, et al. "Adaptive Retrieval Without Self-Knowledge? Bringing Uncertainty Back Home." ACL 2025. arXiv:2501.12835.
- **Summary.** Benchmarks 35 adaptive retrieval methods (8 self-knowledge pipelines, 27 uncertainty estimators) on six datasets with ten metrics for QA, self-knowledge and efficiency; simple uncertainty estimators often beat complex pipelines on efficiency and self-knowledge at similar QA quality.
- **Relation to ours.** Motivates cheap signals; ours is a cheap signal that is also calibrated and model-agnostic, evaluated with cost in money and seconds.

#### Guan et al. 2025, DeepRAG — VERIFIED (https://arxiv.org/abs/2502.01142)

- **Citation.** Xinyan Guan, Jiali Zeng, Fandong Meng, et al. "DeepRAG: Thinking to Retrieve Step by Step for Large Language Models." arXiv:2502.01142, 2025.
- **Summary.** Models retrieval-augmented reasoning as an MDP where each decomposed step chooses between retrieving and answering from parametric knowledge; reports +26.4% answer accuracy with better retrieval efficiency.
- **Relation to ours.** DeepRAG trains the retrieve/no-retrieve policy into the generator; ours is an external threshold on a calibrated judge.

#### Liu et al. 2025, CaRT — VERIFIED (https://arxiv.org/abs/2510.08517)

- **Citation.** Grace Liu, Yuxiao Qu, Jeff Schneider, Aarti Singh, Aviral Kumar. "CaRT: Teaching LLM Agents to Know When They Know Enough." arXiv:2510.08517, Oct 2025.
- **Summary.** Fine-tunes on counterfactual trajectory pairs where stopping is and is not appropriate, with verbal rationales, so the agent learns when to stop gathering information; improves efficiency and success on interactive medical diagnosis and maths.
- **Relation to ours.** Same "know when enough" goal, learned into the agent; we obtain it from a separate calibrated decision model without training.


### B.2 Stopping rules, retrieval gates and calibrated cascades (2025-2026)

These works are the nearest neighbours of contribution 2 (confidence-gated refinement). All were opened on arXiv or the ICLR proceedings during this survey.

#### Joren et al. 2025, "Sufficient Context: A New Lens on Retrieval Augmented Generation Systems" — VERIFIED (https://proceedings.iclr.cc/paper_files/paper/2025/hash/33dffa2e3d2ab74a783d1a8c292f66d9-Abstract-Conference.html, https://arxiv.org/abs/2411.06037)

- **Citation.** Hailey Joren, Jianyi Zhang, Chun-Sung Ferng, Da-Cheng Juan, Ankur Taly, Cyrus Rashtchian. "Sufficient Context: A New Lens on Retrieval Augmented Generation Systems." ICLR 2025. arXiv:2411.06037 (v1 9 Nov 2024, v3 23 Apr 2025).
- **Summary.** Defines "sufficient context" (the retrieved context contains enough information to answer) and builds an LLM autorater for it. With sufficient context, large models (Gemini 1.5 Pro, GPT-4o, Claude 3.5) answer well; without it, they tend to answer wrongly rather than abstain, while smaller models (Llama 3.1, Mistral 3, Gemma 2) hallucinate or abstain even with sufficient context. A selective-generation method that combines the sufficiency label with model confidence raises the fraction of correct answers among non-abstentions by 2-10% for Gemini, GPT and Gemma.
- **Relation to ours.** Our evidence-sufficiency judge is the same notion, but we (a) run it on a calibrated decision model rather than a frontier LLM autorater, (b) use its probability to gate a retrieve-more loop rather than to abstain, and (c) report the resulting cost-quality trade-off. Joren et al. use the label for analysis and abstention only.

#### Wang, Wei and Ling 2025/2026, "Retrieval as a Decision: Training-Free Adaptive Gating for Efficient RAG" (TARG) — VERIFIED (https://arxiv.org/abs/2511.09803)

- **Citation.** Yufeng Wang, Lu Wei, Haibin Ling. "Retrieval as a Decision: Training-Free Adaptive Gating for Efficient RAG." arXiv:2511.09803, v1 12 Nov 2025, v2 14 Apr 2026. No venue listed.
- **Summary.** TARG decides whether to retrieve at all by sampling a short no-context draft and scoring its prefix logits with one of three signals (mean token entropy, top-1/top-2 logit margin, or variance across N stochastic prefixes); retrieval fires only above a threshold. On NQ-Open, TriviaQA, PopQA, MuSiQue and ASQA it matches or improves EM/F1 of always-retrieve while cutting retrieval by 70-90% and reducing end-to-end latency. The margin signal is reported as the most robust default because entropy becomes uninformative as instruction-tuned models sharpen; the limitations section warns that thresholds shift across models, prompts and domains.
- **Relation to ours.** A single-threshold gate on the generator's own logits, before the first retrieval. Ours gates the second and later retrievals on an external calibrated judge, and because the judge is a separate model its threshold is a probability with a fixed meaning rather than a model-specific logit margin, so it transfers across the 2B-27B ladder without re-tuning.

#### Kieback et al. 2026, "TASR: Training-Free Adaptive Stopping for Iterative Retrieval" — VERIFIED (https://arxiv.org/abs/2606.13814)

- **Citation.** Adrian Kieback, Uyiosa Philip Amadasun, Aman Chadha, Aaron Elkins. "TASR: Training-Free Adaptive Stopping for Iterative Retrieval." Agent4IR Workshop, KDD 2026. arXiv:2606.13814, v1 11 Jun 2026, v3 23 Jun 2026.
- **Summary.** A stopping predicate for iterative RAG that fires when the normalised answer repeats the previous round's and an isotonically calibrated logit margin exceeds 0.25, with the threshold fixed across 32 (model, retriever, corpus) configurations. On a 3-model by 2-dataset distractor grid it keeps 94.8% of fixed-k=5 macro-F1 with 62.6% of the calls; on nine open-domain BM25 cells it reaches 55.01 F1 at 2.98 calls versus 54.33 at 3.00 calls for fixed-k=3, and the pattern holds on dense retrievers and on a 550B production model. The rule was chosen from 381 candidate predicates, none of which Pareto-dominates it. The signal analysis shows that verbalised 1-5 confidence collapses on RLHF-tuned models (96.5% of values equal 5) while the logit margin gives about 40 times better class-conditional separation.
- **Relation to ours.** The closest prior work in spirit: a calibrated confidence threshold that stops iterative retrieval and is presented as a Pareto baseline. Differences: TASR needs logits from the generator (unavailable for commercial models and for most hosted endpoints), it stops after the answer has stabilised rather than before generating, and it has no latency or dollar-cost axis. Our gate uses a separate decision model that works identically with open and commercial generators, and we sweep the threshold to draw the Pareto curve in cost and latency as well as calls. The finding that verbalised confidence is useless on RLHF models is a strong argument for not asking the small LLM itself whether evidence is sufficient.

#### Roh and Han 2026, "HALT: Verification-Aware Stopping for Retrieval-Augmented Search Agents" — VERIFIED (https://arxiv.org/abs/2608.02009)

- **Citation.** Daeyoung Roh, Donghee Han. "HALT: Verification-Aware Stopping for Retrieval-Augmented Search Agents." Findings of EMNLP 2026. arXiv:2608.02009, v1 3 Aug 2026, v3 28 Aug 2026. Code: github.com/Noverse0/HALT.
- **Summary.** HALT frames stopping as evidence coverage: it generates the hop claims a question needs, and a small verifier (Qwen2.5-3B-Instruct with a LoRA adapter trained once on HotpotQA) stops the search agent (Self-Ask with Qwen2.5-3B/7B) when every claim is supported. From the full text, with the 3B agent the mean number of search loops falls by 17% on 2Wiki, 18% on HotpotQA and 2% on MuSiQue with generated claims (37%, 45% and 20% with gold claims) while exact match stays non-inferior within a 2-point margin; wall-clock on 100 HotpotQA queries drops from 47.4 s to 40.6 s (generated) and 30.9 s (gold). Ablations show the gain comes from claim-evidence alignment rather than from a generic sufficiency score or a fixed stop position.
- **Relation to ours.** The nearest work to our per-intent coverage check: both decompose what a complete answer needs and stop when each part is covered. HALT trains a verifier per task; ours asks a general calibrated decision model one typed question per intent, with no training. HALT reports loops and seconds; we add dollar cost and run the same gate across model sizes.

#### Park, Cho and Lee 2025, "Stop-RAG: Value-Based Retrieval Control for Iterative RAG" — VERIFIED (https://arxiv.org/abs/2510.14337)

- **Citation.** Jaewan Park, Solbee Cho, Jay-Yoon Lee. "Stop-RAG: Value-Based Retrieval Control for Iterative RAG." NeurIPS 2025 MTI-LLM Workshop. arXiv:2510.14337, 16 Oct 2025.
- **Summary.** Models iterative RAG as a finite-horizon MDP and trains a value-based controller with forward-view Q(lambda) targets from complete trajectories to decide when to stop retrieving. The controller works with black-box generators and is reported to outperform fixed-iteration and prompt-based stopping on multi-hop QA; the abstract gives no numbers.
- **Relation to ours.** A learned stopping controller; ours is training-free and uses a probability threshold, which is what makes the Pareto sweep possible without retraining.

#### Kotte 2026, "UCCI: Calibrated Uncertainty for Cost-Optimal LLM Cascade Routing" — VERIFIED (https://arxiv.org/abs/2605.18796)

- **Citation.** Varun Kotte. "UCCI: Calibrated Uncertainty for Cost-Optimal LLM Cascade Routing." arXiv:2605.18796, 11 May 2026. No venue listed.
- **Summary.** Maps a token-level margin to a per-query error probability with isotonic regression, then chooses the escalation threshold of a small-to-large cascade by constrained cost minimisation; the paper argues threshold policies on the calibrated score are cost-optimal under three assumptions. On a 75,000-query production NER workload with 4B and 12B models on H100s, inference cost falls 31% (95% CI 27-35%) at micro-F1 0.91 while ECE drops from 0.12 to 0.03, beating entropy thresholding, split-conformal routing and a FrugalGPT-style learned threshold.
- **Relation to ours.** Shows that calibrating the gate signal is what makes a threshold transferable and cost-optimal. Our gate is calibrated by construction (the decision model returns a probability trained to be calibrated) and we apply it to "retrieve more" rather than "escalate model".

#### Peale et al. 2026, "Flexible Routing via Uncertainty Decomposition" — VERIFIED (https://arxiv.org/abs/2605.07805)

- **Citation.** Charlotte Peale, Siddartha Devic, Parikshit Gopalan, Udi Wieder, Aravind Gollakota. "Flexible Routing via Uncertainty Decomposition." arXiv:2605.07805, 8 May 2026. No venue listed.
- **Summary.** Splits a weak model's uncertainty into reducible and irreducible parts with higher-order predictors; routes to an oracle (large model or human) when reducible uncertainty is high and abstains when irreducible uncertainty is high, with regret bounds and hyperparameters that trade cost without retraining. The abstract reports no numbers.
- **Relation to ours.** Theoretical support for a three-way gate (answer, retrieve more, abstain) driven by calibrated uncertainty; our unanswerable and out-of-scope classes are the abstain branch.


#### Xie, Liu and Yao 2026, "Know When You're Wrong: Aligning Confidence with Correctness for LLM Error Detection" — VERIFIED (https://arxiv.org/abs/2603.06604)

- **Citation.** Xiaohu Xie, Xiaohu Liu, Benjamin Yao. "Know When You're Wrong: Aligning Confidence with Correctness for LLM Error Detection." arXiv:2603.06604, Feb 2026.
- **Summary.** Normalised confidence from anchor-token probabilities (labels or yes/no self-evaluation) across seven tasks and five models; SFT calibrates while PPO, GRPO and DPO over-confidence. On Qwen3-4B, SFT raises AUROC from 0.806 to 0.879 and lowers calibration error from 0.163 to 0.034. In adaptive RAG, retrieving only when confidence is low uses 58% of retrievals and recovers 95% of the maximum gain on TriviaQA.
- **Relation to ours.** Strong support that calibrated typed answers from a 4B-class model are a usable gate; our judge is such a model used as a dedicated decision step, and we report the full Pareto curve.

#### Qian et al. 2026, "When Should Active RAG Retrieve? A Budget-Aware Evaluation of Utility, Calibration, and Cost" — VERIFIED (https://arxiv.org/abs/2607.24010)

- **Citation.** Pin Qian, Su Wang, Chong Peng, et al. "When Should Active RAG Retrieve? A Budget-Aware Evaluation of Utility, Calibration, and Cost." KDD 2026 Workshop on Evaluation and Trustworthiness of Agentic AI. arXiv:2607.24010.
- **Summary.** Argues that active-RAG comparisons are misleading without a stated operating point and treats retrieval as valuable only when it flips a wrong no-retrieval answer to right. Evaluates ranking quality of trigger scores, threshold transfer across budgets and trigger compute cost on multi-hop QA with open models; retrieval can harm, router rankings shift across datasets and budgets, and simple uncertainty or retrieval-score baselines often match learned routers. Recommends reporting frontiers, realised usage, threshold-transfer error, harm rates and cost.
- **Relation to ours.** The evaluation protocol our Pareto analysis should follow and cite: realised refinement rate, cost breakdown, frontier, and threshold transfer across the model ladder.

#### McCleary and Ghawaly 2026, "Quantifying the Accuracy and Cost Impact of Design Decisions in Budget-Constrained Agentic LLM Search" — VERIFIED (https://arxiv.org/abs/2603.08877)

- **Citation.** Kyle McCleary, James Ghawaly Jr. "Quantifying the Accuracy and Cost Impact of Design Decisions in Budget-Constrained Agentic LLM Search." LREC 2026. arXiv:2603.08877.
- **Summary.** A harness that shows the agent its remaining tool-call and token budget and removes the search tool when exhausted; six LLMs on three QA benchmarks. Accuracy rises with more searches only up to a modest cap; hybrid lexical plus dense retrieval with light reranking gives the largest gains; larger completion budgets help most on synthesis questions.
- **Relation to ours.** Confirms diminishing returns from extra searches; our gate skips the extra search exactly when the judge predicts it will not pay, and our retrieval benchmark reaches the same conclusion about hybrid retrieval with reranking.

#### Fang et al. 2026, "Inference-Time Budget Control for LLM Search Agents" — VERIFIED (https://arxiv.org/abs/2605.05701)

- **Citation.** Zhengru Fang, Senkang Forest Hu, Zhonghao Chang, et al. "Inference-Time Budget Control for LLM Search Agents." arXiv:2605.05701, May 2026.
- **Summary.** Two-stage control under hard tool-call and token budgets: a search-time controller scores retrieve, decompose or answer by estimated value per unit of remaining budget, and a finaliser revises only low-risk formatting errors. Beats four audited baselines on four multi-hop benchmarks, three backbones and four budget levels.
- **Relation to ours.** A richer controller than ours; we show that a one-threshold calibrated gate is enough to trace a useful Pareto curve for cheap models.

#### Sah, Zhang and Lian 2026, "Beyond Self-Knowledge: Propagating Uncertainty Across Reasoning and Retrieval in LLMs" — VERIFIED (https://arxiv.org/abs/2607.25600)

- **Citation.** Chandan Kumar Sah, Li Zhang, Xiaoli Lian. "Beyond Self-Knowledge: Propagating Uncertainty Across Reasoning and Retrieval in LLMs." arXiv:2607.25600, Jul 2026.
- **Summary.** Asks a black-box LLM for a provisional answer plus verbalised confidence and routes low-confidence questions to retrieval with a threshold frozen on validation data. Over 27,000 policy instances (six QA sets, three model families): mean F1 0.483 versus 0.467 always-retrieve and 0.401 never-retrieve, 20.4% fewer passages, better than random allocation in 17 of 18 settings; but the verbalised probe is poorly calibrated (AUROC 0.628) and adds 28.2% tokens.
- **Relation to ours.** Their verbalised confidence is poorly calibrated and costs tokens; our decision model is chosen for calibration and is far smaller than the generator, which is what makes the gate nearly free.

#### Aghajani Asl, Asgari-Bidhendi and Minaei-Bidgoli 2025, FAIR-RAG — VERIFIED (https://arxiv.org/abs/2510.22344)

- **Citation.** Mohammad Aghajani Asl, Majid Asgari-Bidhendi, Behrooz Minaei-Bidgoli. "FAIR-RAG." arXiv:2510.22344, Oct 2025.
- **Summary.** A structured evidence-assessment module builds a checklist of required findings and loops sub-queries until the evidence is sufficient; HotpotQA F1 0.453, 8.3 points above the best iterative baseline.
- **Relation to ours.** Closest to our per-intent coverage check (a checklist of what a complete answer needs), but LLM-driven and without cost reporting.

### B.3 Also verified, lower priority (thread B)

- Marina et al. 2025, "LLM-Independent Adaptive RAG" — VERIFIED (https://arxiv.org/abs/2505.04253). 27 question-only features decide retrieval without touching the LLM; matches LLM-based uncertainty methods on six datasets at much lower cost. Pre-retrieval gating; ours is post-retrieval.
- Wang et al. 2025, Chain-of-Retrieval (CoRAG) — VERIFIED (https://arxiv.org/abs/2501.14342). NeurIPS 2025. Trains step-by-step retrieval chains via rejection sampling and scales test-time compute by chain length; more than 10 EM points on multi-hop QA. Fixed compute budget versus our adaptive gate.
- Zhang et al. 2025, ARise — VERIFIED (https://arxiv.org/abs/2504.10893). ACL 2025. Risk-adaptive MCTS over reasoning states with dynamic retrieval; heavy search with large models, not our regime.
- Wu et al. 2026, "When Knowledge Is Not Free" — VERIFIED (https://arxiv.org/abs/2606.02245). Evidence has access-cost tiers under a budget; fixed selectors are brittle and agentic controllers vary strongly by model and task. Cost of evidence, not of model calls.
- Sun et al. 2026, AnySearch — VERIFIED (https://arxiv.org/abs/2609.00813). RL trains one agent to respect any search budget; learned budget policy versus our threshold.
- Julka 2026, retrieval-state lock-in — VERIFIED (https://arxiv.org/abs/2606.22728). Sample agreement is blind to shared bad retrieval: 42% (KG-RAG) and 59% (dense) of errors show zero dispersion. A caution for answer-side confidence gates; our judge inspects the evidence, not the answer.
- Chan et al. 2025, "Retrieval-augmented reasoning with lean language models" — VERIFIED (https://arxiv.org/abs/2508.11386). Fine-tunes Qwen2.5-Instruct with a dense retriever on NHS pages using DeepSeek-R1 traces; medical small-model RAG, single-shot and fine-tuned.
- Chen et al. 2024, "Learning to Retrieve Iteratively for In-Context Learning" — PARTIAL (https://arxiv.org/abs/2406.14739, EMNLP 2024; page not opened directly). Exemplar selection for semantic parsing; marginal.

**Thread B gap statement.** No published work combines (a) a calibrated, non-generative sufficiency judge external to the generator, (b) a retrieve-more loop gated on its probability, (c) a threshold sweep reported as a cost-latency-quality Pareto curve across a ladder of small models and a commercial model, and (d) a non-English domain corpus. The nearest combinations are TASR (calibrated logit margin, generator-internal), HALT (trained verifier, loops and seconds), Stop-RAG (learned value function), Tiny-Critic RAG (tiny gatekeeper, routing only) and Qian et al. 2026 (the evaluation protocol).


## C. Cost and latency as first-class metrics

### C.1 Cost-aware evaluation of agents and RAG

#### Kapoor et al. 2024, "AI Agents That Matter" — VERIFIED (https://arxiv.org/abs/2407.01502)

- **Citation.** Sayash Kapoor, Benedikt Stroebl, Zachary S. Siegel, Nitya Nadgir, Arvind Narayanan. "AI Agents That Matter." arXiv:2407.01502, 1 Jul 2024. The arXiv page shows no venue; the paper is often cited as TMLR 2025, which this survey could not confirm from the page.
- **Summary.** Argues that agent benchmarks that report accuracy alone reward needlessly complex and expensive agents and that evaluations must be cost-controlled. Proposes plotting agents on an accuracy-versus-inference-cost Pareto curve; on HumanEval, simple baselines (retry, warming, escalation) match complex agents at a fraction of the cost, and a DSPy modification cuts cost substantially at equal accuracy on HotPotQA. Also documents weak holdout sets and reproducibility problems.
- **Relation to ours.** The direct motivation for reporting cost and latency next to quality; we apply the prescription to a domain RAG agent and add wall-clock latency, which the paper does not treat.

#### Kapoor et al. 2026, Holistic Agent Leaderboard — VERIFIED (https://arxiv.org/abs/2510.11977; ICLR 2026 proceedings)

- **Citation.** Sayash Kapoor, Benedikt Stroebl, Peter Kirgis, et al. (31 authors). "Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation." ICLR 2026. arXiv:2510.11977.
- **Summary.** A parallel evaluation harness run over 21,730 agent rollouts, nine models and nine benchmarks at about $40,000, reporting cost next to accuracy; higher reasoning effort lowered accuracy in most runs, and log inspection found agents gaming tasks. Releases 2.5B tokens of logs.
- **Relation to ours.** Establishes cost-aware agent leaderboards as the norm; we add latency and a small-model regime.

#### Erol et al. 2025/2026, Cost-of-Pass — VERIFIED (https://arxiv.org/abs/2504.13359)

- **Citation.** Mehmet Hamza Erol, Batu El, Mirac Suzgun, Mert Yuksekgonul, James Zou. "Cost-of-Pass: An Economic Framework for Evaluating Language Models." arXiv:2504.13359 (v2 Feb 2026).
- **Summary.** Defines cost-of-pass as the expected dollar cost of obtaining a correct answer and the frontier cost-of-pass as the cheapest across models. Lightweight models are cheapest for basic quantitative tasks and large models for knowledge-intensive tasks; majority voting and self-refinement rarely justify their cost.
- **Relation to ours.** We can report cost-of-pass per pipeline variant, and the finding that unconditional self-refinement is rarely worth it is exactly why our refinement is gated.

#### Ferrazzi et al. 2026, "Is Agentic RAG worth it? An experimental comparison of RAG approaches" — VERIFIED (https://arxiv.org/abs/2601.07711; numbers from https://arxiv.org/html/2601.07711v2)

- **Citation.** Pietro Ferrazzi, Milica Cvjeticanin, Alessio Piraccini, Davide Giannuzzi. "Is Agentic RAG worth it? An experimental comparison of RAG approaches." ACL 2026 Industry Track. arXiv:2601.07711, v1 12 Jan 2026, v2 20 Apr 2026.
- **Summary.** Compares an "enhanced" fixed pipeline (semantic router deciding whether to retrieve, HyDE rewriting with gpt-4o, ELECTRA cross-encoder reranking) with an LLM-orchestrated agentic pipeline (PocketFlow, one RAG tool, up to three turns) on NQ, FIQA, CQADupStack-EN and FEVER, with Qwen3-0.6B, 4B, 8B and 32B as generators and Selene-70B as judge. Averaged over datasets the agentic pipeline uses about 3.3 times the input tokens, 1.9 times the output tokens and 1.5 times the time. On FIQA answer quality (Table 7) the agentic pipeline wins only at 0.6B (58.4 versus 51.4) and loses at 4B (87.3 versus 90.9), 8B (91.0 versus 93.7) and 32B (91.8 versus 95.5). Sub-task results: the agent wins intent routing on two datasets but collapses on FEVER (F1 64.6 versus 87.9), wins query rewriting on average (NDCG@10 55.6 versus 52.8), and loses document refinement to both the enhanced pipeline and the naive baseline (FIQA 43.4 versus 51.0 and 45.0), re-retrieving in only about 10% of cases. End-to-end time on FIQA: Qwen3-0.6B 8.1 s enhanced versus 22.1 s agentic; Qwen3-32B 62.6 s versus 93.8 s. The authors conclude that "neither Enhanced nor Agentic RAG is universally superior".
- **Relation to ours.** The closest published analogue of our workflow-versus-agent sweep: same model family (Qwen3), same conclusion direction (the fixed pipeline wins from 4B upward and the agent is costlier). It must be cited and contrasted. Differences we add: a non-generative calibrated decision model for the decision steps, a threshold-swept retrieve-more gate rather than an agent deciding to re-retrieve, a controlled comparison in which both arms use the same tools and the same structured-output interface, multi-turn conversational Vietnamese questions, a commercial model in the ladder, and dollar cost per query rather than token ratios. Note also that their "enhanced" pipeline still spends about half its time on an LLM rewrite step, which is the step our design moves to the small generator.

#### Mishra 2026, "Cost-Aware Query Routing in RAG: Empirical Analysis of Retrieval Depth Tradeoffs" — VERIFIED (https://arxiv.org/abs/2606.02581)

- **Citation.** Sanjay Kumar Mishra. arXiv:2606.02581, 2026.
- **Summary.** A per-query router picks a retrieval-depth bundle (none to top-10) by maximising a utility that penalises predicted latency and billed tokens; on a 28-query benchmark it used 26% fewer billed tokens than always-heavy retrieval and had 34% lower latency than always-direct inference at equal quality. Very small benchmark.
- **Relation to ours.** Same knob (retrieval depth) chosen a priori; we decide after seeing evidence with a calibrated judge on a 500-item set.

#### Dallaire 2025, "Practical RAG Evaluation: A Rarity-Aware Set-Based Metric and Cost-Latency-Quality Trade-offs" — VERIFIED (https://arxiv.org/abs/2511.09545)

- **Citation.** Etienne Dallaire. arXiv:2511.09545, Nov 2025.
- **Summary.** Argues rank metrics fit RAG poorly, proposes RA-nWG@K, and sweeps embedders, rerankers, HNSW and quantisation on a production corpus, keeping Pareto-optimal points across cost, latency and quality with operator rules such as "best quality under a latency SLA".
- **Relation to ours.** The same three-axis framing on the retrieval side; we extend it to the LLM-call structure of an agent and to the model-size ladder.

### C.2 Model cascades and routing

#### Chen, Zaharia and Zou 2023, FrugalGPT — VERIFIED (https://arxiv.org/abs/2305.05176; TMLR venue not confirmed)

- **Citation.** Lingjiao Chen, Matei Zaharia, James Zou. "FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance." arXiv:2305.05176, May 2023. Often cited as TMLR 2024; the arXiv page lists no journal reference and OpenReview could not be opened during this survey.
- **Summary.** Observes that LLM API prices differ by up to two orders of magnitude and proposes prompt adaptation, LLM approximation (caching, cheaper fine-tunes) and LLM cascades. The cascade queries cheaper models first and escalates when a learned scorer deems the answer unreliable; it matches GPT-4 at up to 98% lower cost or beats GPT-4 accuracy by 4% at the same cost.
- **Relation to ours.** FrugalGPT's scorer decides which generator to call; our judge decides whether to retrieve more, is itself a calibrated tiny model, and we report latency as well as cost.

#### Ong et al. 2025, RouteLLM — VERIFIED (https://arxiv.org/abs/2406.18665; ICLR 2025 proceedings)

- **Citation.** Isaac Ong, Amjad Almahairi, Vincent Wu, et al. "RouteLLM: Learning to Route LLMs with Preference Data." ICLR 2025. arXiv:2406.18665.
- **Summary.** Trains routers (matrix factorisation, BERT and causal-LLM classifiers, similarity-weighted ranking) on Chatbot Arena preference data to choose between a strong and a weak model per query; over 2x cost reduction on MT-Bench, MMLU and GSM8K with no quality loss, and the routers transfer when the model pair is swapped.
- **Relation to ours.** RouteLLM routes between generators before generation; we fix the generator per step and spend the decision budget on typed judgments inside the loop.

#### Aggarwal et al. 2024, AutoMix — VERIFIED (https://arxiv.org/abs/2310.12963)

- **Citation.** Pranjal Aggarwal, Aman Madaan, Ankit Anand, et al. "AutoMix: Automatically Mixing Language Models." NeurIPS 2024. arXiv:2310.12963.
- **Summary.** A small model answers and then performs few-shot self-verification; because that signal is noisy, a POMDP router decides whether to escalate. Across five LLMs and five datasets it beats cascade baselines and cuts compute cost by more than 50% at comparable accuracy.
- **Relation to ours.** We replace the noisy self-verification with a separate calibrated decision model and gate on its probability.

#### Ding et al. 2024, Hybrid LLM — VERIFIED (https://arxiv.org/abs/2404.14618)

- **Citation.** Dujian Ding, Ankur Mallick, Chi Wang, et al. "Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing." ICLR 2024. arXiv:2404.14618.
- **Summary.** A router predicts query difficulty and sends easy queries to a small edge model and hard ones to a large cloud model, with a quality target tunable at test time; reduces calls to the large model by up to 40% without lowering quality.
- **Relation to ours.** The threshold-adjustable quality knob is the same mechanism as our gate, applied to model choice rather than retrieval depth.

#### Yue et al. 2024, "LLM Cascades with Mixture of Thoughts Representations" — VERIFIED (https://arxiv.org/abs/2310.03094)

- **Citation.** Murong Yue, Jie Zhao, Min Zhang, Liang Du, Ziyu Yao. ICLR 2024. arXiv:2310.03094.
- **Summary.** Uses agreement between chain-of-thought and program-of-thought samples from GPT-3.5-turbo as a difficulty signal, escalating to GPT-4 on disagreement; matches GPT-4 at about 40% of its cost on six reasoning benchmarks.
- **Relation to ours.** Confidence from sampling agreement costs multiple generations; ours is one forward pass of a decision model.

#### Dohan et al. 2022, "Language Model Cascades" — VERIFIED (https://arxiv.org/abs/2207.10342). ICML 2022 Beyond Bayes workshop. Formalises compositions of prompted models as probabilistic programs; no experiments. The conceptual origin of the term; our workflow is a fixed cascade whose non-generative nodes are decision-model calls.

#### Hu et al. 2024, RouterBench — VERIFIED (https://arxiv.org/abs/2403.12031). ICML 2024 Agentic Markets workshop. Over 405k inference outcomes on eight datasets for offline router evaluation, with routing evaluated on a cost-quality plane by non-decreasing convex hulls. We adopt the same Pareto-plane presentation for retrieve-more decisions and add latency.

#### Varangot-Reille et al. 2025, "Doing More with Less: A Survey on Routing Strategies" — VERIFIED (https://arxiv.org/abs/2502.00409; JAIR, DOI 10.1613/jair.1.19801). Organises routing by when it happens, the objective and the mechanism. Our paper is an instance of pre-generation supervised cost-quality routing applied to a domain RAG agent.

#### Behera et al. 2025, "Towards Efficient Multi-LLM Inference: Characterization and Analysis of LLM Routing and Hierarchical Techniques" — VERIFIED (https://arxiv.org/abs/2506.06579). Contrasts routing with cascading and compares both on latency, cost and accuracy with an edge focus. Vocabulary for describing our design as a confidence-gated hierarchical step inside a fixed workflow.

#### Moslem and Kelleher 2026, "Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey" — VERIFIED (https://arxiv.org/abs/2603.04445). TMLR 2026. Seven routing paradigms including uncertainty quantification and cascading. The most recent survey to cite.

#### Kotte 2026, UCCI; Peale et al. 2026, Flexible Routing — see B.2.

### C.3 RAG serving latency (systems papers)

- Jin et al. 2024, RAGCache — VERIFIED (https://arxiv.org/abs/2404.12457). Caches KV states of retrieved documents in a knowledge tree across GPU and host memory; cuts time-to-first-token by up to 4x and raises throughput up to 2.1x on vLLM and Faiss.
- Jiang et al. 2024, PipeRAG — VERIFIED (https://arxiv.org/abs/2403.05676). Pipelines retrieval and generation with flexible retrieval intervals and a performance model; up to 2.6x lower latency while improving quality. A systems-level version of the latency-quality trade-off of iterative retrieval.
- Lin et al. 2025/2026, TeleRAG — VERIFIED (https://arxiv.org/abs/2502.20969). Lookahead prefetch of IVF clusters; up to 1.53x lower single-query latency.
- Jiang et al. 2025, RAGO — VERIFIED (https://arxiv.org/abs/2503.14649). RAGSchema for RAG variants including iterative ones; up to 2x QPS per chip and 55% lower TTFT. RAGO treats pipeline shape as given; we ask which shape a cheap deployment should choose.
- Zhang et al. 2026, RAG-Stack — VERIFIED (https://arxiv.org/abs/2608.03487). Co-optimises algorithm and system configuration to produce quality-performance Pareto frontiers covering 52.5% to 153.2% more normalised space than prior search. The closest systems work to our Pareto curve; ours is over one interpretable knob and includes an autonomous-agent arm.
- Cai and Zafarani 2026, PACE — VERIFIED (https://arxiv.org/abs/2608.25115). Adaptive reranking budgets under load; peripheral.

### C.4 Healthcare RAG that reports latency or cost

#### Nygren et al. 2026 — see G (Scientific Reports 16:12754; text RAG 82.63 s versus GraphRAG 0.09 s on reverse queries).

#### Xiong et al. 2024, MedRAG / MIRAGE — VERIFIED (https://arxiv.org/abs/2402.13178; https://aclanthology.org/2024.findings-acl.372/)

- **Citation.** Guangzhi Xiong, Qiao Jin, Zhiyong Lu, Aidong Zhang. "Benchmarking Retrieval-Augmented Generation for Medicine." Findings of ACL 2024, pp. 6233-6251. arXiv:2402.13178.
- **Summary.** MIRAGE has 7,663 questions from five medical QA sets; 41 corpus-retriever-LLM combinations consumed 1.8 trillion prompt tokens. RAG improves six LLMs by up to 18% over chain-of-thought and lifts GPT-3.5 and Mixtral to GPT-4 level; combining corpora and retrievers helps. No latency or cost reported.
- **Relation to ours.** Already cited; we add cost, latency, agentic control and a non-English pharmaceutical domain.

#### Zakka et al. 2024, Almanac — VERIFIED (https://arxiv.org/abs/2303.01229; NEJM AI 1(2), DOI 10.1056/AIoa2300068). Retrieval over guidelines plus a calculator tool; on 130 scenarios rated by five physicians it raised factuality by a mean 18%. No cost or latency.

#### Kazemzadeh et al. 2025/2026, DrugRAG — VERIFIED (https://arxiv.org/abs/2512.14896)

- **Citation.** Houman Kazemzadeh, Kiarash Mokhtari Dizaji, Seyed Reza Tavakoli, et al. "DrugRAG: Enhancing Pharmacy LLM Performance Through A Novel Retrieval-Augmented Generation Pipeline." arXiv:2512.14896 (v2 May 2026).
- **Summary.** Ten LLMs (8B to 70B+) on 141 pharmacy-licensure-style questions (baseline 46% to 92%); a three-step RAG pipeline raises all five tested models by 7 to 21 points (Llama 3.1 8B from 46% to 67%, Gemma 3 27B from 61% to 71%), with significance mainly for small open models. Latency and cost discussed only qualitatively.
- **Relation to ours.** Confirms RAG helps small models most on drug questions; we quantify the efficiency price.

#### Bang et al. 2025, "Retrieval Augmented LLM System for Comprehensive Drug Contraindications" — VERIFIED (https://arxiv.org/abs/2508.06145). GPT-4o-mini with hybrid retrieval and reranking over Korean DUR data; on 300 QA pairs accuracy rose from 0.49-0.57 to 0.94 (age), 0.87 (pregnancy) and 0.89 (concomitant drugs). No efficiency metrics. Same question types as ours.

#### Wada et al. 2025, "RAG elevates local LLM quality in radiology contrast media consultation" — VERIFIED (https://pmc.ncbi.nlm.nih.gov/articles/PMC12223273/; npj Digital Medicine 8:395, DOI 10.1038/s41746-025-01802-z)

- **Summary.** A local Llama 3.2 11B with RAG versus GPT-4o mini, Gemini 2.0 Flash and Claude 3.5 Haiku on 100 consultations; RAG cut hallucinations from 8% to 0% and raised clinical accuracy from 14.2 to 21.5 of 25; mean response time 2.58 s versus 4.87 s, 3.14 s and 7.25 s for the cloud models, although Gemini still ranked first overall.
- **Relation to ours.** One of the few clinical RAG papers with wall-clock latency for a small local model; we extend to an agentic loop and dollar cost.

#### Wind et al. 2025, "Multi-step retrieval and reasoning improves radiology question answering with LLMs" — VERIFIED (https://arxiv.org/abs/2508.00743; npj Digital Medicine 8:790, DOI 10.1038/s41746-025-02250-5)

- **Summary.** 25 LLMs from 0.5B to over 670B on 104 expert questions plus 65 board-style questions; multi-step retrieval and reasoning improves accuracy most for small models, with under 2% gain above 200B, and cuts hallucinations by 9.4%. A search snippet of the PDF reports response time rising from about 54 s to 324 s per question for 7-8B models (not confirmed from the abstract page).
- **Relation to ours.** Evidence that agentic retrieval helps small models at a large latency cost, which is what our gate aims to control.

#### Fensore et al. 2025, "Does Domain-Specific RAG Help LLMs Answer Consumer Health Questions?" — VERIFIED (https://proceedings.mlr.press/v298/fensore25a.html). MLHC 2025. Plain models beat RAG on NIDDK MedQuAD because retrieval was weak (Precision@5 0.15). A negative result that argues for measuring evidence sufficiency before trusting retrieval, which is what our judge does.

#### Hasan et al. 2026, CareConnect, "Toward Trustworthy LLM Agents in Healthcare" — VERIFIED (https://arxiv.org/abs/2607.05055). A tool-calling scheduling agent with RAG and deterministic guardrails; on 680 scenarios 91.8% task completion, 96.0% safety compliance, 2.2 s median latency and $0.0324 per appointment. Reports agent latency and per-task cost in healthcare, for logistics rather than drug information.

#### Choi et al. 2024, MALADE — UNVERIFIED (arXiv:2408.01869 not opened). Multi-agent pharmacovigilance RAG with GPT-4 class models, AUC 0.90 against OMOP ground truth per search listing; no cost reporting.

### C.5 Thread C items searched and not found

No arXiv paper titled "A Survey on LLM Routing"; no dedicated efficiency-focused RAG survey (general RAG surveys arXiv 2506.00054 and 2508.06401 touch efficiency only in passing); no 2025-2026 pharmacovigilance RAG beyond Nygren et al. and MALADE.

**Thread C gap statement.** Cost-aware agent evaluation (Kapoor et al.), cascades and routers (FrugalGPT, RouteLLM, AutoMix, UCCI), RAG serving (RAGCache, RAGO, RAG-Stack) and one direct workflow-versus-agent RAG study (Ferrazzi et al. 2026) exist, but no work reports quality, wall-clock latency and dollar cost per configuration for an agentic RAG pipeline across a small-model ladder and a commercial model on a non-English medical corpus, and none isolates the cost of the decision steps from the generation steps.


## D. Small and classifier models as guardrails and judges

### D.1 Guardrail models

#### Inan et al. 2023, Llama Guard — VERIFIED (https://arxiv.org/abs/2312.06674)

- **Citation.** Hakan Inan, Kartikeya Upasani, Jianfeng Chi, et al. "Llama Guard: LLM-based Input-Output Safeguard for Human-AI Conversations." arXiv:2312.06674, Dec 2023.
- **Summary.** Instruction-tunes Llama 2 7B to classify prompts and responses against a safety taxonomy, emitting safe/unsafe plus category labels; matches or exceeds existing moderation tools on OpenAI Moderation and ToxicChat and supports zero- and few-shot taxonomy changes.
- **Relation to ours.** A guardrail as a generative 7B model; ours is a sub-second typed decision from a decision model, and we measure its latency share.

#### Meta 2024, Llama Guard 3 (1B, 8B) — VERIFIED (https://huggingface.co/meta-llama/Llama-Guard-3-8B; https://huggingface.co/meta-llama/Llama-Guard-3-1B)

- **Summary.** 8B classifies 14 categories in eight languages; English response-classification F1 0.939 at FPR 0.040. The 1B model, pruned and distilled from 8B, scores F1 0.899 / FPR 0.090 in English and 0.723 / 0.130 in Vietnamese versus 0.890 / 0.034 for 8B, a large small-model penalty in Vietnamese.
- **Relation to ours.** A directly relevant baseline for a Vietnamese guardrail, and a documented warning that small guards degrade in Vietnamese, which is why our guardrail is evaluated on in-domain Vietnamese pharma prompts.

#### Meta 2025, Llama Guard 4 — VERIFIED (https://dev.meta.ai/llama/docs/model-cards-and-prompt-formats/llama-guard-4/). 12B multimodal safeguard; no numbers on the page. Shows the guardrail-size trend we push against.

#### Zeng et al. 2024, ShieldGemma — VERIFIED (https://arxiv.org/abs/2407.21772)

- **Citation.** Wenjun Zeng, Yuchi Liu, Ryan Mullins, et al. "ShieldGemma: Generative AI Content Moderation Based on Gemma." arXiv:2407.21772, 2024.
- **Summary.** Gemma 2 classifiers (2B, 9B, 27B) for four harm types, trained mostly on synthetic data; 10.8% AU-PRC gain over Llama Guard and 4.3% over WildGuard.
- **Relation to ours.** Same yes/no decision shape; we need calibrated probabilities to gate downstream steps, not only labels.

#### Zeng et al. 2025, ShieldGemma 2 — VERIFIED (https://arxiv.org/abs/2504.01081). 4B Gemma 3 image moderation; image-only.

#### Meta 2024/2025, Prompt Guard and Llama Prompt Guard 2 — VERIFIED (https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M)

- **Summary.** Encoder classifiers (mDeBERTa 86M, DeBERTa-xsmall 22M) that label inputs benign or malicious. Prompt Guard 2 86M reaches AUC 0.998 and 97.5% recall at 1% FPR with 92.4 ms latency on an A100 for 512 tokens; the 22M model gives 88.7% recall at 19.3 ms. AgentDojo attack-prevention rate 81.2% (86M) versus 22.2% for the ProtectAI classifier.
- **Relation to ours.** Shows an 86M encoder can be a sub-100 ms injection guard; ours must also judge in-domain scope and Vietnamese.

#### ProtectAI 2024, deberta-v3-base-prompt-injection-v2 — VERIFIED (https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2). About 0.2B parameters; 95.25% accuracy and 99.74% recall on 20,000 held-out English prompts. The reference tiny encoder guardrail; Red Hat's 2026 benchmark (D.3) shows it beating Jev on injection at 54 ms.

#### Li and Liu 2024/2025, InjecGuard — VERIFIED (https://arxiv.org/abs/2410.22770). NotInject (339 benign trigger-word prompts) drops state-of-the-art guards to about 60% accuracy; InjecGuard improves by 30.8% on it. Over-defence is a false-positive cost that a calibrated probability lets us trade off explicitly.

#### Jacob et al. 2025, PromptShield — VERIFIED (https://arxiv.org/abs/2501.15145). ACM CODASPY 2025. A benchmark and detector focused on low false-positive operating points, which is how we tune our guardrail threshold.

#### Piet et al. 2024, Jatmo — VERIFIED (https://arxiv.org/abs/2312.17673). Task-specific fine-tuning of a non-instruction-tuned base so it cannot follow injected instructions; attacks succeed under 0.5% of the time versus 87% on GPT-3.5-Turbo. Our decision-only steps have the same property by construction because they cannot emit free text.

#### Greshake et al. 2023, "Not what you've signed up for" — VERIFIED (https://arxiv.org/abs/2302.12173). Defines indirect prompt injection via retrieved data. The threat model that justifies screening retrieved documents with a non-generative judge.

#### Han et al. 2024, WildGuard — VERIFIED (https://arxiv.org/abs/2406.18495). NeurIPS 2024. A 7B moderator for harmful prompts, harmful responses and refusals; cuts jailbreak success from 79.8% to 2.4% as a filter. Three decisions from one model, which we do with a decision model and report per-decision latency.

#### Ghosh et al. 2024/2025, Aegis and Aegis 2.0 — VERIFIED (https://arxiv.org/abs/2404.05993; https://arxiv.org/abs/2501.09004). Risk taxonomy and 34,248-sample dataset; parameter-efficient small guards match fully fine-tuned ones.

#### Liu et al. 2025, GuardReasoner — VERIFIED (https://arxiv.org/abs/2501.18492). 1B/3B/8B guards that reason before deciding; the 8B averages 5.74% higher F1 than GPT-4o with CoT over 13 benchmarks. The opposite design choice (spend tokens on reasoning inside the guard); we quantify what a non-reasoning typed guard gives up against its latency gain.

#### Kumar et al. 2025, PolyGuard — VERIFIED (https://arxiv.org/abs/2504.04377). COLM 2025. 17-language guard; Vietnamese is not listed in the abstract.

#### OpenAI 2025, gpt-oss-safeguard — VERIFIED (technical report PDF at cdn.openai.com; https://huggingface.co/openai/gpt-oss-safeguard-120b). Policy-conditioned reasoning classifiers (120B and 20B); the report states that classifiers trained on tens of thousands of labels can still beat policy reasoning and that OpenAI uses smaller faster classifiers to decide what to send to the reasoner. That deployment pattern (tiny classifier in front, reasoner behind) is what we evaluate end to end.

#### Zhao et al. 2025, Qwen3Guard — VERIFIED (https://arxiv.org/abs/2510.14276). 0.6B, 4B and 8B guards for 119 languages with three-way labels and a streaming token-level variant. The natural guard baseline for a Qwen-based pipeline and the only one with an explicit 0.6B size.

#### Padhi et al. 2024, Granite Guardian — VERIFIED (https://arxiv.org/abs/2412.07724). Risk detectors that also cover RAG risks (context relevance, groundedness, answer relevance); AUC 0.854 on RAG-hallucination benchmarks. One of few guards that also judges groundedness; our evidence-sufficiency judge plays that role with calibrated probabilities.

#### Zheng, Rana and Stolcke 2025, "Lightweight Safety Guardrails Using Fine-tuned BERT Embeddings" — VERIFIED (https://arxiv.org/abs/2411.14398). COLING 2025 Industry. A 67M Sentence-BERT guard comparable to 7B LlamaGuard on AEGIS. Direct support that guard decisions do not need a generative LLM.

### D.2 Small judges, judge calibration and structured outputs

#### Kim et al. 2024, Prometheus and Prometheus 2 — VERIFIED (https://arxiv.org/abs/2310.08491; https://arxiv.org/abs/2405.01535). ICLR 2024 and EMNLP 2024. 13B and 7B/8x7B open judges; Prometheus reaches 0.897 Pearson with humans versus 0.882 for GPT-4. Open judges that generate rubric feedback; ours is a non-generative probability used for control.

#### Zhu, Wang and Wang 2025, JudgeLM — VERIFIED (https://arxiv.org/abs/2310.17631). ICLR 2025. 7B/13B/33B judges; JudgeLM-7B judges 5K samples in about three minutes on eight A100s. Reports throughput; we report per-decision latency on cheap hosted inference.

#### Wang et al. 2024, PandaLM — VERIFIED (https://arxiv.org/abs/2306.05087). ICLR 2024. A 7B pairwise judge at 88.28% of GPT-4's F1.

#### Flow AI 2024, Flow-Judge-v0.1 — VERIFIED (https://flow-ai.com/blog/flow-judge). A 3.8B judge; pass/fail F1 0.955 versus 0.910 for gpt-4o-mini; PubMedQA 0.767 versus 0.832. A sub-4B judge with medical numbers.

#### Alexandru et al. 2025, Atla Selene Mini — VERIFIED (https://arxiv.org/abs/2501.17195). An 8B evaluator that beats GPT-4o-mini on 11 benchmarks; used as the judge in Ferrazzi et al. 2026.

#### Deshpande et al. 2024, GLIDER — VERIFIED (https://arxiv.org/abs/2412.14140). A 3B evaluator with span highlighting, comparable to models 17 times its size.

#### LLM-as-a-judge surveys — VERIFIED (Gu et al., arXiv:2411.15594; Li et al., EMNLP 2025, arXiv:2411.16594; Li et al., arXiv:2412.05579). None has a dedicated small-judge section; the missing "small, calibrated, in-loop judge" angle is ours.

#### Saad-Falcon et al. 2024, ARES — VERIFIED (https://arxiv.org/abs/2311.09476)

- **Citation.** Jon Saad-Falcon, Omar Khattab, Christopher Potts, Matei Zaharia. "ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems." NAACL 2024. arXiv:2311.09476.
- **Summary.** Fine-tunes lightweight judges for context relevance, answer faithfulness and answer relevance on synthetic data, then corrects their errors with prediction-powered inference using a few hundred human labels; judges stay accurate across eight tasks under domain shift.
- **Relation to ours.** Already cited. The PPI-calibrated small-judge recipe is the template for our calibrated evidence-sufficiency judge, which we move from offline evaluation into the online control loop.

#### Angelopoulos et al. 2023, Prediction-Powered Inference — VERIFIED (https://arxiv.org/abs/2301.09633; Science 382:669-674, DOI 10.1126/science.adi6000). Already cited.

#### Jung, Brahman and Choi 2025, "Trust or Escalate: LLM Judges with Provable Guarantees for Human Agreement" — VERIFIED (https://arxiv.org/abs/2407.18370; ICLR 2025 proceedings)

- **Summary.** Judges estimate confidence and abstain or escalate; simulated annotators improve calibration, and cascaded selective evaluation starts with a cheap judge and escalates with a risk-control guarantee. A Mistral-7B-first cascade guarantees over 80% human agreement with almost 80% coverage on a Chatbot Arena subset where GPT-4 alone rarely reaches 80%.
- **Relation to ours.** The closest formal precedent for confidence-gated escalation; we gate a retrieval action rather than a judge, with a decision model whose calibration is trained in.

#### Tian et al. 2025, "Overconfidence in LLM-as-a-Judge" — VERIFIED (https://arxiv.org/abs/2508.06225). Judges' verbalised confidence exceeds accuracy across 14 models on JudgeBench. Confirms LLM self-confidence is a poor gate signal.

#### Radharapu et al. 2025, "Calibrating LLM Judges: Linear Probes" — VERIFIED (https://arxiv.org/abs/2512.22245). Brier-loss linear probes on hidden states give better-calibrated uncertainty than verbalised or multi-sample methods at about 10x lower compute. An alternative route to a calibrated gate when one controls the judge's weights.

#### Lee et al. 2026, "How to Correctly Report LLM-as-a-Judge Evaluations" — VERIFIED (https://arxiv.org/abs/2511.21140). ICML 2026. Corrects judge sensitivity and specificity bias with a human-labelled calibration set and gives confidence intervals accounting for both datasets. We follow this for judge-scored results.

#### Landesberg and Narayan 2025/2026, Causal Judge Evaluation — VERIFIED (https://arxiv.org/abs/2512.11150). A 5% oracle fraction yields 99% pairwise ranking accuracy at 14x lower cost.

#### Tian et al. 2023, "Just Ask for Calibration" — VERIFIED (https://arxiv.org/abs/2305.14975). EMNLP 2023. For RLHF models, verbalised confidences beat token probabilities on TriviaQA, SciQ and TruthfulQA. The baseline way to get confidence from a generative small LLM, against which a calibration-trained model is compared.

#### Xiong et al. 2024, "Can LLMs Express Their Uncertainty?" — VERIFIED (https://arxiv.org/abs/2306.13063). ICLR 2024. Verbalised confidence is overconfident and consistency-based methods help only somewhat. Explains why sampling-based confidence is costly and weak for small models.

#### Es et al. 2023/2025, RAGAS — VERIFIED (https://arxiv.org/abs/2309.15217). Already cited; metric definitions only.

#### Tang, Laban and Durrett 2024, MiniCheck — VERIFIED (https://arxiv.org/abs/2404.10774). EMNLP 2024. MiniCheck-FT5 (770M) matches GPT-4 on LLM-AggreFact at 400x lower cost. Strong evidence that a sub-1B model can do faithfulness checks.

#### Ravi et al. 2024, Lynx — VERIFIED (https://arxiv.org/abs/2407.08488). 8B and 70B hallucination judges with HaluBench (includes PubMedQA-derived items); above our decision-model budget.

#### Warner et al. 2024, ModernBERT — VERIFIED (https://arxiv.org/abs/2412.13663). The natural open encoder for training one's own decision steps, and the base of the open decision model Laya.

#### Structured output and small models

- Tam et al. 2024, "Let Me Speak Freely?" — VERIFIED (https://arxiv.org/abs/2408.02442). Reports that JSON format constraints reduce reasoning accuracy while classification is less affected.
- Kurt 2024, "Say What You Mean" (dottxt) — VERIFIED (https://blog.dottxt.ai/say-what-you-mean.html). Re-runs the disputed tasks with constrained decoding and finds structured at least as good; identifies flaws in the original setup.
- Schall and de Melo 2025, "The Hidden Cost of Structure" — VERIFIED (https://aclanthology.org/2025.ranlp-1.124/). RANLP 2025. Across 11 models, instruction-tuned models degrade under constrained decoding on generation but stay stable on classification.
- Ray 2026, "The Constraint Tax" — VERIFIED (https://arxiv.org/abs/2605.26128). On Qwen2.5-0.5B/1.5B and SmolLM2-1.7B, hard schema decoding raised validity from 61.5% to 100% but dropped accuracy from 19.7% to 11.0%; a 1.5B model fell from 91.5% to 48.0% executable accuracy on a tool-call task.
- **Relation to ours.** Together these support the split at the heart of contribution 1: constrain the decision steps (classification-like, stable under constraints, and better served by a purpose-trained decision model than by a tiny generative LLM under a hard schema) and leave the generation steps free.

#### Small classifiers versus LLM prompting in production

- Valdes Gonzalez 2026, "Cost-Aware Model Selection for Text Classification" — VERIFIED (https://arxiv.org/abs/2602.06370). Fine-tuned encoders match or beat GPT-4o and Claude Sonnet 4.5 at one to two orders of magnitude lower cost and latency, analysed with Pareto frontiers.
- Rodrigues and Vas 2026, "When Do LLMs Replace Fine-Tuned NLU?" — VERIFIED (https://arxiv.org/abs/2608.20371). Fine-tuned RoBERTa beats zero-shot Claude Haiku on ATIS (95.9 versus 84.1) at millisecond latency versus 981 ms, but the LLM wins out-of-scope recall (85.6 versus 58.1). Why our per-intent coverage decision keeps a calibrated probability rather than a hard label.
- Tran et al. 2025, Arch-Router — VERIFIED (https://arxiv.org/abs/2506.16655). A 1.5B routing model for preference-aligned routing.


### D.3 Decision models ("System One" models) and their independent evaluations (September-October 2026)

This is the thread that contribution 1 depends on. "Decision model" is a product category that appeared in September 2026: a non-generative model that reads text plus one or more typed questions and returns, for each, a probability distribution over caller-defined options (or a yes/no probability, or a probability over ordered levels) in one forward pass, with no output tokens. Because every answer is a probability, the output can be thresholded, which is what our confidence gate does. The category has no peer-reviewed origin paper; the primary sources are vendor posts and model cards, and the independent evidence is a handful of arXiv preprints from late September and October 2026. Each is listed below with what it actually shows.

#### TypeSafe AI, Jev 1.13 (closed weights, hosted) — VERIFIED (vendor pages: https://typesafe.ai/blog/introducing-system-one-models-and-jev, https://docs.typesafe.ai/models)

- **Citation.** Diogo Almeida (TypeSafe AI). "Introducing System One models and Jev." TypeSafe AI blog, 2026 (launch reported by multiple secondary sources as 15 September 2026; the post page displays 13 October 2026 as its date, so cite the URL with an access date). Model documentation: docs.typesafe.ai, model id `jev-1.13.0` (aliases `jev-latest`, `jev-preview`).
- **Summary.** The post defines a System One model as "a new class of frontier models built to make fast, structured decisions that software can use directly": input is unstructured state, output is typed probabilistic decisions, and the model cannot produce a type error because the output space is declared in advance. Three question types: Choice (one of up to 255 options, with a probability per option and a confidence), Score (an ordered rubric of 2-10 levels, returning an expected level and per-level probabilities) and Noul (the probability that a yes/no proposition holds). Training is described only as "Reinforcement Learning for Calibrated Decisions (RLCD)", which rewards honest probabilities; no architecture, weights or paper are published. Documented limits: 64k tokens per request and 32k for state plus the longest question, text input only, English is the primary language and CJK is handled less well, and the docs warn the model is weak at arithmetic, counting and dates and can be steered by adversarial text. Price $0.042 per million input tokens with output free; the post claims 70-500 ms end-to-end and a Pareto lead on TypeSafe's own "workflow evals", with the caveats (written by the vendor) that the reference answers average two frontier models and that the headline 193.6x speed and 444.6x cost figures are "likely at the high end". Intended uses named in the post: guardrails (verifying outputs, reasoning traces and prompts; jailbreak detection), routing and branching inside software workflows, and judging.
- **Relation to ours.** Jev is the decision model in our pipeline. The paper should cite the launch post and the model docs with the model id and access date, state that calibration is a vendor claim with no published metric, and note the English-primary limitation, since our inputs are Vietnamese. Our measurements of the judge's calibration on Vietnamese drug evidence are therefore new evidence, not a reproduction.

#### Simon Willison 2026, "Jev" (independent write-up) — VERIFIED (https://simonwillison.net/2026/Sep/21/jev/)

- **Citation.** Simon Willison. "Jev." simonwillison.net, 21 September 2026.
- **Summary.** An independent description of the API shape (state plus parallel questions; Noul, Choice, Score), small experiments (scoring cities, reranking BM25 results), and a trust caveat: because the model returns only numbers, one cannot see which parts of the input drove a decision, so hidden bias is harder to find and evaluation matters more than for a generative model. Confirms the pricing and that output is unmetered.
- **Relation to ours.** Useful as a neutral citation for what the API does and for the "opaque score" caveat that motivates our calibration measurement.

#### Jev Decision Index (community leaderboard) — PARTIAL (https://huggingface.co/spaces/multimodalart/jev-decision-index; secondary description at https://aiweekly.co/alerts/jev-decision-index-ranks-30-open-weight-decision-models)

- **Citation.** "Jev Decision Index." Hugging Face Space by multimodalart, posted 22 September 2026.
- **Summary.** A frozen suite of 132,422 requests across 37 benchmarks, 19 of which form the scored panel in five equal-weight areas (Tools and Automation, Retrieval and Classification, Language Understanding, Knowledge and Reasoning, Arts and Human Judgment); headline score is 100 times the mean of the area scores. Engines may not truncate requests, drop options or use custom prompts; unsupported, errored and abstained requests score zero before chance normalisation; submissions go through pull requests and are re-scored. The Space page itself could not be read during this survey (it showed only a "Refreshing" state), so the current version and rows are unconfirmed; vendors quote scores against versions 0.2.1, 0.3 and 0.4.0.
- **Relation to ours.** The only shared benchmark for the category. Scores quoted by vendors (d1-3B 48.57 on 0.2.1, for example) are self-reported runs of the official scorer, which the paper should say if it cites them.

#### AWS Strands Labs, Strands Decider 2B (open weights, full recipe) — PARTIAL (primary: https://strandsagents.com/blog/introducing-strands-decider/, https://github.com/strands-labs/strands-decider, https://huggingface.co/StrandsAgents/strands-decider-2B-hobson-v21; details read from https://www.eesel.ai/blog/strands-decider)

- **Citation.** Marc Brooker, Mike Chambers, Fabio Nonato de Paula (Strands Labs, AWS). "Introducing Strands Decider." Strands Agents blog, 1 October 2026. Model: `StrandsAgents/strands-decider-2B-hobson-v21`, Apache-2.0.
- **Summary.** A 1.9B-parameter decision model built on Qwen3.5-2B-Base with a rank-16 LoRA and a pointer head of about one million parameters that scores each answer option in one pass instead of generating text. Training data are ContractNLI, MuSiQue, synthetic rows checked by open-weight models and distilled output distributions from a frozen Qwen3.5-4B teacher; the whole recipe is one script and retrains in about 11 hours on one RTX 3090. On the public JevBench set (231 tasks) v21 reaches accuracy 0.762, Brier 0.323 and ECE 0.064 (v19: 0.723, 0.342, 0.052); v19 ranks 50th of 89 overall and 3rd of 33 in the 2B class. Latency: median 115 ms and p95 299 ms on an RTX 3090, 153 ms warm median on an M3 Pro. These numbers were read from a third-party summary of the launch post; open the launch post before quoting them.
- **Relation to ours.** The natural open-weight replacement for Jev in our pipeline, built on the same Qwen3.5 family as our generators, with published ECE. If the paper runs an open decision model as the judge, this is the one to run and cite; if it does not, it is the obvious future-work line.

#### Liquid AI, d1 and Open d1 (d1-3B, d1-omni-600M) — VERIFIED (https://www.liquid.ai/blog/open-d1, https://huggingface.co/LiquidAI/d1-3B)

- **Citation.** Liquid AI. "Open d1: Edge decision models for text, vision, and audio." Liquid AI blog, 7 October 2026. Model card `LiquidAI/d1-3B` (license LFM 1.0).
- **Summary.** d1-3B (3.12B parameters, built on LFM2.5-VL-3B with a SigLIP2 vision encoder, 32,768-token context) and d1-omni-600M (from a 350M bidirectional encoder, text plus image or audio, "early experimental") answer noul, choice and score questions in one forward pass with zero output tokens. Reported Decision Index 0.2.1 (public split) scores: d1-3B 48.57, described as ahead of every model under 10B and on par with Decider 35B-A3B; d1-omni-600M 15.95. Text benchmark means (SQuAD 2.0, BoolQ, Civil Comments, MASSIVE, PubMedQA, XNLI, PAWS-X): d1-3B 82.9, Decider 4B 81.1, Decider 2B 77.1. Latency for one question with d1-3B: 8 ms on an RTX 4090, 9 ms on an MI325X, 30 ms on an Apple M5 Pro, 16-50 ms on Jetson boards. The post and card make no calibration claim beyond returning "calibrated, typed answers" and report no ECE or Brier.
- **Relation to ours.** Confirms that the category runs at single-digit milliseconds per decision on commodity GPUs, which is the latency floor our decision steps approach. Vendor-reported; no independent calibration.

#### Microsoft, Microsoft-Decision-1 — VERIFIED (https://commandline.microsoft.com/microsoft-decision-1-model-foundry/; secondary: https://www.infoworld.com/article/4234290/microsoft-separates-decision-making-from-generative-ai-with-a-new-model.html)

- **Citation.** Achint Srivastava (Microsoft, Office of the CTO). "Introducing Microsoft-Decision-1, our model for fast decision-making." Microsoft Command Line blog, 9 October 2026. Available in Microsoft Foundry and on OpenRouter.
- **Summary.** A decision-scoring model post-trained from Qwen3.5-9B that returns a probability for each of a fixed set of answer options through a structured API call; Microsoft says it will be rebased on MAI and OpenAI models. Vendor claims: highest accuracy in a 36-benchmark comparison of nearly 150,000 held-out questions against nine systems (secondary sources quote 83.5% average accuracy and 85 ms p50, 125 ms p95); 2.5 times faster than the runner-up (H2O-Lightning-4B v1.1) and 35 times faster than GPT-6 Sol at p50; decision flips on 1.3% of perturbed inputs with zero flips for paraphrased option descriptions or reordered options; 5,250 safety requests across 11 benchmarks. Price $0.042 per million input tokens, output free; 32,768-token context; weights not released. No technical report and no ECE or Brier are given; the post states the calibration goal ("a 90% prediction should be right about nine times in 10") rather than a measurement. Listed uses include agent control, model routing, AI judging, search relevance, content filtering and safety screening.
- **Relation to ours.** Evidence that the decision-model design our pipeline relies on is being adopted by a second major vendor and, notably, built on the same Qwen3.5-9B that is one of our generators. The absence of published calibration numbers from any vendor is the gap our judge-calibration measurement addresses.

#### Community open-weight clones (Laya, Kev, openjev, open-alternative-jev) — UNVERIFIED (known from https://rohitraj.tech/notes/jev-alternatives-open-weights-decision-models-2026 and search snippets)

- **Summary.** Within weeks of Jev, several open-weight re-implementations appeared: Laya (Convai Innovations; 421M ModernBERT-large base and a 322M multilingual mmBERT variant; reported ECE 0.081 after temperature fitting, 33 ms per question on a T4), Kev (Jared Palmer; 0.8B/4B/9B on Qwen3.5 bases; Kev-9B accuracy 0.852, Brier 0.237 on the same public set) and openjev (4B on Qwen3.5-4B-Base and a 35B-A3B MoE variant, MIT). None of these has a paper or a model card that this survey opened; the numbers come from one third-party note.
- **Relation to ours.** Mention only in a footnote-free sentence if at all; the paper does not need them. They matter because they show the design is reproducible with a 400M encoder, which bounds the latency a decision step can reach.

#### Ibrahim and Zaki 2026, "Evaluating Decision Models for Text Annotation in Computational Social Science" — VERIFIED (https://arxiv.org/abs/2609.24574)

- **Citation.** Hazem Ibrahim, Yasir Zaki. "Evaluating Decision Models for Text Annotation in Computational Social Science." arXiv:2609.24574, v1 21 Sep 2026, v2 23 Sep 2026.
- **Summary.** Replicates the 18-task, 7,977-item zero-shot protocol of Ziems et al. (2024) with "the first commercial decision model" (Jev, not named in the abstract) and two open-weight counterparts against 19 frontier and open LLMs. The decision model trails the per-task best LLM on 14 of 15 tasks with a median deficit of 11.6 macro-F1 points, but its confidence is better calibrated than the verbalised confidence of 16 of the 19 LLMs (median calibration error 0.157; three frontier models reach 0.066). Items above 0.9 confidence have median accuracy 0.815, with a named failure (empathy in peer-support dialogue) where confidence is high and accuracy near chance. Measured cost is a median 44 times lower than the LLMs. Routing low-confidence items to an LLM matches or exceeds the LLM alone at a quarter to half of its cost.
- **Relation to ours.** The most directly relevant independent evaluation: it establishes the two properties our design needs (calibration good enough to threshold, cost two orders of magnitude lower) and the one it must handle (lower peak accuracy than a strong LLM), and it validates confidence-routed cascading as the right way to use such a model. Our paper applies the same pattern inside a RAG loop and in Vietnamese, where the vendor states accuracy is lower.

#### Rafe and Das 2026, "Calibrated Decisions at Scale: Converting Police Crash Narratives into Probabilistic Crash Variables with a System One Model (Jev)" — VERIFIED (https://arxiv.org/abs/2609.24052)

- **Citation.** Amir Rafe, Subasish Das. "Calibrated Decisions at Scale: Converting Police Crash Narratives into Probabilistic Crash Variables with a System One Model (Jev)." arXiv:2609.24052, 21 Sep 2026.
- **Summary.** Codes 195,857 Texas crash narratives (screened from 499,500) with a 27-question typed schema on Jev. Against 2,416 blinded human judgments the typed model reaches F1 0.908; one frontier LLM gains 0.059 F1 over it and another is about equal. Recalibrating on the same labels reduces calibration error by a factor of 3.3, and the authors note that calibration varies by model rather than by paradigm. Cost depends on schema size rather than narrative length.
- **Relation to ours.** Shows that vendor calibration is not sufficient out of the box for a new domain (a 3.3-fold reduction after recalibration) and that frontier LLMs retain a small accuracy edge. Both points support our choice to measure and, if needed, recalibrate the judge on a held-out labelled set before using its probability as a gate.

#### Guo et al. 2026, "Just Ask Jev: Reinforcement Learning for Calibrated Decisions as a Zero-Shot Detector of AI Alignment Failures" — VERIFIED (https://arxiv.org/abs/2609.29429)

- **Citation.** Ruoqi Guo, Yi Liu, Gelei Deng, Yuekang Li, Lida Zhao, Yutao Wu, Simin Chen, Ying Zhang, Leo Yu Zhang. "Just Ask Jev: Reinforcement Learning for Calibrated Decisions as a Zero-Shot Detector of AI Alignment Failures." arXiv:2609.29429, 24 Sep 2026.
- **Summary.** Builds RLCDAlignBench (ten alignment-failure types, 44 benchmarks, five target models) and asks Jev a single generic typed question per sample. Median AUROC 0.886 zero-shot, above supervised baselines on most benchmarks; question wording matters little while input fields that encode the label matter a lot; Jev matches the reference scorer's agreement with human labels at a reported 63 times lower cost than LLM-judge scorers, and surfaces label defects in existing benchmarks.
- **Relation to ours.** Independent evidence that a decision model can replace an LLM judge for binary verdicts at a large cost reduction, which is the premise of running our guardrail and judge steps on it.

#### Azizi, Baghaei Potraghloo and Pedram 2026, "One Word Opens the Gate: The Option-Channel Attack on Typed Decision Models as Agent Guardrails" — VERIFIED (https://arxiv.org/abs/2610.12292)

- **Citation.** Seyedarmin Azizi, Erfan Baghaei Potraghloo, Massoud Pedram. "One Word Opens the Gate: The Option-Channel Attack on Typed Decision Models as Agent Guardrails." arXiv:2610.12292, 8 Oct 2026.
- **Summary.** Evaluates seven open-weight typed decision models as allow/block gates on tool calls and messages. Base accuracy on the allow/block decision is 36-72% against a 50% chance level. Six lines of irrelevant server-log text raise the fail-open rate (prohibited action allowed) from 0% to 63% on a policy the model otherwise decides correctly, and renaming the permissive option (definition and judged text unchanged) raises it to 93-100% on the four models that put the label in their input. Attacked decisions were as confident as the ones they replaced, so escalating low-confidence decisions does not help. Parsing policy fields into typed values removed one attack class, and a deterministic rule over those values reached 100% on all six policies. The authors conclude that such models "should not be the component that decides" and should only reduce the number of cases reaching a human.
- **Relation to ours.** The strongest caution for contribution 1 and it must be cited. Our design is consistent with its recommendation in two ways: the decision model is never the sole gate for prompt-injection requests (the code path also checks deterministic signals, and the measured AgentDojo-style injection success rate is reported), and the judge gates only whether to retrieve more, where a wrong "sufficient" costs completeness, not safety. The paper should say this explicitly and report the guardrail's behaviour under the option-renaming attack if it can.

#### Barbosa 2026, "Calibrated Decision Models for Autonomous Penetration-Testing Harnesses: JEV and Laya as System One Decision Layers" — VERIFIED (https://arxiv.org/abs/2609.28940)

- **Citation.** Joas Antonio dos Santos Barbosa. "Calibrated Decision Models for Autonomous Penetration-Testing Harnesses: JEV and Laya as System One Decision Layers for LLM-Driven Pentest Agents." arXiv:2609.28940, 24 Sep 2026.
- **Summary.** A design paper that places decision models at four decision points of an LLM pentest harness (finding adjudication, severity recalibration, agent pruning, confirmation loops), with one exploratory run with and without Jev on a 13-vulnerability target that the author says does not establish significance. Reviews Jev, Jev-Ultrafast and the open Laya, and proposes a domain-adapted model.
- **Relation to ours.** Same architectural idea (decision layer inside an agent loop) in another domain, without a controlled evaluation. Cite as a contemporaneous design, not as evidence.

#### Hayes et al. 2026, "Pinocchio: Fast Uncertainty Estimates for Black-Box Language Models" — VERIFIED (https://arxiv.org/abs/2609.24881)

- **Citation.** Kevin David Hayes, Arka Pal, Haosong Zhang, Tom Goldstein, Micah Goldblum. "Pinocchio: Fast Uncertainty Estimates for Black-Box Language Models." arXiv:2609.24881, v1 21 Sep 2026, v2 22 Sep 2026.
- **Summary.** An external calibrator that scores the probability that a black-box LLM response is correct in one forward pass, trained on responses from seven LLMs (AUROC 0.862 held-out) and transferring zero-shot to 13 unseen models; a 0.8B text-only checkpoint matches the largest version.
- **Relation to ours.** An external small model that scores another model's output is the same pattern as our judge; Pinocchio scores correctness of a response, ours scores sufficiency of evidence before generation.


#### Wu and Lim 2026, "REFLEX with Jev for Efficient Selective Control in LLM Agents" — VERIFIED (https://arxiv.org/abs/2609.26532)

- **Citation.** Tiantong Wu, Wei Yang Bryan Lim. "REFLEX with Jev for Efficient Selective Control in LLM Agents." arXiv:2609.26532, 22 Sep 2026.
- **Summary.** Uses Jev as a fast typed decision layer and hands off to a strong LLM when confidence is low or generation is needed. On a frozen 100-task benchmark it reaches 95% success with 72.7% fewer strong-model calls than a strong-only agent, across three fallback families; reliability depends on the size of the action set and on near-valid alternatives near authorization boundaries. On BFCL and tau-style evaluations the advantage over a cheap generative cascade is limited when routing is already accurate. Only one proprietary decision model was tested.
- **Relation to ours.** The nearest prior use of Jev for confidence-gated escalation inside an agent; we gate retrieval rather than model choice, in a controlled workflow-versus-ReAct comparison with latency and cost, and on Vietnamese text.

#### Rao and Callison-Burch 2026, "Decision Models vs. LLMs as Rubric Judges: Cheaper, Faster, and Wrong in the Same Places" — VERIFIED (https://arxiv.org/abs/2609.29769)

- **Citation.** Delip Rao, Chris Callison-Burch. arXiv:2609.29769, v1 24 Sep 2026, v3 13 Oct 2026.
- **Summary.** Compares Jev and Perplexity's open Decider with three flash-tier LLM judges on nine panels from seven benchmarks against human labels with identical criterion texts. The LLM judges cost 16 to 357 times more and take 5 to 350 times longer, yet each decision model trails significantly in at most 6 of 27 comparisons. The two judge types err in the same places: on ordinal criteria they agree with each other more than with humans, and over 85% of flash-tier LLM verdicts on a decision model's most confident errors repeat those errors (about 50% expected if independent). Confidence ranks the decision models' errors well enough to serve as a first stage, but cascades with flash-tier or higher-tier fallbacks gain at most 2.7 and 1.7 points over the strongest single judge even with oracle thresholds.
- **Relation to ours.** The most important caveat for contribution 2: if the fallback (retrieve more, then the same generator) shares the judge's errors, the gain from gating is capped. Our design differs in that the fallback is new evidence rather than a second opinion on the same evidence, but the paper's correlated-error analysis should be reproduced for our judge versus the blind grader.

#### Xu et al. 2026, "JevOut: Natural Context Can Flip Decision Models" — VERIFIED (https://arxiv.org/abs/2609.30243)

- **Citation.** Zixiang Xu, Zirui Song, Chiyu Zhang, et al. arXiv:2609.30243 (v2 Oct 2026).
- **Summary.** Short, natural, answer-preserving added context flips 61.4% to 73.2% of initially correct decisions across four decision systems and seven datasets; 91.6% of sampled attacks were judged natural by annotators.
- **Relation to ours.** A robustness risk for decision models fed with retrieved text (our judge reads retrieved leaflet passages); belongs in the limitations section with Azizi et al. 2026.

#### Zhang et al. 2026, "Same Scores, Different Decisions: Evaluating JEV and Language Models for Legal Document Understanding" — VERIFIED (https://arxiv.org/abs/2609.27678)

- **Citation.** Fan Zhang, Yankai Chen, Zhuohan Xie, et al. arXiv:2609.27678 (v2 Oct 2026).
- **Summary.** Repeated-request evaluation of Jev and nine language models on ContractNLI; accuracy can stay flat while individual decisions flip, majority voting helps little, and Jev is cheapest and fastest while hosted LLMs are more accurate.
- **Relation to ours.** Decision consistency across repeated calls should be measured, not only accuracy; we can report flip rates for the judge on repeated runs.

#### Cloudflare 2026, Clef and Clef-Flash (open weights) — VERIFIED (https://huggingface.co/cloudflare/clef)

- **Citation.** Cloudflare. "Clef" model card, Hugging Face, 2026 (release reported as 1 October 2026 by press coverage). 27B, post-trained from Qwen3.8-27B; Clef-Flash is a smaller variant with no parameter count on the card. Apache-2.0.
- **Summary.** A Jev-compatible API: state (text, JSON, images, video) plus typed noul, choice and score questions in, one logit per option per question out of a single forward pass through a joint schema head over the backbone's final hidden states, with per-question softmax giving probabilities and no text generation. Vendor-run Decision Index 0.2.1 numbers: Clef MMLU 90.3, BFCL 98.5, GSM8K 80.8; Clef-Flash BFCL 98.8, MMLU 91.8. Median latency 209.3 ms (Clef) and 38.8 ms (Clef-Flash); Laya 5.8 ms in the same table. No calibration claim or ECE on the card.
- **Relation to ours.** The largest open-weight decision model and a natural follow-up to re-run our decision steps on; its Qwen3.8 base also shows the decision-model category converging on the same open families as our generators.

#### Geada, Misiura and Cyril 2026, "Benchmarking AI decision models against traditional guardrails" (Red Hat) — VERIFIED (https://developers.redhat.com/articles/2026/10/02/benchmarking-ai-decision-models-against-traditional-guardrails)

- **Citation.** Rob Geada, Mac Misiura, Shelton Cyril. Red Hat Developer, 2 October 2026. Grey literature.
- **Summary.** On prompt injection, the ProtectAI DeBERTa-v3 classifier (about 200M) scores 89.01% at 54.1 ms median versus a Qwen3.6-35B judge at 89.31% and 312.5 ms and Jev-1.13.0 at 86.35% and 348.1 ms. On content safety the order flips: Jev 86.20% at 360.4 ms, Qwen 85.47%, Granite Guardian HAP 125M 80.27% at 33.2 ms. The authors conclude decision models do not reliably beat LLM judges or trained classifiers on speed or accuracy.
- **Relation to ours.** Counter-evidence to cite when positioning the decision-model guardrail. Our contribution is the end-to-end pipeline trade-off (what the split buys in total latency and cost at equal quality), not a claim that the decision model wins every guard task in isolation. Note that the measured hosted latency (about 350 ms) is far above the vendor's 70 ms floor and should be the figure used in our cost model.



### D.4 Small classifiers as guardrails: cost and failure modes (2025-2026)

#### Majhi et al. 2025/2026, "Do You Really Need a GPU to Guard Your LLM? CPU-Class Classifiers and Multi-Stage Pipelines for Safety Enforcement at Scale" — VERIFIED (https://arxiv.org/abs/2512.19011)

- **Citation.** Vasudev Majhi, Dhruv Gupta, Advait Singh, Matthew Barker, Dhruv Kumar. "Do You Really Need a GPU to Guard Your LLM? CPU-Class Classifiers and Multi-Stage Pipelines for Safety Enforcement at Scale." arXiv:2512.19011, v1 22 Dec 2025, v3 13 Jun 2026. Listed as under review.
- **Summary.** Compares five CPU classifier families (SVM and gradient-boosted trees on TF-IDF features) with Mamba-130M, DeBERTa-v3 and Gemma-2B-LoRA jailbreak detectors across nine jailbreak sources in in-distribution, out-of-distribution and adversarially obfuscated regimes. In distribution the best CPU classifier matches the best transformer at about one fifth of the deployment cost; out of distribution the CPU classifiers fail through overconfident miscalibration (high-confidence false negatives that skip escalation); under obfuscation they beat the transformers by more than 26 F1 points. The proposed GuardChain (regex, then CPU, then GPU) resolves 80% of in-distribution prompts at the CPU stage.
- **Relation to ours.** A staged guardrail that routes each input to the cheapest stage that is confident is the same cost logic as our decision-first pipeline, and the finding that cheap classifiers fail out of distribution through overconfidence is the reason our guardrail's calibration is measured on held-out injection and out-of-scope requests.

#### Deng et al. 2025/2026, "Enhancing LLM Safety Through a Theoretical Minimax Game Lens" — VERIFIED (https://arxiv.org/abs/2502.05163)

- **Citation.** Yihe Deng, Yu Yang, Junkai Zhang, Wei Wang, Bo Li. "Enhancing LLM Safety Through a Theoretical Minimax Game Lens." arXiv:2502.05163, v1 7 Feb 2025, v2 15 Jun 2026.
- **Summary.** A minimax framework in which a data generator and a safety classifier co-evolve to produce multilingual synthetic safety data, with a convergence proof; a substantially smaller classifier (search snippets say Qwen2.5-0.5B and 1.5B bases, not confirmed from the abstract) surpasses the state of the art by nearly 10% on English benchmarks with 4.5 times faster inference.
- **Relation to ours.** Supports the claim that sub-2B guardrail classifiers can match larger guard models; our guardrail goes one step further by using a non-generative decision model.

**Thread D gap statement.** Guardrails (Llama Guard, ShieldGemma, Prompt Guard, Qwen3Guard, Granite Guardian) and small judges (Prometheus, MiniCheck, Flow-Judge, GLIDER) are mature, and judge calibration (ARES, Trust or Escalate, Lee et al. 2026) is well studied for offline evaluation. Decision models appeared in September 2026 and now have four vendor implementations and six independent evaluations (Ibrahim and Zaki; Rafe and Das; Guo et al.; Wu and Lim; Rao and Callison-Burch; Zhang et al.) plus two attack papers (Azizi et al.; Xu et al.). None of these places a decision model inside a RAG control loop as the evidence-sufficiency judge, measures its calibration on a non-English domain, or reports what the decision/generation split saves in latency and cost end to end. That is what contribution 1 adds, and the attack papers define the limitations it must state.

## E. Multi-turn and conversational RAG evaluation, conversational query rewriting

### E.1 Multi-turn RAG benchmarks

#### Katsis et al. 2025, MTRAG — VERIFIED (https://arxiv.org/abs/2501.03468; https://aclanthology.org/2025.tacl-1.36)

- **Citation.** Yannis Katsis, Sara Rosenthal, Kshitij Fadnis, et al. (IBM Research). "mtRAG: A Multi-Turn Conversational Benchmark for Evaluating Retrieval-Augmented Generation Systems." Transactions of the ACL 13:784-808, 2025. arXiv:2501.03468. DOI 10.1162/tacl.a.19.
- **Summary.** A human-written end-to-end multi-turn RAG benchmark with 110 conversations averaging 7.7 turns over four domains, 842 tasks, each with a retrieval corpus, deliberately including later-turn, unanswerable and non-standalone (context-dependent) questions. The authors also build synthetic conversations and test LLM-as-a-judge evaluation. Human and automatic evaluation show that state-of-the-art RAG systems degrade on later turns, on unanswerable and non-standalone questions, and across domains. Code at github.com/IBM/mt-rag-benchmark.
- **Relation to ours.** The closest English analogue to our multi-turn setting (non-standalone follow-ups, unanswerables). We add a Vietnamese drug-leaflet corpus, measure latency and cost alongside quality, and attribute the cost to decision versus generation steps.

#### Rosenthal et al. 2026, MTRAG-UN — VERIFIED (https://arxiv.org/abs/2602.23184; https://aclanthology.org/2026.findings-acl.503/)

- **Citation.** Sara Rosenthal, Yannis Katsis, Vraj Shah, Lihong He, Lucian Popa, Marina Danilevsky. "MTRAG-UN: A Benchmark for Open Challenges in Multi-Turn RAG Conversations." Findings of ACL 2026, pp. 10363-10369. arXiv:2602.23184. DOI 10.18653/v1/2026.findings-acl.503.
- **Summary.** A follow-up focused on four open problems, namely unanswerable, underspecified and non-standalone questions and unclear responses, with 666 conversations and more than 2,800 turns across six domains (adding banking and telecommunications). Retrieval and generation models still fail on these cases.
- **Relation to ours.** Provides the vocabulary for our guardrail and evidence-sufficiency judge (unanswerable and underspecified turns). We cite it as evidence that these decision steps matter and show they can run on a tiny calibrated model.

#### Rosenthal et al. 2026, SemEval-2026 Task 8 (MTRAGEval) — VERIFIED (https://research.ibm.com/publications/semeval-2026-task-8-mtrageval-evaluating-multi-turn-rag-conversations; Anthology id 2026.semeval-1.447 seen in search)

- **Citation.** Sara Rosenthal, Vraj Shah, Yannis Katsis, Marina Danilevsky. "SemEval-2026 Task 8: MTRAGEval: Evaluating Multi-Turn RAG Conversations." Proceedings of SemEval 2026, pp. 3673-3690.
- **Summary.** A shared task on MTRAG-UN with retrieval, generation and full retrieve-and-generate subtasks; 107 registered teams, 92 submissions. Specific retrieval and query-rewriting techniques help, the strongest systems use ensembles, and retrieval errors compound into generation errors. Several system papers report that concatenating the last turn with a standalone rewrite beats either alone.
- **Relation to ours.** Community-scale confirmation that rewriting and retrieval quality dominate multi-turn RAG outcomes, which motivates our rewrite-strategy comparison and the gated retrieve-more loop.

#### Cheng et al. 2025, CORAL — VERIFIED (https://arxiv.org/abs/2410.23090; https://aclanthology.org/2025.findings-naacl.72/)

- **Citation.** Yiruo Cheng, Kelong Mao, Ziliang Zhao, et al. "CORAL: Benchmarking Multi-turn Conversational Retrieval-Augmented Generation." Findings of NAACL 2025, pp. 1308-1330. arXiv:2410.23090. DOI 10.18653/v1/2025.findings-naacl.72.
- **Summary.** 8,000 Wikipedia-derived information-seeking conversations (3-20 turns) with passage retrieval, response generation and citation-labelling tasks. From the full text: best retrieval MRR 23.2 (KD-ANCE); a fine-tuned Qwen2.5-1.5B rewriter reaches MRR 23.1 versus 21.2 for GPT-3.5 rewriting; compressing history from about 2,226 tokens to about 478 costs little quality; generation gains flatten beyond 3B parameters while citation quality keeps improving to 7B; four history turns is the sweet spot.
- **Relation to ours.** Directly supports two of our claims with English data: small open rewriters can match a commercial model, and generation quality saturates with model size. We extend this to Vietnamese, a domain corpus, and latency and cost.

#### Liu et al. 2024, ChatQA and ChatRAG Bench — VERIFIED (https://arxiv.org/abs/2401.10225)

- **Citation.** Zihan Liu, Wei Ping, Rajarshi Roy, et al. (NVIDIA). "ChatQA: Surpassing GPT-4 on Conversational QA and RAG." NeurIPS 2024. arXiv:2401.10225.
- **Summary.** Two-stage instruction tuning plus a conversational dense retriever; ChatRAG Bench aggregates ten conversational QA datasets (Doc2Dial, QuAC, QReCC, TopiOCQA, INSCIT, CoQA, DoQA, ConvFinQA, SQA, HybriDial). Fine-tuning the Dragon retriever on conversational data gives top-1 recall 52.72 versus 54.46 for GPT-3.5-Turbo query rewriting and top-5 80.67 versus 80.13, so a fine-tuned retriever matches rewriting without the extra generation latency and API cost; for an unsupervised E5 retriever, fine-tuning lifts top-5 recall from 61.02 to 75.00.
- **Relation to ours.** The standard "rewrite versus conversational retriever" baseline and the canonical list of conversational QA datasets. We cite the cost argument against LLM rewriting and test cheap rewriters instead.

#### Alushi et al. 2026, "Comprehensive Comparison of RAG Methods Across Multi-Domain Conversational QA" — VERIFIED (https://arxiv.org/abs/2602.09552)

- **Citation.** Klejda Alushi, Jan Strich, Chris Biemann, Martin Semmann. EACL 2026 Student Research Workshop. arXiv:2602.09552.
- **Summary.** A unified comparison of vanilla and advanced RAG techniques on eight conversational QA datasets, tracking retrieval and generation across turns. Reranking, hybrid BM25 and HyDE consistently beat vanilla RAG; several advanced techniques give no gain and some fall below a no-RAG baseline; dialogue length and dataset structure drive retrieval effectiveness.
- **Relation to ours.** Supports our controlled fixed-workflow comparison and our finding that added agentic complexity does not automatically pay off.

#### Friel, Belyi and Sanyal 2024, RAGBench — VERIFIED (https://arxiv.org/abs/2407.11005)

- **Citation.** Robert Friel, Masha Belyi, Atindriyo Sanyal. "RAGBench: Explainable Benchmark for Retrieval-Augmented Generation Systems." arXiv:2407.11005, 2024.
- **Summary.** 100k examples over five industry domains with the TRACe metric family (utilisation, relevance, adherence, completeness); a fine-tuned RoBERTa evaluator beats LLM judges on these metrics. Single-turn.
- **Relation to ours.** Source for component-level RAG metrics; single-turn and English.

#### Li et al. 2025/2026, "Beyond Single-Turn: A Survey on Multi-Turn Interactions with LLMs" — VERIFIED (https://arxiv.org/abs/2504.04717)

- **Citation.** Yubo Li, Xiaobin Shen, Yidi Miao, et al. arXiv:2504.04717 (v1 Apr 2025, v6 Apr 2026).
- **Summary.** A taxonomy of multi-turn evaluation and improvement (instruction following versus conversational engagement, context maintenance, benchmarks, improvement methods). No dedicated conversational-RAG survey was found; this is the general pointer.
- **Relation to ours.** Framing only.

Note: MT-RAIG (Seo, Kwon and Lee, ACL 2025, arXiv:2502.11735) is multi-table, not multi-turn; do not cite it as a conversational benchmark.

### E.2 Conversational QA datasets used as standard baselines

- Adlakha et al. 2022, TopiOCQA — VERIFIED (https://arxiv.org/abs/2110.00768). TACL 2022. 3,920 Wikipedia conversations, about 13 turns and four topics each, free-form answers. The primary benchmark of CHIQ, IterCQR, AdaCQR, RETPO and SynRewrite.
- Anantha et al. 2021, QReCC — VERIFIED (https://arxiv.org/abs/2010.04898). NAACL 2021. 14K conversations, 80K QA pairs with gold human rewrites; the reference dataset for rewrite supervision. Our Vietnamese corpus has no gold rewrites, which motivates zero-shot cheap rewriters.
- Wu et al. 2023, INSCIT — VERIFIED (https://arxiv.org/abs/2207.00746; TACL 11:453-468). Mixed-initiative information-seeking conversations with clarification turns; source for under-specified questions our guardrail and judge must classify.
- Feng et al. 2020, Doc2Dial — VERIFIED (https://arxiv.org/abs/2011.06623). EMNLP 2020. About 4,800 goal-oriented dialogues grounded in 480+ public-service documents; the closest structural match to leaflet-grounded multi-turn QA.
- Feng et al. 2021, MultiDoc2Dial — VERIFIED (https://arxiv.org/abs/2109.12595). EMNLP 2021. Dialogues grounded in multiple documents; our per-intent coverage case (several leaflets for one question).
- Reddy, Chen and Manning 2019, CoQA — VERIFIED (https://arxiv.org/abs/1808.07042). TACL 2019. 127k questions from 8k conversations.
- Choi et al. 2018, QuAC — VERIFIED (https://arxiv.org/abs/1808.07036). EMNLP 2018. 100K questions with unanswerable turns; source of the unanswerable-turn protocol reused by ChatQA.

### E.3 Conversational query rewriting and conversational retrieval

#### Lin et al. 2020, T5QR — VERIFIED (https://arxiv.org/abs/2004.01909)

- **Citation.** Sheng-Chieh Lin, Jheng-Hong Yang, Rodrigo Nogueira, Ming-Feng Tsai, Chuan-Ju Wang, Jimmy Lin. "Conversational Question Reformulation via Sequence-to-Sequence Architectures and Pretrained Language Models." arXiv:2004.01909, April 2020 (no venue listed; cite as a 2020 preprint, not 2021).
- **Summary.** Fine-tunes seq2seq models on CANARD and tests on TREC CAsT 2019; T5 performs best. Later papers use "T5QR" as the supervised rewriting baseline (TopiOCQA MRR 23.0, QReCC 34.5 under dense retrieval in CHIQ's Table 1).
- **Relation to ours.** The canonical small supervised rewriter; our small-LLM rewrite is the zero-shot analogue.

#### Voskarides et al. 2020, QuReTeC — VERIFIED (https://arxiv.org/abs/2005.11723). SIGIR 2020. Term classification over the history (add a term or not), distant supervision from relevance labels. The cheapest non-generative rewriting family; a possible extra point on our latency axis.

#### Yu et al. 2021, ConvDR — VERIFIED (https://arxiv.org/abs/2105.04166). SIGIR 2021, DOI 10.1145/3404835.3462856. A session encoder distilled to mimic an ad hoc retriever's embeddings of oracle rewrites; matches oracle-rewrite accuracy on CAsT and OR-QuAC without a rewriting step. The "no rewrite, conversational encoder" alternative that avoids generation latency entirely.

#### Wu et al. 2022, CONQRR — VERIFIED (https://arxiv.org/abs/2112.08558). EMNLP 2022. RL-trained rewriter with a retrieval reward; the ancestor of IterCQR, RETPO and AdaCQR.

#### Mo et al. 2023, ConvGQR — VERIFIED (https://arxiv.org/abs/2305.15645)

- **Citation.** Fengran Mo, Kelong Mao, Yutao Zhu, Yihong Wu, Kaiyu Huang, Jian-Yun Nie. "ConvGQR: Generative Query Reformulation for Conversational Search." ACL 2023. arXiv:2305.15645.
- **Summary.** One generative model rewrites the query and another generates a potential answer; outputs are combined and a knowledge-infusion objective ties reformulation to retrieval. Reported later as TopiOCQA MRR 25.6 and QReCC 42.0 (dense).
- **Relation to ours.** Standard supervised rewrite-plus-expansion baseline cited alongside CHIQ.

#### Mao et al. 2023, LLM4CS — VERIFIED (https://arxiv.org/abs/2303.06573)

- **Citation.** Kelong Mao, Zhicheng Dou, Fengran Mo, Jiewen Hou, Haonan Chen, Hongjin Qian. "Large Language Models Know Your Contextual Search Intent: A Prompting Framework for Conversational Search." Findings of EMNLP 2023. arXiv:2303.06573.
- **Summary.** Prompts GPT-3.5 to produce multiple rewrites and hypothetical responses and aggregates them into one intent vector; beats human rewrites on CAsT-19/20/21. TopiOCQA MRR 27.7 and QReCC 44.8 in CHIQ's table.
- **Relation to ours.** The commercial-LLM rewriting baseline; our comparison puts cheap open models on the same axis.

#### Jin et al. 2023, InstructoR — VERIFIED (https://aclanthology.org/2023.findings-emnlp.443/)

- **Citation.** Zhuoran Jin, Pengfei Cao, Yubo Chen, Kang Liu, Jun Zhao. "InstructoR: Instructing Unsupervised Conversational Dense Retrieval with Large Language Models." Findings of EMNLP 2023, pp. 6649-6675. DOI 10.18653/v1/2023.findings-emnlp.443.
- **Summary.** Uses LLM-estimated session-passage relevance as soft labels to train a conversational retriever without supervision; surpasses the supervised state of the art and works zero-shot.
- **Relation to ours.** Shows LLM signals can replace gold rewrites, which is relevant to building Vietnamese training data without human rewrites.

#### Ye et al. 2023, InfoCQR — VERIFIED (https://arxiv.org/abs/2310.09716). Findings of EMNLP 2023. LLM as rewriter and rewrite editor, distilled into a T5 student to cut latency; informative LLM rewrites beat human rewrites on QReCC. The earliest explicit "distil the rewriter into a small model for latency" argument, which is our generation-step-on-small-LLM design.

#### Jang et al. 2024, IterCQR — VERIFIED (https://arxiv.org/abs/2311.09820; NAACL 2024)

- **Citation.** Yunah Jang, Kang-il Lee, Hyunkyung Bae, Hwanhee Lee, Kyomin Jung. "IterCQR: Iterative Conversational Query Reformulation with Retrieval Guidance." NAACL 2024. arXiv:2311.09820.
- **Summary.** Trains a T5-base rewriter (about 220M) iteratively with retrieval signals instead of human rewrites. Dense MRR: TopiOCQA 0.263 versus ConvGQR 0.256 and T5QR 0.230; QReCC 0.429 versus 0.420 and 0.345.
- **Relation to ours.** A 220M rewriter beats larger supervised ones when trained from retrieval feedback; a candidate cheap rewriter for Vietnamese.

#### Mao et al. 2024, ChatRetriever — VERIFIED (https://arxiv.org/abs/2404.13556; EMNLP 2024). LLM-based session encoder with contrastive learning and masked instruction tuning; comparable to LLM rewriting on five benchmarks with better robustness. The "LLM as retriever" path; we keep the retriever fixed and vary only rewriting to isolate cost.

#### Mo et al. 2024, CHIQ — VERIFIED (https://arxiv.org/abs/2406.05013)

- **Citation.** Fengran Mo, Abbas Ghaddar, Kelong Mao, Mehdi Rezagholizadeh, Boxing Chen, Qun Liu, Jian-Yun Nie. "CHIQ: Contextual History Enhancement for Improving Query Rewriting in Conversational Search." EMNLP 2024. arXiv:2406.05013.
- **Summary.** Two-step rewriting with an open LLaMA-2-7B-chat (also Mistral-7B): first clean and disambiguate the history, then rewrite; variants CHIQ-AD, CHIQ-FT (FlanT5-base on pseudo-queries) and CHIQ-Fusion. Dense MRR/NDCG@3: TopiOCQA CHIQ-Fusion 38.0/37.0 versus LLM4CS 27.7/26.7, ConvGQR 25.6/24.3, T5QR 23.0/22.2; QReCC CHIQ-AD 47.0/44.6 versus LLM4CS 44.8/42.1. Five benchmarks including zero-shot CAsT-19/20/21.
- **Relation to ours.** The paper's current rewriting reference; our "history-cleaning then rewrite on a small model" strategy is a CHIQ-style variant measured for latency and cost on Vietnamese.

#### Yoon et al. 2025, RETPO — VERIFIED (https://arxiv.org/abs/2402.11827; Findings of NAACL 2025, pp. 5899-5921)

- **Citation.** Chanwoong Yoon, Gangwoo Kim, Byeongguk Jeon, Sungdong Kim, Yohan Jo, Jaewoo Kang. "Ask Optimal Questions: Aligning Large Language Models with Retriever's Preference in Conversation." Findings of NAACL 2025. arXiv:2402.11827.
- **Summary.** An LLM generates candidate rewrites, retrieval scores each, and a smaller model is preference-tuned toward retriever-preferred rewrites (410K+ rewrites over 12K conversations); the small model beats rewrite-then-retrieve baselines including GPT-3.5 on QReCC and TopiOCQA.
- **Relation to ours.** The strongest evidence that a small aligned rewriter beats a commercial LLM rewriter; supports our small-LLM-for-generation-steps claim.

#### Lai et al. 2025, AdaCQR — VERIFIED (https://arxiv.org/abs/2407.01965). COLING 2025. Aligns one rewriter with both sparse and dense retrievers; relevant because we use hybrid retrieval over leaflets, so rewrites must serve both.

#### Wang et al. 2025, MaFeRw — VERIFIED (https://arxiv.org/abs/2408.17072; AAAI-25, DOI 10.1609/aaai.v39i24.34732). T5 rewriter for conversational RAG trained with PPO on three rewards (rewrite-to-gold-document similarity, ranking metrics, answer ROUGE); rewriting optimised for end answer quality, as our evaluation also scores the final answer.

#### Danilevsky et al. 2025, "A Library of LLM Intrinsics for RAG" (Granite) — VERIFIED (https://arxiv.org/abs/2504.11704)

- **Citation.** Marina Danilevsky, Kristjan Greenewald, Chulaka Gunasekara, et al. (IBM). "A Library of LLM Intrinsics for Retrieval-Augmented Generation." arXiv:2504.11704 (v2 Jul 2025).
- **Summary.** LoRA adapters on Granite 3.3 8B for RAG sub-steps. Query rewrite lifts Recall@20 on MTRAG from 0.67 to 0.76 overall and from 0.44 to 0.66 on non-standalone turns, and RAGAS faithfulness from 0.73 to 0.81. Answerability determination reaches weighted F1 90 on MTRAG; hallucination detection F1 68.6 on RAGTruth QA (versus 45.6 for prompted GPT-4-turbo); uncertainty quantification ECE 0.064 versus 0.20 base; citation generation F1 68.6 on LongBench-Cite.
- **Relation to ours.** The closest published decomposition of RAG into decision intrinsics (answerability, hallucination, uncertainty) versus generation (rewrite). We go further by putting the decision steps on a separate tiny calibrated model and reporting cost and latency.

#### Zheng et al. 2025, SynRewrite — VERIFIED (https://arxiv.org/abs/2509.22325). GPT-4o writes rewrites conditioned on history, positives and answers; a Flan-T5 student is fine-tuned then DPO-tuned with generator feedback; beats human rewrites on TopiOCQA and QReCC. A recipe for synthetic Vietnamese rewrite supervision with a small student.

#### Mo et al. 2026, ConvMix — VERIFIED (https://arxiv.org/abs/2508.04001). AAAI 2026. LLM-assisted data augmentation for conversational dense retrieval; latest work on the retrieval-side alternative to rewriting.

#### Mo et al. 2024/2025, "A Survey of Conversational Search" — VERIFIED (https://arxiv.org/abs/2410.15576). Organises conversational search into query reformulation, clarification, conversational retrieval and response generation. A SIGIR 2025 tutorial by the same group exists (arXiv:2506.10635, verified).

### E.4 Thread E negative results

No paper named "RewriteRAG" exists; no dedicated conversational-RAG survey was found; no benchmark named "ConvRAG benchmark 2025"; nothing on small-model conversational rewriting beyond RETPO, SynRewrite, AdaCQR and the Granite LoRA. The explicit distillation-for-latency argument is still Ye et al. 2023.

**Thread E gap statement.** The standard rewrite baselines (T5QR, ConvGQR, LLM4CS, CHIQ, IterCQR, RETPO) are all English and tuned on TopiOCQA or QReCC. No Vietnamese conversational query rewriting work exists, no Vietnamese multi-turn RAG benchmark exists, and none of the English works reports latency or cost for the rewrite step inside a full pipeline.


## F. Vietnamese RAG, medical QA and embeddings (2024-2026)

### F.1 Vietnamese embedding and retrieval benchmarks

#### Pham et al. 2025, VN-MTEB — VERIFIED (https://arxiv.org/abs/2507.21500; Findings of EACL 2026, Anthology id 2026.findings-eacl.86 seen in search)

- **Citation.** Loc Pham, Tung Luu, Thu Vo, Minh Nguyen, Viet Hoang (GreenNode AI, VNU-HCM IU). "VN-MTEB: Vietnamese Massive Text Embedding Benchmark." arXiv:2507.21500, 29 Jul 2025; Findings of EACL 2026, pp. 1705-1725.
- **Summary.** 41 datasets over six tasks (retrieval 15, classification, pair classification, clustering, reranking, STS) built by LLM-translating and filtering MTEB data; 18 models evaluated. Overall top five: multilingual-e5-large-instruct 67.99, e5-Mistral-7B-instruct 67.67, gte-Qwen2-7B-instruct 65.84, gte-multilingual-base 65.22, bge-m3 64.90. Retrieval: multilingual-e5-large-instruct 40.88, bge-m3 39.84, multilingual-e5-large 37.65, halong_embedding 34.45, AITeamVN/Vietnamese_Embedding 34.18, vietnamese-bi-encoder 25.37. Qwen3-Embedding and commercial embeddings are not included. Larger RoPE-based models beat APE models.
- **Relation to ours.** Already cited in the paper; the paper should update the citation to the EACL 2026 Findings venue. Vietnamese-finetuned models do not beat bge-m3 or multilingual-e5 on broad retrieval, which matches our retrieval benchmark. There is no separate "ViMTEB".

#### Nguyen and Quan 2026, "Which Works Best for Vietnamese? A Practical Study of IR Methods across Domains" (ViRE) — VERIFIED (https://aclanthology.org/2026.findings-eacl.110/)

- **Citation.** Long S. T. Nguyen, Tho T. Quan (HCMUT). "Which Works Best for Vietnamese? A Practical Study of Information Retrieval Methods across Domains." Findings of EACL 2026, pp. 2098-2119. DOI 10.18653/v1/2026.findings-eacl.110. No arXiv copy.
- **Summary.** Six domains, ten datasets (including healthcare: ViNewsQA, ViMedAQA), 25 retrieval configurations over lexical, SPLADE, ColBERT, dense and hybrid. Best overall: multilingual-e5-large plus BM25 (linear fusion, alpha 0.6-0.8), then bge-m3 plus BM25. Model scale is a weak predictor (Spearman rho 0.16): bge-m3 (568M) has the highest mean nDCG@10 (64.5%) while the 9.2B bge-multilingual-gemma2 ranks tenth (54.4%). On ViMedAQA dense encoders beat BM25 clearly (nDCG@10 BM25 74.51; multilingual-e5-large 90.01, hybrid 90.69; bge-m3 87.67, hybrid 88.52; Qwen3-Embedding-0.6B 85.23, hybrid 89.00; Vietnamese_Embedding_v2 85.06, hybrid 87.40), while on medical news BM25 stays competitive. Vietnamese-specialised encoders excel on formal institutional text and generalise worse to conversational domains.
- **Relation to ours.** The most important new Vietnamese retrieval citation: direct justification for hybrid BM25 plus multilingual dense retrieval on Vietnamese medical text, for not relying on embedding size, and the only Vietnamese source with Qwen3-Embedding numbers. It does not cover drug leaflets, rerankers in a cost frame, or end-to-end RAG.

#### Nguyen et al. 2024/2025, "Advancing Vietnamese Information Retrieval with Learning Objective and Benchmark" — VERIFIED (https://arxiv.org/abs/2503.07470)

- **Citation.** Phu-Vinh Nguyen, Minh-Nam Tran, Long Nguyen, Dien Dinh. PACLIC 38 (2024); arXiv:2503.07470.
- **Summary.** A Vietnamese Context Search benchmark with ViMedRetrieve (built from ViMedAQA, 2,000+ test samples) and reranking sets; proposes a weighted InfoNCE variant. A 20M model is best at k=5 (0.30) while vietnamese-bi-encoder is best at k=10/20 (0.45/0.73); sup-SimCSE leads reranking.
- **Relation to ours.** The only published retrieval benchmark on Vietnamese medical text that includes drug content; a comparison point for our leaflet retrieval benchmark.

#### Nguyen et al. 2024, "Towards Comprehensive Vietnamese RAG and LLMs" (BKAI) — VERIFIED (https://arxiv.org/abs/2403.01616; https://huggingface.co/bkai-foundation-models/vietnamese-bi-encoder)

- **Citation.** Nguyen Quang Duc, Le Hai Son, Nguyen Duc Nhan, Nguyen Dich Nhat Minh, Le Thanh Huong, Dinh Viet Sang (BKAI, HUST). "Towards Comprehensive Vietnamese Retrieval-Augmented Generation and Large Language Models." arXiv:2403.01616, 2024.
- **Summary.** Releases NewsCorpus (32M articles), about 30K synthetic multi-turn dialogues, the vietnamese-bi-encoder (PhoBERT-base-v2, trained on translated MS MARCO, SQuAD v2 and Zalo Legal 2021) and two LLaMA2-7B continual-pretraining models. On the Zalo legal split: Acc@1 73.28, Acc@10 93.59, MRR@10 80.73 versus 32.34/52.97/45.30 for Vietnamese-SBERT. No end-to-end RAG numbers.
- **Relation to ours.** The standard Vietnamese baseline encoder (about 485K monthly downloads).

#### Vietnamese embedding and reranker model cards (no papers) — VERIFIED (Hugging Face)

- hiieu/halong_embedding (2024): multilingual-e5-base fine-tune on about 100K pairs; Zalo legal NDCG@10 0.8976.
- AITeamVN/Vietnamese_Embedding (2025): BGE-M3 fine-tune on about 300K triplets; Zalo Legal Acc@1 0.7274, MRR@10 0.8181 versus BGE-M3 0.5682/0.6822; v2 on 1.1M triplets.
- AITeamVN/Vietnamese_Reranker (2025): bge-reranker-v2-m3 fine-tune, 0.6B; Zalo Legal MRR@10 0.8672.
- VoVanPhuc/sup-SimCSE-VietNamese-phobert-base: no numbers on the card.
- "ViEmbed": not found.
- **Relation to ours.** Candidate encoders and rerankers; all self-reported on Zalo legal, so VN-MTEB and ViRE are the neutral comparisons.

### F.2 Vietnamese medical QA datasets and benchmarks

#### Tran et al. 2024, ViMedAQA — VERIFIED (https://aclanthology.org/2024.acl-srw.31/)

- **Citation.** Minh-Nam Tran, Phu-Vinh Nguyen, Long Nguyen, Dien Dinh (HCMUS). "ViMedAQA: A Vietnamese Medical Abstractive Question-Answering Dataset and Findings of Large Language Model." ACL 2024 Student Research Workshop, pp. 252-260. DOI 10.18653/v1/2024.acl-srw.31.
- **Summary.** 44,313 QA pairs generated by Gemini from YouMed articles and human-annotated, over Disease (15,690), Medicine (13,873), Drug (9,780) and Body part (4,970). Open-book average of BERTScore, BLEU, METEOR and ROUGE-L: VinaLlama-7B 58.01, Llama3-8B 57.01, PhoGPT-4B 49.97; closed-book best PhoGPT-4B 36.88. Adding unrelated paragraphs degrades most models. CC BY-NC.
- **Relation to ours.** The only Vietnamese QA dataset with explicit drug and medicine partitions. It is single-turn, abstractive and sourced from a health website, not from labelling; our multi-turn drug-leaflet set fills that gap. The paper should cite it in the Vietnamese medical QA paragraph next to ViMQ, ViHealthQA and UIT-ViCoQA.

#### Nguyen et al. 2025, VM14K — VERIFIED (https://arxiv.org/abs/2506.01305)

- **Citation.** Thong Nguyen, Duc Nguyen, Minh Dang, et al. "VM14K: First Vietnamese Medical Benchmark." arXiv:2506.01305, Jun 2025.
- **Summary.** 14,000 multiple-choice questions over 34 specialties from exams and clinical records, expert-annotated, four difficulty tiers. Pass@1: DeepSeek-R1 78.17%, Gemini 2.0 Flash 75.67%, GPT-4o 72.74%; 70B medical models beat 8B ones. No dedicated pharmacology category.
- **Relation to ours.** The current reference for closed-book Vietnamese medical knowledge in LLMs; our work is open-book over leaflets with cheap models, so VM14K sets the closed-book ceiling we contrast against.

#### Huynh et al. 2026, VietMed-MCQ — PARTIAL (https://www.arxiv.org/abs/2601.03792 seen in search; abstract page not opened)

- **Citation.** Huynh Trung Kiet et al. (HCMUS). "VietMed-MCQ: A Consistency-Filtered Data Synthesis Framework for Vietnamese Traditional Medicine Evaluation." arXiv:2601.03792, Jan 2026.
- **Summary.** 3,190 traditional-medicine MCQs generated by a RAG pipeline with dual-model consistency filtering; 94.2% expert approval; Qwen2.5 beats Vietnamese-centric models.
- **Relation to ours.** Evidence that RAG-generated Vietnamese medical questions need consistency filtering, relevant to how our golden set was built; traditional medicine, not leaflets.

#### Huy et al. 2021, ViMQ — VERIFIED (https://arxiv.org/abs/2304.14405; ICONIP 2021, DOI 10.1007/978-3-030-92310-5_76). 9,000 patient questions with intent and NER labels. Already cited.

#### Nguyen et al. 2022, ViHealthQA / SPBERTQA — VERIFIED (https://arxiv.org/abs/2206.09600). 10,015 expert-answered question-answer-passage pairs; two-stage BM25 plus SBERT retrieval. Already cited.

#### Luu et al. 2020, ViMMRC — VERIFIED (https://arxiv.org/abs/2008.08810). Vietnamese multiple-choice reading comprehension; background only.

#### Nguyen et al. 2026, ViHERMES — VERIFIED (https://arxiv.org/abs/2602.07361)

- **Citation.** Long S. T. Nguyen, Quan M. Bui, Tin T. Ngo, Quynh T. N. Vo, Dung N. H. Le, Tho T. Quan. "ViHERMES: A Graph-Grounded Multihop Question Answering Benchmark and System for Vietnamese Healthcare Regulations." ACIIDS 2026. arXiv:2602.07361.
- **Summary.** Multihop QA over Vietnamese healthcare regulatory documents (amendment tracing, cross-document comparison, procedural synthesis) with evidence annotations; a graph-aware retriever beats strong baselines. No numbers in the abstract.
- **Relation to ours.** The nearest 2026 Vietnamese health-domain RAG benchmark; regulatory text rather than drug information, single-turn.

#### Nguyen et al. 2026, DSC2025 ViHallu Challenge — VERIFIED (https://arxiv.org/abs/2601.04711)

- **Citation.** Anh Thi-Hoang Nguyen, Khanh Quoc Tran, Tin Van Huynh, Phuoc Tan-Hoang Nguyen, Cam Tan Nguyen, Kiet Van Nguyen. "DSC2025 - ViHallu Challenge: Detecting Hallucination in Vietnamese LLMs." arXiv:2601.04711, Jan 2026.
- **Summary.** 10,000 (context, prompt, response) triplets labelled no, intrinsic or extrinsic hallucination; 111 teams; best macro-F1 84.80% versus 32.83% for an encoder baseline; intrinsic hallucinations are hardest.
- **Relation to ours.** The only Vietnamese faithfulness benchmark; supports using a Vietnamese-capable grader for answer faithfulness. VietPS-Hallu (LNCS 16608, JSAI-isAI 2026) is PARTIAL, seen only in a listing.

#### Nguyen et al. 2025, CSConDa customer-support benchmark — VERIFIED (https://arxiv.org/abs/2507.22542). 9,000+ QA pairs from real advisor-customer interactions; 11 lightweight Vietnamese LLMs evaluated; single-turn. Evidence that Vietnamese small-LLM evaluation on real conversational data exists, but without multi-turn dependence.

### F.3 Vietnamese LLM benchmarks and open models

- Bui et al. 2025, VMLU Benchmarks — VERIFIED (https://aclanthology.org/2025.acl-long.563/). ACL 2025. Vi-MQA, Vi-SQuAD, Vi-DROP and Vi-Dialog; finds that open LLMs can be cost-efficient judges for Vietnamese, which supports our open-model grader.
- Tran et al. 2024, ViGLUE — VERIFIED (https://aclanthology.org/2024.findings-naacl.261/). Findings of NAACL 2024. Background.
- Truong et al. 2024, "Crossing Linguistic Horizons" — VERIFIED (https://aclanthology.org/2024.findings-naacl.182/). Findings of NAACL 2024. Fine-tunes open LLMs for Vietnamese with 10 tasks and 31 metrics; larger models show more bias and poorer calibration. The calibration finding supports our separate calibrated decision model.
- Nguyen, Le and Nguyen 2024, ViLLM-Eval — VERIFIED (https://arxiv.org/abs/2404.11086). Background.
- Dao et al. 2023, VNHSGE — VERIFIED (https://arxiv.org/abs/2305.12199). Background.
- Nguyen et al. 2023, ViGPTQA — VERIFIED (https://aclanthology.org/2023.emnlp-industry.70/). EMNLP 2023 Industry. Deployed Vietnamese LLM QA; a baseline model in ViMedAQA.
- Open Vietnamese and SEA models, all VERIFIED: VinaLLaMA (arXiv:2312.11011), PhoGPT (arXiv:2311.02945; 3.7B, 102B Vietnamese tokens), Vistral-7B-Chat (Hugging Face card, no report), Vi-Qwen2-RAG 1.5B/3B/7B (AITeamVN Hugging Face cards; Qwen2 fine-tuned for Vietnamese RAG with refusal on missing context, no paper), SeaLLMs (arXiv:2312.00738, ACL 2024 demo), Sailor (arXiv:2404.03608), Sailor2 (arXiv:2502.12982; 1B/8B/20B from Qwen2.5, 13 SEA languages, Apache-2.0). "Gemma-Vi": not found. Sailor2 and Vi-Qwen2-RAG are the closest prior Vietnamese Qwen derivatives to cite next to our Qwen3.5 ladder.
- Liu et al. 2025, SeaExam and SeaBench — VERIFIED (https://arxiv.org/abs/2502.06298). Findings of NAACL 2025. Vietnamese exam MCQs (1,745) and 100 open-ended multi-turn tasks judged by GPT-4o; Gemma-2-9b-it best for Vietnamese among 7-9B models. The only SEA benchmark with multi-turn Vietnamese evaluation (not RAG); supports using native rather than translated Vietnamese conversations.
- Alonso, Oronoz and Agerri 2024, MedExpQA — VERIFIED (https://arxiv.org/abs/2404.05590; Artificial Intelligence in Medicine 155:102938). Multilingual medical exam QA (no Vietnamese); RAG with strong retrieval did not clearly improve results and non-English languages lag. Cited for the finding that naive RAG does not automatically help non-English medical QA, which our sufficiency gate addresses.

### F.4 Vietnamese RAG systems and shared tasks

- Nguyen Ba et al. 2024, "Vietnamese Legal Information Retrieval in Question-Answering System" — VERIFIED (https://arxiv.org/abs/2409.13699). Hybrid RAG with normalised RRF and LLM reranking; no numbers. Prior Vietnamese hybrid-RAG engineering.
- Nguyen and Quan 2025, URAG — VERIFIED (https://arxiv.org/abs/2501.16276). Hybrid RAG lets a lightweight in-house Vietnamese model answer admission queries comparably to commercial models; no cost or latency measurement. Same thesis as ours in another domain.
- VLSP 2025 shared tasks — VERIFIED (MLQA-TSR arXiv:2510.20381; DRILL https://aclanthology.org/2025.vlsp-1.16/). Legal retrieval and QA only; no medical or RAG track. ALQAC 2025 (KSE 2025) likewise legal.
- Bui et al. 2025, "Fine-tuning large language models for improved health communication in low-resource languages" (RMIT) — PARTIAL (repository page returned 403; details from search snippets). About 337,000 Vietnamese prompt-response pairs, LoRA/QLoRA on three open models; closed-book. A related ICIIT 2026 ACM paper on Vietnamese healthcare LLM fine-tuning (DOI 10.1145/3805862.3805898) is UNVERIFIED.

### F.5 Drug-leaflet and pharmaceutical RAG outside Vietnam

#### Garcia et al. 2026, "RAG for Clinical Question Answering in Portuguese Drug Leaflets: Benefits and Limitations" — VERIFIED (https://aclanthology.org/2026.propor-2.18/)

- **Citation.** Gabriel Lino Garcia, Pedro Henrique Paiola, João Vitor Mariano Correia, Douglas Rodrigues, João Paulo Papa. "Retrieval-Augmented Generation for Clinical Question Answering in Portuguese Drug Leaflets: Benefits and Limitations." PROPOR 2026, vol. 2, pp. 112-120.
- **Summary.** Over 7,000 Brazilian regulatory leaflets; retrieval raises F1 on medication questions from 0.276 to 0.412, but naive retrieval can hurt clinical-reasoning questions ("retrieval-induced anchoring bias"); critique-based and adaptive retrieval give the best clinical accuracy (54.25%).
- **Relation to ours.** The closest methodological precedent for leaflet-grounded QA in a non-English language, and its adaptive-retrieval finding parallels our gated retrieve-more loop. It reports no latency or cost and is single-turn.

#### Navarro et al. 2025, RagPharma — VERIFIED (https://journals-sol.sbc.org.br/index.php/jbcs/article/view/5767)

- **Citation.** Letícia C. Navarro, Filipe Mutz, Thiago M. Paixão, et al. "RagPharma: A RAG-Based Chatbot for Medicine Leaflets with a Dual-Dataset Evaluation Framework." Journal of the Brazilian Computer Society 31(1):1136-1148, 2025. DOI 10.5753/jbcs.2025.5767.
- **Summary.** A RAG chatbot over Brazilian package leaflets; shows evaluation bias when test questions come from the same data as the knowledge base and proposes separating them; 81% accuracy with Mistral 7B, about 60% above standalone LLMs.
- **Relation to ours.** Supports our blind-grader and separately written golden set protocol for leaflet QA.

#### Owoyemi et al. 2025, "Open-Source RAG Framework for Retrieving Accurate Medication Insights from Formularies for African Healthcare Workers" — VERIFIED (https://arxiv.org/abs/2502.15722). Nigerian formulary RAG chatbot with pharmacist feedback; no quantitative results. Low-resource drug-information RAG; we provide the evaluation it lacks.

#### Abedu et al. 2026, "Experiences Developing an AI Chatbot in the Pharmaceutical Industry" — VERIFIED (PDF https://aabdllatif.github.io/assets/pdf/Abedu2026ExperiencesAIChatbotPharma.pdf; ACM DOI 10.1145/3786161.3788463 seen in search)

- **Citation.** Samuel Abedu, Saviour Owolabi, Mayra Sofia Ruiz Rodriguez, et al. (Concordia, Calgary, Sandoz). BoatSE '26 workshop at ICSE 2026.
- **Summary.** A deployed RAG chatbot over product monographs with drug-name normalisation (brand and generic, misspellings), a whitelist-restricted web search, interactive clarification for ambiguous dosage forms, adverse-event detection and a confidence score with each answer; experience report, no benchmark numbers.
- **Relation to ours.** Industry confirmation that a guardrail, clarification and a confidence signal are required in drug QA; we quantify those decision steps on a tiny model.

### F.6 Thread F negative results

Searched and not found: any Vietnamese drug-leaflet, pharmacy or medication QA/RAG paper (2024-2026); any Vietnamese multi-turn conversational QA dataset (EduCoQA and CSConDa come from conversations but are released as single pairs); any Vietnamese conversational query rewriting work; "ViMTEB", "ViEmbed", "ViMedQA", "MedViet", "ViMedical", "Vi-Med LLM", "ViMedLLM", "MedVi", "Gemma-Vi"; any South-East-Asian medical LLM benchmark covering Vietnamese beyond VM14K; Qwen3-Embedding on Vietnamese outside the ViRE paper.

**Thread F gap statement.** Vietnamese resources cover embeddings (VN-MTEB, ViRE), general medical QA (ViMQ, ViHealthQA, ViMedAQA, VM14K), hallucination (ViHallu), regulations (ViHERMES) and legal retrieval. No Vietnamese drug-information corpus, retrieval benchmark, multi-turn evaluation set or agentic RAG evaluation exists; the only leaflet-grounded RAG precedents are Portuguese (Garcia et al. 2026, Navarro et al. 2025), and neither reports latency or cost.


## G. Primary sources for the models and systems the paper uses

#### Qwen Team 2026, Qwen3.5 (2B, 4B, 9B, 27B) — VERIFIED (model card https://huggingface.co/Qwen/Qwen3.5-9B; blog https://qwen.ai/blog?id=qwen3.5)

- **Citation.** Qwen Team. "Qwen3.5: Towards Native Multimodal Agents." Qwen blog, February 2026, https://qwen.ai/blog?id=qwen3.5 (this is the BibTeX entry the model card suggests). The small dense series (0.8B, 2B, 4B, 9B) was released on 2 March 2026 under Apache-2.0 (secondary sources: Artificial Analysis, Gigazine quoting the Qwen team post); the 27B dense model was released in February 2026 together with the 397B-A17B, 122B-A10B and 35B-A3B mixture-of-experts models.
- **Summary.** From the 9B model card: a causal language model with a vision encoder, about 9B parameters, 32 layers in eight blocks of three Gated DeltaNet plus feed-forward units followed by one gated-attention unit, multi-token prediction in training, 248,320-token padded vocabulary, 262,144-token native context extendable to about 1M with YaRN. The card's benchmark tables also list Qwen3.5-4B. No arXiv technical report for the text models was found during this survey (the Qwen3 report is arXiv:2505.09388; Qwen3.5-Omni has arXiv:2604.15804), so the blog post is the citable source.
- **Relation to ours.** These are the four open-weight generators of the size ladder. The paper should cite the blog post once and give the exact model ids and quantisation in the setup section.

#### Google 2026, Gemini 3.8 Flash — VERIFIED (https://blog.google/innovation-and-ai/models-and-research/gemini-models/3-8-flash-and-3-8-flash-cyber/)

- **Citation.** Tulsee Doshi, Raluca Ada Popa (Google DeepMind). "Introducing Gemini 3.8 Flash and 3.8 Flash Cyber." Google blog, 2 September 2026.
- **Summary.** Positioned as the most capable of Google's "workhorse" models with gains over 3.7 Flash in software engineering, agentic tasks and multi-step reasoning; 54.9% on HLE-Verified; the post says the model takes extra reasoning steps and calls tools iteratively on hard tasks, which raises token use at higher effort levels. Introductory price $0.75 per million input and $3.75 per million output tokens until 31 December 2026, then $1.50 and $7.50. The post also claims improved prompt-injection robustness on Gray Swan's benchmark without a number.
- **Relation to ours.** The commercial reference model. Cost figures in the paper should state which price (introductory or list) was used and the date, since the price doubles on 1 January 2027.

#### TypeSafe AI 2026, Jev 1.13 — see D.3 above.

#### Nygren et al. 2026, "RAG-based architectures for drug side effect retrieval using compact LLMs" — VERIFIED (Crossref record for DOI 10.1038/s41598-026-41495-2; https://research.hub.ku.edu.tr/entities/publication/a285fac2-a0ac-4912-a150-58a0d4bbb062/full; preprint https://arxiv.org/abs/2507.13822)

- **Citation.** Shad Nygren, Omer Erdogan, Pinar Avci, Andre Daniels, Reza Rassool, Afshin Beheshti, Diego Galeano. "RAG-based architectures for drug side effect retrieval using compact LLMs." Scientific Reports 16, article 12754, published 9 March 2026. DOI 10.1038/s41598-026-41495-2 (author order and article number from the Crossref record; the Koç University repository lists Erdoğan last, so check the Nature page before final submission). Preprint: Shad Nygren, Pinar Avci, Andre Daniels, Reza Rassol, Afshin Beheshti, Diego Galeano, "RAG-based Architectures for Drug Side Effect Retrieval in LLMs," arXiv:2507.13822, 18 Jul 2025 (the preprint lacks Erdoğan and uses Llama 3 8B).
- **Summary.** Text RAG and a Neo4j GraphRAG over SIDER 4.1 answer drug side-effect questions with compact models. On a balanced forward benchmark of 19,520 drug-side-effect pairs GraphRAG reaches 99.95% accuracy with Qwen2.5-7B-Instruct and 99.96% with Llama-3.1-8B-Instruct. On reverse queries (side effect to drug set) GraphRAG returns exact sets (precision, recall and F1 100%) in about 0.09 s while the text-RAG baseline reaches F1 99.18% in 82.63 s. A compact-LLM name-normalisation step corrects misspellings and brand variants.
- **Relation to ours.** The one drug-information RAG paper that reports latency alongside accuracy, already cited in the paper. It answers single-fact lookups from a structured database; ours answers open conversational questions from unstructured Vietnamese leaflets and reports cost as well. The 0.09 s versus 82.63 s contrast is a useful example of how large the latency spread between designs can be.


## H. Gaps the paper fills, by contribution

### Contribution 1: decision steps on a calibrated decision model, generation steps on a small LLM

- **What exists.** Belcak et al. (2025) argue for heterogeneous agents with small models on narrow sub-tasks but give no measurement. Danilevsky et al. (2025) decompose RAG into decision intrinsics (answerability, hallucination, uncertainty) and generation intrinsics (rewrite) as LoRA adapters on one 8B model. Adaptive-RAG, CRAG, Tiny-Critic RAG and HALT each put a small trained classifier at one decision point. Guardrail encoders (Prompt Guard 2, ProtectAI, Zheng et al. 2025) and small judges (MiniCheck, Flow-Judge, GLIDER) show sub-1B models can make single decisions. Decision models (Jev, Strands Decider, d1, Decision-1, Clef) make this a product category with calibrated typed outputs and millisecond latency, and six independent 2026 evaluations characterise them on annotation, alignment detection, crash coding, legal NLI, rubric judging and agent control.
- **What is missing.** No work runs all the decision steps of a RAG agent (guardrail, sufficiency judge, per-intent coverage) on one non-generative calibrated model and the generation steps on a separate small LLM, and reports what the split costs and saves end to end. No work measures a decision model's calibration on a non-English domain (the vendor states English-primary accuracy). The constraint-tax results (Ray 2026; Schall and de Melo 2025) show that tiny generative LLMs under hard schemas lose accuracy, which is the argument for a purpose-trained decision model that the paper can now make with citations.
- **What the paper must also say.** Azizi et al. (2026) and Xu et al. (2026) show option-channel and natural-context attacks flip decision models with unchanged confidence; the Red Hat benchmark shows a 200M encoder beats Jev on injection at a sixth of the latency; Rao and Callison-Burch (2026) show decision models and flash-tier LLM judges err in the same places. The paper should state that the decision model is not the sole safety gate, report the measured hosted latency rather than the vendor floor, and report judge-versus-grader error correlation.

### Contribution 2: confidence-gated refinement with a cost-quality Pareto curve

- **What exists.** Adaptive retrieval gates on the generator's own signals (FLARE, DRAGIN, SKR, SEAKR, CtrlA, Probing-RAG, TARG), on a trained classifier (Adaptive-RAG, CRAG, UAR, RAGate), on sampling consistency (Rowen), or on a learned controller (Stop-RAG, CaRT, DeepRAG, AnySearch). Training-free calibrated stopping appeared in 2026 (TASR with an isotonic logit margin; HALT with a claim-coverage verifier). Calibrated cascades (UCCI; Trust or Escalate; Peale et al.) show that calibrating the gate signal makes thresholds transferable and cost-optimal. Qian et al. (2026) define how to report active-RAG trade-offs (frontier, realised usage, threshold transfer, harm rate, cost). Sufficient-context (Joren et al. 2025) defines the quantity our judge estimates.
- **What is missing.** No work gates the retrieve-more loop on an external calibrated decision model that works identically for open and commercial generators, sweeps the probability threshold to trace a quality-latency-cost Pareto curve, and does so across a 2B-27B ladder plus a commercial model on a non-English domain corpus with multi-turn questions. TASR needs generator logits; HALT trains a verifier per task; Stop-RAG trains a value function; none reports dollar cost. The paper's Pareto curve is new, and Qian et al. (2026) give it a reporting standard to follow.

### Contribution 3: workflow versus autonomous agent across model sizes

- **What exists.** Anthropic (2024) gives the taxonomy. Kumar et al. (2026) show on 19 benchmarks with one large model that fixed workflows are more accurate on 12 of 19 and cheaper on all 19 ("agentic tax" above 2x). Ferrazzi et al. (2026) compare an enhanced fixed RAG pipeline with an LLM-orchestrated agent on Qwen3-0.6B to 32B and find the agent wins only at 0.6B and costs 1.5x the time and 3.3x the input tokens. Gray et al. (2025) find the opposite on code repair (agency helps mid-sized models most). Zhang et al. (2026) find small differences at 7B on extraction. AgentFloor (2026) gives a tool-use ladder for 16 small open models including Qwen3.5-2B and locates the break at branching (tier C), not explained by scale alone. Evoflux, EffGen and the tool-use benchmarks (BFCL, tau-bench) document small-model fragility in free-running loops; Patel et al. (2026) show the calling interface is a confound.
- **What is missing.** No study holds the task, tools and calling interface fixed and varies only control flow (code-controlled workflow with one structured decision per call versus ReAct) across a ladder of small open-weight models plus a commercial model, on a RAG task, reporting quality, latency and cost together and locating the size at which the autonomous arm catches up. Ferrazzi et al. is the nearest and should be contrasted explicitly: their agent orchestrates a different pipeline (different rewriting, reranking and routing components) rather than the same tools, and they report token ratios rather than dollars or a calibrated gate.

### Contribution 4: quality, latency and cost together, in Vietnamese pharmaceutical multi-turn QA

- **What exists.** Cost-aware agent evaluation (Kapoor et al. 2024, 2026; Erol et al. 2025), RAG serving latency (RAGCache, RAGO, RAG-Stack), one clinical RAG with latency (Wada et al. 2025; Nygren et al. 2026), conversational RAG benchmarks (MTRAG, MTRAG-UN, CORAL, ChatRAG Bench), rewriting baselines (T5QR, ConvGQR, LLM4CS, CHIQ, IterCQR, RETPO), Vietnamese retrieval benchmarks (VN-MTEB, ViRE), Vietnamese medical QA (ViMedAQA with drug partitions, VM14K, ViHallu), and Portuguese drug-leaflet RAG (Garcia et al. 2026; Navarro et al. 2025).
- **What is missing.** No Vietnamese drug-information corpus or benchmark; no Vietnamese multi-turn RAG evaluation; no Vietnamese conversational rewriting; no leaflet-grounded RAG paper in any language that reports latency and cost; no agentic RAG paper that reports all three axes per configuration on a small-model ladder.


## I. Suggested citation plan for the paper

The paper's references.bib currently has 37 entries. The survey suggests the following additions and corrections, grouped by where they would be cited. Entries marked "core" are the ones the related-work section cannot do without; the rest are optional support.

### Corrections to existing entries

- `pham2025vnmteb`: the paper is now in Findings of EACL 2026 (pp. 1705-1725); update the venue.
- `nygren2026drug`: Scientific Reports 16, article 12754, 9 March 2026; author order per Crossref is Nygren, Erdogan, Avci, Daniels, Rassool, Beheshti, Galeano. Check the Nature page before submission.
- `yan2024crag`: no peer-reviewed venue found; keep as arXiv.
- If `kapoor2024agents` is added, cite as arXiv:2407.01502 unless the TMLR venue is confirmed.

### Introduction and related work, paragraph on agentic RAG and control flow (core)

- Anthropic 2024, "Building effective agents" (URL with access date).
- Yao et al. 2023, ReAct (ICLR 2023, arXiv:2210.03629).
- Singh et al. 2025, Agentic RAG survey (arXiv:2501.09136).
- Belcak et al. 2025, SLMs are the future of agentic AI (arXiv:2506.02153).
- Kumar et al. 2026, Learning to Construct Practical Agentic Systems (arXiv:2606.00189).
- Ferrazzi et al. 2026, Is Agentic RAG worth it? (ACL 2026 Industry, arXiv:2601.07711).
- Gray et al. 2025, Workflows vs Agents for Code Translation (NeurIPS 2025 DL4C, arXiv:2512.14762), as the counter-case.
- Karmakar and Chatterjee 2026, AgentFloor (arXiv:2605.00334).
- Optional: Zhang et al. 2026 (arXiv:2607.15715), Albayaydh et al. 2026 (arXiv:2607.05775), Patel et al. 2026 (arXiv:2608.06370), Kavathekar et al. 2025 (EASE 2025, arXiv:2504.19277), Li et al. 2025 RAG-reasoning survey (arXiv:2507.09477), Search-R1 (COLM 2025, arXiv:2503.09516), AFlow (ICLR 2025, arXiv:2410.10762).

### Related work, paragraph on adaptive retrieval and confidence gating (core)

- Keep Self-RAG, CRAG, Adaptive-RAG; add FLARE (EMNLP 2023, arXiv:2305.06983), DRAGIN (ACL 2024, arXiv:2403.10081), SKR (Findings of EMNLP 2023, arXiv:2310.05002), Joren et al. 2025 Sufficient Context (ICLR 2025, arXiv:2411.06037).
- 2026 stopping rules: TASR (KDD 2026 Agent4IR, arXiv:2606.13814), HALT (Findings of EMNLP 2026, arXiv:2608.02009), Stop-RAG (NeurIPS 2025 workshop, arXiv:2510.14337), TARG (arXiv:2511.09803).
- Evaluation protocol: Qian et al. 2026 (KDD 2026 workshop, arXiv:2607.24010).
- Calibrated cascades: UCCI (arXiv:2605.18796), Jung et al. 2025 Trust or Escalate (ICLR 2025, arXiv:2407.18370).
- Optional: SEAKR (ACL 2025), UAR (Findings of EMNLP 2024), Rowen (SIGIR-AP 2025), Probing-RAG (Findings of NAACL 2025), Moskvoretskii et al. 2025 (ACL 2025), Xie et al. 2026 (arXiv:2603.06604), Tiny-Critic RAG (arXiv:2603.00846), FAIR-RAG (arXiv:2510.22344).

### Related work, paragraph on cost and latency (core)

- Kapoor et al. 2024 (arXiv:2407.01502) and 2026 HAL (ICLR 2026, arXiv:2510.11977).
- Erol et al. 2025 Cost-of-Pass (arXiv:2504.13359).
- FrugalGPT (arXiv:2305.05176), RouteLLM (ICLR 2025, arXiv:2406.18665), AutoMix (NeurIPS 2024, arXiv:2310.12963).
- Moslem and Kelleher 2026 routing survey (TMLR 2026, arXiv:2603.04445).
- RAGO (arXiv:2503.14649) or RAG-Stack (arXiv:2608.03487) as the systems-side latency reference; RAGCache (arXiv:2404.12457) optional.
- Healthcare with latency: Nygren et al. 2026 (already cited), Wada et al. 2025 (npj Digital Medicine 8:395), Wind et al. 2025 (npj Digital Medicine 8:790); DrugRAG (arXiv:2512.14896) and Bang et al. 2025 (arXiv:2508.06145) as drug-QA RAG without efficiency metrics.

### Method, decision model and guardrail (core)

- TypeSafe Jev: launch post and docs (URLs, model id jev-1.13.0, access date).
- Ibrahim and Zaki 2026 (arXiv:2609.24574), Guo et al. 2026 (arXiv:2609.29429), Rafe and Das 2026 (arXiv:2609.24052), Wu and Lim 2026 REFLEX (arXiv:2609.26532).
- Open-weight equivalents: Strands Decider 2B (Strands Labs blog, 1 Oct 2026), Liquid d1 (blog, 7 Oct 2026), Cloudflare Clef (model card), Microsoft Decision-1 (blog, 9 Oct 2026).
- Constrained output: Schall and de Melo 2025 (RANLP 2025), Ray 2026 Constraint Tax (arXiv:2605.26128), Tam et al. 2024 (arXiv:2408.02442).
- Guardrail baselines: Llama Guard 3 1B/8B model cards (Vietnamese F1 numbers), Prompt Guard 2 (model card), Qwen3Guard (arXiv:2510.14276), Zheng et al. 2025 (COLING 2025 Industry, arXiv:2411.14398), Majhi et al. 2026 (arXiv:2512.19011).
- Judge calibration: keep ARES and PPI; add Lee et al. 2026 (ICML 2026, arXiv:2511.21140), MiniCheck (EMNLP 2024, arXiv:2404.10774), Danilevsky et al. 2025 Granite intrinsics (arXiv:2504.11704).

### Method and results, conversational rewriting (core)

- Benchmarks: MTRAG (TACL 2025, arXiv:2501.03468), MTRAG-UN (Findings of ACL 2026, arXiv:2602.23184), CORAL (Findings of NAACL 2025, arXiv:2410.23090), ChatQA (NeurIPS 2024, arXiv:2401.10225).
- Rewriters: T5QR (arXiv:2004.01909, 2020), ConvGQR (ACL 2023), LLM4CS (Findings of EMNLP 2023), InstructoR (Findings of EMNLP 2023), CHIQ (EMNLP 2024, already the reference), IterCQR (NAACL 2024), RETPO (Findings of NAACL 2025), AdaCQR (COLING 2025).
- Optional: InfoCQR (Findings of EMNLP 2023) for the distil-for-latency argument; ConvDR (SIGIR 2021) for the no-rewrite alternative.

### Related work, Vietnamese paragraph (core)

- Add ViMedAQA (ACL 2024 SRW) next to ViMQ, ViHealthQA and UIT-ViCoQA, since it has drug and medicine partitions.
- Add Nguyen and Quan 2026 ViRE (Findings of EACL 2026) next to VN-MTEB for hybrid retrieval on Vietnamese medical text.
- Optional: VM14K (arXiv:2506.01305) as the closed-book ceiling, ViHallu (arXiv:2601.04711) for Vietnamese faithfulness, ViHERMES (ACIIDS 2026, arXiv:2602.07361) as the nearest Vietnamese health RAG benchmark, Sailor2 (arXiv:2502.12982) and Vi-Qwen2-RAG (model card) as prior Vietnamese Qwen derivatives, SeaExam/SeaBench (Findings of NAACL 2025) for native multi-turn Vietnamese evaluation.
- Drug-leaflet precedents in other languages: Garcia et al. 2026 (PROPOR 2026), Navarro et al. 2025 (JBCS 31(1)).

### Limitations (core)

- Azizi et al. 2026 option-channel attack (arXiv:2610.12292), Xu et al. 2026 JevOut (arXiv:2609.30243), Rao and Callison-Burch 2026 correlated errors (arXiv:2609.29769), Zhang et al. 2026 decision flips (arXiv:2609.27678), Red Hat benchmark (grey literature), Llama Guard 3 1B Vietnamese penalty, Jev docs on English-primary accuracy.

### Models (setup section)

- Qwen Team 2026, "Qwen3.5: Towards Native Multimodal Agents" (blog, February 2026; small series 2 March 2026).
- Google 2026, "Introducing Gemini 3.8 Flash and 3.8 Flash Cyber" (blog, 2 September 2026), with the price tier and date used.


## J. Verification ledger

Entries whose page was opened and read (VERIFIED): 193 headed entries plus 38 short bulleted entries. Every heading carries its status and the URL that was opened; the lists below collect the entries that are not fully verified so they can be checked before citation.

### PARTIAL (page opened but a field could not be confirmed, or details read from a secondary source)
- Jev Decision Index (community leaderboard)
- AWS Strands Labs, Strands Decider 2B (open weights, full recipe)
- Huynh et al. 2026, VietMed-MCQ
- Chen et al. 2024, "Learning to Retrieve Iteratively for In-Context Learning"
- Bui et al. 2025, "Fine-tuning large language models for improved health communication in low-resource languages" (RMIT)

### UNVERIFIED (known only from search snippets or third-party pages; open the page before citing)
- Note on other 2026 search hits (UNVERIFIED, not opened)
- Choi et al. 2024, MALADE
- Community open-weight clones (Laya, Kev, openjev, open-alternative-jev)

### Items the sub-surveys searched for and could not find at all
- "A Survey on LLM Routing" (exact title), "Cal-Eval", "RewriteRAG", a dedicated conversational-RAG survey, "ConvRAG benchmark 2025", "NVIDIA Nemotron Nano router", "ViMTEB", "ViEmbed", "ViMedQA", "MedViet", "ViMedical", "Vi-Med LLM", "ViMedLLM", "MedVi", "Gemma-Vi", a Vietnamese drug-leaflet QA or RAG paper, a Vietnamese multi-turn RAG dataset, a Vietnamese conversational query-rewriting paper, a Qwen3.5 text-model technical report on arXiv, a peer-reviewed paper from TypeSafe on Jev or RLCD, and any published calibration metric (ECE or Brier) from any decision-model vendor for its hosted model.

### Venues often cited but not confirmed from the page opened
- AI Agents That Matter (often TMLR 2025), FrugalGPT (often TMLR 2024), RAGAS (often EACL 2024 demo; the paper already cites it that way), "Let Me Speak Freely?" (often EMNLP 2024 Industry), Greshake et al. (often AISec 2023), VN-MTEB (Findings of EACL 2026 seen in an Anthology listing, page not opened), SemEval-2026 Task 8 (Anthology id seen in search).

### Sources used
- WebSearch (standard and extended), arXiv abstract and HTML pages, ACL Anthology, ICLR/NeurIPS/PMLR proceedings pages, Crossref API, Hugging Face model cards and Spaces, vendor blogs (Anthropic, TypeSafe, Liquid AI, Microsoft, Strands Labs, Google, Qwen), and three sub-surveys run in parallel on threads A+B, C+D and E+F whose per-entry verification URLs are reproduced in the headings above.
