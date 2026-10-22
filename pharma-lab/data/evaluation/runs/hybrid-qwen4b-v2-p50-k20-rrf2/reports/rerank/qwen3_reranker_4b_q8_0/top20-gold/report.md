# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 92.45% |
| Hit@5 | 95.57% |
| Hit@10 | 97.76% |
| Hit@20 | 98.73% |
| nDCG@5 | 0.8840 |
| MRR@5 | 0.8615 |
| nDCG@10 | 0.8920 |
| MRR@10 | 0.8645 |
| MRR@20 | 0.8652 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 83.50% |
| Complete-evidence rate@3 | 73.80% |
| Recall@5 | 92.70% |
| Complete-evidence rate@5 | 87.40% |
| Recall@10 | 98.60% |
| Complete-evidence rate@10 | 97.40% |
| Recall@20 | 99.50% |
| Complete-evidence rate@20 | 99.00% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 89.50% | 93.82% | 97.10% | 98.60% | 0.8483 | 0.8180 | 0.8590 | 0.8225 | 0.8236 |
| leaflet | 2500 | 98.88% | 99.24% | 99.36% | 99.36% | 0.9622 | 0.9517 | 0.9627 | 0.9519 | 0.9519 |
| leaflet_short | 500 | 99.20% | 100.00% | 100.00% | 100.00% | 0.9706 | 0.9605 | 0.9706 | 0.9605 | 0.9605 |
| multi_intent | 500 | 93.20% | 98.00% | 99.80% | 100.00% | 0.8478 | 0.8398 | 0.8711 | 0.8422 | 0.8423 |
| noisy | 500 | 79.20% | 87.20% | 91.60% | 93.80% | 0.7322 | 0.6855 | 0.7466 | 0.6916 | 0.6932 |
| structured | 1000 | 94.00% | 95.90% | 98.00% | 99.00% | 0.9171 | 0.9028 | 0.9240 | 0.9057 | 0.9064 |
