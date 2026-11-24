"""Pregame context inputs and the additive/multiplicative skill adjustment (issue #33).

Pure functions: no file access, no EPM outputs. The frozen protocol is
docs/research/skill-context-protocol.md. Every input for a target on played date `t` uses schedule
facts of the game itself (home flag, team game dates) and box evidence from games dated strictly
before `t`. Each input array has a companion "latest source date" so the cutoff can be audited.

The adjustment moves a frozen #32 base prediction `b` on the link scale:

    eta = link(b) + beta_0 + sum_j beta_j z_j,    prediction = link^-1(eta)

with `link = log` for per-36 rates (a multiplicative adjustment) and `logit` for fractions.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize  # type: ignore[import-untyped]

from bil.features.box import FEATURES, Appearance, Feature
from bil.features.skill_history import LOSS_EPSILON

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

OPP_K_TEAM_GAMES = 10.0
TREND_WINDOW_DAYS = 28
REST_CAP = 4
UNKNOWN_REST_DAYS = 1
RIDGE = 1e-3
FACTORS = ("trend", "home", "rest", "opp", "team")
FACTOR_COLUMNS: dict[str, tuple[str, ...]] = {
    "trend": ("trend",),
    "home": ("home",),
    "rest": ("b2b", "rest_days"),
    "opp": ("opp",),
    "team": ("team",),
}
VARIANTS: dict[str, tuple[str, ...]] = {
    "agnostic": (),
    "recal": (),
    **{f"add_{f}": (f,) for f in FACTORS},
    "full": FACTORS,
    **{f"drop_{f}": tuple(g for g in FACTORS if g != f) for f in FACTORS},
}
REFERENCES: dict[str, tuple[str, ...]] = {
    "recal": ("agnostic",),
    **{f"add_{f}": ("agnostic", "recal") for f in FACTORS},
    "full": ("agnostic", "recal"),
    **{f"drop_{f}": ("agnostic", "full") for f in FACTORS},
}
MISSING_INPUTS = (
    "birthdates (aging)",
    "pregame injury and availability reports",
    "announced starters",
    "expected minutes or a minutes model",
    "opponent rosters and opponent rest",
    "travel and time-zone distance",
    "betting lines",
    "independently timestamped pregame roster feed",
)


@dataclass(frozen=True)
class TeamGame:
    """One team's side of a scheduled game (known before tip-off)."""

    game_id: str
    team_id: str
    opp_team_id: str
    game_date: date
    home: bool


@dataclass(frozen=True)
class Schedule:
    home: bool
    b2b: bool
    rest_days: int
    rest_known: bool
    previous_game: date | None


def schedule_inputs(team_games: Sequence[TeamGame]) -> dict[tuple[str, str], Schedule]:
    """Home flag, back-to-back and rest days per (game_id, team_id) from the schedule alone.

    Rest uses only the team's earlier game dates (any season type). The first game of a team has
    unknown rest, which takes `b2b = False` and `rest_days = UNKNOWN_REST_DAYS`.
    """
    by_team: dict[str, list[TeamGame]] = defaultdict(list)
    for game in team_games:
        by_team[game.team_id].append(game)
    result: dict[tuple[str, str], Schedule] = {}
    for games in by_team.values():
        ordered = sorted(games, key=lambda g: (g.game_date, g.game_id))
        previous: date | None = None
        for game in ordered:
            if previous is not None and game.game_date <= previous:
                raise ValueError(f"Team {game.team_id} has two games on {game.game_date}")
            if previous is None:
                known, b2b, rest = False, False, UNKNOWN_REST_DAYS
            else:
                days = (game.game_date - previous).days
                known, b2b, rest = True, days == 1, min(days - 1, REST_CAP)
            result[(game.game_id, game.team_id)] = Schedule(game.home, b2b, rest, known, previous)
            previous = game.game_date
    return result


