import math

import pytest

from pharma_lab.e2e.decision_metrics import (
    accuracy_at,
    auroc,
    best_threshold,
    brier,
    ece,
)


def test_auroc_of_a_perfect_and_a_random_scorer() -> None:
    assert auroc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert auroc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) == 0.5


def test_auroc_averages_ranks_over_ties() -> None:
    # One positive ties with one negative (half a win) and beats the other.
    assert auroc([0, 0, 1], [0.2, 0.5, 0.5]) == pytest.approx(0.75)


def test_auroc_of_a_single_class_is_nan() -> None:
    assert math.isnan(auroc([1, 1, 1], [0.1, 0.5, 0.9]))
    assert math.isnan(auroc([0, 0], [0.1, 0.9]))


def test_ece_and_brier_of_calibrated_scores() -> None:
    labels, scores = [1] * 8 + [0] * 2, [0.8] * 10
    assert ece(labels, scores, bins=10) == pytest.approx(0.0)
    assert brier(labels, scores) == pytest.approx(0.16)


def test_ece_counts_a_score_of_one_in_the_last_bin() -> None:
    assert ece([0, 0], [1.0, 1.0], bins=10) == pytest.approx(1.0)


def test_best_threshold_maximises_balanced_accuracy() -> None:
    labels, scores = [0, 0, 1, 1, 1], [0.2, 0.4, 0.45, 0.7, 0.9]
    assert best_threshold(labels, scores) == 0.45
    assert accuracy_at(labels, scores, 0.45) == 1.0
