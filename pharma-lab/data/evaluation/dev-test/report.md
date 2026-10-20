# Dev/test check (seed 0)

## Fusion constant

Chosen on dev by hit@10 (5000 queries): **rrf2**.

| Option | dev hit@10 | test Hit@10 | test MRR@10 | test nDCG@10 |
| --- | ---: | ---: | ---: | ---: |
| rrf2 | 0.9564 | 0.9614 | 0.7350 | 0.7878 |
| rrf60 | 0.9368 | 0.9380 | 0.6953 | 0.7483 |

rrf2 reranked by Qwen3-Reranker-4B on test (5000 queries): Hit@10 0.9754, MRR@10 0.8328, nDCG@10 0.8638.

## Rerank instruction (Qwen3-Reranker-0.6B pilot)

Pilot queries on dev: 508; on test: 492. Chosen on dev by mrr: **with**.

| Option | dev MRR@30 | test MRR@30 |
| --- | ---: | ---: |
| without | 0.7659 | 0.7606 |
| with | 0.8117 | 0.8037 |
