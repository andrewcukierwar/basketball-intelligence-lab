"""Offline adapter for the pinned pbpstats version used by the pilot."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from unittest.mock import Mock, patch

from pbpstats.data_loader.stats_nba.enhanced_pbp.loader import (  # type: ignore[import-untyped]
    StatsNbaEnhancedPbpLoader,
)
from pbpstats.data_loader.stats_nba.possessions.file import (  # type: ignore[import-untyped]
    StatsNbaPossessionFileLoader,
)
from pbpstats.data_loader.stats_nba.possessions.loader import (  # type: ignore[import-untyped]
    StatsNbaPossessionLoader,
)
from pbpstats.resources.enhanced_pbp import (  # type: ignore[import-untyped]
    InvalidNumberOfStartersException,
)
from pbpstats.resources.enhanced_pbp.foul import Foul  # type: ignore[import-untyped]
from pbpstats.resources.enhanced_pbp.rebound import (  # type: ignore[import-untyped]
    EventOrderError,
    Rebound,
)
from pbpstats.resources.enhanced_pbp.stats_nba.start_of_period import (  # type: ignore[import-untyped]
    StatsStartOfPeriod,
)

from bil.data.pilot_inputs import GameBox, GameIssue, RawEvent, event_payload, shot_payload

PARSER_VERSION = "pbpstats-1.3.11-bil-v5"

# Starter choices for ambiguous periods, keyed by (period, team ID).
Starters = dict[tuple[int, int], tuple[int, ...]]


class StarterGap(GameIssue):
    """Events alone do not establish five starters for one or both teams in a period."""

    def __init__(self, period: int, partial: dict[int, tuple[int, ...]]) -> None:
        super().__init__("unresolved_starters", "Offline period starters are ambiguous")
        self.period = period
        self.partial = partial


class ParserEvent(Protocol):
    event_num: int
    event_type: int
    period: int

    @property
    def current_players(self) -> dict[int, list[int]]: ...
    @property
    def score(self) -> dict[int, int]: ...
    @property
    def seconds_remaining(self) -> float: ...
    @property
    def count_as_possession(self) -> bool: ...


class ParserPossession(Protocol):
    events: list[ParserEvent]

    @property
    def offense_team_id(self) -> int: ...


@dataclass(frozen=True)
class ParseResult:
    events: list[ParserEvent]
    possessions: list[ParserPossession]
    # True when the archived V3 action order replaced the V2 file order.
    v3_order: bool
    # Indices into ``possessions`` that the parser would reject as back-to-back possessions.
    unresolved_possessions: frozenset[int]


def _record_back_to_back(flagged: set[int]) -> Callable[[object], None]:
    """Record, rather than raise, the parser's back-to-back possession check.

    This mirrors ``_check_that_possessions_alternate`` in pbpstats 1.3.11, including its flagrant
    foul exemption, and flags both possessions in each offending pair.
    """

    def check(loader: object) -> None:
        items = cast(list[object], getattr(loader, "items"))
        for index, possession in enumerate(items):
            if getattr(possession, "previous_possession") is not None:
                pair = index - 1, index
            elif getattr(possession, "next_possession") is not None:
                pair = index, index + 1
            else:
                continue
            first, second = (items[i] for i in pair)
            if getattr(first, "offense_team_id") != getattr(second, "offense_team_id"):
                continue
            nearby = list(getattr(first, "events"))
            before = getattr(first, "previous_possession")
            if before is not None:
                nearby += getattr(before, "events")
            if any(isinstance(event, Foul) and event.is_flagrant for event in nearby):
                continue
            flagged.update(pair)

    return check


def _archived_order(event_order: list[int], applied: list[bool]) -> Callable[[object], None]:
    """Replace the parser's live data.nba.com reorder with the pinned V3 action order."""

    def reorder(loader: object) -> None:
        data = cast(dict[str, list[dict[str, list[object]]]], getattr(loader, "source_data"))
        table = data["resultSets"][0]
        index = cast(list[str], table["headers"]).index("EVENTNUM")
        rows = cast(list[list[object]], table["rowSet"])
        by_num = {cast(int, row[index]): row for row in rows}
        if (
            len(by_num) != len(rows)
            or len(event_order) != len(set(event_order))
            or set(event_order) != by_num.keys()
        ):
            raise GameIssue(
                "unresolved_event_order", "Archived V3 order does not cover the V2 events"
            )
        table["rowSet"] = [by_num[event_num] for event_num in event_order]
        getattr(loader, "_save_data_to_file")()
        applied.append(True)

    return reorder


