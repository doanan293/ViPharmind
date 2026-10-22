# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 75.54% |
| Hit@5 | 84.87% |
| Hit@10 | 92.68% |
| Hit@20 | 96.08% |
| nDCG@5 | 0.6689 |
| MRR@5 | 0.6169 |
| nDCG@10 | 0.6968 |
| MRR@10 | 0.6277 |
| MRR@20 | 0.6302 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 62.40% |
| Complete-evidence rate@3 | 32.80% |
| Recall@5 | 78.70% |
| Complete-evidence rate@5 | 60.60% |
| Recall@10 | 92.60% |
| Complete-evidence rate@10 | 85.80% |
| Recall@20 | 97.50% |
| Complete-evidence rate@20 | 95.20% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 77.80% | 85.64% | 92.26% | 95.34% | 0.6908 | 0.6349 | 0.7124 | 0.6440 | 0.6462 |
| leaflet | 2500 | 74.28% | 85.64% | 95.24% | 99.00% | 0.6805 | 0.6220 | 0.7120 | 0.6352 | 0.6381 |
| leaflet_short | 500 | 70.40% | 84.80% | 98.00% | 100.00% | 0.6317 | 0.5599 | 0.6757 | 0.5788 | 0.5805 |
| multi_intent | 500 | 92.00% | 96.80% | 99.40% | 99.80% | 0.6705 | 0.7375 | 0.7265 | 0.7413 | 0.7416 |
| noisy | 500 | 55.40% | 66.40% | 77.60% | 87.00% | 0.4853 | 0.4257 | 0.5218 | 0.4409 | 0.4478 |
| structured | 1000 | 71.80% | 82.40% | 89.90% | 93.20% | 0.6396 | 0.5778 | 0.6643 | 0.5883 | 0.5908 |
