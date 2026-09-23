"""Selection-fairness metrics.

Every number here is computed from the outcomes passed in. Nothing is
defaulted or assumed — a fairness figure that was not measured is worse than
no figure at all, because it invites reliance it cannot support. Where a metric
is undefined for the given data this returns ``None`` and says why, rather than
substituting a plausible-looking value.

Group membership is always supplied by the caller. This module never infers a
protected attribute from a name, a school or a location.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

FOUR_FIFTHS = 0.8


class GroupOutcome(BaseModel):
    """Selection outcome for one group."""

    group: str
    total: int = Field(..., ge=0)
    selected: int = Field(..., ge=0)
    selection_rate: float = Field(..., ge=0.0, le=1.0)


class FairnessReport(BaseModel):
    """Measured selection fairness across groups.

    Attributes:
        groups: Per-group totals and selection rates, ordered by group name.
        demographic_parity_difference: Highest minus lowest selection rate.
            0.0 means every group was selected at the same rate.
        demographic_parity_ratio: Lowest rate divided by the highest.
        passes_four_fifths_rule: Whether the ratio reaches 0.8, the threshold
            in the US EEOC Uniform Guidelines. A rule of thumb for flagging
            disparity, not a legal verdict.
        equal_opportunity_difference: Spread in selection rate among
            *qualified* candidates only. None when qualification labels were
            not supplied, or when fewer than two groups contain a qualified
            candidate.
        notes: Plain-language statements about what could not be computed.
    """

    groups: list[GroupOutcome]
    demographic_parity_difference: float = Field(..., ge=0.0, le=1.0)
    demographic_parity_ratio: float = Field(..., ge=0.0, le=1.0)
    passes_four_fifths_rule: bool
    equal_opportunity_difference: float | None = None
    notes: list[str] = Field(default_factory=list)


def _validate(groups: Sequence[str], selected: Sequence[bool]) -> None:
    if len(groups) != len(selected):
        raise ValueError(
            f"groups and selected must be the same length, got {len(groups)} and {len(selected)}"
        )
    if not groups:
        raise ValueError("Cannot measure fairness over an empty outcome set")


def selection_rates(groups: Sequence[str], selected: Sequence[bool]) -> dict[str, GroupOutcome]:
    """Compute the selection rate for each group.

    Args:
        groups: Group label per candidate, supplied by the caller.
        selected: Whether each candidate was selected.

    Returns:
        A mapping of group name to its outcome, keys sorted.

    Raises:
        ValueError: If the sequences differ in length or are empty.
    """
    _validate(groups, selected)

    totals: dict[str, int] = {}
    hits: dict[str, int] = {}
    for group, was_selected in zip(groups, selected, strict=True):
        totals[group] = totals.get(group, 0) + 1
        hits[group] = hits.get(group, 0) + int(bool(was_selected))

    return {
        group: GroupOutcome(
            group=group,
            total=totals[group],
            selected=hits[group],
            selection_rate=hits[group] / totals[group],
        )
        for group in sorted(totals)
    }


def equal_opportunity_difference(
    groups: Sequence[str],
    selected: Sequence[bool],
    qualified: Sequence[bool],
) -> tuple[float | None, str | None]:
    """Spread in selection rate among qualified candidates only.

    Demographic parity asks whether groups are selected at equal rates. Equal
    opportunity asks the narrower question: among people who *should* be
    selected, are groups selected at equal rates? A process can satisfy one and
    fail the other.

    Returns:
        A ``(difference, note)`` pair. ``difference`` is None when the metric
        is undefined, in which case ``note`` explains why.

    Raises:
        ValueError: If the sequences differ in length or are empty.
    """
    _validate(groups, selected)
    if len(qualified) != len(groups):
        raise ValueError(
            f"qualified must match groups in length, got {len(qualified)} and {len(groups)}"
        )

    qualified_totals: dict[str, int] = {}
    qualified_hits: dict[str, int] = {}
    for group, was_selected, is_qualified in zip(groups, selected, qualified, strict=True):
        if not is_qualified:
            continue
        qualified_totals[group] = qualified_totals.get(group, 0) + 1
        qualified_hits[group] = qualified_hits.get(group, 0) + int(bool(was_selected))

    if len(qualified_totals) < 2:
        return None, (
            "Equal opportunity needs qualified candidates in at least two groups; "
            f"found {len(qualified_totals)}."
        )

    rates = [qualified_hits[g] / qualified_totals[g] for g in qualified_totals]
    return max(rates) - min(rates), None


def fairness_report(
    groups: Sequence[str],
    selected: Sequence[bool],
    qualified: Sequence[bool] | None = None,
) -> FairnessReport:
    """Measure selection fairness across groups.

    Args:
        groups: Group label per candidate.
        selected: Whether each candidate was selected.
        qualified: Optional ground-truth qualification label per candidate.
            Supplying it adds the equal-opportunity metric.

    Returns:
        The measured report.

    Raises:
        ValueError: If the sequences differ in length or are empty.
    """
    outcomes = selection_rates(groups, selected)
    rates = [outcome.selection_rate for outcome in outcomes.values()]
    highest, lowest = max(rates), min(rates)

    notes: list[str] = []
    if highest == 0.0:
        # Nobody was selected in any group. There is no disparity to measure,
        # and a "failed" ratio here would be an artefact of dividing by zero.
        difference, ratio, passes = 0.0, 1.0, True
        notes.append("No candidate was selected in any group; parity holds trivially.")
    else:
        difference = highest - lowest
        ratio = lowest / highest
        passes = ratio >= FOUR_FIFTHS

    if len(outcomes) < 2:
        notes.append("Only one group is present; parity metrics compare a group against itself.")

    equal_opportunity: float | None = None
    if qualified is None:
        notes.append("Equal opportunity not computed: no qualification labels supplied.")
    else:
        equal_opportunity, note = equal_opportunity_difference(groups, selected, qualified)
        if note:
            notes.append(note)

    return FairnessReport(
        groups=list(outcomes.values()),
        demographic_parity_difference=difference,
        demographic_parity_ratio=ratio,
        passes_four_fifths_rule=passes,
        equal_opportunity_difference=equal_opportunity,
        notes=notes,
    )
