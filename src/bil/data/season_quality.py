"""Season-level M1 quality classification and missingness diagnostics for built pilot seasons.

This reads only the exported tables of a build and the pinned box log of its snapshot. It does
not run the reconstruction, fit a model or touch any other season. It applies the revised M1
policy of ADR-0022 (hard limits, targets, warnings) and asks whether the games and possessions
the pipeline did not keep are missing at random or in a pattern.

Everything is deterministic. Tests use permutations and bootstraps with seeds derived from the
season, season type and dimension, so a rerun with the same inputs gives byte-identical output.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

SEASON_TYPES = ("regular", "playoffs")
# Hard limits: unchanged from the original M1 table, and never relaxed by ADR-0022.
GAME_COVERAGE_FLOOR = 0.97
UNRESOLVED_SEASON_LIMIT = 0.001
# A target, not a gate, under ADR-0022.
STRATUM_COVERAGE_TARGET = 0.95
M1_STRATA = ("overtime", "technical_free_throw", "same_clock_free_throw_substitution")
# The strata that carry weaker verification than the full-evidence builds.
WEAK_STRATA = ("no_livedata", "v2_home_designation")

# Documented flag rule, applied to every dimension:
#   systematic: permutation (quarantines) or Bonferroni-adjusted bootstrap (unresolved) at 1%
#               and the most affected cell at least twice its expected rate with 5 or more events
#   watch:      evidence at the 5% level only
SYSTEMATIC_ALPHA = 0.01
WATCH_ALPHA = 0.05
MIN_LIFT = 2.0
MIN_CELL_EVENTS = 5
DIMENSIONS = ("all", "month", "offense_team", "period", "margin")
BOOTSTRAP_CHUNK = 2000
MIN_TESTABLE_QUARANTINES = 5
MIN_PLAYER_MINUTES = 500.0
MARGIN_EDGES = (5, 10, 20)  # score margin bands: 0-5, 6-10, 11-20, 21+
PERIOD_LABELS = {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}


def margin_band(margin: int) -> str:
    """Band an absolute score margin as 0-5, 6-10, 11-20 or 21+."""
    low = 0
    for edge in MARGIN_EDGES:
        if margin <= edge:
            return f"{low}-{edge}"
        low = edge + 1
    return f"{low}+"


def period_label(period: int) -> str:
    return PERIOD_LABELS.get(period, "OT")


@dataclass(frozen=True)
class Games:
    """One row per expected game in a build, with the box log attached."""

    game_id: list[str]
    season_type: list[str]
    month: list[str]
    home: list[str]
    away: list[str]
    margin: npt.NDArray[np.int64]
    accepted: npt.NDArray[np.bool_]
    reason: list[str]
    strata: list[frozenset[str]]
    minutes: FloatArray
    est_possessions: FloatArray

    def __len__(self) -> int:
        return len(self.game_id)


@dataclass(frozen=True)
class Season:
    """A loaded season: game rows, per-player box minutes, and unresolved-possession counts."""

    year: int
    label: str
    build: Path
    games: Games
    player_ids: list[str]
    player_minutes: FloatArray  # players by games, box minutes
    possession_cells: list[dict[str, Any]]  # per game, dimension and cell: possessions, unresolved
    status_counts: dict[str, dict[str, int]]  # season type -> status -> possessions
    exposure: list[tuple[str, str, bool, int, int]]  # game, player, overtime, possessions, ms


def season_label(year: int) -> str:
    return f"{year}-{(year + 1) % 100:02d}"


def _literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def load_season(build: Path, snapshot: Path | None) -> Season:
    """Read one build, and its snapshot's box log when given, into numpy-friendly rows."""
    manifest = json.loads((build / "manifest.json").read_text(encoding="utf-8"))
    year = manifest["season_start_year"]
    if type(year) is not int:
        raise ValueError("Manifest does not record an integer season start year")
    with duckdb.connect() as con:
        for table in (
            "game",
            "game_review",
            "possession",
            "event",
            "stint",
            "lineup",
        ):
            con.execute(
                f"create view {table} as select * from read_parquet("
                f"{_literal(build / (table + '.parquet'))})"
            )
        if snapshot is not None:
            con.execute(
                "create view box as select lpad(cast(game_id as varchar), 10, '0') as game_id,"
                " cast(player_id as varchar) as player_id, cast(team_id as varchar) as team_id,"
                ' coalesce("min", 0) as minutes, coalesce(fga, 0) as fga,'
                " coalesce(fta, 0) as fta, coalesce(oreb, 0) as oreb, coalesce(tov, 0) as tov"
                f" from read_parquet({_literal(snapshot / 'player_game_logs.parquet')})"
            )
        else:
            con.execute(
                "create view box as select cast(null as varchar) as game_id,"
                " cast(null as varchar) as player_id, cast(null as varchar) as team_id,"
                " 0.0 as minutes, 0 as fga, 0 as fta, 0 as oreb, 0 as tov where false"
            )
        rows = con.execute(
            """
            with b as (
              select game_id, sum(minutes) as minutes,
                     sum(fga + 0.44 * fta - oreb + tov) / 2.0 as est_possessions
              from box group by 1)
            select g.game_id, g.season_type, strftime(g.game_date, '%Y-%m'), g.home_team_id,
                   g.away_team_id, abs(g.home_final - g.away_final), r.accepted,
                   coalesce(r.reason, ''), r.strata, coalesce(b.minutes, 0.0),
                   coalesce(b.est_possessions, 0.0)
            from game g join game_review r using (game_id) left join b using (game_id)
            order by g.game_id
            """
        ).fetchall()
        games = Games(
            game_id=[r[0] for r in rows],
            season_type=[r[1] for r in rows],
            month=[r[2] for r in rows],
            home=[r[3] for r in rows],
            away=[r[4] for r in rows],
            margin=np.array([r[5] for r in rows], dtype=np.int64),
            accepted=np.array([bool(r[6]) for r in rows], dtype=np.bool_),
            reason=[r[7] for r in rows],
            strata=[frozenset(r[8] or ()) for r in rows],
            minutes=np.array([r[9] for r in rows], dtype=np.float64),
            est_possessions=np.array([r[10] for r in rows], dtype=np.float64),
        )
        index = {game_id: i for i, game_id in enumerate(games.game_id)}
        box_rows = con.execute(
            "select game_id, player_id, sum(minutes) from box group by all"
        ).fetchall()
        players = sorted({r[1] for r in box_rows})
        position = {player: i for i, player in enumerate(players)}
        player_minutes = np.zeros((len(players), len(games)), dtype=np.float64)
        for game_id, player_id, minutes in box_rows:
            if game_id in index:
                player_minutes[position[player_id], index[game_id]] += minutes
        cells = [
            {
                "game_id": r[0],
                "dimension": r[1],
                "cell": r[2],
                "possessions": r[3],
                "unresolved": r[4],
                "accepted": r[5],
            }
            for r in con.execute(_POSSESSION_CELLS_SQL).fetchall()
        ]
        status_rows = con.execute(
            """
            select g.season_type, p.status, count(*) from possession p
            join game g using (game_id) group by all
            """
        ).fetchall()
        status_counts: dict[str, dict[str, int]] = {t: {} for t in SEASON_TYPES}
        for season_type, status, count in status_rows:
            status_counts.setdefault(season_type, {})[status] = int(count)
        exposure = [
            (r[0], r[1], bool(r[2]), int(r[3]), int(r[4]))
            for r in con.execute(_EXPOSURE_SQL).fetchall()
        ]
    return Season(
        year=year,
        label=season_label(year),
        build=build,
        games=games,
        player_ids=players,
        player_minutes=player_minutes,
        possession_cells=cells,
        status_counts=status_counts,
        exposure=exposure,
    )


