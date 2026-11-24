"""Box-score feature definitions and aggregation (contract: docs/research/box-score-feature-contract.md).

Everything here is pure: no file access, no model targets. Rates are ratios of summed numerators
and denominators over appearances where both components are known.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any, Literal

from bil.evaluation.eligibility import (
    Revision,
    eastern_origin,
    resolve_revisions,
)

FEATURE_VERSION = "box-v1"
MS_PER_36 = 36 * 60_000
COUNT_FIELDS = (
    "fgm",
    "fga",
    "fg3m",
    "fg3a",
    "ftm",
    "fta",
    "pts",
    "oreb",
    "dreb",
    "ast",
    "tov",
    "stl",
    "blk",
    "pf",
)
SeasonType = Literal["regular", "playoffs"]
SEASON_PREFIX: dict[str, SeasonType] = {"002": "regular", "004": "playoffs"}


@dataclass(frozen=True)
class Appearance:
    """One player's box line in one game, with the team of that appearance."""

    game_id: str
    player_id: str
    team_id: str
    opp_team_id: str
    season_type: SeasonType
    game_date: date
    minutes_ms: int
    fgm: int | None
    fga: int | None
    fg3m: int | None
    fg3a: int | None
    ftm: int | None
    fta: int | None
    pts: int | None
    oreb: int | None
    dreb: int | None
    ast: int | None
    tov: int | None
    stl: int | None
    blk: int | None
    pf: int | None

    @property
    def key(self) -> str:
        return f"{self.game_id}:{self.player_id}"

    @classmethod
    def from_record(cls, row: Mapping[str, Any]) -> Appearance:
        """Build from a source-style record with decimal `min` and ISO `game_date`."""
        played = row["game_date"]
        return cls(
            game_id=row["game_id"],
            player_id=str(row["player_id"]),
            team_id=str(row["team_id"]),
            opp_team_id=str(row["opp_team_id"]),
            season_type=row.get("season_type") or SEASON_PREFIX[row["game_id"][:3]],
            game_date=played if isinstance(played, date) else date.fromisoformat(played),
            minutes_ms=round(row["min"] * 60_000),
            **{name: row.get(name) for name in COUNT_FIELDS},
        )

    def content_sha256(self) -> str:
        parts = [
            self.game_id,
            self.player_id,
            self.team_id,
            self.opp_team_id,
            self.season_type,
            self.game_date.isoformat(),
            str(self.minutes_ms),
            *(
                "" if getattr(self, name) is None else str(getattr(self, name))
                for name in COUNT_FIELDS
            ),
        ]
        return sha256("\x1f".join(parts).encode()).hexdigest()


def _diff(left: int | None, right: int | None) -> int | None:
    return None if left is None or right is None else left - right


@dataclass(frozen=True)
class Feature:
    code: str
    group: Literal["offense", "defense"]
    numerator: Callable[[Appearance], int | None]
    denominator: Callable[[Appearance], int | None]
    scale: int  # 1 for a fraction, MS_PER_36 for a per-36-minute rate


def _count(name: str) -> Callable[[Appearance], int | None]:
    return lambda row: getattr(row, name)


def _minutes(row: Appearance) -> int | None:
    return row.minutes_ms


def _per36(code: str, field: str, group: Literal["offense", "defense"]) -> Feature:
    return Feature(code, group, _count(field), _minutes, MS_PER_36)


FEATURES: tuple[Feature, ...] = (
    Feature(
        "fg2_pct",
        "offense",
        lambda r: _diff(r.fgm, r.fg3m),
        lambda r: _diff(r.fga, r.fg3a),
        1,
    ),
    Feature("fg3_pct", "offense", _count("fg3m"), _count("fg3a"), 1),
    Feature("ft_pct", "offense", _count("ftm"), _count("fta"), 1),
    Feature("fg3_share", "offense", _count("fg3a"), _count("fga"), 1),
    _per36("fga_per_36", "fga", "offense"),
    _per36("fta_per_36", "fta", "offense"),
    _per36("ast_per_36", "ast", "offense"),
    _per36("tov_per_36", "tov", "offense"),
    _per36("oreb_per_36", "oreb", "offense"),
    _per36("dreb_per_36", "dreb", "defense"),
    _per36("stl_per_36", "stl", "defense"),
    _per36("blk_per_36", "blk", "defense"),
    _per36("pf_per_36", "pf", "defense"),
)
FEATURE_CODES = tuple(feature.code for feature in FEATURES)


@dataclass(frozen=True)
class FeatureValue:
    numerator: int | None
    denominator: int | None
    value: float | None
    covered_appearances: int
    eligible_appearances: int

    @property
    def coverage(self) -> float | None:
        if not self.eligible_appearances:
            return None
        return self.covered_appearances / self.eligible_appearances


