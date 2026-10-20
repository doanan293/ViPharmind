# Retrieval slices

| Slice | Size | Comparison | Win inside | Win outside | Ratio |
| --- | ---: | --- | ---: | ---: | ---: |
| rare_term | 3657 | bm25_over_dense_hit10 | 0.037 | 0.017 | 2.2x |
| rare_term | 3657 | hybrid_over_dense_hit10 | 0.032 | 0.013 | 2.5x |
| sibling_products | 846 | rerank_over_hybrid_hit5 | 0.082 | 0.058 | 1.4x |
| sibling_products | 846 | rerank_over_hybrid_hit5_leaflets | 0.082 | 0.041 | 2.0x |
| sibling_products | 846 | rerank_over_hybrid_top1 | 0.239 | 0.197 | 1.2x |
