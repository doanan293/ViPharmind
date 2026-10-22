# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 86.13% |
| Hit@5 | 90.96% |
| Hit@10 | 94.16% |
| Hit@20 | 95.89% |
| nDCG@5 | 0.7919 |
| MRR@5 | 0.7526 |
| nDCG@10 | 0.8026 |
| MRR@10 | 0.7571 |
| MRR@20 | 0.7583 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 92.80% |
| Complete-evidence rate@3 | 87.20% |
| Recall@5 | 98.00% |
| Complete-evidence rate@5 | 96.60% |
| Recall@10 | 99.30% |
| Complete-evidence rate@10 | 98.80% |
| Recall@20 | 99.60% |
| Complete-evidence rate@20 | 99.40% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 82.52% | 88.18% | 91.74% | 93.82% | 0.7573 | 0.7152 | 0.7690 | 0.7202 | 0.7217 |
| leaflet | 2500 | 91.92% | 95.44% | 98.08% | 99.00% | 0.8420 | 0.8037 | 0.8506 | 0.8072 | 0.8079 |
| leaflet_short | 500 | 95.20% | 97.60% | 99.00% | 99.40% | 0.8838 | 0.8522 | 0.8886 | 0.8542 | 0.8545 |
| multi_intent | 500 | 98.40% | 99.40% | 99.80% | 99.80% | 0.9111 | 0.8941 | 0.9164 | 0.8947 | 0.8947 |
| noisy | 500 | 67.80% | 78.20% | 85.40% | 90.60% | 0.6021 | 0.5419 | 0.6255 | 0.5516 | 0.5553 |
| structured | 1000 | 88.20% | 92.50% | 95.60% | 97.40% | 0.8291 | 0.7966 | 0.8394 | 0.8011 | 0.8024 |