class Accumulator:
    """Running sums for one player over a set of appearances."""

    def __init__(self) -> None:
        self.eligible = 0
        self.minutes_ms = 0
        self.points = 0
        self.points_known = 0
        self.positive_time_games = 0
        self._sums = {feature.code: [0, 0, 0] for feature in FEATURES}

    def add(self, row: Appearance) -> None:
        self.eligible += 1
        self.minutes_ms += row.minutes_ms
        self.positive_time_games += row.minutes_ms > 0
        if row.pts is not None:
            self.points += row.pts
            self.points_known += 1
        for feature in FEATURES:
            numerator, denominator = feature.numerator(row), feature.denominator(row)
            if numerator is not None and denominator is not None:
                total = self._sums[feature.code]
                total[0] += numerator
                total[1] += denominator
                total[2] += 1

    def values(self) -> dict[str, FeatureValue]:
        result = {}
        for feature in FEATURES:
            numerator, denominator, covered = self._sums[feature.code]
            if covered == 0:
                result[feature.code] = FeatureValue(None, None, None, 0, self.eligible)
                continue
            rate = numerator * feature.scale / denominator if denominator > 0 else None
            result[feature.code] = FeatureValue(
                numerator, denominator, rate, covered, self.eligible
            )
        return result

    def summary(self) -> dict[str, int | None]:
        """Exposure diagnostics. Null when no eligible appearance exists."""
        if not self.eligible:
            return {"minutes_ms": None, "points": None, "games_with_time": 0}
        return {
            "minutes_ms": self.minutes_ms,
            "points": self.points if self.points_known else None,
            "games_with_time": self.positive_time_games,
        }


def aggregate(rows: Iterable[Appearance]) -> Accumulator:
    accumulator = Accumulator()
    for row in rows:
        accumulator.add(row)
    return accumulator


def same_window(
    rows: Iterable[Appearance],
    start: date,
    end: date,
    season_types: Sequence[str],
) -> list[Appearance]:
    """Retrospective training window: every finalized game dated in [start, end]."""
    return [r for r in rows if start <= r.game_date <= end and r.season_type in season_types]


def dated_retrospective(
    rows: Iterable[Appearance], rating_date: date, season_types: Sequence[str]
) -> list[Appearance]:
    """Frozen-snapshot history: strictly earlier played dates (same-day games are excluded)."""
    return [r for r in rows if r.game_date < rating_date and r.season_type in season_types]


def history_rows(
    rows: Iterable[Appearance],
) -> Iterable[tuple[Appearance, dict[str, FeatureValue], dict[str, int | None]]]:
    """Per appearance, features from the same player's earlier-dated games of the same type.

    Appearances are processed one played date at a time: every row of a date is emitted from the
    state before any row of that date is added, so no same-day game can reach another's history.
    """
    by_date: dict[date, list[Appearance]] = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    state: dict[tuple[str, str], Accumulator] = defaultdict(Accumulator)
    for played in sorted(by_date):
        group = sorted(by_date[played], key=lambda r: (r.game_id, r.player_id))
        for row in group:
            history = state[(row.player_id, row.season_type)]
            yield row, history.values(), history.summary()
        for row in group:
            state[(row.player_id, row.season_type)].add(row)


@dataclass(frozen=True)
class Provenance:
    """Source capture evidence used to build strict revisions."""

    source_artifact_id: str
    available_at: datetime
    evidence_ref: str


def capture_bound_revisions(
    rows: Iterable[Appearance], provenance: Provenance
) -> dict[str, Revision]:
    """One revision per appearance whose only availability evidence is the later capture."""
    return {
        row.key: Revision(
            key=row.key,
            revision=1,
            source_artifact_id=provenance.source_artifact_id,
            content_sha256=row.content_sha256(),
            kind="observation",
            availability_basis="capture_bound",
            available_at=provenance.available_at,
            evidence_ref=provenance.evidence_ref,
            observed_date=row.game_date,
        )
        for row in rows
    }


def strict_history(
    rows: Iterable[Appearance],
    revisions: Mapping[str, Revision],
    rating_date: date,
    season_types: Sequence[str],
) -> tuple[list[Appearance], dict[str, int]]:
    """Appearances usable before the NY-midnight cutoff of `rating_date`, and exclusion counts.

    Uses the evaluation resolver in strict mode: availability must be known and no later than the
    cutoff, and the observation must be finalized before it and played on an earlier date.
    """
    candidates = {
        r.key: r for r in rows if r.game_date <= rating_date and r.season_type in season_types
    }
    selection = resolve_revisions(
        (revisions[key] for key in candidates),
        cutoff=eastern_origin(rating_date),
        mode="strict_rolling",
        role="features",
        rating_date=rating_date,
    )
    return [candidates[row.key] for row in selection.rows], dict(selection.exclusions)


def snapshot_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(None):
        raise ValueError(f"expected a UTC timestamp, got {value!r}")
    return parsed.astimezone(UTC).replace(microsecond=parsed.microsecond)
