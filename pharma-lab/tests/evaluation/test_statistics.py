import math

import pytest

from pharma_lab.evaluation.statistics import (
    PairedTest,
    Summary,
    bootstrap_mean,
    gwet_ac1,
    holm,
    paired_test,
    percent_agreement,
    ppi_mean,
    weighted_bootstrap_mean,
    wilson,
)


def test_wilson_interval_matches_the_textbook_value() -> None:
    # 10/10: the 95% Wilson interval is [0.7225, 1.0].
    summary = wilson([1.0] * 10)
    assert summary.mean == 1.0
    assert summary.ci_low == pytest.approx(0.7225, abs=1e-4)
    assert summary.ci_high == pytest.approx(1.0)
    half = wilson([1.0] * 5 + [0.0] * 5)
    assert (half.ci_low, half.ci_high) == pytest.approx((0.2366, 0.7634), abs=1e-4)
    assert wilson([]).n == 0


def test_bootstrap_mean_of_a_constant_is_exact() -> None:
    summary = bootstrap_mean([2.0, 2.0, 2.0])
    assert (summary.mean, summary.ci_low, summary.ci_high) == (2.0, 2.0, 2.0)


def test_paired_test_separates_a_clear_shift_from_noise() -> None:
    shifted = paired_test([0.5] * 30)
    noise = paired_test([1.0, -1.0] * 15)
    assert shifted.p_value < 0.001
    assert shifted.summary.mean == pytest.approx(0.5)
    assert noise.p_value > 0.5
    assert math.isnan(paired_test([]).p_value)


def test_holm_adjusts_in_input_order() -> None:
    assert holm([0.04, 0.01, 0.03]) == pytest.approx([0.06, 0.03, 0.06])
    adjusted = holm([0.5, math.nan])
    assert adjusted[0] == 0.5 and math.isnan(adjusted[1])


def test_ppi_removes_a_constant_judge_bias() -> None:
    judge_all = [0.9, 0.8, 1.0, 0.7] * 25
    judge_labelled = [0.9, 0.8, 1.0, 0.7]
    human_labelled = [0.7, 0.6, 0.8, 0.5]

    estimate = ppi_mean(judge_all, judge_labelled, human_labelled)

    assert estimate.mean == pytest.approx(0.65)
    assert estimate.ci_low < 0.65 < estimate.ci_high
    with pytest.raises(ValueError, match="one human label"):
        ppi_mean(judge_all, [0.1], [])


def test_gwet_ac1_stays_high_when_kappa_collapses_on_skewed_labels() -> None:
    judge = [True] * 19 + [False]
    human = [True] * 20
    assert percent_agreement(judge, human) == 0.95
    assert gwet_ac1(judge, human) == pytest.approx(0.9474, abs=1e-3)
    assert gwet_ac1([True, True], [True, True]) == 1.0


def test_blocked_resampling_matches_one_block() -> None:
    # Reference values from the single-block implementation (2026-10-25): resampling in
    # blocks must draw the same random stream and give the same numbers.
    values = [(i * 37 % 11 - 4.8) / 5 for i in range(3000)]
    expected = Summary(
        3000, 0.039666666666666704, 0.017131666666666705, 0.061933333333333375
    )
    assert bootstrap_mean(values) == expected
    assert paired_test(values) == PairedTest(expected, 0.0007999200079992001)


def test_resampling_never_draws_the_whole_matrix_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    from pharma_lab.evaluation import statistics as stats

    rows: list[int] = []
    make = np.random.default_rng

    class Recording:
        def __init__(self, seed: int) -> None:
            self.rng = make(seed)

        def integers(self, low: int, high: int, size: tuple[int, int]) -> np.ndarray:
            rows.append(size[0])
            return self.rng.integers(low, high, size)

        def choice(
            self, options: tuple[float, float], size: tuple[int, int]
        ) -> np.ndarray:
            rows.append(size[0])
            return self.rng.choice(options, size=size)

    monkeypatch.setattr(stats.np.random, "default_rng", Recording)
    stats.paired_test([0.5, -0.25] * 50)
    assert sum(rows) == 2 * stats.RESAMPLES
    assert max(rows) <= stats.RESAMPLE_BLOCK


def test_weighted_bootstrap_mean_with_equal_weights_is_the_plain_mean() -> None:
    values = [(i * 37 % 11 - 4.8) / 5 for i in range(300)]
    weighted = weighted_bootstrap_mean(values, [2.0] * 300)
    plain = bootstrap_mean(values)
    assert weighted.n == 300
    assert weighted.mean == pytest.approx(plain.mean)
    assert weighted.ci_low < weighted.mean < weighted.ci_high


def test_weighted_bootstrap_mean_weights_the_items() -> None:
    summary = weighted_bootstrap_mean([1.0, 1.0, 0.0, 0.0], [1.5, 1.5, 0.5, 0.5])
    assert summary.mean == pytest.approx(0.75)
