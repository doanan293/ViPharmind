from collections import defaultdict

from pharma_lab.evaluation.metrics_service import (
    accumulate_breakdown_metrics,
    markdown_breakdown_tables,
)


def test_accumulate_breakdown_metrics_groups_rows_by_eval_group():
    breakdowns = {"eval_group": defaultdict(lambda: defaultdict(float))}
    hits = {
        "hit@3": 1,
        "hit@5": 1,
        "hit@10": 1,
        "hit@30": 1,
        "mrr": 0.5,
        "multi_section_recall@3": 0.5,
    }

    accumulate_breakdown_metrics(
        breakdowns,
        hits,
        {
            "eval_group": "leaflet_short",
            "answer_mode": "multi_required",
        },
    )
    accumulate_breakdown_metrics(
        breakdowns,
        {**hits, "hit@3": 0, "mrr": 0.25},
        {
            "eval_group": "leaflet_short",
            "answer_mode": "single",
        },
    )
    accumulate_breakdown_metrics(
        breakdowns,
        hits,
        {"eval_group": "", "answer_mode": "single"},
    )

    short = breakdowns["eval_group"]["leaflet_short"]
    assert short["count"] == 2
    assert short["hit@3"] == 1
    assert short["mrr"] == 0.75
    assert breakdowns["eval_group"]["unknown"]["count"] == 1


def test_markdown_breakdown_tables_renders_only_compact_metrics():
    breakdowns = {
        "eval_group": {
            "chunk_risk": {
                "count": 2,
                "hit@3": 1,
                "hit@5": 2,
                "hit@10": 2,
                "hit@30": 2,
                "mrr": 0.75,
                "ndcg@10": 1.5,
                "mrr@10": 1.5,
                "multi_count": 1,
            },
            "leaflet": {
                "count": 1,
                "hit@3": 1,
                "hit@5": 1,
                "hit@10": 1,
                "hit@30": 1,
                "mrr": 1.0,
                "ndcg@10": 1.0,
                "mrr@10": 1.0,
            },
        },
    }

    rendered = markdown_breakdown_tables(breakdowns)

    assert "## Breakdown by eval_group" in rendered
    assert (
        "| eval_group | Count | Hit@3 | Hit@5 | Hit@10 | Hit@30 | nDCG@10 | MRR@10 "
        "| MRR@30 |" in rendered
    )
    assert (
        "| leaflet | 1 | 100.00% | 100.00% | 100.00% | 100.00% | 1.0000 "
        "| 1.0000 | 1.0000 |" in rendered
    )
    assert (
        "| chunk_risk | 2 | 50.00% | 100.00% | 100.00% | 100.00% | 0.7500 "
        "| 0.7500 | 0.3750 |" in rendered
    )
    assert "## Breakdown by difficulty" not in rendered
    assert "Complete-evidence" not in rendered
