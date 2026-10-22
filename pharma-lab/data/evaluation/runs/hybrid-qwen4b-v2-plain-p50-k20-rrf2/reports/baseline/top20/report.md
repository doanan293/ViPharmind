# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 77.84% |
| Hit@5 | 85.93% |
| Hit@10 | 92.38% |
| Hit@20 | 96.13% |
| nDCG@5 | 0.7035 |
| MRR@5 | 0.6532 |
| nDCG@10 | 0.7251 |
| MRR@10 | 0.6621 |
| MRR@20 | 0.6648 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 83.40% |
| Complete-evidence rate@3 | 73.60% |
| Recall@5 | 92.40% |
| Complete-evidence rate@5 | 86.60% |
| Recall@10 | 96.10% |
| Complete-evidence rate@10 | 92.60% |
| Recall@20 | 99.10% |
| Complete-evidence rate@20 | 98.20% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 82.24% | 89.50% | 94.36% | 97.08% | 0.7363 | 0.6827 | 0.7523 | 0.6895 | 0.6915 |
| leaflet | 2500 | 70.08% | 79.40% | 88.92% | 94.44% | 0.6429 | 0.5926 | 0.6739 | 0.6055 | 0.6096 |
| leaflet_short | 500 | 86.60% | 93.00% | 97.00% | 99.20% | 0.8178 | 0.7799 | 0.8309 | 0.7853 | 0.7868 |
| multi_intent | 500 | 93.20% | 98.20% | 99.60% | 100.00% | 0.8375 | 0.8296 | 0.8525 | 0.8314 | 0.8317 |
| noisy | 500 | 61.20% | 71.60% | 81.00% | 86.40% | 0.5323 | 0.4707 | 0.5631 | 0.4836 | 0.4876 |
| structured | 1000 | 71.50% | 81.90% | 90.90% | 97.00% | 0.6523 | 0.5968 | 0.6818 | 0.6092 | 0.6135 |
