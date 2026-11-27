"""Chronologically fitted, versioned Estimated Skills bundles (issue #125).

Pure functions: no file access, no EPM outputs. The registered protocol is
docs/research/skill-prior-protocol.md.

A bundle serves one scoring season `S`. Its decay and shrinkage parameters come from the #32
model and Differential Evolution settings, refit on box history from seasons `S-3` to `S-1`:

- **Clock choice.** For each statistic and clock, fit on regular-season targets of `S-2` and score
  the mean loss on regular-season targets of `S-1`. The clock with the lowest validation loss wins.
- **Final fit.** Refit the chosen clock on regular-season targets of `S-2` and `S-1`.

Every outcome the bundle reads is dated on or before `outcomes_through`, the last appearance of
the fit stream. `fit_cutoff` is the day after. A consumer at origin `O` may use the bundle only if
`fit_cutoff <= O`. `bundle_values` re-checks this and builds the as-of snapshot from appearances
dated strictly before its as-of date, so later games and later parameter-training data cannot
change an earlier eligible feature.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.features.box import FEATURE_CODES, FEATURES, Appearance
from bil.features.skill_decay import (
    CLOCKS,
    Appearances,
    DESettings,
    FitResult,
    StatTable,
    assemble,
    fit_rows,
    mean_loss,
    predict_fit,
    scorable,
)
from bil.features.skill_history import season_start_year
from bil.features.skill_snapshot import SkillParams, skill_snapshot

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

VERSION = "skills-bundle-issue-125-v1"
SEED_BASE = 125_000
HISTORY_SEASONS = 3  # S-3 .. S-1 for the fit; S-3 .. S for snapshots in season S
MIN_TARGET_ROWS = 1000  # per statistic, in both the inner-fit and validation seasons


class SkillLineageError(ValueError):
    """A Skills bundle is not eligible for, or not consistent with, its consumer."""


@dataclass(frozen=True)
class SkillBundle:
    version: str
    scoring_season: int
    history_seasons: tuple[int, ...]
    validation_season: int
    outcomes_through: date
    fit_cutoff: date
    source_view: str  # digest of the fit stream's appearances
    source_pins: Mapping[str, Any]  # box-log snapshot pins of the fit seasons, as given
    params: Mapping[str, SkillParams]
    selection: Mapping[str, Mapping[str, Any]]  # per code: inner losses, chosen clock, fits
    fit_id: str

    def record(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "scoring_season": self.scoring_season,
            "history_seasons": list(self.history_seasons),
            "validation_season": self.validation_season,
            "outcomes_through": self.outcomes_through.isoformat(),
            "fit_cutoff": self.fit_cutoff.isoformat(),
            "source_view": self.source_view,
            "source_pins": {key: self.source_pins[key] for key in sorted(self.source_pins)},
            "params": {code: asdict(p) for code, p in sorted(self.params.items())},
            "selection": {code: dict(v) for code, v in sorted(self.selection.items())},
            "fit_id": self.fit_id,
        }


def rows_digest(rows: Sequence[Appearance]) -> str:
    """Order-independent content hash of appearances."""
    records = sorted(json.dumps(asdict(r), sort_keys=True, default=str) for r in rows)
    return hashlib.sha256("\n".join(records).encode()).hexdigest()


def _fit_id(bundle: SkillBundle) -> str:
    """Hash of every recorded field except the ID itself."""
    body = {key: value for key, value in bundle.record().items() if key != "fit_id"}
    text = json.dumps(body, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def stream_for(rows: Sequence[Appearance], seasons: Sequence[int]) -> list[Appearance]:
    wanted = set(seasons)
    return [r for r in rows if season_start_year(r.game_id) in wanted]


def seed_for(stat_index: int, clock: str, stage: int, scoring_season: int) -> int:
    return (
        SEED_BASE
        + 10_000 * (scoring_season % 100)
        + 100 * stat_index
        + 10 * CLOCKS.index(clock)
        + stage
    )


def _target_rows(appearances: Appearances, table: StatTable, seasons: set[int]) -> IntArray:
    season = np.asarray([season_start_year(g) for g in appearances.game])
    regular = np.asarray([kind == "regular" for kind in appearances.season_type], dtype=np.bool_)
    mask = scorable(table) & regular & np.isin(season, sorted(seasons)).astype(np.bool_)
    return np.flatnonzero(mask).astype(np.int64)


def _result(result: FitResult) -> dict[str, Any]:
    return {
        "seed": result.seed,
        "log10_half_life": result.log10_half_life,
        "log10_k": result.log10_k,
        "objective": result.objective,
        "nfev": result.nfev,
        "success": result.success,
        "rows": result.rows,
        "bound_hits": list(result.bound_hits),
    }


def fit_bundle(
    rows: Sequence[Appearance],
    scoring_season: int,
    settings: DESettings = DESettings(),
    source_pins: Mapping[str, Any] | None = None,
    min_rows: int = MIN_TARGET_ROWS,
) -> SkillBundle:
    """Fit the bundle for ``scoring_season`` from appearances of the three earlier seasons."""
    history = tuple(range(scoring_season - HISTORY_SEASONS, scoring_season))
    stream = stream_for(rows, history)
    if not stream:
        raise SkillLineageError(f"no box history for seasons {history}")
    seasons_seen = {season_start_year(r.game_id) for r in stream}
    if seasons_seen != set(history):
        raise SkillLineageError(f"box history covers {sorted(seasons_seen)}, not {list(history)}")
    panel, appearances, tables, _, _ = assemble(stream)
    inner, validation = history[1], history[2]
    params: dict[str, SkillParams] = {}
    selection: dict[str, dict[str, Any]] = {}
    for stat_index, feature in enumerate(FEATURES):
        table = tables[feature.code]
        inner_rows = _target_rows(appearances, table, {inner})
        valid_rows = _target_rows(appearances, table, {validation})
        final_rows = _target_rows(appearances, table, {inner, validation})
        if min(inner_rows.size, valid_rows.size) < min_rows:
            raise SkillLineageError(
                f"{feature.code}: {inner_rows.size} inner and {valid_rows.size} validation "
                f"target rows, below {min_rows}; the bundle for {scoring_season} is "
                "unavailable"
            )
        losses: dict[str, float] = {}
        inner_fits: dict[str, dict[str, Any]] = {}
        for clock in CLOCKS:
            seed = seed_for(stat_index, clock, 0, scoring_season)
            result = fit_rows(panel, table, appearances, clock, inner_rows, seed, 0, settings)
            pred = predict_fit(panel, table, appearances, result, valid_rows)
            losses[clock] = float(mean_loss(table, valid_rows, pred[None, :])[0])
            inner_fits[clock] = _result(result)
        chosen = min(CLOCKS, key=lambda c: (losses[c], CLOCKS.index(c)))
        seed = seed_for(stat_index, chosen, 1, scoring_season)
        final = fit_rows(panel, table, appearances, chosen, final_rows, seed, 1, settings)
        params[feature.code] = SkillParams(chosen, final.half_life, final.k)
        selection[feature.code] = {
            "validation_loss": losses,
            "chosen_clock": chosen,
            "inner_fits": inner_fits,
            "final_fit": _result(final),
            "inner_rows": int(inner_rows.size),
            "validation_rows": int(valid_rows.size),
        }
    outcomes_through = max(r.game_date for r in stream)
    source_view = rows_digest(stream)
    draft = SkillBundle(
        VERSION,
        scoring_season,
        history,
        validation,
        outcomes_through,
        outcomes_through + timedelta(days=1),
        source_view,
        dict(source_pins or {}),
        params,
        selection,
        "",
    )
    return replace(draft, fit_id=_fit_id(draft))


def check_bundle(bundle: SkillBundle, origin: date, scoring_season: int) -> None:
    """Refuse a bundle that is late, for another season, or altered since it was fitted."""
    if bundle.version != VERSION:
        raise SkillLineageError(f"bundle version {bundle.version} is not {VERSION}")
    if bundle.scoring_season != scoring_season:
        raise SkillLineageError(
            f"bundle serves {bundle.scoring_season}, not the scoring season {scoring_season}"
        )
    if (
        bundle.history_seasons != tuple(range(scoring_season - HISTORY_SEASONS, scoring_season))
        or bundle.validation_season != scoring_season - 1
    ):
        raise SkillLineageError("bundle history seasons are not the three before its season")
    if bundle.fit_cutoff != bundle.outcomes_through + timedelta(days=1):
        raise SkillLineageError("bundle fit cutoff does not follow its outcomes")
    if not bundle.fit_cutoff <= origin:
        raise SkillLineageError(
            f"bundle {bundle.fit_id} read outcomes through {bundle.outcomes_through}, "
            f"not before the origin {origin}"
        )
    if bundle.fit_id != _fit_id(bundle):
        raise SkillLineageError(f"bundle {bundle.fit_id} does not match its recorded contents")
    if set(bundle.params) != set(FEATURE_CODES):
        raise SkillLineageError("bundle does not cover every feature code")


@dataclass(frozen=True)
class SkillValues:
    values: FloatArray  # (players, FEATURE_CODES), NaN for players with no earlier appearance
    has_history: NDArray[np.bool_]
    audit: dict[str, Any]


def bundle_values(
    rows: Sequence[Appearance],
    bundle: SkillBundle,
    as_of: date,
    players: Sequence[int],
    lookback: int = HISTORY_SEASONS,
) -> SkillValues:
    """As-of skill estimates for ``players`` in FEATURE_CODES order, under a checked bundle.

    The snapshot reads seasons ``S - lookback`` to ``S`` before ``as_of``. The registered input
    uses all three history seasons. ``lookback=1`` is the recent-history ablation, which spans
    the same seasons as the v1 raw prior. A player with no positive-minute appearance in that
    span gets NaN inputs, the v1 cold prior.
    """
    season = bundle.scoring_season
    check_bundle(bundle, as_of, season)
    if not 1 <= lookback <= HISTORY_SEASONS:
        raise ValueError(f"lookback must be 1 to {HISTORY_SEASONS} seasons")
    if rows_digest(stream_for(rows, bundle.history_seasons)) != bundle.source_view:
        raise SkillLineageError(f"box rows differ from the source view of bundle {bundle.fit_id}")
    seasons = tuple(range(season - lookback, season + 1))
    stream = [r for r in stream_for(rows, seasons) if r.game_date < as_of]
    snapshot = skill_snapshot(stream, bundle.params, as_of)
    played = {int(r.player_id) for r in stream if r.minutes_ms > 0}
    column = {code: i for i, code in enumerate(FEATURE_CODES)}
    position = {int(p): i for i, p in enumerate(players)}
    values = np.full((len(players), len(FEATURE_CODES)), np.nan)
    has_history = np.zeros(len(players), dtype=np.bool_)
    for row in snapshot:
        i = position.get(int(row.player_id))
        if i is None or int(row.player_id) not in played:
            continue
        values[i, column[row.feature_code]] = row.estimate
        has_history[i] = True
    used = [r.game_date for r in stream]
    audit = {
        "skill_bundle": bundle.fit_id,
        "skill_fit_cutoff": bundle.fit_cutoff.isoformat(),
        "skill_seasons": list(seasons),
        "skill_lookback": lookback,
        "skill_box_last": max(used).isoformat() if used else None,
        "skill_players": int(has_history.sum()),
        "skill_cold_players": int((~has_history).sum()),
    }
    if used and max(used) >= as_of:
        raise SkillLineageError("a skill input row is not strictly before the as-of date")
    return SkillValues(values, has_history, audit)
