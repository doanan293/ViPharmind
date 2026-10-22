# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 86.96% |
| Hit@5 | 91.77% |
| Hit@10 | 94.84% |
| Hit@20 | 96.32% |
| nDCG@5 | 0.8108 |
| MRR@5 | 0.7754 |
| nDCG@10 | 0.8210 |
| MRR@10 | 0.7797 |
| MRR@20 | 0.7808 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 95.40% |
| Complete-evidence rate@3 | 91.80% |
| Recall@5 | 98.90% |
| Complete-evidence rate@5 | 98.00% |
| Recall@10 | 99.70% |
| Complete-evidence rate@10 | 99.40% |
| Recall@20 | 99.70% |
| Complete-evidence rate@20 | 99.40% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 86.20% | 91.18% | 94.06% | 95.50% | 0.8009 | 0.7634 | 0.8104 | 0.7674 | 0.7685 |
| leaflet | 2500 | 86.12% | 90.88% | 94.88% | 96.80% | 0.7997 | 0.7629 | 0.8129 | 0.7684 | 0.7699 |
| leaflet_short | 500 | 92.00% | 94.80% | 96.40% | 97.00% | 0.8682 | 0.8411 | 0.8738 | 0.8435 | 0.8440 |
| multi_intent | 500 | 99.00% | 99.80% | 100.00% | 100.00% | 0.9512 | 0.9496 | 0.9545 | 0.9499 | 0.9499 |
| noisy | 500 | 77.60% | 85.80% | 90.40% | 92.60% | 0.7035 | 0.6518 | 0.7185 | 0.6581 | 0.6598 |
| structured | 1000 | 89.00% | 94.40% | 97.50% | 98.90% | 0.8425 | 0.8084 | 0.8526 | 0.8126 | 0.8138 |