# Score margin before a possession is the running score difference of all earlier events.
_POSSESSION_CELLS_SQL = f"""
    with running as (
      select game_id, stream_revision, seq,
             abs(sum(home_delta - away_delta) over (
               partition by game_id, stream_revision order by seq)) as margin
      from event),
    base as (
      select p.game_id, p.status, p.period, p.offense_team_id, strftime(g.game_date, '%Y-%m') as month,
             coalesce(r.margin, 0) as margin
      from possession p join game g using (game_id)
      asof left join running r
        on p.game_id = r.game_id and p.stream_revision = r.stream_revision and p.start_seq > r.seq),
    cells as (
      select game_id, 'month' as dimension, month as cell, status from base
      union all select game_id, 'offense_team', offense_team_id, status from base
      union all select game_id, 'period',
        case when period <= 4 then 'Q' || cast(period as varchar) else 'OT' end, status from base
      union all select game_id, 'margin',
        case when margin <= {MARGIN_EDGES[0]} then '0-{MARGIN_EDGES[0]}'
             when margin <= {MARGIN_EDGES[1]} then '{MARGIN_EDGES[0] + 1}-{MARGIN_EDGES[1]}'
             when margin <= {MARGIN_EDGES[2]} then '{MARGIN_EDGES[1] + 1}-{MARGIN_EDGES[2]}'
             else '{MARGIN_EDGES[2] + 1}+' end, status from base
      union all select game_id, 'all', 'all', status from base)
    select game_id, dimension, cell, count(*), count(*) filter (where status = 'unresolved'),
           count(*) filter (where status = 'accepted')
    from cells group by all order by all
"""

# Possessions that count (status accepted) and on-court time, per player, game and regulation or
# overtime. A player is on court for a possession when in either lineup at its start.
_EXPOSURE_SQL = """
    with at_start as (
      select p.game_id, p.stream_revision, p.period > 4 as ot,
             s.home_lineup_id, s.away_lineup_id
      from possession p join stint s
        on s.game_id = p.game_id and s.stream_revision = p.stream_revision
       and p.start_seq >= s.start_seq and p.start_seq < s.end_seq
      where p.status = 'accepted'),
    counted as (
      select a.game_id, a.ot, unnest(l.player_ids) as player_id
      from at_start a join lineup l
        on l.game_id = a.game_id and l.stream_revision = a.stream_revision
       and l.lineup_id = a.home_lineup_id
      union all
      select a.game_id, a.ot, unnest(l.player_ids)
      from at_start a join lineup l
        on l.game_id = a.game_id and l.stream_revision = a.stream_revision
       and l.lineup_id = a.away_lineup_id),
    possessions as (select game_id, ot, player_id, count(*) as n from counted group by all),
    timed as (
      select s.game_id, s.period > 4 as ot, unnest(l.player_ids) as player_id,
             s.end_elapsed_ms - s.start_elapsed_ms as ms
      from stint s join lineup l
        on l.game_id = s.game_id and l.stream_revision = s.stream_revision
       and l.lineup_id = s.home_lineup_id
      union all
      select s.game_id, s.period > 4, unnest(l.player_ids), s.end_elapsed_ms - s.start_elapsed_ms
      from stint s join lineup l
        on l.game_id = s.game_id and l.stream_revision = s.stream_revision
       and l.lineup_id = s.away_lineup_id),
    minutes as (select game_id, ot, player_id, sum(ms) as ms from timed group by all)
    select coalesce(p.game_id, m.game_id), coalesce(p.player_id, m.player_id),
           coalesce(p.ot, m.ot), coalesce(p.n, 0), coalesce(m.ms, 0)
    from possessions p full join minutes m using (game_id, ot, player_id)
    order by 1, 2, 3
"""


