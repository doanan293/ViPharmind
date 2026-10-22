# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 94.30% |
| Hit@5 | 96.56% |
| Hit@10 | 98.20% |
| Hit@20 | 98.81% |
| nDCG@5 | 0.9004 |
| MRR@5 | 0.8801 |
| nDCG@10 | 0.9063 |
| MRR@10 | 0.8823 |
| MRR@20 | 0.8828 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 92.60% |
| Complete-evidence rate@3 | 85.80% |
| Recall@5 | 96.60% |
| Complete-evidence rate@5 | 93.60% |
| Recall@10 | 99.50% |
| Complete-evidence rate@10 | 99.00% |
| Recall@20 | 99.80% |
| Complete-evidence rate@20 | 99.60% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 92.10% | 95.32% | 97.86% | 98.76% | 0.8784 | 0.8531 | 0.8867 | 0.8565 | 0.8572 |
| leaflet | 2500 | 98.76% | 99.20% | 99.32% | 99.36% | 0.9455 | 0.9292 | 0.9459 | 0.9294 | 0.9295 |
| leaflet_short | 500 | 99.60% | 100.00% | 100.00% | 100.00% | 0.9716 | 0.9617 | 0.9716 | 0.9617 | 0.9617 |
| multi_intent | 500 | 99.40% | 99.60% | 100.00% | 100.00% | 0.9313 | 0.9478 | 0.9429 | 0.9485 | 0.9485 |
| noisy | 500 | 83.00% | 89.00% | 92.40% | 93.80% | 0.7550 | 0.7095 | 0.7664 | 0.7144 | 0.7154 |
| structured | 1000 | 94.60% | 96.70% | 98.20% | 99.00% | 0.9191 | 0.9028 | 0.9240 | 0.9049 | 0.9055 |