def link_values(feature: Feature, rate: FloatArray) -> FloatArray:
    """log for per-36 rates, logit for fractions, with the #31 clipping floor."""
    if feature.scale == 1:
        p = np.clip(rate, LOSS_EPSILON, 1 - LOSS_EPSILON)
        return np.asarray(np.log(p) - np.log1p(-p))
    return np.asarray(np.log(np.maximum(rate, LOSS_EPSILON)))


def inverse_link(feature: Feature, eta: FloatArray) -> FloatArray:
    if feature.scale == 1:
        return np.asarray(1.0 / (1.0 + np.exp(-eta)))
    return np.asarray(np.exp(eta))


@dataclass
class ContextInputs:
    """Context arrays aligned to a list of appearance keys."""

    keys: tuple[str, ...]
    home: FloatArray
    b2b: FloatArray
    rest_days: FloatArray
    rest_known: np.ndarray[Any, np.dtype[np.bool_]]
    schedule_source: IntArray  # ordinal of the team's previous game, 0 if none
    league_source: IntArray  # ordinal of the latest league date used, 0 if none
    opp_source: IntArray
    team_source: IntArray
    played: IntArray  # ordinal of the target date
    trend: dict[str, FloatArray] = field(default_factory=dict)
    opp: dict[str, FloatArray] = field(default_factory=dict)
    team: dict[str, FloatArray] = field(default_factory=dict)
    defaults: dict[str, int] = field(default_factory=dict)

    def latest_source(self) -> IntArray:
        stacked = np.stack(
            [self.schedule_source, self.league_source, self.opp_source, self.team_source]
        )
        return np.asarray(stacked.max(axis=0), dtype=np.int64)

    def cutoff_violations(self) -> int:
        """Rows whose latest source date is not strictly before the target date."""
        return int((self.latest_source() >= self.played).sum())


def _production(rows: Sequence[Appearance]) -> dict[tuple[str, str], FloatArray]:
    """Per (game, team) summed covered numerator and exposure, shape (2, features)."""
    out: dict[tuple[str, str], FloatArray] = {}
    for row in rows:
        total = out.setdefault((row.game_id, row.team_id), np.zeros((2, len(FEATURES))))
        for f, feature in enumerate(FEATURES):
            numerator, denominator = feature.numerator(row), feature.denominator(row)
            if numerator is not None and denominator is not None:
                total[0, f] += numerator
                total[1, f] += denominator / feature.scale
    return out


def _cumulative(values: list[FloatArray]) -> FloatArray:
    """(n + 1, 2, features) running totals with a leading zero row."""
    stack = np.zeros((len(values) + 1, 2, len(FEATURES)))
    if values:
        stack[1:] = np.cumsum(np.stack(values), axis=0)
    return stack