def _chosen_starters(
    teams: tuple[int, int], starters: Starters
) -> Callable[[object, object], dict[int, list[int]]]:
    """Replace the parser's live box-score starter request with explicit choices."""

    def period_starters(
        period_start: object, file_directory: object = None
    ) -> dict[int, list[int]]:
        infer = getattr(period_start, "_get_period_starters_from_period_events")
        try:
            return cast(dict[int, list[int]], infer(None))
        except InvalidNumberOfStartersException:
            partial = cast(dict[int, list[int]], infer(None, ignore_missing_starters=True))
        period = cast(int, getattr(period_start, "period"))
        found = {team: tuple(partial.get(team, [])) for team in teams}
        if set(partial) - set(teams):
            raise GameIssue("unresolved_starters", "Period starters name an unknown team")
        gaps = {team: ids for team, ids in found.items() if len(ids) != 5}
        missing = {team: ids for team, ids in gaps.items() if (period, team) not in starters}
        if missing:
            raise StarterGap(period, missing)
        result = {team: list(ids) for team, ids in found.items()}
        for team in gaps:
            result[team] = list(starters[(period, team)])
        return result

    return period_starters


def parse_game(
    game: GameBox,
    raw: dict[int, RawEvent],
    shots: dict[int, list[tuple[int, ...]]],
    scratch: Path,
    event_order: list[int] | None = None,
    starters: Starters | None = None,
    primary_order: list[int] | None = None,
) -> ParseResult:
    """Parse one game offline.

    When the pinned parser cannot repair rebound order it requests data.nba.com event order.
    That request is replaced by the archived V3 action order of the same events, if supplied.
    The returned flag reports whether that order was applied.

    When period events do not identify five starters for a team, the parser would request a
    live box score. Instead, ``starters`` supplies the choice for that period and team, or a
    ``StarterGap`` reports the partial starters so a caller can search candidates.

    ``primary_order`` writes the events in that order instead of V2 file order. It must cover
    exactly the V2 events.

    The parser rejects a game when consecutive possessions have the same offense, which usually
    means a source event is missing or misordered. Those possession pairs are returned as
    unresolved instead, so lineups and scoring can still be reconciled for the whole game.
    """
    for folder in ("pbp", "game_details", "overrides"):
        (scratch / folder).mkdir(exist_ok=True)
    pbp_file = scratch / "pbp" / f"stats_{game.game_id}.json"
    if primary_order is not None:
        if len(primary_order) != len(set(primary_order)) or set(primary_order) != raw.keys():
            raise GameIssue(
                "unresolved_event_order", "Archived V3 order does not cover the V2 events"
            )
        raw = {event_num: raw[event_num] for event_num in primary_order}
    pbp_file.write_text(json.dumps(event_payload(raw)), encoding="utf-8")
    for side, team_id in (("home", game.home_id), ("away", game.away_id)):
        if team_id not in shots:
            raise GameIssue("missing_shot_chart", f"Missing {side} shot chart")
        target = scratch / "game_details" / f"stats_{side}_shots_{game.game_id}.json"
        target.write_text(json.dumps(shot_payload(shots[team_id])), encoding="utf-8")

    applied: list[bool] = []
    flagged: set[int] = set()
    if event_order:
        reorder = _archived_order(event_order, applied)
    else:
        reorder = Mock(
            side_effect=GameIssue("unresolved_event_order", "Offline event order is ambiguous")
        )
    # The pinned file parser may otherwise fall back to two live NBA endpoints.
    with (
        patch.object(
            StatsStartOfPeriod,
            "_get_starters_from_boxscore_request",
            side_effect=GameIssue("unresolved_starters", "Offline period starters are ambiguous"),
        ),
        patch.object(StatsNbaEnhancedPbpLoader, "_use_data_nba_event_order", reorder),
        patch.object(
            StatsStartOfPeriod,
            "get_period_starters",
            _chosen_starters((game.home_id, game.away_id), starters or {}),
        ),
        patch(
            "pbpstats.data_loader.stats_nba.possessions.loader."
            "StatsNbaPossessionLoader._check_that_possessions_alternate",
            _record_back_to_back(flagged),
        ),
        patch(
            "requests.sessions.Session.request",
            side_effect=GameIssue("offline_parser_request", "Parser attempted a network request"),
        ),
    ):
        try:
            loader = StatsNbaPossessionLoader(
                game.game_id, StatsNbaPossessionFileLoader(str(scratch))
            )
            events = cast(list[ParserEvent], loader.events)
            possessions = cast(list[ParserPossession], loader.items)
            # Resolve lazy parser properties while fallbacks are disabled. The parser does not
            # recheck rebound order after its fallback reorder, so check it here.
            for event in events:
                try:
                    if isinstance(event, Rebound):
                        event.missed_shot
                except EventOrderError as error:
                    raise GameIssue(
                        "unresolved_event_order",
                        "Rebound order remains unresolved",
                        event.event_num,
                    ) from error
                event.current_players
            for possession in possessions:
                possession.offense_team_id
                possession.events[-1].count_as_possession
        except GameIssue:
            raise
        except (ValueError, KeyError, IndexError, AttributeError, TypeError) as error:
            raise GameIssue("parser_error", type(error).__name__) from error
        except Exception as error:
            if not type(error).__module__.startswith("pbpstats."):
                raise
            raise GameIssue("parser_error", type(error).__name__) from error
    return ParseResult(events, possessions, bool(applied), frozenset(flagged))
