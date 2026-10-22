# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 93.53% |
| Hit@5 | 96.13% |
| Hit@10 | 97.92% |
| Hit@20 | 98.81% |
| nDCG@5 | 0.9002 |
| MRR@5 | 0.8805 |
| nDCG@10 | 0.9064 |
| MRR@10 | 0.8829 |
| MRR@20 | 0.8836 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 93.30% |
| Complete-evidence rate@3 | 88.00% |
| Recall@5 | 98.20% |
| Complete-evidence rate@5 | 96.40% |
| Recall@10 | 99.80% |
| Complete-evidence rate@10 | 99.60% |
| Recall@20 | 99.80% |
| Complete-evidence rate@20 | 99.60% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 91.12% | 94.74% | 97.40% | 98.76% | 0.8716 | 0.8460 | 0.8803 | 0.8496 | 0.8506 |
| leaflet | 2500 | 98.88% | 99.24% | 99.36% | 99.36% | 0.9622 | 0.9517 | 0.9627 | 0.9519 | 0.9519 |
| leaflet_short | 500 | 99.20% | 100.00% | 100.00% | 100.00% | 0.9706 | 0.9605 | 0.9706 | 0.9605 | 0.9605 |
| multi_intent | 500 | 98.60% | 100.00% | 100.00% | 100.00% | 0.9396 | 0.9394 | 0.9459 | 0.9394 | 0.9394 |
| noisy | 500 | 79.20% | 87.20% | 91.60% | 93.80% | 0.7322 | 0.6855 | 0.7466 | 0.6916 | 0.6932 |
| structured | 1000 | 94.00% | 95.90% | 98.00% | 99.00% | 0.9171 | 0.9028 | 0.9240 | 0.9057 | 0.9064 |
