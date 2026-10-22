# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 85.62% |
| Hit@5 | 89.54% |
| Hit@10 | 93.65% |
| Hit@20 | 96.08% |
| nDCG@5 | 0.8050 |
| MRR@5 | 0.7814 |
| nDCG@10 | 0.8205 |
| MRR@10 | 0.7870 |
| MRR@20 | 0.7888 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 65.90% |
| Complete-evidence rate@3 | 43.40% |
| Recall@5 | 80.50% |
| Complete-evidence rate@5 | 65.60% |
| Recall@10 | 93.90% |
| Complete-evidence rate@10 | 88.80% |
| Recall@20 | 97.50% |
| Complete-evidence rate@20 | 95.20% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 80.38% | 86.12% | 91.88% | 95.34% | 0.7460 | 0.7072 | 0.7647 | 0.7150 | 0.7176 |
| leaflet | 2500 | 96.28% | 97.60% | 98.72% | 99.00% | 0.9349 | 0.9208 | 0.9386 | 0.9224 | 0.9226 |
| leaflet_short | 500 | 98.60% | 99.60% | 99.60% | 100.00% | 0.9592 | 0.9466 | 0.9592 | 0.9466 | 0.9470 |
| multi_intent | 500 | 88.40% | 95.40% | 99.00% | 99.80% | 0.7013 | 0.7525 | 0.7550 | 0.7578 | 0.7585 |
| noisy | 500 | 65.60% | 70.40% | 81.80% | 87.00% | 0.5836 | 0.5429 | 0.6208 | 0.5584 | 0.5623 |
| structured | 1000 | 87.30% | 88.10% | 90.10% | 93.20% | 0.8612 | 0.8545 | 0.8677 | 0.8572 | 0.8592 |
