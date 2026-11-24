"""Player-game skill histories, exposure denominators and baseline forecasters (issue #31).

Pure functions: no file access, no model targets, no EPM outputs. For player-game g with played date
t, the target is g's own observed numerator and denominator for each box feature, and every
predictor uses only appearances dated strictly before t (same-day games never see each other).
The rules are written up in docs/research/skill-histories.md.

Baselines are fixed, untuned reference forecasters. Fitting any decay or shrinkage belongs to #32.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from math import log
from typing import Literal

from bil.evaluation.eligibility import Revision
from bil.features.box import FEATURES, Appearance, Feature, strict_history

LAST_N = 10
HALF_LIVES_DAYS = (30, 90)
PLAYER_BASELINES = (
    "career_to_date",
    "season_to_date",
    f"last_{LAST_N}",
    *(f"decay_{h}d" for h in HALF_LIVES_DAYS),
)
LEAGUE_BASELINE = "league_to_date"
BASELINES = (*PLAYER_BASELINES, LEAGUE_BASELINE)
LOSS_EPSILON = 1e-3
TargetStatus = Literal["observed", "zero_exposure", "missing_component"]
HistoryStatus = Literal[
    "no_prior_history", "no_covered_history", "zero_exposure_history", "has_history"
]


def season_start_year(game_id: str) -> int:
    """NBA game IDs are `00T SS NNNNN`: characters 4-5 hold the two-digit season start year."""
    return 2000 + int(game_id[3:5])


def _ratio(numerator: float, denominator: float, scale: int) -> float | None:
    return numerator * scale / denominator if denominator > 0 else None


class _Rate:
    """Running ratio state for one player and statistic over earlier covered appearances."""

    __slots__ = ("count", "decayed", "denominator", "last_date", "numerator", "recent")

    def __init__(self) -> None:
        self.count = 0
        self.numerator = 0
        self.denominator = 0
        self.recent: deque[tuple[int, int]] = deque(maxlen=LAST_N)
        self.decayed = {h: [0.0, 0.0] for h in HALF_LIVES_DAYS}
        self.last_date: date | None = None

    def add(self, played: date, numerator: int, denominator: int) -> None:
        self.count += 1
        self.numerator += numerator
        self.denominator += denominator
        self.recent.append((numerator, denominator))
        for half_life, state in self.decayed.items():
            # Both sums decay by the same factor, so the ratio depends only on relative age.
            factor = 1.0
            if self.last_date is not None:
                factor = 0.5 ** ((played - self.last_date).days / half_life)
            state[0] = state[0] * factor + numerator
            state[1] = state[1] * factor + denominator
        self.last_date = played

    def last_n(self, scale: int) -> float | None:
        return _ratio(sum(n for n, _ in self.recent), sum(d for _, d in self.recent), scale)

    def decay(self, half_life: int, scale: int) -> float | None:
        numerator, denominator = self.decayed[half_life]
        return _ratio(numerator, denominator, scale) if self.denominator > 0 else None


class _History:
    def __init__(self) -> None:
        self.appearances = 0
        self.rates = {feature.code: _Rate() for feature in FEATURES}

    def add(self, row: Appearance) -> None:
        self.appearances += 1
        for feature in FEATURES:
            numerator, denominator = feature.numerator(row), feature.denominator(row)
            if numerator is not None and denominator is not None:
                self.rates[feature.code].add(row.game_date, numerator, denominator)


@dataclass(frozen=True)
class AppearanceOpportunity:
    """Feature-independent history evidence for one player-game."""

    row: Appearance
    season: int
    career_prior_appearances: int
    season_prior_appearances: int

    @property
    def history_status(self) -> str:
        return "no_prior_history" if self.career_prior_appearances == 0 else "has_prior_history"


@dataclass(frozen=True)
class SkillRow:
    """One (player-game, statistic): its realized target and strictly earlier baselines."""

    opportunity: AppearanceOpportunity
    feature: Feature
    target_numerator: int | None
    target_denominator: int | None
    target_status: TargetStatus
    history_status: HistoryStatus
    career_covered_games: int
    season_covered_games: int
    career_numerator: int
    career_denominator: int
    season_numerator: int
    season_denominator: int
    predictions: Mapping[str, float | None]

    @property
    def target_rate(self) -> float | None:
        if self.target_status != "observed":
            return None
        assert self.target_numerator is not None and self.target_denominator is not None
        return self.target_numerator * self.feature.scale / self.target_denominator

    @property
    def weight(self) -> float:
        """Exposure weight: attempts for fractions, 36-minute units for per-36 rates."""
        if self.target_status != "observed":
            return 0.0
        assert self.target_denominator is not None
        return self.target_denominator / self.feature.scale


def target_of(feature: Feature, row: Appearance) -> tuple[int | None, int | None, TargetStatus]:
    numerator, denominator = feature.numerator(row), feature.denominator(row)
    if numerator is None or denominator is None:
        return None, None, "missing_component"
    return numerator, denominator, "observed" if denominator > 0 else "zero_exposure"


def history_status(career: _Rate, appearances: int) -> HistoryStatus:
    if appearances == 0:
        return "no_prior_history"
    if career.count == 0:
        return "no_covered_history"
    if career.denominator == 0:
        return "zero_exposure_history"
    return "has_history"


def skill_rows(
    rows: Iterable[Appearance],
) -> Iterator[tuple[AppearanceOpportunity, list[SkillRow]]]:
    """Per appearance, in date order, its realized targets and baselines from earlier dates only.

    Appearances are processed one played date at a time: every row of a date is emitted from the
    state before any row of that date is added. Career history is per player and season type
    across seasons; season history additionally restricts to the target game's season. League
    history pools all players' earlier dates within the same season type and season.
    """
    by_date: dict[date, list[Appearance]] = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    career: dict[tuple[str, str], _History] = defaultdict(_History)
    season: dict[tuple[str, str, int], _History] = defaultdict(_History)
    league: dict[tuple[str, int], dict[str, list[int]]] = defaultdict(
        lambda: {feature.code: [0, 0] for feature in FEATURES}
    )
    for played in sorted(by_date):
        group = sorted(by_date[played], key=lambda r: (r.game_id, r.player_id))
        for row in group:
            year = season_start_year(row.game_id)
            ever = career[(row.player_id, row.season_type)]
            within = season[(row.player_id, row.season_type, year)]
            pool = league[(row.season_type, year)]
            opportunity = AppearanceOpportunity(row, year, ever.appearances, within.appearances)
            out: list[SkillRow] = []
            for feature in FEATURES:
                code, scale = feature.code, feature.scale
                rate, in_season = ever.rates[code], within.rates[code]
                numerator, denominator, status = target_of(feature, row)
                predictions: dict[str, float | None] = {
                    "career_to_date": _ratio(rate.numerator, rate.denominator, scale),
                    "season_to_date": _ratio(in_season.numerator, in_season.denominator, scale),
                    f"last_{LAST_N}": rate.last_n(scale),
                    **{f"decay_{h}d": rate.decay(h, scale) for h in HALF_LIVES_DAYS},
                    LEAGUE_BASELINE: _ratio(pool[code][0], pool[code][1], scale),
                }
                out.append(
                    SkillRow(
                        opportunity,
                        feature,
                        numerator,
                        denominator,
                        status,
                        history_status(rate, ever.appearances),
                        rate.count,
                        in_season.count,
                        rate.numerator,
                        rate.denominator,
                        in_season.numerator,
                        in_season.denominator,
                        predictions,
                    )
                )
            yield opportunity, out
        for row in group:
            year = season_start_year(row.game_id)
            career[(row.player_id, row.season_type)].add(row)
            season[(row.player_id, row.season_type, year)].add(row)
            pool = league[(row.season_type, year)]
            for feature in FEATURES:
                numerator, denominator = feature.numerator(row), feature.denominator(row)
                if numerator is not None and denominator is not None:
                    pool[feature.code][0] += numerator
                    pool[feature.code][1] += denominator


def strict_prior_counts(
    rows: Iterable[Appearance], revisions: Mapping[str, Revision]
) -> dict[str, int]:
    """Per appearance key, earlier same-type appearances usable under the strict resolver.

    Uses the evaluation resolver at each (played date, season type) cutoff, so unknown or late
    availability, missing finalization, retractions and same-day games all remove history.
    """
    materialized = list(rows)
    cutoffs: dict[tuple[date, str], dict[str, int]] = {}
    for row in materialized:
        key = (row.game_date, row.season_type)
        if key not in cutoffs:
            usable, _ = strict_history(materialized, revisions, row.game_date, [row.season_type])
            per_player: dict[str, int] = defaultdict(int)
            for earlier in usable:
                per_player[earlier.player_id] += 1
            cutoffs[key] = per_player
    return {r.key: cutoffs[(r.game_date, r.season_type)].get(r.player_id, 0) for r in materialized}


def loss_terms(feature: Feature, numerator: int, denominator: int, prediction: float) -> float:
    """Negative log-likelihood of the realized counts under a rate prediction.

    Fractions use a binomial likelihood over attempts. Per-36 rates use a Poisson likelihood over
    exposure in 36-minute units, without the constant log(n!) term. Predictions are clipped to
    [LOSS_EPSILON, 1 - LOSS_EPSILON] for fractions and at LOSS_EPSILON for per-36 rates, so a
    zero-history rate is penalised finitely.
    """
    if feature.scale == 1:
        p = min(max(prediction, LOSS_EPSILON), 1 - LOSS_EPSILON)
        return -(numerator * log(p) + (denominator - numerator) * log(1 - p))
    mean = max(prediction, LOSS_EPSILON) * denominator / feature.scale
    return mean - numerator * log(mean)


LOSS_KIND = {1: "binomial_nll_per_attempt", 2_160_000: "poisson_nll_per_36_minutes"}


def history_bucket(covered_games: int) -> str:
    if covered_games < 5:
        return "1-4"
    return "5-19" if covered_games < 20 else "20+"


class Scorer:
    """Exposure-weighted error accumulator, fed in chronological order.

    Sets: `common` scores every baseline on rows where all six baselines predict, so the numbers
    are comparable; `cold` scores the league baseline on rows with no covered player history.
    Dimensions: `all`, calendar `month` of the played date, and covered-game `history_games`.
    """

    def __init__(self) -> None:
        self.cells: dict[tuple[str, str, str, str, str, str], list[float]] = defaultdict(
            lambda: [0.0, 0.0, 0.0, 0.0]
        )
        self.last_date: date | None = None

    def add(self, rows: Iterable[SkillRow]) -> None:
        for sk in rows:
            played = sk.opportunity.row.game_date
            if self.last_date is not None and played < self.last_date:
                raise ValueError("Scorer requires chronological input")
            self.last_date = played
            rate = sk.target_rate
            if rate is None:
                continue
            assert sk.target_numerator is not None and sk.target_denominator is not None
            kind = sk.opportunity.row.season_type
            code = sk.feature.code
            preds = sk.predictions
            if all(preds[b] is not None for b in BASELINES):
                scored = BASELINES
                cohort = "common"
                dims: tuple[tuple[str, str], ...] = (
                    ("all", "all"),
                    ("month", f"{played:%Y-%m}"),
                    ("history_games", history_bucket(sk.career_covered_games)),
                )
            elif sk.career_covered_games == 0 and preds[LEAGUE_BASELINE] is not None:
                scored = (LEAGUE_BASELINE,)
                cohort = "cold"
                dims = (("all", "all"), ("month", f"{played:%Y-%m}"))
            else:
                continue
            for baseline in scored:
                prediction = preds[baseline]
                assert prediction is not None
                squared = (prediction - rate) ** 2
                nll = loss_terms(sk.feature, sk.target_numerator, sk.target_denominator, prediction)
                for dim, value in dims:
                    cell = self.cells[(kind, cohort, dim, value, code, baseline)]
                    cell[0] += 1
                    cell[1] += sk.weight
                    cell[2] += sk.weight * squared
                    cell[3] += nll

    def table(self) -> list[dict[str, object]]:
        result = []
        for (kind, cohort, dim, value, code, baseline), (n, weight, wse, nll) in sorted(
            self.cells.items()
        ):
            scale = next(f.scale for f in FEATURES if f.code == code)
            result.append(
                {
                    "season_type": kind,
                    "cohort_set": cohort,
                    "dim": dim,
                    "dim_value": value,
                    "feature_code": code,
                    "baseline": baseline,
                    "rows": int(n),
                    "weight_sum": weight,
                    "weighted_mse": wse / weight,
                    "log_loss": nll / weight,
                    "log_loss_kind": LOSS_KIND[1 if scale == 1 else 2_160_000],
                }
            )
        return result
