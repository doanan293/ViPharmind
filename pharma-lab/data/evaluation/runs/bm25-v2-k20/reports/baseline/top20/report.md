# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 72.45% |
| Hit@5 | 82.70% |
| Hit@10 | 90.45% |
| Hit@20 | 94.76% |
| nDCG@5 | 0.6424 |
| MRR@5 | 0.5823 |
| nDCG@10 | 0.6688 |
| MRR@10 | 0.5931 |
| MRR@20 | 0.5962 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 69.70% |
| Complete-evidence rate@3 | 57.20% |
| Recall@5 | 83.70% |
| Complete-evidence rate@5 | 76.20% |
| Recall@10 | 92.30% |
| Complete-evidence rate@10 | 88.00% |
| Recall@20 | 97.70% |
| Complete-evidence rate@20 | 95.40% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 73.16% | 82.84% | 90.52% | 95.18% | 0.6483 | 0.5880 | 0.6736 | 0.5987 | 0.6020 |
| leaflet | 2500 | 76.36% | 86.64% | 94.88% | 98.00% | 0.6776 | 0.6143 | 0.7047 | 0.6258 | 0.6280 |
| leaflet_short | 500 | 88.80% | 97.60% | 99.40% | 100.00% | 0.7928 | 0.7311 | 0.7988 | 0.7337 | 0.7342 |
| multi_intent | 500 | 82.20% | 91.20% | 96.60% | 100.00% | 0.7089 | 0.6736 | 0.7438 | 0.6810 | 0.6837 |
| noisy | 500 | 39.20% | 49.80% | 55.40% | 62.20% | 0.3478 | 0.2981 | 0.3664 | 0.3061 | 0.3111 |
| structured | 1000 | 62.70% | 76.90% | 89.00% | 95.60% | 0.5638 | 0.4960 | 0.6036 | 0.5127 | 0.5175 |
