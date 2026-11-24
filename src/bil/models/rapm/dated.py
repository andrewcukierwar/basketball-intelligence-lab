"""Dated prior-centered RAPM with a strict as-of cutoff and exponential decay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from math import isfinite

from bil.evaluation.eligibility import played_before
from bil.models.rapm.reference import Possession, RAPMFit, fit_prior_rapm


@dataclass(frozen=True, slots=True)
class DatedRAPMFit:
    """A fit with the audit counts of the eligibility filter."""

    fit: RAPMFit
    as_of: date
    included: int
    excluded_same_or_later: int


def decay_multiplier(age_days: int, half_life_days: float | None) -> float:
    """Return 0.5 ** (age_days / half_life_days), or 1.0 without decay."""
    if half_life_days is None:
        return 1.0
    return float(0.5 ** (age_days / half_life_days))


def fit_dated_prior_rapm(
    possessions: Sequence[Possession],
    *,
    as_of: date,
    half_life_days: float | None,
    offense_ridge: float,
    defense_ridge: float,
    offense_prior: Mapping[int, float] | None = None,
    defense_prior: Mapping[int, float] | None = None,
) -> DatedRAPMFit:
    """Fit prior-centered RAPM using only possessions played strictly before ``as_of``.

    Dates are Eastern calendar dates. Age is ``(as_of - played_date).days`` and is at
    least 1 for every eligible row. Each row's weight is its supplied base weight times
    ``0.5 ** (age / half_life_days)``; ``None`` disables decay. Weights are not
    renormalized, so decay lowers the data weight relative to the unchanged penalties.
    Every row must carry a true ``date`` (a missing or ``datetime`` value raises, even
    for rows that would be excluded). Excluded rows contribute nothing: their players
    do not enter the fit universe and their weights are never computed.
    """
    if type(as_of) is not date:
        raise ValueError("as_of must be a calendar date")
    if half_life_days is not None and (not isfinite(half_life_days) or half_life_days <= 0):
        raise ValueError("half_life_days must be positive and finite, or None")
    eligible: list[Possession] = []
    for row, possession in enumerate(possessions):
        played = possession.played_date
        if type(played) is not date:
            raise ValueError(f"possession {row} requires a calendar played_date")
        if not played_before(played, as_of):
            continue
        multiplier = decay_multiplier((as_of - played).days, half_life_days)
        weight = possession.weight * multiplier
        if not isfinite(weight) or weight <= 0:
            raise ValueError(f"possession {row} decayed weight must be positive and finite")
        eligible.append(replace(possession, weight=weight))
    if not eligible:
        raise ValueError("no possessions were played before as_of")
    fit = fit_prior_rapm(
        eligible,
        offense_ridge=offense_ridge,
        defense_ridge=defense_ridge,
        offense_prior=offense_prior,
        defense_prior=defense_prior,
    )
    return DatedRAPMFit(fit, as_of, len(eligible), len(possessions) - len(eligible))
