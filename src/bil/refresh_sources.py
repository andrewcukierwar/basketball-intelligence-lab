"""Per-origin source-revision resolution for the local refresh (#143).

A **capture** is one pinned retrieval of a source: a box-log snapshot or a possession row set. It
carries, per game, the official Eastern game date and a content hash. Successive captures of the
same source give a game a new **revision** whenever its content changes. A revision becomes
available at its capture's retrieval instant.

``resolve(captures, origin, mode)`` picks one revision per game for an origin ``D``, whose cutoff
is midnight Eastern at the start of ``D``.

- **``strict_rolling``.** A revision is visible only if it was available **strictly before** the
  cutoff. The game's latest visible revision is used, and it must have been played on an earlier
  official date and finished before the cutoff. A correction that becomes available after the
  cutoff therefore never enters that origin, but does enter later ones.
- **Finish time.** Neither pinned source records when a game finished. The conservative rule
  takes the finish as no later than the capture that first showed the content, so
  ``finalized_at`` is the capture instant unless a source records an earlier one. A game played
  late on its official date ``D-1`` is unavailable at origin ``D`` until a capture made after it
  finished.
- **Refusals.** A game with an unknown or non-UTC time, an unknown official date, or official
  dates that disagree across captures is refused and counted. It is never guessed.
- **``retrospective``.** Pinned replay snapshots (2023–25) were captured after their seasons, so
  their only time is a capture bound later than every in-season origin. Strict resolution would
  select nothing. Retrospective resolution requires exactly one capture per source and selects
  the games whose official date is before ``D``. This is the #36 rule. Corrections made before
  the capture are in every origin, which is the documented limit of retrospective pins.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

import numpy as np

from bil.evaluation.eligibility import Revision, eastern_origin, resolve_revisions
from bil.features.box import Appearance
from bil.models.rapm.multiseason import SEASON_PINS, Rows

VERSION = "source-resolution-issue-143-v1"
Mode = Literal["strict_rolling", "retrospective"]
MODES = ("strict_rolling", "retrospective")


class SourceError(ValueError):
    """Captures cannot be resolved as given (order, mode or structure)."""


@dataclass(frozen=True)
class GameRecord:
    """One game as one capture shows it."""

    game_date: date | None  # official Eastern game date
    content_sha256: str
    finalized_at: datetime | None = None  # recorded finish instant (UTC), if the source has one


@dataclass(frozen=True)
class Capture:
    """One pinned retrieval of a source."""

    source: str  # e.g. "box_logs/2023" or "possessions/2023-24"
    capture_id: str  # snapshot or row-manifest digest
    retrieved_at: datetime | None  # UTC retrieval instant, None when not recorded
    games: Mapping[str, GameRecord]


@dataclass(frozen=True)
class Resolution:
    """The revision of every selected game at one origin, and counted refusals."""

    origin: date
    mode: Mode
    games: Mapping[str, tuple[int, str, str]]  # "source:game" -> (revision, content, capture)
    exclusions: Mapping[str, int]

    def record(self) -> dict[str, Any]:
        """The selected revisions. Exclusion counts are left out because later games change
        them, and the record (and its digest) must depend only on what the origin reads."""
        return {
            "version": VERSION,
            "origin": self.origin.isoformat(),
            "cutoff": eastern_origin(self.origin).isoformat(),
            "mode": self.mode,
            "games": {key: list(value) for key, value in sorted(self.games.items())},
        }

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.record(), sort_keys=True).encode()).hexdigest()

    def summary(self) -> dict[str, Any]:
        revised = sum(1 for revision, _, _ in self.games.values() if revision > 1)
        return {
            "version": VERSION,
            "mode": self.mode,
            "cutoff": eastern_origin(self.origin).isoformat(),
            "games": len(self.games),
            "games_on_a_later_revision": revised,
            "exclusions": dict(sorted(self.exclusions.items())),
            "digest": self.digest(),
        }


def _utc(value: datetime | None) -> bool:
    return value is None or (value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(None))


def _game_revisions(
    captures: Sequence[Capture],
) -> tuple[dict[str, list[Revision]], Counter[str]]:
    """Revisions per ``source:game`` in capture order, and games refused before selection."""
    by_source: dict[str, list[Capture]] = defaultdict(list)
    for capture in captures:
        by_source[capture.source].append(capture)
    revisions: dict[str, list[Revision]] = {}
    refused: Counter[str] = Counter()
    for source, ordered in by_source.items():
        known = [c.retrieved_at for c in ordered if c.retrieved_at and _utc(c.retrieved_at)]
        if known != sorted(known):
            raise SourceError(f"{source} captures are not in retrieval order")
        history: dict[str, list[tuple[Capture, GameRecord]]] = defaultdict(list)
        for capture in ordered:
            for game, record in capture.games.items():
                history[game].append((capture, record))
        for game, seen in history.items():
            reason = _refusal(seen)
            if reason:
                refused[reason] += 1
                continue
            rows: list[Revision] = []
            for capture, record in seen:
                if rows and rows[-1].content_sha256 == record.content_sha256:
                    continue
                assert capture.retrieved_at is not None and record.game_date is not None
                rows.append(
                    Revision(
                        key=f"{source}:{game}",
                        revision=len(rows) + 1,
                        source_artifact_id=capture.capture_id,
                        content_sha256=record.content_sha256,
                        kind="observation",
                        availability_basis="capture_bound",
                        available_at=capture.retrieved_at,
                        evidence_ref=f"{capture.capture_id}#retrieved_at="
                        + capture.retrieved_at.isoformat(),
                        observed_date=record.game_date,
                        finalized_at=record.finalized_at or capture.retrieved_at,
                    )
                )
            revisions[f"{source}:{game}"] = rows
    return revisions, refused


def _refusal(seen: Sequence[tuple[Capture, GameRecord]]) -> str | None:
    """Why a game's captures cannot be resolved without guessing, if they cannot."""
    if any(c.retrieved_at is None for c, _ in seen):
        return "availability_unknown"
    if any(not _utc(c.retrieved_at) or not _utc(r.finalized_at) for c, r in seen):
        return "time_ambiguous"
    for capture, record in seen:
        assert capture.retrieved_at is not None
        if record.finalized_at is not None and record.finalized_at > capture.retrieved_at:
            return "time_ambiguous"
    dates = {r.game_date for _, r in seen}
    if None in dates:
        return "played_date_unknown"
    if len(dates) > 1:
        return "played_date_ambiguous"
    return None


