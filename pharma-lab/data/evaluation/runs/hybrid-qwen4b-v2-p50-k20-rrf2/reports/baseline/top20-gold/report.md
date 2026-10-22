# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 87.41% |
| Hit@5 | 93.33% |
| Hit@10 | 97.05% |
| Hit@20 | 98.73% |
| nDCG@5 | 0.7730 |
| MRR@5 | 0.7195 |
| nDCG@10 | 0.7858 |
| MRR@10 | 0.7248 |
| MRR@20 | 0.7260 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 85.10% |
| Complete-evidence rate@3 | 75.20% |
| Recall@5 | 94.50% |
| Complete-evidence rate@5 | 91.00% |
| Recall@10 | 98.10% |
| Complete-evidence rate@10 | 96.80% |
| Recall@20 | 99.50% |
| Complete-evidence rate@20 | 99.00% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 86.72% | 93.14% | 96.76% | 98.60% | 0.7676 | 0.7119 | 0.7796 | 0.7170 | 0.7184 |
| leaflet | 2500 | 88.32% | 93.88% | 97.72% | 99.36% | 0.7886 | 0.7376 | 0.8013 | 0.7430 | 0.7442 |
| leaflet_short | 500 | 95.40% | 98.40% | 99.60% | 100.00% | 0.8641 | 0.8230 | 0.8681 | 0.8248 | 0.8250 |
| multi_intent | 500 | 95.00% | 98.00% | 99.40% | 100.00% | 0.8429 | 0.8161 | 0.8576 | 0.8182 | 0.8187 |
| noisy | 500 | 73.40% | 81.60% | 91.00% | 93.80% | 0.6242 | 0.5593 | 0.6554 | 0.5727 | 0.5748 |
| structured | 1000 | 87.80% | 93.90% | 97.40% | 99.00% | 0.7547 | 0.6919 | 0.7665 | 0.6971 | 0.6984 |
