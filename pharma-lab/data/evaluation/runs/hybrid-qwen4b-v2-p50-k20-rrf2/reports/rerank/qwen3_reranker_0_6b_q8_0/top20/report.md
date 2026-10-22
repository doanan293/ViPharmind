# Retrieval Metrics

| Metric | Value |
| --- | ---: |
| Total Queries | 10000.0 |
| Hit@3 | 93.14% |
| Hit@5 | 96.69% |
| Hit@10 | 98.34% |
| Hit@20 | 98.81% |
| nDCG@5 | 0.8704 |
| MRR@5 | 0.8377 |
| nDCG@10 | 0.8760 |
| MRR@10 | 0.8401 |
| MRR@20 | 0.8405 |

## Multi-required queries

| Metric | Value |
| --- | ---: |
| Total Multi-required Queries | 500 |
| Recall@3 | 94.50% |
| Complete-evidence rate@3 | 90.80% |
| Recall@5 | 99.30% |
| Complete-evidence rate@5 | 98.60% |
| Recall@10 | 99.80% |
| Complete-evidence rate@10 | 99.60% |
| Recall@20 | 99.80% |
| Complete-evidence rate@20 | 99.60% |

## Breakdown by eval_group

| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@20 | nDCG@5 | MRR@5 | nDCG@10 | MRR@10 | MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| formulary | 5000 | 91.90% | 96.20% | 98.26% | 98.76% | 0.8576 | 0.8222 | 0.8645 | 0.8251 | 0.8255 |
| leaflet | 2500 | 96.88% | 98.56% | 99.32% | 99.36% | 0.9025 | 0.8738 | 0.9050 | 0.8749 | 0.8749 |
| leaflet_short | 500 | 97.80% | 100.00% | 100.00% | 100.00% | 0.9265 | 0.9012 | 0.9265 | 0.9012 | 0.9012 |
| multi_intent | 500 | 98.20% | 100.00% | 100.00% | 100.00% | 0.9408 | 0.9259 | 0.9427 | 0.9259 | 0.9259 |
| noisy | 500 | 76.20% | 85.20% | 91.00% | 93.80% | 0.6662 | 0.6038 | 0.6851 | 0.6117 | 0.6138 |
| structured | 1000 | 93.60% | 96.90% | 98.30% | 99.00% | 0.8927 | 0.8669 | 0.8975 | 0.8690 | 0.8695 |
