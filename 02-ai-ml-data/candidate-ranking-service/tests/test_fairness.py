"""Tests for the fairness metrics.

Every expected value here is computed by hand in the test, so the assertions
are independent of the implementation. That is the whole point: the module
these replaced returned 0.95 and "PASS" for any input at all.
"""

from __future__ import annotations

import pytest

from src.monitoring.fairness import (
    equal_opportunity_difference,
    fairness_report,
    selection_rates,
)

# --- selection rates -------------------------------------------------------


def test_selection_rates_are_computed_per_group():
    groups = ["a", "a", "a", "a", "b", "b", "b", "b"]
    selected = [True, True, False, False, True, False, False, False]

    rates = selection_rates(groups, selected)

    assert rates["a"].total == 4
    assert rates["a"].selected == 2
    assert rates["a"].selection_rate == 0.5
    assert rates["b"].selection_rate == 0.25


def test_selection_rates_reject_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        selection_rates(["a", "b"], [True])


def test_selection_rates_reject_empty_input():
    with pytest.raises(ValueError, match="empty outcome set"):
        selection_rates([], [])


def test_groups_are_returned_in_sorted_order():
    rates = selection_rates(["z", "a", "m"], [True, True, True])
    assert list(rates) == ["a", "m", "z"]


# --- demographic parity ----------------------------------------------------


def test_perfect_parity_is_reported_as_such():
    report = fairness_report(["a", "a", "b", "b"], [True, False, True, False])

    assert report.demographic_parity_difference == 0.0
    assert report.demographic_parity_ratio == 1.0
    assert report.passes_four_fifths_rule is True


def test_disparity_is_measured_not_assumed():
    # Group a: 2/4 = 0.5. Group b: 1/4 = 0.25. Difference 0.25, ratio 0.5.
    report = fairness_report(
        ["a", "a", "a", "a", "b", "b", "b", "b"],
        [True, True, False, False, True, False, False, False],
    )

    assert report.demographic_parity_difference == pytest.approx(0.25)
    assert report.demographic_parity_ratio == pytest.approx(0.5)
    assert report.passes_four_fifths_rule is False


def test_the_four_fifths_boundary_is_inclusive():
    # Group a: 5/5 = 1.0. Group b: 4/5 = 0.8. Ratio exactly 0.8 -> passes.
    report = fairness_report(
        ["a"] * 5 + ["b"] * 5,
        [True] * 5 + [True, True, True, True, False],
    )

    assert report.demographic_parity_ratio == pytest.approx(0.8)
    assert report.passes_four_fifths_rule is True


def test_just_below_the_four_fifths_boundary_fails():
    # Group a: 10/10 = 1.0. Group b: 7/10 = 0.7.
    report = fairness_report(
        ["a"] * 10 + ["b"] * 10,
        [True] * 10 + [True] * 7 + [False] * 3,
    )

    assert report.demographic_parity_ratio == pytest.approx(0.7)
    assert report.passes_four_fifths_rule is False


def test_selecting_nobody_is_not_reported_as_a_disparity():
    """A zero denominator must not masquerade as bias."""
    report = fairness_report(["a", "a", "b", "b"], [False, False, False, False])

    assert report.demographic_parity_difference == 0.0
    assert report.demographic_parity_ratio == 1.0
    assert report.passes_four_fifths_rule is True
    assert any("trivially" in note for note in report.notes)


def test_a_single_group_is_flagged_in_the_notes():
    report = fairness_report(["a", "a"], [True, False])
    assert any("Only one group" in note for note in report.notes)


def test_total_exclusion_of_one_group_is_the_worst_case():
    report = fairness_report(["a", "a", "b", "b"], [True, True, False, False])

    assert report.demographic_parity_difference == 1.0
    assert report.demographic_parity_ratio == 0.0
    assert report.passes_four_fifths_rule is False


# --- equal opportunity -----------------------------------------------------


def test_equal_opportunity_measures_qualified_candidates_only():
    groups = ["a", "a", "b", "b"]
    selected = [True, False, False, False]
    qualified = [True, True, True, True]

    # Qualified selection rate: a = 1/2 = 0.5, b = 0/2 = 0.0.
    difference, note = equal_opportunity_difference(groups, selected, qualified)

    assert difference == pytest.approx(0.5)
    assert note is None


def test_equal_opportunity_is_undefined_with_fewer_than_two_groups():
    difference, note = equal_opportunity_difference(
        ["a", "a", "b"], [True, False, True], [True, True, False]
    )

    assert difference is None
    assert note is not None
    assert "at least two groups" in note


def test_equal_opportunity_rejects_a_mismatched_label_length():
    with pytest.raises(ValueError, match="qualified must match groups"):
        equal_opportunity_difference(["a", "b"], [True, False], [True])


def test_report_omits_equal_opportunity_when_labels_are_absent():
    report = fairness_report(["a", "b"], [True, False])

    assert report.equal_opportunity_difference is None
    assert any("no qualification labels" in note for note in report.notes)


def test_report_includes_equal_opportunity_when_labels_are_supplied():
    report = fairness_report(
        ["a", "a", "b", "b"],
        [True, False, False, False],
        qualified=[True, True, True, True],
    )

    assert report.equal_opportunity_difference == pytest.approx(0.5)


def test_a_process_can_pass_parity_and_fail_equal_opportunity():
    """The two metrics answer different questions; the report must show both."""
    groups = ["a", "a", "a", "a", "b", "b", "b", "b"]
    selected = [True, True, False, False, True, True, False, False]
    # Both groups selected 2/4 -> parity is perfect.
    # But in group b the selected pair are the unqualified ones.
    qualified = [True, True, False, False, False, False, True, True]

    report = fairness_report(groups, selected, qualified)

    assert report.demographic_parity_difference == 0.0
    assert report.passes_four_fifths_rule is True
    assert report.equal_opportunity_difference == pytest.approx(1.0)


# --- report shape ----------------------------------------------------------


def test_report_lists_every_group():
    report = fairness_report(["a", "b", "c"], [True, False, True])
    assert [outcome.group for outcome in report.groups] == ["a", "b", "c"]


def test_report_rejects_empty_input():
    with pytest.raises(ValueError, match="empty outcome set"):
        fairness_report([], [])
