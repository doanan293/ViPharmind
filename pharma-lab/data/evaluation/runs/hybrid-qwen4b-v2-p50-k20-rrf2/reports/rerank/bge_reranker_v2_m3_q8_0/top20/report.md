# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 91.75% |
| Hit@5 | 95.07% |
| Hit@10 | 97.53% |
| Hit@20 | 98.81% |
| nDCG@5 | 0.8653 |
| MRR@5 | 0.8375 |
| nDCG@10 | 0.8737 |
| MRR@10 | 0.8410 |
| MRR@20 | 0.8419 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 94.20% |
| Complete-evidence rate@3 | 88.80% |
| Recall@5 | 98.20% |
| Complete-evidence rate@5 | 96.60% |
| Recall@10 | 99.60% |
| Complete-evidence rate@10 | 99.20% |
| Recall@20 | 99.80% |
| Complete-evidence rate@20 | 99.60% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 88.30% | 93.12% | 96.72% | 98.76% | 0.8215 | 0.7844 | 0.8334 | 0.7894 | 0.7909 |
| leaflet | 2500 | 98.40% | 99.12% | 99.32% | 99.36% | 0.9429 | 0.9261 | 0.9436 | 0.9264 | 0.9264 |
| leaflet_short | 500 | 99.80% | 100.00% | 100.00% | 100.00% | 0.9695 | 0.9588 | 0.9695 | 0.9588 | 0.9588 |
| multi_intent | 500 | 99.60% | 99.80% | 100.00% | 100.00% | 0.9386 | 0.9442 | 0.9445 | 0.9445 | 0.9445 |
| noisy | 500 | 71.00% | 81.20% | 90.20% | 93.80% | 0.6416 | 0.5846 | 0.6712 | 0.5971 | 0.5997 |
| structured | 1000 | 94.80% | 96.80% | 98.30% | 99.00% | 0.9132 | 0.8945 | 0.9180 | 0.8965 | 0.8969 |
