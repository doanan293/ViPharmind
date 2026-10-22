# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 85.74% |
| Hit@5 | 92.48% |
| Hit@10 | 96.68% |
| Hit@20 | 98.53% |
| nDCG@5 | 0.7676 |
| MRR@5 | 0.7160 |
| nDCG@10 | 0.7819 |
| MRR@10 | 0.7218 |
| MRR@20 | 0.7232 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 88.40% |
| Complete-evidence rate@3 | 80.20% |
| Recall@5 | 95.10% |
| Complete-evidence rate@5 | 91.00% |
| Recall@10 | 98.00% |
| Complete-evidence rate@10 | 96.00% |
| Recall@20 | 99.40% |
| Complete-evidence rate@20 | 98.80% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 85.34% | 91.96% | 96.10% | 98.22% | 0.7664 | 0.7146 | 0.7800 | 0.7203 | 0.7219 |
| leaflet | 2500 | 88.32% | 94.40% | 98.16% | 99.44% | 0.7920 | 0.7405 | 0.8043 | 0.7457 | 0.7466 |
| leaflet_short | 500 | 94.80% | 98.60% | 99.40% | 100.00% | 0.8667 | 0.8260 | 0.8694 | 0.8272 | 0.8275 |
| multi_intent | 500 | 96.60% | 99.20% | 100.00% | 100.00% | 0.8742 | 0.8649 | 0.8860 | 0.8660 | 0.8660 |
| noisy | 500 | 66.20% | 79.20% | 90.00% | 93.60% | 0.5602 | 0.4826 | 0.5958 | 0.4976 | 0.5001 |
| structured | 1000 | 81.10% | 90.50% | 96.20% | 98.80% | 0.7134 | 0.6491 | 0.7323 | 0.6570 | 0.6590 |
