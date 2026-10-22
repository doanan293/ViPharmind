# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 89.19% |
| Hit@5 | 94.51% |
| Hit@10 | 97.63% |
| Hit@20 | 98.85% |
| nDCG@5 | 0.7951 |
| MRR@5 | 0.7447 |
| nDCG@10 | 0.8056 |
| MRR@10 | 0.7491 |
| MRR@20 | 0.7500 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 91.10% |
| Complete-evidence rate@3 | 83.40% |
| Recall@5 | 97.90% |
| Complete-evidence rate@5 | 96.00% |
| Recall@10 | 99.20% |
| Complete-evidence rate@10 | 98.40% |
| Recall@20 | 99.70% |
| Complete-evidence rate@20 | 99.40% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 89.20% | 94.74% | 97.64% | 98.82% | 0.7967 | 0.7454 | 0.8063 | 0.7495 | 0.7503 |
| leaflet | 2500 | 88.84% | 94.44% | 98.00% | 99.28% | 0.7984 | 0.7488 | 0.8101 | 0.7538 | 0.7547 |
| leaflet_short | 500 | 94.60% | 98.00% | 99.80% | 100.00% | 0.8654 | 0.8261 | 0.8714 | 0.8287 | 0.8288 |
| multi_intent | 500 | 98.80% | 99.80% | 100.00% | 100.00% | 0.8937 | 0.8725 | 0.8989 | 0.8728 | 0.8728 |
| noisy | 500 | 76.80% | 85.00% | 91.40% | 94.40% | 0.6535 | 0.5868 | 0.6750 | 0.5960 | 0.5981 |
| structured | 1000 | 88.70% | 93.90% | 97.50% | 99.00% | 0.7650 | 0.7055 | 0.7768 | 0.7104 | 0.7115 |