def resolve(captures: Sequence[Capture], origin: date, mode: Mode) -> Resolution:
    """One revision per game for ``origin`` under ``mode`` (see the module docstring)."""
    if mode not in MODES:
        raise SourceError(f"unknown resolution mode {mode!r}")
    if mode == "retrospective":
        return _retrospective(captures, origin)
    cutoff = eastern_origin(origin)
    revisions, refused = _game_revisions(captures)
    exclusions: Counter[str] = Counter(refused)
    visible: list[Revision] = []
    for rows in revisions.values():
        shown = [r for r in rows if r.available_at is not None and r.available_at < cutoff]
        if not shown:
            exclusions["available_at_or_after_cutoff"] += 1
            continue
        visible.extend(shown)
    selection = resolve_revisions(
        visible, cutoff=cutoff, mode="strict_rolling", role="features", rating_date=origin
    )
    exclusions.update(dict(selection.exclusions))
    return Resolution(
        origin,
        mode,
        {r.key: (r.revision, r.content_sha256, r.source_artifact_id) for r in selection.rows},
        dict(exclusions),
    )


def _retrospective(captures: Sequence[Capture], origin: date) -> Resolution:
    counts = Counter(c.source for c in captures)
    if any(n != 1 for n in counts.values()):
        raise SourceError("retrospective resolution needs exactly one pinned capture per source")
    games: dict[str, tuple[int, str, str]] = {}
    exclusions: Counter[str] = Counter()
    for capture in captures:
        for game, record in capture.games.items():
            if record.game_date is None:
                exclusions["played_date_unknown"] += 1
            elif record.game_date >= origin:
                exclusions["same_or_later_played_date"] += 1
            else:
                key = f"{capture.source}:{game}"
                games[key] = (1, record.content_sha256, capture.capture_id)
    return Resolution(origin, "retrospective", games, dict(exclusions))


# --- adapters for the pinned sources ----------------------------------------------------


def box_capture(
    source: str, capture_id: str, retrieved_at: datetime | None, logs: Iterable[Appearance]
) -> Capture:
    """Per game: its official date and a hash of its player appearances' content."""
    by_game: dict[str, list[Appearance]] = defaultdict(list)
    for row in logs:
        by_game[row.game_id].append(row)
    games = {}
    for game, rows in by_game.items():
        dates = {r.game_date for r in rows}
        content = "\n".join(sorted(r.content_sha256() for r in rows))
        games[game] = GameRecord(
            dates.pop() if len(dates) == 1 else None, hashlib.sha256(content.encode()).hexdigest()
        )
    return Capture(source, capture_id, retrieved_at, games)


def possession_captures(rows: Rows, row_ids: Mapping[str, str]) -> list[Capture]:
    """One capture per pinned row-set season. A game's content is its possession rows.

    The loaded rows keep no stream availability time, so ``retrieved_at`` is None. Only
    retrospective resolution can use these captures.
    """
    order = np.argsort(rows.game, kind="stable")
    games = rows.game[order]
    starts = np.flatnonzero(np.r_[True, games[1:] != games[:-1]])
    ends = np.r_[starts[1:], games.size]
    fields = (
        rows.day,
        rows.playoff,
        rows.team_game,
        rows.possession_seq,
        rows.period,
        rows.y,
        rows.offense,
        rows.defense,
        rows.context,
        rows.no_livedata,
    )
    by_season: dict[int, dict[str, GameRecord]] = defaultdict(dict)
    for start, end in zip(starts, ends, strict=True):
        index = order[start:end]
        digest = hashlib.sha256()
        for values in fields:
            digest.update(np.ascontiguousarray(values[index]).tobytes())
        days = np.unique(rows.day[index])
        seasons = np.unique(rows.season[index])
        if seasons.size != 1:
            raise SourceError(f"game {rows.game_ids[games[start]]} spans seasons")
        by_season[int(seasons[0])][rows.game_ids[games[start]]] = GameRecord(
            date.fromordinal(int(days[0])) if days.size == 1 else None, digest.hexdigest()
        )
    captures = []
    for season, found in sorted(by_season.items()):
        label = SEASON_PINS[season].label if season in SEASON_PINS else str(season)
        captures.append(
            Capture(f"possessions/{label}", row_ids.get(label, "unpinned"), None, found)
        )
    return captures