def build_context(
    rows: Sequence[Appearance], team_games: Sequence[TeamGame], keys: Sequence[str]
) -> ContextInputs:
    """Context inputs for the appearances `keys` from schedule facts and strictly earlier games."""
    schedule = schedule_inputs(team_games)
    by_key = {r.key: r for r in rows}
    target = [by_key[k] for k in keys]
    n = len(target)
    produced = _production(rows)
    zero = np.zeros((2, len(FEATURES)))
    # Per-team own and allowed production in schedule order.
    own_dates: dict[str, list[int]] = defaultdict(list)
    own_cum_src: dict[str, list[FloatArray]] = defaultdict(list)
    allowed_cum_src: dict[str, list[FloatArray]] = defaultdict(list)
    for game in sorted(team_games, key=lambda g: (g.game_date, g.game_id, g.team_id)):
        own_dates[game.team_id].append(game.game_date.toordinal())
        own_cum_src[game.team_id].append(produced.get((game.game_id, game.team_id), zero))
        allowed_cum_src[game.team_id].append(produced.get((game.game_id, game.opp_team_id), zero))
    own_cum = {t: _cumulative(v) for t, v in own_cum_src.items()}
    allowed_cum = {t: _cumulative(v) for t, v in allowed_cum_src.items()}
    dates_by_team = {t: np.array(v, dtype=np.int64) for t, v in own_dates.items()}
    # League totals by played date over every appearance (pooled season types).
    daily: dict[int, FloatArray] = defaultdict(lambda: np.zeros((2, len(FEATURES))))
    team_date = {(g.game_id, g.team_id): g.game_date.toordinal() for g in team_games}
    games_per_day: dict[int, int] = defaultdict(int)
    for (game_id, team_id), value in produced.items():
        day = team_date[(game_id, team_id)]
        daily[day] = daily[day] + value
        games_per_day[day] += 1
    league_days = np.array(sorted(daily), dtype=np.int64)
    league_cum = _cumulative([daily[int(d)] for d in league_days])
    played = np.array([r.game_date.toordinal() for r in target], dtype=np.int64)
    after = np.searchsorted(league_days, played, side="left")
    recent_start = np.searchsorted(league_days, played - TREND_WINDOW_DAYS, side="left")
    league_total = league_cum[after]  # (n, 2, features)
    league_recent = league_total - league_cum[recent_start]
    team_total = np.zeros((n, 2, len(FEATURES)))
    opp_total = np.zeros((n, 2, len(FEATURES)))
    team_source = np.zeros(n, dtype=np.int64)
    opp_source = np.zeros(n, dtype=np.int64)
    team_ids = np.array([r.team_id for r in target])
    opp_ids = np.array([r.opp_team_id for r in target])
    for team in np.unique(team_ids):
        select = np.flatnonzero(team_ids == team)
        dates = dates_by_team.get(str(team), np.zeros(0, dtype=np.int64))
        idx = np.searchsorted(dates, played[select], side="left")
        team_total[select] = own_cum.get(str(team), _cumulative([]))[idx]
        team_source[select] = np.where(
            idx > 0, dates[np.maximum(idx - 1, 0)] if dates.size else 0, 0
        )
    for team in np.unique(opp_ids):
        select = np.flatnonzero(opp_ids == team)
        dates = dates_by_team.get(str(team), np.zeros(0, dtype=np.int64))
        idx = np.searchsorted(dates, played[select], side="left")
        opp_total[select] = allowed_cum.get(str(team), _cumulative([]))[idx]
        opp_source[select] = np.where(
            idx > 0, dates[np.maximum(idx - 1, 0)] if dates.size else 0, 0
        )
    league_source = np.where(after > 0, league_days[np.maximum(after - 1, 0)], 0).astype(np.int64)
    sched = [schedule[(r.game_id, r.team_id)] for r in target]
    inputs = ContextInputs(
        tuple(keys),
        np.array([1.0 if s.home else 0.0 for s in sched]),
        np.array([1.0 if s.b2b else 0.0 for s in sched]),
        np.array([float(s.rest_days) for s in sched]),
        np.array([s.rest_known for s in sched]),
        np.array([s.previous_game.toordinal() if s.previous_game else 0 for s in sched], np.int64),
        league_source,
        opp_source,
        team_source,
        played,
    )
    team_games_before = np.cumsum([0, *(games_per_day[int(d)] for d in league_days)])[after]
    with np.errstate(divide="ignore", invalid="ignore"):
        for f, feature in enumerate(FEATURES):
            code = feature.code
            league_d = league_total[:, 1, f]
            m = np.where(league_d > 0, league_total[:, 0, f] / league_d, np.nan)
            known = (league_d > 0) & (team_games_before > 0)
            k = OPP_K_TEAM_GAMES * league_d / np.maximum(team_games_before, 1)
            link_m = link_values(feature, np.nan_to_num(m))
            for name, total in (("opp", opp_total), ("team", team_total)):
                a = (total[:, 0, f] + k * np.nan_to_num(m)) / (total[:, 1, f] + k)
                value = np.where(known, link_values(feature, np.nan_to_num(a)) - link_m, 0.0)
                getattr(inputs, name)[code] = value
                inputs.defaults[f"{name}:{code}"] = int((~known).sum())
            recent_d = league_recent[:, 1, f]
            r = np.where(recent_d > 0, league_recent[:, 0, f] / recent_d, np.nan)
            ok = known & (recent_d > 0)
            inputs.trend[code] = np.where(ok, link_values(feature, np.nan_to_num(r)) - link_m, 0.0)
            inputs.defaults[f"trend:{code}"] = int((~ok).sum())
    inputs.defaults["rest_unknown_rows"] = int((~inputs.rest_known).sum())
    return inputs


