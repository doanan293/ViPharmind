# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 78.55% |
| Hit@5 | 85.71% |
| Hit@10 | 90.72% |
| Hit@20 | 93.93% |
| nDCG@5 | 0.7046 |
| MRR@5 | 0.6569 |
| nDCG@10 | 0.7221 |
| MRR@10 | 0.6639 |
| MRR@20 | 0.6662 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 79.60% |
| Complete-evidence rate@3 | 67.40% |
| Recall@5 | 88.50% |
| Complete-evidence rate@5 | 80.40% |
| Recall@10 | 95.40% |
| Complete-evidence rate@10 | 92.00% |
| Recall@20 | 97.80% |
| Complete-evidence rate@20 | 96.20% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 74.52% | 82.40% | 88.18% | 91.68% | 0.6650 | 0.6115 | 0.6841 | 0.6196 | 0.6221 |
| leaflet | 2500 | 81.44% | 87.80% | 92.96% | 96.56% | 0.7296 | 0.6795 | 0.7466 | 0.6867 | 0.6893 |
| leaflet_short | 500 | 90.00% | 93.00% | 95.00% | 96.80% | 0.8373 | 0.8056 | 0.8437 | 0.8083 | 0.8096 |
| multi_intent | 500 | 91.80% | 96.60% | 98.80% | 99.40% | 0.8200 | 0.8457 | 0.8479 | 0.8487 | 0.8492 |
| noisy | 500 | 67.00% | 80.20% | 85.80% | 90.20% | 0.5916 | 0.5214 | 0.6097 | 0.5289 | 0.5322 |
| structured | 1000 | 84.90% | 90.70% | 94.10% | 96.30% | 0.7719 | 0.7263 | 0.7833 | 0.7312 | 0.7328 |
