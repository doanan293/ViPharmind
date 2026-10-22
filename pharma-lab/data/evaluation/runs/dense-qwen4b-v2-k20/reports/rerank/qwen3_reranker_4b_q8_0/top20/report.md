# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 91.69% |
| Hit@5 | 94.06% |
| Hit@10 | 95.46% |
| Hit@20 | 96.32% |
| nDCG@5 | 0.8848 |
| MRR@5 | 0.8669 |
| nDCG@10 | 0.8896 |
| MRR@10 | 0.8688 |
| MRR@20 | 0.8695 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 93.40% |
| Complete-evidence rate@3 | 88.00% |
| Recall@5 | 98.20% |
| Complete-evidence rate@5 | 96.60% |
| Recall@10 | 99.40% |
| Complete-evidence rate@10 | 98.80% |
| Recall@20 | 99.70% |
| Complete-evidence rate@20 | 99.40% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 89.14% | 92.38% | 94.28% | 95.50% | 0.8571 | 0.8346 | 0.8634 | 0.8373 | 0.8381 |
| leaflet | 2500 | 96.28% | 96.68% | 96.80% | 96.80% | 0.9371 | 0.9267 | 0.9375 | 0.9269 | 0.9269 |
| leaflet_short | 500 | 96.20% | 97.00% | 97.00% | 97.00% | 0.9406 | 0.9305 | 0.9406 | 0.9305 | 0.9305 |
| multi_intent | 500 | 98.80% | 99.80% | 100.00% | 100.00% | 0.9421 | 0.9441 | 0.9469 | 0.9444 | 0.9444 |
| noisy | 500 | 78.20% | 85.60% | 90.00% | 92.60% | 0.7245 | 0.6806 | 0.7388 | 0.6864 | 0.6883 |
| structured | 1000 | 93.90% | 95.80% | 97.70% | 98.90% | 0.9160 | 0.9017 | 0.9222 | 0.9043 | 0.9051 |