def input_columns(inputs: ContextInputs, code: str) -> dict[str, FloatArray]:
    return {
        "trend": inputs.trend[code],
        "home": inputs.home,
        "b2b": inputs.b2b,
        "rest_days": inputs.rest_days,
        "opp": inputs.opp[code],
        "team": inputs.team[code],
    }


@dataclass(frozen=True)
class Adjustment:
    terms: tuple[str, ...]
    beta0: float
    beta: tuple[float, ...]
    mean: tuple[float, ...]
    std: tuple[float, ...]
    rows: int
    nfev: int
    success: bool

    def eta(
        self, offset: FloatArray, columns: Mapping[str, FloatArray], rows: IntArray
    ) -> FloatArray:
        total = offset + self.beta0
        for name, b, mu, sd in zip(self.terms, self.beta, self.mean, self.std, strict=True):
            total = total + b * (columns[name][rows] - mu) / sd
        return np.asarray(total)


def fit_adjustment(
    feature: Feature,
    terms: Sequence[str],
    columns: Mapping[str, FloatArray],
    rows: IntArray,
    offset: FloatArray,
    numerator: FloatArray,
    exposure: FloatArray,
    ridge: float = RIDGE,
) -> Adjustment:
    """Penalized maximum likelihood on `rows` (offset = link of the frozen base prediction).

    `numerator` and `exposure` are the targets' counts and weight-unit exposures for `rows`.
    Columns with no spread are dropped. The intercept is not penalized.
    """
    kept: list[str] = []
    means: list[float] = []
    stds: list[float] = []
    cols: list[FloatArray] = []
    for name in terms:
        values = columns[name][rows]
        sd = float(values.std())
        if sd > 1e-12:
            kept.append(name)
            means.append(float(values.mean()))
            stds.append(sd)
            cols.append((values - values.mean()) / sd)
    z = np.column_stack([np.ones(rows.size), *cols]) if cols else np.ones((rows.size, 1))
    total = float(exposure.sum())
    poisson = feature.scale != 1

    def objective(theta: FloatArray) -> tuple[float, FloatArray]:
        eta = offset + z @ theta
        if poisson:
            mean = exposure * np.exp(eta)
            loss = float((mean - numerator * np.log(np.maximum(mean, 1e-300))).sum())
            resid = mean - numerator
        else:
            p = 1.0 / (1.0 + np.exp(-eta))
            loss = float((exposure * np.logaddexp(0.0, eta) - numerator * eta).sum())
            resid = exposure * p - numerator
        penalty = 0.5 * ridge * float((theta[1:] ** 2).sum())
        grad = z.T @ resid / total
        grad[1:] += ridge * theta[1:]
        return loss / total + penalty, grad

    result = minimize(
        objective,
        np.zeros(z.shape[1]),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": 200, "ftol": 1e-12},
    )
    theta = np.asarray(result.x, dtype=np.float64)
    return Adjustment(
        tuple(kept),
        float(theta[0]),
        tuple(float(v) for v in theta[1:]),
        tuple(means),
        tuple(stds),
        int(rows.size),
        int(result.nfev),
        bool(result.success),
    )
