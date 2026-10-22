# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 88.04% |
| Hit@5 | 92.53% |
| Hit@10 | 95.21% |
| Hit@20 | 96.53% |
| nDCG@5 | 0.8254 |
| MRR@5 | 0.7926 |
| nDCG@10 | 0.8343 |
| MRR@10 | 0.7963 |
| MRR@20 | 0.7973 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 95.60% |
| Complete-evidence rate@3 | 92.20% |
| Recall@5 | 98.40% |
| Complete-evidence rate@5 | 97.20% |
| Recall@10 | 99.10% |
| Complete-evidence rate@10 | 98.40% |
| Recall@20 | 99.30% |
| Complete-evidence rate@20 | 98.80% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 87.48% | 92.00% | 94.58% | 95.84% | 0.8179 | 0.7834 | 0.8265 | 0.7870 | 0.7879 |
| leaflet | 2500 | 86.92% | 91.88% | 95.32% | 96.96% | 0.8090 | 0.7718 | 0.8202 | 0.7765 | 0.7776 |
| leaflet_short | 500 | 92.00% | 95.60% | 96.60% | 97.40% | 0.8676 | 0.8378 | 0.8710 | 0.8392 | 0.8398 |
| multi_intent | 500 | 99.00% | 99.60% | 99.80% | 99.80% | 0.9571 | 0.9636 | 0.9601 | 0.9640 | 0.9640 |
| noisy | 500 | 81.00% | 87.20% | 91.40% | 93.40% | 0.7461 | 0.7037 | 0.7595 | 0.7092 | 0.7107 |
| structured | 1000 | 89.70% | 94.40% | 97.00% | 98.40% | 0.8568 | 0.8275 | 0.8651 | 0.8309 | 0.8320 |
