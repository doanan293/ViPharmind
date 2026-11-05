"""English speaker notes, keyed by output SVG stem. Spoken prose only."""

NOTES = {
    "p01_title": """
Good morning, everyone. I am Van-An Doan from Hanoi University of Science and Technology, and this is joint work with Tuan Quoc Nguyen. Our paper is about agentic retrieval-augmented generation for Vietnamese pharmaceutical documents.
""",
    "p02_motivation": """
Let me start with a real question from our evaluation set. A breastfeeding mother asks whether she can take metformin, a common diabetes drug. Without retrieval, Gemini 3.8 Flash confidently says yes, it is safe. The National Drug Formulary says otherwise: metformin passes into breast milk and may cause low blood sugar in the infant, so stopping either breastfeeding or the drug should be considered. Inside our pipeline, the same model gives exactly that answer, with citations.
For drug information, a wrong answer can cause direct harm. Three gaps make this hard. Vietnamese has no evaluation resource for drug labelling, and real questions use brand names, colloquial names or no diacritics. Retrieval methods are ranked by quality alone, while a deployed system also pays for embedding size and reranker throughput. And agentic RAG usually assumes a capable model and reports one aggregate score.
""",
    "p03_contributions": """
So this is a resource and evaluation paper with three contributions. A Vietnamese drug-information corpus, with a ten-thousand-question retrieval benchmark and a five-hundred-item end-to-end golden set. A retrieval study that sets quality against cost. And an agentic RAG pipeline that small open-weight models can run, with an evaluation that shows what each step contributes. Everything is public: code on GitHub, data and every run on Kaggle.
""",
    "p04_corpus": """
The corpus combines two kinds of official labelling. On the left, the Vietnamese National Drug Formulary, with six hundred eighty-nine monographs and twenty-five general chapters; this is the Paracetamol page. On the right, a real package leaflet; we collected two thousand four hundred six of them from an online pharmacy in July 2026. In total, three thousand one hundred twenty documents and almost twenty-five thousand chunks, and we keep formulary page numbers so that answers can cite them.
""",
    "p05_enrichment": """
This is the part I like most. Patients do not ask about Panadol Extra; they ask about red Panadol. They ask about the stomach medicine with the letter Y, which is Yumangel, or the one with the letter P, which is Phosphalugel. None of these names appear in the source text.
So before embedding, every chunk gets three deterministic additions: a context header with the title and heading path, the colloquial names and visual signs of the product, and an explanation of abbreviations such as TKTW, central nervous system. In total, two thousand four hundred nine colloquial mappings and a seventy-one-term glossary, all done offline, with no model call at query time.
""",
    "p06_evalsets": """
We evaluate at two levels. The retrieval benchmark has ten thousand questions generated with rules and templates, not with a language model, so the gold section of every question is known by construction. They cover six groups, from formulary questions to noisy questions without diacritics.
The golden set has five hundred items written with a pharmacist: four hundred twenty answerable questions, fifty multi-turn follow-ups, and ten each of unanswerable, out-of-scope and prompt-injection requests. Every answer is checked against atomic key facts with verbatim evidence quotes.
""",
    "p07_pipeline": """
Here is the pipeline. The control flow lives in code, and every model call makes one small structured decision. The guard decides whether a turn is an attack or off-topic. Rephrase turns a follow-up into a standalone query. Search fuses BM25 and dense results with reciprocal rank fusion, and a reranker keeps the top five. The judge asks whether the evidence is enough; if not, refine writes new queries, for at most three rounds. The answer cites its sources, and invalid citations are removed.
Code enforces a budget of ten model calls per turn. We run two settings: Gemini models, and an all open-weight setting where every step is the open Qwen 3.5 nine-billion model.
""",
    "p08_retrieval_table": """
Now the results, starting with retrieval. We compared fourteen configurations on the ten thousand questions: BM25, six dense embedding models, hybrid fusion, and five rerankers on top of the hybrid candidates. The orange rows are what the pipeline uses. Together they place a relevant chunk in the top ten for ninety-seven point five percent of the questions. The hybrid candidates already contain one in the top thirty for ninety-nine point two percent, so the reranker only has to move it to the top. Three lessons come out of this table.
""",
    "p09_embeddings": """
The first lesson: do not hesitate to self-host the embedding model. The open Qwen3 embedding 4B beats OpenAI's text-embedding-3-large in every column we report, for example an nDCG at ten of point eight two zero against point eight zero zero, with a smaller vector. It even matches the 8B model in Hit at ten.
The second lesson is about fusion. With the common constant k equals sixty, hybrid retrieval falls below dense retrieval alone in nDCG, at point seven four seven. With k equals two, hybrid gives the best Hit at ten and Hit at thirty before reranking, and the choice holds on a held-out half: ninety-six point one against ninety-three point eight percent.
""",
    "p10_rerankers": """
The third lesson: a mid-size reranker is the sweet spot. Qwen3 reranker 4B raises Hit at five by three point seven points and comes within point eight points of the 8B model at two point seven times its throughput. BGE reranker v2 m3 is eight times faster but leaves Hit at ten unchanged, and the Gemma-based BGE reranker brings no improvement. A Vietnamese medical instruction also helps the small reranker, from point seven six one to point eight zero four in MRR.
At the bottom: each part pays off where it is designed to. On questions that share a rare word with their gold section, BM25 rescues a chunk that dense retrieval misses two point two times as often. On products with a same-brand sibling, the reranker lifts the right chunk into the top five one point four times as often.
""",
    "p11_grounding": """
Now end to end. Grounding is what makes the answers usable. Without retrieval, Gemini 3.8 Flash reaches a truthfulness of only point two six eight, and Qwen 3.5 nine-billion is even negative: it is wrong more often than right. Inside the pipeline they reach point nine two three and point nine one three. Hallucinated answers drop eighteenfold with Gemini, from eighteen point three to one percent, and twenty-five-fold with Qwen, and severe harm drops with them.
""",
    "p12_open_model": """
This is the result I find most useful in practice. In the open-weight setting, every step is Qwen 3.5 nine-billion, an open Apache-licensed model. Without retrieval it scored minus point zero six; inside the pipeline it reaches point nine one three. Row by row it stays close to Gemini: point nine one three against point nine two three in truthfulness, and one point two against one percent hallucination. It declines all unanswerable questions, defends all injections, and redirects nine of ten out-of-scope requests, with about five model calls per turn. The reason is the design: each call only has to make one small structured decision, and code owns the control flow.
""",
    "p13_steps": """
Averages can mislead here. Over all items, removing the reranker changes no quality metric significantly. But each step targets a specific group of questions, and that is where we measure it. Without rephrasing, truthfulness on follow-ups falls from point nine two to point zero two, because the system searches the pronoun as typed; one-step RAG leaves ninety-six percent of them unanswered. Without the judge-refine loop, patient-style questions fall from one to point six five seven. The reranker matters for answers hidden in a single chunk, a borderline result. And without the guard, none of the ten off-topic requests is redirected.
""",
    "p14_concat": """
What do the extra calls buy? Concat RAG appends the earlier user questions to the search query without a rewrite call. It uses two calls per turn instead of five point three, more than forty percent fewer calls and tokens, and it recovers most follow-ups. But rephrasing is still better: point nine two against point seven five truthfulness, and eighty-four against sixty-four percent perfect answers. With the small model, Concat even raises hallucination to four percent, because the query pulls in evidence about earlier drugs.
And the loop is cheaper than it looks: the judge accepts the first search for two hundred ninety-five of four hundred eighty items, so only the other hundred eighty-five pay for further rounds.
""",
    "p15_judge": """
All of this relies on an automatic judge, so we validated it. A pharmacist graded four hundred shuffled, blinded items with the same rubric. Agreement is high: Cohen's kappa about point eight five and Spearman's rho about point nine. Prediction-powered inference shows the judge is slightly strict but favours no system.
On citations, ninety-six and a half percent of cited sentences are supported. The weakness is sentences without any citation: about a quarter, and ten point eight percent state a fact a reader cannot trace.
""",
    "p16_takeaways": """
To summarise. We release a Vietnamese drug resource built from the national formulary and real leaflets, with the colloquial names patients use. Self-hosted retrieval is enough: open embeddings beat a commercial API, and we reach ninety-seven point five percent Hit at ten. Grounding does the heavy lifting. Small structured decisions let a nine-billion open model run every step at almost the quality of Gemini. And each step should be judged on the questions it targets.
Our main limits are template-generated questions, a single pharmacist, and small safety sets.
""",
    "p17_thanks": """
Thank you very much. I am happy to take your questions.
""",
}
