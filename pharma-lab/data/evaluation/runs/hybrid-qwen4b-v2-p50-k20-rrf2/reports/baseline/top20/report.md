# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 88.75% |
| Hit@5 | 94.13% |
| Hit@10 | 97.37% |
| Hit@20 | 98.81% |
| nDCG@5 | 0.7873 |
| MRR@5 | 0.7356 |
| nDCG@10 | 0.7982 |
| MRR@10 | 0.7401 |
| MRR@20 | 0.7412 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 90.50% |
| Complete-evidence rate@3 | 83.00% |
| Recall@5 | 98.00% |
| Complete-evidence rate@5 | 96.40% |
| Recall@10 | 99.40% |
| Complete-evidence rate@10 | 98.80% |
| Recall@20 | 99.80% |
| Complete-evidence rate@20 | 99.60% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 89.10% | 94.58% | 97.34% | 98.76% | 0.7911 | 0.7384 | 0.8003 | 0.7423 | 0.7434 |
| leaflet | 2500 | 88.32% | 93.88% | 97.72% | 99.36% | 0.7886 | 0.7376 | 0.8013 | 0.7430 | 0.7442 |
| leaflet_short | 500 | 95.40% | 98.40% | 99.60% | 100.00% | 0.8641 | 0.8230 | 0.8681 | 0.8248 | 0.8250 |
| multi_intent | 500 | 98.00% | 99.60% | 100.00% | 100.00% | 0.8938 | 0.8725 | 0.8995 | 0.8731 | 0.8731 |
| noisy | 500 | 73.40% | 81.60% | 91.00% | 93.80% | 0.6242 | 0.5593 | 0.6554 | 0.5727 | 0.5748 |
| structured | 1000 | 87.80% | 93.90% | 97.40% | 99.00% | 0.7547 | 0.6919 | 0.7665 | 0.6971 | 0.6984 |
