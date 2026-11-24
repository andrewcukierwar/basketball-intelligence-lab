"""As-of Estimated Skill snapshot for downstream consumers such as the SPM prior (issue #33).

Pure function: no file access, no EPM outputs. `skill_snapshot(rows, params, as_of)` returns, for
every player with an appearance dated strictly before `as_of`, one row per #62 box feature code:
the #32 league-shrunk exponentially discounted skill estimate, its discounted numerator and
exposure, the league reference and the evidence counts. Appearances on or after `as_of` never
enter (so a game on the as-of date, and anything later, cannot move the snapshot). Frozen
per-statistic `(clock, half_life, k)` come from the #32 fits. Context adjustments (home, rest,
opponent, team, trend) are deliberately not part of the snapshot: it is the game-agnostic skill.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from bil.features.box import FEATURE_CODES, FEATURES, Appearance
from bil.features.skill_decay import (
    CLOCKS,
    as_of_sums,
    build_panel,
    pooled,
    possession_exposure,
)


@dataclass(frozen=True)
class SkillParams:
    """Frozen decay and shrinkage for one statistic: half-life in `clock` units, strength `k`."""

    clock: str
    half_life: float
    k: float

    def __post_init__(self) -> None:
        if self.clock not in CLOCKS:
            raise ValueError(f"Unknown clock {self.clock!r}")
        if self.half_life <= 0 or self.k < 0:
            raise ValueError("half_life must be positive and k non-negative")


@dataclass(frozen=True)
class SnapshotRow:
    as_of: date
    player_id: str
    feature_code: str
    feature_group: str
    unit: str
    estimate: float
    discounted_numerator: float
    discounted_exposure: float
    league_rate: float
    covered_games: int
    prior_appearances: int
    clock: str
    half_life: float
    k: float


def skill_snapshot(
    rows: Sequence[Appearance], params: Mapping[str, SkillParams], as_of: date
) -> list[SnapshotRow]:
    """Skill estimates per player and #62 feature code from appearances before `as_of`.

    Regular-season and playoff appearances pool on one clock, the #32 convention. A player with
    no covered history for a statistic gets the league rate with zero exposure. A statistic with
    no league evidence yet (no earlier covered exposure) yields no rows. `params` must cover every
    code in `FEATURE_CODES`.
    """
    missing = set(FEATURE_CODES) - set(params)
    if missing:
        raise ValueError(f"No parameters for {sorted(missing)}")
    usable = [r for r in rows if r.game_date < as_of]
    if not usable:
        return []
    stream = pooled(usable)
    possessions, _ = possession_exposure(usable)
    panel = build_panel(stream, possessions)
    shape = panel.shape
    out: list[SnapshotRow] = []
    for feature in FEATURES:
        x = np.zeros((2, *shape))
        covered = np.zeros(len(panel.players), dtype=np.int64)
        for row in stream:
            count, opportunity = feature.numerator(row), feature.denominator(row)
            if count is None or opportunity is None:
                continue
            p, j = panel.position[row.key]
            x[0, p, j] = count
            x[1, p, j] = opportunity / feature.scale
            covered[p] += 1
        league_den = float(x[1].sum())
        if league_den <= 0:
            continue
        league = float(x[0].sum()) / league_den
        param = params[feature.code]
        sums = as_of_sums(panel, x, param.clock, param.half_life, as_of)
        unit = "fraction" if feature.scale == 1 else "per_36_minutes"
        for p, player in enumerate(panel.players):
            numerator, exposure = float(sums[0, p]), float(sums[1, p])
            out.append(
                SnapshotRow(
                    as_of,
                    player,
                    feature.code,
                    feature.group,
                    unit,
                    (numerator + param.k * league) / (exposure + param.k)
                    if exposure + param.k > 0
                    else league,
                    numerator,
                    exposure,
                    league,
                    int(covered[p]),
                    int(panel.lengths[p]),
                    param.clock,
                    param.half_life,
                    param.k,
                )
            )
    return out