# ---------------------------------------------------------------------------------------------
# M1 classification


@dataclass(frozen=True)
class M1Result:
    """Original and revised M1 results for one season."""

    year: int
    coverage: list[dict[str, Any]]
    strata: list[dict[str, Any]]
    unresolved: list[dict[str, Any]]
    invariants_failed: int | None
    original_failures: list[str]
    hard_failures: list[str]
    warnings: list[str]

    @property
    def original_status(self) -> str:
        return "fail" if self.original_failures else "pass"

    @property
    def revised_status(self) -> str:
        if self.hard_failures:
            return "fails_hard_limit"
        return "meets_with_warnings" if self.warnings else "meets"


def m1_classification(season: Season, invariants_failed: int | None = None) -> M1Result:
    """Apply the original M1 table and the ADR-0022 revision to one season's build."""
    games = season.games
    types = np.array(games.season_type)
    coverage, strata, unresolved = [], [], []
    original: list[str] = []
    hard: list[str] = []
    warnings: list[str] = []
    label = season.label
    if invariants_failed:
        hard.append(f"{label}: {invariants_failed} hard correctness checks fail")
        original.append(f"{label}: {invariants_failed} invariants fail")
    for season_type in SEASON_TYPES:
        mask = types == season_type
        expected = int(mask.sum())
        accepted = int((mask & games.accepted).sum())
        share = accepted / expected if expected else float("nan")
        coverage.append(
            {
                "season": label,
                "season_type": season_type,
                "expected": expected,
                "accepted": accepted,
                "quarantined": expected - accepted,
                "coverage": share,
                "floor": GAME_COVERAGE_FLOOR,
                "meets_floor": share >= GAME_COVERAGE_FLOOR,
            }
        )
        if expected and share < GAME_COVERAGE_FLOOR:
            note = (
                f"{label} {season_type}: game coverage {share:.1%} below {GAME_COVERAGE_FLOOR:.0%}"
            )
            hard.append(note)
            original.append(note)
        names = [*M1_STRATA, *sorted({s for x in games.strata for s in x} - set(M1_STRATA))]
        for stratum in names:
            has = np.array([stratum in s for s in games.strata], dtype=np.bool_)
            total = int((mask & has).sum())
            kept = int((mask & has & games.accepted).sum())
            if not total:
                continue
            rate = kept / total
            is_m1 = stratum in M1_STRATA
            strata.append(
                {
                    "season": label,
                    "season_type": season_type,
                    "stratum": stratum,
                    "m1_stratum": is_m1,
                    "games": total,
                    "accepted": kept,
                    "coverage": rate,
                    "target": STRATUM_COVERAGE_TARGET,
                    "meets_target": rate >= STRATUM_COVERAGE_TARGET,
                }
            )
            if is_m1 and rate < STRATUM_COVERAGE_TARGET:
                note = (
                    f"{label} {season_type}: {stratum} stratum {kept} of {total} "
                    f"({rate:.1%}) below {STRATUM_COVERAGE_TARGET:.0%}"
                )
                original.append(note)
                warnings.append(note)
    sums = {"possessions": 0, "unresolved": 0}
    for season_type in SEASON_TYPES:
        counts = season.status_counts.get(season_type, {})
        total = sum(counts.values())
        bad = counts.get("unresolved", 0)
        sums["possessions"] += total
        sums["unresolved"] += bad
        rate = bad / total if total else float("nan")
        unresolved.append(
            {
                "season": label,
                "season_type": season_type,
                "possessions": total,
                "accepted": counts.get("accepted", 0),
                "excluded": counts.get("excluded", 0),
                "unresolved": bad,
                "unresolved_share": rate,
                "limit": UNRESOLVED_SEASON_LIMIT,
                "above_limit": rate > UNRESOLVED_SEASON_LIMIT,
            }
        )
        if total and rate > UNRESOLVED_SEASON_LIMIT:
            warnings.append(
                f"{label} {season_type}: unresolved possessions {rate:.3%} above "
                f"{UNRESOLVED_SEASON_LIMIT:.1%}"
            )
    whole = sums["unresolved"] / sums["possessions"] if sums["possessions"] else float("nan")
    unresolved.append(
        {
            "season": label,
            "season_type": "season",
            "possessions": sums["possessions"],
            "accepted": sum(
                season.status_counts.get(t, {}).get("accepted", 0) for t in SEASON_TYPES
            ),
            "excluded": sum(
                season.status_counts.get(t, {}).get("excluded", 0) for t in SEASON_TYPES
            ),
            "unresolved": sums["unresolved"],
            "unresolved_share": whole,
            "limit": UNRESOLVED_SEASON_LIMIT,
            "above_limit": whole > UNRESOLVED_SEASON_LIMIT,
        }
    )
    if sums["possessions"] and whole > UNRESOLVED_SEASON_LIMIT:
        note = f"{label} season: unresolved possessions {whole:.3%} above {UNRESOLVED_SEASON_LIMIT:.1%}"
        hard.append(note)
        original.append(note)
    # Under the original table a warning-level season-type unresolved rate was not a failure,
    # because the limit applied to the whole season. Only the strata above were original gates.
    return M1Result(
        year=season.year,
        coverage=coverage,
        strata=strata,
        unresolved=unresolved,
        invariants_failed=invariants_failed,
        original_failures=original,
        hard_failures=hard,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------------------------
# Quarantine missingness: permutation chi-square over games


def chi_square(observed: FloatArray, expected: FloatArray) -> FloatArray:
    """Pearson statistic over cells with positive expectation, along the last axis."""
    keep = expected > 0
    diff = observed[..., keep] - expected[keep]
    return np.asarray((diff * diff / expected[keep]).sum(axis=-1), dtype=np.float64)


def permutation_test(
    weights: FloatArray,
    exposure: FloatArray,
    membership: FloatArray,
    rng: np.random.Generator,
    permutations: int,
) -> tuple[float, float, FloatArray, FloatArray]:
    """Chi-square of cell totals of `weights` against exposure-proportional expectation.

    `membership` is games by cells. The null shuffles `weights` across games, which keeps their
    total and any clustering in them, and so needs no large-sample approximation. Returns the
    statistic, the permutation p-value, observed cell totals and expected cell totals.
    """
    total_exposure = float(exposure.sum())
    expected = (
        float(weights.sum()) * (membership.T @ exposure) / total_exposure
        if total_exposure > 0
        else np.zeros(membership.shape[1])
    )
    observed = weights @ membership
    statistic = float(chi_square(observed, expected))
    order = np.argsort(rng.random((permutations, len(weights))), axis=1)
    null = chi_square(weights[order] @ membership, expected)
    p_value = (1 + int((null >= statistic - 1e-9).sum())) / (permutations + 1)
    return statistic, p_value, observed, expected


def flag(p_value: float, lift: float, events: float) -> str:
    """The documented rule: systematic, watch or none."""
    if p_value < SYSTEMATIC_ALPHA and lift >= MIN_LIFT and events >= MIN_CELL_EVENTS:
        return "systematic"
    if p_value < WATCH_ALPHA:
        return "watch"
    return "none"


def one_hot(labels: Sequence[str]) -> tuple[FloatArray, list[str]]:
    cells = sorted(set(labels))
    position = {cell: i for i, cell in enumerate(cells)}
    matrix = np.zeros((len(labels), len(cells)), dtype=np.float64)
    for row, label in enumerate(labels):
        matrix[row, position[label]] = 1.0
    return matrix, cells


def _team_membership(games: Games, select: npt.NDArray[np.bool_]) -> tuple[FloatArray, list[str]]:
    home = [t for t, s in zip(games.home, select, strict=True) if s]
    away = [t for t, s in zip(games.away, select, strict=True) if s]
    cells = sorted(set(home) | set(away))
    position = {cell: i for i, cell in enumerate(cells)}
    matrix = np.zeros((len(home), len(cells)), dtype=np.float64)
    for row, (h, a) in enumerate(zip(home, away, strict=True)):
        matrix[row, position[h]] += 1.0
        matrix[row, position[a]] += 1.0
    return matrix, cells


def _seed(*parts: int) -> np.random.Generator:
    return np.random.default_rng(list(parts))


def quarantine_missingness(
    season: Season, seed: int, permutations: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Cells, tests and cause counts for the games the build quarantined, by season type."""
    games = season.games
    types = np.array(games.season_type)
    cells_out: list[dict[str, Any]] = []
    tests_out: list[dict[str, Any]] = []
    causes_out: list[dict[str, Any]] = []
    for type_index, season_type in enumerate(SEASON_TYPES):
        select = types == season_type
        if not select.any():
            continue
        quarantined = ~games.accepted[select]
        weights = quarantined.astype(np.float64)
        exposure = np.ones(len(weights))
        poss = games.est_possessions[select]
        minutes = games.minutes[select]
        overtime = [
            "overtime" if "overtime" in s else "regulation"
            for s, k in zip(games.strata, select, strict=True)
            if k
        ]
        margin = [margin_band(int(m)) for m in games.margin[select]]
        month = [m for m, k in zip(games.month, select, strict=True) if k]
        dimensions: list[tuple[str, FloatArray, list[str]]] = [
            ("team", *_team_membership(games, select)),
            ("month", *one_hot(month)),
            ("overtime", *one_hot(overtime)),
            ("final_margin", *one_hot(margin)),
        ]
        reasons = [r for r, k in zip(games.reason, select, strict=True) if k]
        for reason in sorted({r for r, q in zip(reasons, quarantined, strict=True) if q}):
            hit = np.array([r == reason and q for r, q in zip(reasons, quarantined, strict=True)])
            causes_out.append(
                {
                    "season": season.label,
                    "season_type": season_type,
                    "cause": reason,
                    "games": int(hit.sum()),
                    "overtime_games": sum(
                        1 for h, o in zip(hit, overtime, strict=True) if h and o == "overtime"
                    ),
                    "share_of_quarantines": float(hit.sum() / quarantined.sum()),
                    "est_possessions_lost": float(poss[hit].sum()),
                    "box_minutes_lost": float(minutes[hit].sum()),
                }
            )
        for dim_index, (dimension, matrix, cells) in enumerate(dimensions):
            rng = _seed(seed, season.year, type_index, dim_index)
            testable = int(quarantined.sum()) >= MIN_TESTABLE_QUARANTINES
            statistic, p_value, observed, expected = (
                permutation_test(weights, exposure, matrix, rng, permutations)
                if testable
                else (float("nan"), float("nan"), weights @ matrix, np.zeros(len(cells)))
            )
            exposure_games = matrix.T @ exposure
            lifts = np.divide(observed, expected, out=np.zeros_like(observed), where=expected > 0)
            candidates = [i for i in range(len(cells)) if observed[i] > 0]
            top = max(candidates, key=lambda i: lifts[i], default=None)
            top_lift = float(lifts[top]) if top is not None else 0.0
            top_events = float(observed[top]) if top is not None else 0.0
            for i, cell in enumerate(cells):
                member = matrix[:, i] > 0
                cells_out.append(
                    {
                        "season": season.label,
                        "season_type": season_type,
                        "dimension": dimension,
                        "cell": cell,
                        "games": float(exposure_games[i]),
                        "quarantined": float(observed[i]),
                        "quarantine_rate": float(observed[i] / exposure_games[i]),
                        "expected_quarantined": float(expected[i]),
                        "lift": float(lifts[i]),
                        "est_possessions_lost": float((poss * quarantined * matrix[:, i]).sum()),
                        "est_possessions": float(poss[member].sum()),
                        "box_minutes_lost": float((minutes * quarantined * matrix[:, i]).sum()),
                    }
                )
            tests_out.append(
                {
                    "season": season.label,
                    "season_type": season_type,
                    "dimension": dimension,
                    "events": int(quarantined.sum()),
                    "cells": len(cells),
                    "chi_square": statistic,
                    "p_value": p_value,
                    "max_lift": top_lift,
                    "max_lift_cell": cells[top] if top is not None else "",
                    "max_lift_events": top_events,
                    "flag": flag(p_value, top_lift, top_events) if testable else "not_testable",
                }
            )
    return cells_out, tests_out, causes_out


# ---------------------------------------------------------------------------------------------
# Players: minutes and appearances lost


def player_missingness(
    season: Season, seed: int, permutations: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Box minutes and appearances in quarantined games, with a concentration test.

    The statistic is the largest share of a player's box minutes that fall in quarantined games,
    among players with at least 500 minutes. The null shuffles quarantine labels across the
    season type's games.
    """
    games = season.games
    types = np.array(games.season_type)
    summary: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    for type_index, season_type in enumerate(SEASON_TYPES):
        select = types == season_type
        if not select.any():
            continue
        matrix = season.player_minutes[:, select]
        quarantined = (~games.accepted[select]).astype(np.float64)
        total = matrix.sum(axis=1)
        eligible = total >= MIN_PLAYER_MINUTES if season_type == "regular" else total >= 100.0
        lost = matrix @ quarantined
        appearances = (matrix > 0).sum(axis=1)
        lost_appearances = (matrix > 0) @ quarantined
        shares = np.divide(lost, total, out=np.zeros_like(lost), where=total > 0)
        rate = float(lost.sum() / total.sum()) if total.sum() > 0 else float("nan")
        observed_max = float(shares[eligible].max()) if eligible.any() else float("nan")
        p_value = float("nan")
        if eligible.any() and quarantined.sum() >= MIN_TESTABLE_QUARANTINES:
            rng = _seed(seed, season.year, type_index, 99)
            order = np.argsort(rng.random((permutations, len(quarantined))), axis=1)
            null_lost = quarantined[order] @ matrix[eligible].T
            null_max = (null_lost / total[eligible]).max(axis=1)
            p_value = (1 + int((null_max >= observed_max - 1e-9).sum())) / (permutations + 1)
        ordered = np.sort(shares[eligible])
        summary.append(
            {
                "season": season.label,
                "season_type": season_type,
                "players_with_minutes": int((total > 0).sum()),
                "eligible_players": int(eligible.sum()),
                "box_minutes": float(total.sum()),
                "box_minutes_lost": float(lost.sum()),
                "minutes_lost_share": rate,
                "appearances": int(appearances.sum()),
                "appearances_lost": int(lost_appearances.sum()),
                "players_losing_any_game": int((lost_appearances > 0).sum()),
                "median_lost_share": float(np.median(ordered)) if len(ordered) else float("nan"),
                "p95_lost_share": float(np.percentile(ordered, 95))
                if len(ordered)
                else float("nan"),
                "max_lost_share": observed_max,
                "eligible_players_over_10pct_lost": int((shares[eligible] >= 0.10).sum()),
                "eligible_players_over_2x_rate_lost": int((shares[eligible] >= 2 * rate).sum()),
                "max_share_permutation_p": p_value,
            }
        )
        lift = observed_max / rate if rate and rate > 0 else 0.0
        # The events behind the maximum are the lost appearances of the player who holds it.
        top_events = (
            float(lost_appearances[eligible][int(np.argmax(shares[eligible]))])
            if eligible.any()
            else 0.0
        )
        tests.append(
            {
                "season": season.label,
                "season_type": season_type,
                "dimension": "player_minutes",
                "events": int(quarantined.sum()),
                "cells": int(eligible.sum()),
                "chi_square": float("nan"),
                "p_value": p_value,
                "max_lift": lift,
                "max_lift_cell": "max player share",
                "max_lift_events": top_events,
                "flag": flag(p_value, lift, top_events) if p_value == p_value else "not_testable",
            }
        )
    return summary, tests


# ---------------------------------------------------------------------------------------------
# Unresolved possessions: game-clustered bootstrap of rate ratios


def unresolved_missingness(
    season: Season, seed: int, replicates: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Unresolved-possession rate by cell, with game-clustered bootstrap intervals.

    Each cell is compared with all other cells of the same dimension: the ratio of its rate to
    the rate elsewhere, with a percentile interval from resampling games with replacement.

    The reported p-value is approximate: twice the smaller tail share of the bootstrap ratios
    around 1, with one added replicate per tail. A percentile bootstrap does not simulate the
    null, so treat it as a ranking and flag device, not an exact test. Its floor is 2 / replicates
    (2 k / replicates after Bonferroni over k cells), so too few replicates make a flag
    unreachable; the function refuses when that floor reaches the systematic threshold.
    """
    games = season.games
    kind = dict(zip(games.game_id, games.season_type, strict=True))
    accepted_ids = [g for g, a in zip(games.game_id, games.accepted, strict=True) if a]
    cells_out: list[dict[str, Any]] = []
    tests_out: list[dict[str, Any]] = []
    concentration: list[dict[str, Any]] = []
    for type_index, season_type in enumerate(SEASON_TYPES):
        ids = [g for g in accepted_ids if kind[g] == season_type]
        if not ids:
            continue
        row = {g: i for i, g in enumerate(ids)}
        rng = _seed(seed, season.year, type_index, 7)
        by_dimension: dict[str, dict[str, list[tuple[int, int, int]]]] = {}
        for cell in season.possession_cells:
            if cell["game_id"] in row:
                by_dimension.setdefault(cell["dimension"], {}).setdefault(cell["cell"], []).append(
                    (row[cell["game_id"]], cell["possessions"], cell["unresolved"])
                )
        matrices: dict[str, tuple[list[str], FloatArray, FloatArray]] = {}
        for dimension in DIMENSIONS:
            groups = by_dimension.get(dimension, {})
            labels = sorted(groups)
            poss = np.zeros((len(ids), len(labels)))
            bad = np.zeros((len(ids), len(labels)))
            for j, label in enumerate(labels):
                for i, p, u in groups[label]:
                    poss[i, j] += p
                    bad[i, j] += u
            matrices[dimension] = (labels, poss, bad)
            if dimension != "all" and 2 * len(labels) / replicates >= SYSTEMATIC_ALPHA:
                raise ValueError(
                    f"{replicates} bootstrap replicates cannot reach p < {SYSTEMATIC_ALPHA} "
                    f"for {len(labels)} {dimension} cells after Bonferroni; "
                    f"use more than {int(2 * len(labels) / SYSTEMATIC_ALPHA)}"
                )
        boot: dict[str, tuple[FloatArray, FloatArray]] = {
            d: (np.zeros((replicates, len(m[0]))), np.zeros((replicates, len(m[0]))))
            for d, m in matrices.items()
        }
        for start in range(0, replicates, BOOTSTRAP_CHUNK):
            size = min(BOOTSTRAP_CHUNK, replicates - start)
            draws = rng.multinomial(len(ids), np.full(len(ids), 1.0 / len(ids)), size=size)
            draws = draws.astype(np.float64)
            for dimension, (_labels, poss, bad) in matrices.items():
                boot[dimension][0][start : start + size] = draws @ poss
                boot[dimension][1][start : start + size] = draws @ bad
        for dimension in DIMENSIONS:
            labels, poss, bad = matrices[dimension]
            total_poss, total_bad = poss.sum(), bad.sum()
            boot_poss, boot_bad = boot[dimension]
            for j, label in enumerate(labels):
                cell_poss, cell_bad = poss[:, j].sum(), bad[:, j].sum()
                rate = cell_bad / cell_poss if cell_poss else float("nan")
                if dimension == "all":
                    low, high = np.percentile(boot_bad[:, 0] / boot_poss[:, 0], [2.5, 97.5])
                    ratio = ratio_low = ratio_high = float("nan")
                    p_value = float("nan")
                else:
                    rest_poss = total_poss - cell_poss
                    rest_rate = (total_bad - cell_bad) / rest_poss if rest_poss else float("nan")
                    if rest_rate and rest_rate > 0:
                        ratio = rate / rest_rate
                    else:  # nothing is unresolved elsewhere: any unresolved here is an infinite ratio
                        ratio = float("inf") if cell_bad > 0 else float("nan")
                    b_cell = boot_bad[:, j] / np.maximum(boot_poss[:, j], 1)
                    b_rest = (boot_bad.sum(axis=1) - boot_bad[:, j]) / np.maximum(
                        boot_poss.sum(axis=1) - boot_poss[:, j], 1
                    )
                    with np.errstate(divide="ignore", invalid="ignore"):
                        b_ratio = np.where(b_rest > 0, b_cell / b_rest, 1e9)
                    ratio_low, ratio_high = np.percentile(b_ratio, [2.5, 97.5])
                    low, high = np.percentile(b_cell, [2.5, 97.5])
                    p_value = float(
                        2
                        * min(
                            (b_ratio <= 1).mean() + 1 / replicates,
                            (b_ratio >= 1).mean() + 1 / replicates,
                            0.5,
                        )
                    )
                cells_out.append(
                    {
                        "season": season.label,
                        "season_type": season_type,
                        "dimension": dimension,
                        "cell": label,
                        "possessions": int(cell_poss),
                        "unresolved": int(cell_bad),
                        "unresolved_share": float(rate),
                        "share_ci_low": float(low),
                        "share_ci_high": float(high),
                        "rate_ratio_vs_rest": float(ratio),
                        "ratio_ci_low": float(ratio_low),
                        "ratio_ci_high": float(ratio_high),
                        "bootstrap_p": p_value,
                    }
                )
            if dimension != "all":
                candidates = [
                    c
                    for c in cells_out
                    if c["season"] == season.label
                    and c["season_type"] == season_type
                    and c["dimension"] == dimension
                    and c["unresolved"] >= MIN_CELL_EVENTS
                    and c["rate_ratio_vs_rest"] == c["rate_ratio_vs_rest"]
                ]
                top = max(candidates, key=lambda c: c["rate_ratio_vs_rest"], default=None)
                if top is None:
                    status, p_top, lift, name, events = "not_testable", float("nan"), 0.0, "", 0
                else:
                    # The largest of several cell ratios is tested, so its bootstrap p-value is
                    # multiplied by the number of cells with enough events (Bonferroni).
                    p_top = min(1.0, top["bootstrap_p"] * len(candidates))
                    lift, name, events = top["rate_ratio_vs_rest"], top["cell"], top["unresolved"]
                    status = flag(p_top, lift, events)
                tests_out.append(
                    {
                        "season": season.label,
                        "season_type": season_type,
                        "dimension": f"unresolved_{dimension}",
                        "events": int(total_bad),
                        "cells": len(labels),
                        "chi_square": float("nan"),
                        "p_value": p_top,
                        "max_lift": lift,
                        "max_lift_cell": name,
                        "max_lift_events": float(events),
                        "flag": status,
                    }
                )
        per_game = np.zeros(len(ids))
        for i, _p, u in by_dimension.get("all", {}).get("all", []):
            per_game[i] += u
        total = float(per_game.sum())
        ordered = np.sort(per_game)[::-1]
        top_n = max(1, int(np.ceil(0.05 * len(ids))))
        mean = per_game.mean()
        concentration.append(
            {
                "season": season.label,
                "season_type": season_type,
                "games": len(ids),
                "unresolved": int(total),
                "games_with_unresolved": int((per_game > 0).sum()),
                "share_of_games_with_unresolved": float((per_game > 0).mean()),
                "top_5pct_games_share": float(ordered[:top_n].sum() / total) if total else 0.0,
                "largest_game_share": float(ordered[0] / total) if total else 0.0,
                "largest_game_count": int(ordered[0]),
                "dispersion_index": float(per_game.var() / mean) if mean > 0 else float("nan"),
            }
        )
    return cells_out, tests_out, concentration


# ---------------------------------------------------------------------------------------------
# Sensitivity of the primary cohort


SCENARIOS: tuple[tuple[str, tuple[int, ...], bool, bool, bool], ...] = (
    # name, seasons dropped, drop overtime periods, drop games with an overtime period, drop weak
    ("baseline", (), False, False, False),
    ("exclude_2018_19", (2018,), False, False, False),
    ("exclude_2021_22", (2021,), False, False, False),
    ("exclude_both_conditional_seasons", (2018, 2021), False, False, False),
    ("exclude_overtime_periods", (), True, False, False),
    ("exclude_overtime_games", (), False, True, False),
    ("exclude_weaker_verification_games", (), False, False, True),
    ("exclude_conditional_seasons_and_overtime_periods", (2018, 2021), True, False, False),
    ("exclude_all_three", (2018, 2021), True, False, True),
)


def sensitivity(seasons: Iterable[Season], primary_years: Sequence[int]) -> list[dict[str, Any]]:
    """Count games, possessions, players and exposure left under each exclusion, data only."""
    loaded = {s.year: s for s in seasons}
    missing = [y for y in primary_years if y not in loaded]
    if missing:
        raise ValueError(f"Primary seasons not loaded: {missing}")
    rows: list[tuple[int, str, str, bool, int, int]] = []
    game_flags: dict[tuple[int, str], tuple[bool, bool]] = {}
    for year in primary_years:
        season = loaded[year]
        for game_id, accepted, strata in zip(
            season.games.game_id, season.games.accepted, season.games.strata, strict=True
        ):
            if accepted:
                game_flags[(year, game_id)] = (
                    "overtime" in strata,
                    any(s in strata for s in WEAK_STRATA),
                )
        for game_id, player, overtime, possessions, ms in season.exposure:
            rows.append((year, game_id, player, overtime, possessions, ms))
    result: list[dict[str, Any]] = []
    base: dict[str, float] = {}
    for name, dropped, drop_ot, drop_ot_games, drop_weak in SCENARIOS:
        games: set[tuple[int, str]] = set()
        player_possessions: dict[str, int] = {}
        player_ms: dict[str, int] = {}
        for key, (is_ot_game, is_weak) in game_flags.items():
            if key[0] in dropped or (drop_ot_games and is_ot_game) or (drop_weak and is_weak):
                continue
            games.add(key)
        for year, game_id, player, overtime, possessions, ms in rows:
            if (year, game_id) not in games or (drop_ot and overtime):
                continue
            player_possessions[player] = player_possessions.get(player, 0) + possessions
            player_ms[player] = player_ms.get(player, 0) + ms
        possession_total = _scenario_possessions(loaded, primary_years, games, drop_ot)
        minutes = sum(player_ms.values()) / 60000.0
        row: dict[str, Any] = {
            "scenario": name,
            "seasons_dropped": " ".join(season_label(y) for y in dropped),
            "overtime_periods_dropped": drop_ot,
            "overtime_games_dropped": drop_ot_games,
            "weaker_verification_dropped": drop_weak,
            "games": len(games),
            "possessions": possession_total,
            "players": sum(1 for v in player_possessions.values() if v > 0),
            "players_1000_possessions": sum(1 for v in player_possessions.values() if v >= 1000),
            "player_minutes_on_court": minutes,
        }
        if name == "baseline":
            base = {
                k: float(v)
                for k, v in row.items()
                if isinstance(v, int | float) and not isinstance(v, bool)
            }
        for column in (
            "games",
            "possessions",
            "players",
            "players_1000_possessions",
            "player_minutes_on_court",
        ):
            row[f"{column}_change"] = row[column] - base[column]
            row[f"{column}_change_share"] = (
                (row[column] - base[column]) / base[column] if base[column] else float("nan")
            )
        result.append(row)
    return result


def _scenario_possessions(
    loaded: dict[int, Season],
    primary_years: Sequence[int],
    games: set[tuple[int, str]],
    drop_ot: bool,
) -> int:
    """Accepted possessions in kept games, optionally without overtime periods."""
    total = 0
    for year in primary_years:
        for cell in loaded[year].possession_cells:
            if cell["dimension"] != ("period" if drop_ot else "all"):
                continue
            if (year, cell["game_id"]) not in games or (drop_ot and cell["cell"] == "OT"):
                continue
            total += cell["accepted"]
    return total


# ---------------------------------------------------------------------------------------------
# Output


def _flatten(value: Any) -> Any:
    if isinstance(value, float):
        return "" if value != value else repr(round(value, 8))
    return value


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _flatten(v) for k, v in row.items()})


def run(
    builds: Sequence[tuple[Path, Path | None]],
    output: Path,
    *,
    seed: int = 20261123,
    permutations: int = 5000,
    replicates: int = 20_000,
    primary_years: Sequence[int] = (2018, 2019, 2020, 2021, 2022),
    run_checks: bool = False,
) -> dict[str, Any]:
    """Diagnose each build and write aggregate CSV and JSON files to a new directory."""
    output.mkdir(parents=True, exist_ok=False)
    seasons: list[Season] = []
    tables: dict[str, list[dict[str, Any]]] = {
        name: []
        for name in (
            "m1_coverage",
            "m1_strata",
            "m1_unresolved",
            "m1_classification",
            "quarantine_cells",
            "quarantine_causes",
            "player_loss",
            "unresolved_cells",
            "unresolved_concentration",
            "flags",
        )
    }
    tests: list[dict[str, Any]] = []
    for build, snapshot in builds:
        season = load_season(build, snapshot)
        seasons.append(season)
        failed: int | None = None
        if run_checks:
            if snapshot is None:
                raise ValueError("Running the hard checks needs the snapshot")
            from bil.data.pilot_check import check_build

            failed = sum(1 for v in check_build(build, snapshot).values() if v != 0)
        m1 = m1_classification(season, failed)
        tables["m1_coverage"] += m1.coverage
        tables["m1_strata"] += m1.strata
        tables["m1_unresolved"] += m1.unresolved
        tables["m1_classification"].append(
            {
                "season": season.label,
                "original_status": m1.original_status,
                "original_failures": " | ".join(m1.original_failures),
                "revised_status": m1.revised_status,
                "hard_failures": " | ".join(m1.hard_failures),
                "warnings": " | ".join(m1.warnings),
                "invariants_failed": "" if failed is None else failed,
            }
        )
        cells, qtests, causes = quarantine_missingness(season, seed, permutations)
        tables["quarantine_cells"] += cells
        tables["quarantine_causes"] += causes
        tests += qtests
        if snapshot is not None:
            summary, ptests = player_missingness(season, seed, permutations)
            tables["player_loss"] += summary
            tests += ptests
        ucells, utests, concentration = unresolved_missingness(season, seed, replicates)
        tables["unresolved_cells"] += ucells
        tables["unresolved_concentration"] += concentration
        tests += utests
    tables["flags"] = [t for t in tests if t["flag"] in ("systematic", "watch")]
    for name, rows in tables.items():
        write_csv(output / f"{name}.csv", rows)
    write_csv(output / "tests.csv", tests)
    sens: list[dict[str, Any]] = []
    if all(y in {s.year for s in seasons} for y in primary_years):
        sens = sensitivity(seasons, primary_years)
        write_csv(output / "sensitivity.csv", sens)
    summary_json: dict[str, Any] = {
        "seed": seed,
        "permutations": permutations,
        "bootstrap_replicates": replicates,
        "primary_years": list(primary_years),
        "rules": {
            "systematic": f"p < {SYSTEMATIC_ALPHA}, lift >= {MIN_LIFT}, events >= {MIN_CELL_EVENTS}",
            "watch": f"p < {WATCH_ALPHA}",
            "min_testable_quarantines": MIN_TESTABLE_QUARANTINES,
        },
        "classification": tables["m1_classification"],
        "flags": tables["flags"],
        "sensitivity": sens,
    }
    (output / "summary.json").write_text(
        json.dumps(summary_json, indent=2, sort_keys=True, default=float) + "\n", encoding="utf-8"
    )
    return summary_json
