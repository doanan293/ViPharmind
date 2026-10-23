import pytest

from pharma_lab.e2e.golden import Category, GoldenItem
from pharma_lab.e2e.harness import requested_items, run_extra


def golden(index: int, category: Category = Category.ANSWERABLE) -> GoldenItem:
    return GoldenItem.model_validate(
        {
            "item_id": f"e2e-{index:04d}",
            "category": category.value,
            "turns": [{"role": "user", "text": f"q{index}"}],
            "expected_behavior": "grounded",
        }
    )


def test_requested_items_without_ids_follow_limit_and_category() -> None:
    items = [golden(i) for i in range(10)]

    chosen = requested_items(items, only_ids=None, limit=5, category=None)

    assert len(chosen) == 5


def test_only_ids_limits_the_items_in_golden_order() -> None:
    items = [golden(i) for i in range(10)]

    chosen = requested_items(
        items, only_ids=frozenset({"e2e-0007", "e2e-0002"}), limit=None, category=None
    )

    assert [item.item_id for item in chosen] == ["e2e-0002", "e2e-0007"]


def test_only_ids_ignores_limit_and_category() -> None:
    items = [golden(1), golden(2, Category.INJECTION)]

    chosen = requested_items(
        items, only_ids=frozenset({"e2e-0002"}), limit=1, category=Category.ANSWERABLE
    )

    assert [item.item_id for item in chosen] == ["e2e-0002"]


def test_only_ids_must_exist_in_the_golden_set() -> None:
    with pytest.raises(ValueError, match="e2e-9999"):
        requested_items(
            [golden(1)], only_ids=frozenset({"e2e-9999"}), limit=None, category=None
        )


def test_run_extra_records_software_only_when_given() -> None:
    assert run_extra(8, {}) == {"concurrency": 8}
    assert run_extra(4, {"llama_server": "b1"}) == {
        "concurrency": 4,
        "software": {"llama_server": "b1"},
    }
