"""Offline adapter for the pinned pbpstats version used by the pilot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, cast
from unittest.mock import patch

from pbpstats.data_loader.stats_nba.enhanced_pbp.loader import (  # type: ignore[import-untyped]
    StatsNbaEnhancedPbpLoader,
)
from pbpstats.data_loader.stats_nba.possessions.file import (  # type: ignore[import-untyped]
    StatsNbaPossessionFileLoader,
)
from pbpstats.data_loader.stats_nba.possessions.loader import (  # type: ignore[import-untyped]
    StatsNbaPossessionLoader,
)
from pbpstats.resources.enhanced_pbp.stats_nba.start_of_period import (  # type: ignore[import-untyped]
    StatsStartOfPeriod,
)

from bil.data.pilot_inputs import GameBox, GameIssue, RawEvent, event_payload, shot_payload

PARSER_VERSION = "pbpstats-1.3.11-bil-v1"


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


def parse_game(
    game: GameBox,
    raw: dict[int, RawEvent],
    shots: dict[int, list[tuple[int, ...]]],
    scratch: Path,
) -> tuple[list[ParserEvent], list[ParserPossession]]:
    for folder in ("pbp", "game_details", "overrides"):
        (scratch / folder).mkdir(exist_ok=True)
    pbp_file = scratch / "pbp" / f"stats_{game.game_id}.json"
    pbp_file.write_text(json.dumps(event_payload(raw)), encoding="utf-8")
    for side, team_id in (("home", game.home_id), ("away", game.away_id)):
        if team_id not in shots:
            raise GameIssue("missing_shot_chart", f"Missing {side} shot chart")
        target = scratch / "game_details" / f"stats_{side}_shots_{game.game_id}.json"
        target.write_text(json.dumps(shot_payload(shots[team_id])), encoding="utf-8")

    # The pinned file parser may otherwise fall back to two live NBA endpoints.
    with (
        patch.object(
            StatsStartOfPeriod,
            "_get_starters_from_boxscore_request",
            side_effect=GameIssue("unresolved_starters", "Offline period starters are ambiguous"),
        ),
        patch.object(
            StatsNbaEnhancedPbpLoader,
            "_use_data_nba_event_order",
            side_effect=GameIssue("unresolved_event_order", "Offline event order is ambiguous"),
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
            # Resolve lazy parser properties while fallbacks are disabled.
            for event in events:
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
    return events, possessions
