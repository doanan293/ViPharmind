# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 82.86% |
| Hit@5 | 88.18% |
| Hit@10 | 92.53% |
| Hit@20 | 94.74% |
| nDCG@5 | 0.7627 |
| MRR@5 | 0.7245 |
| nDCG@10 | 0.7775 |
| MRR@10 | 0.7305 |
| MRR@20 | 0.7321 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 87.30% |
| Complete-evidence rate@3 | 79.00% |
| Recall@5 | 94.30% |
| Complete-evidence rate@5 | 90.20% |
| Recall@10 | 97.30% |
| Complete-evidence rate@10 | 95.60% |
| Recall@20 | 98.20% |
| Complete-evidence rate@20 | 97.20% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 81.60% | 87.58% | 92.20% | 94.42% | 0.7483 | 0.7054 | 0.7634 | 0.7117 | 0.7133 |
| leaflet | 2500 | 83.00% | 87.20% | 91.48% | 94.08% | 0.7646 | 0.7282 | 0.7787 | 0.7341 | 0.7359 |
| leaflet_short | 500 | 89.80% | 93.00% | 94.80% | 96.00% | 0.8523 | 0.8260 | 0.8582 | 0.8285 | 0.8293 |
| multi_intent | 500 | 95.60% | 98.40% | 99.00% | 99.20% | 0.8817 | 0.8877 | 0.8939 | 0.8886 | 0.8887 |
| noisy | 500 | 70.40% | 79.00% | 86.80% | 91.00% | 0.6191 | 0.5616 | 0.6447 | 0.5724 | 0.5753 |
| structured | 1000 | 85.20% | 90.70% | 95.30% | 97.00% | 0.7971 | 0.7602 | 0.8124 | 0.7667 | 0.7679 |
