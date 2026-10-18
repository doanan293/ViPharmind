from tests.e2e.test_conversational import CORPUS, PARA, ROWS

from pharma_lab.e2e.benchmark_extension import GENERATED_GROUPS, extend_rows

ALIASES = [("Panadol trắng", ["leaflet:t:panadol:01-thanh-phan"])]


def extended(base: list[dict]) -> list[dict]:
    return extend_rows(
        base, CORPUS, ALIASES, covered=None, conversational_total=16, seed=0
    )


def test_extend_appends_the_generated_groups_after_the_base_rows() -> None:
    rows = extended(ROWS)
    assert rows[: len(ROWS)] == ROWS
    groups = [row["eval_group"] for row in rows[len(ROWS) :]]
    # Generated groups come in a fixed order, each in one block.
    assert groups == sorted(groups, key=GENERATED_GROUPS.index)
    assert "conversational" in groups
    conversational = [r for r in rows if r["eval_group"] == "conversational"]
    assert all(r["query"] == r["turns"][-1]["text"] for r in conversational)
    assert {r["parent_query_id"] for r in conversational} <= {
        r["query_id"] for r in ROWS
    }
    assert any(PARA in str(r["expected_section_ids"]) for r in conversational)


def test_extend_is_idempotent() -> None:
    once = extended(ROWS)
    assert extended(once) == once
