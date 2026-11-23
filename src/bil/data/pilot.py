"""Capture and build the private 2022–23 possession pilot."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import duckdb

from bil.data.pilot_inputs import (
    GAME_PREFIXES,
    GameBox,
    GameIssue,
    PlayerBox,
    RawEvent,
    V3Game,
    box_scores,
    deduplicate_events,
    event_games,
    nba_game_id,
    shot_rows,
    v2_substitutions,
    v3_games,
)
from bil.data.pilot_normalize import MINUTES_TOLERANCE_MS, Row, Rows, located, normalize_game
from bil.data.pilot_output import read_game_reviews, write_tables
from bil.data.pilot_parser import PARSER_VERSION, ParserEvent, Starters, parse_game
from bil.data.pilot_sources import (
    ATTRIBUTION,
    NBA_TERMS,
    Artifact,
    capture_snapshot,
    load_snapshot,
    sha256_file,
    utc_now,
    write_json,
)
from bil.data.pilot_starters import choose_starters

SUFFIXES = {"regular": "", "playoffs": "_po"}


class PeriodScoreMismatch(GameIssue):
    def __init__(self, reconciled: int) -> None:
        super().__init__(
            "v3_period_score_mismatch", "V2 reconstructed period scores differ from V3"
        )
        self.reconciled = reconciled


def _ref(artifact: Artifact, locator: str) -> dict[str, str]:
    return {"artifact_id": artifact["artifact_id"], "locator": locator}


def _version(when: str, source_ids: list[Artifact], refs: list[dict[str, str]]) -> Row:
    return {
        "revision": 1,
        "available_at": max(
            (item["retrieved_at"] for item in source_ids), key=datetime.fromisoformat
        ),
        "availability_basis": "capture_bound",
        "ingested_at": when,
        "source_refs": refs,
        "change": "upsert",
    }


def _game_row(game: GameBox, kind: str, source: Artifact, when: str) -> Row:
    ref = _ref(source, f"game_id={game.game_id};home_and_away")
    return {
        "game_id": game.game_id,
        **_version(when, [source], [ref]),
        "league": "NBA",
        "season_start_year": 2022,
        "season_type": kind,
        "game_date": game.played_date.isoformat(),
        "date_basis": "played",
        "home_team_id": str(game.home_id),
        "away_team_id": str(game.away_id),
        "neutral_site": None,
        "status": "final",
        "scheduled_tip_at": None,
        "actual_tip_at": None,
        "finalized_at": None,
        "home_final": game.home_points,
        "away_final": game.away_points,
    }


def compare_periods(
    events: list[ParserEvent], game: GameBox, reference: dict[int, tuple[int, int]]
) -> tuple[bool, int]:
    scores = {
        event.period: (event.score.get(game.home_id, 0), event.score.get(game.away_id, 0))
        for event in events
    }
    return scores == reference, sum(
        scores.get(period) == score for period, score in reference.items()
    )


def _strata(events: list[RawEvent], periods: dict[int, tuple[int, int]]) -> list[str]:
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for raw in events:
        row = raw.fields
        groups[(row["PERIOD"], row["PCTIMESTRING"])].add(row["EVENTMSGTYPE"])
    labels = []
    if max(periods, default=0) > 4:
        labels.append("overtime")
    if any({"3", "8"} <= types for types in groups.values()):
        labels.append("same_clock_free_throw_substitution")
    if any(
        raw.fields["EVENTMSGTYPE"] == "3"
        and "technical"
        in (raw.fields["HOMEDESCRIPTION"] + raw.fields["VISITORDESCRIPTION"]).lower()
        for raw in events
    ):
        labels.append("technical_free_throw")
    return labels


def _issue_row(
    game_id: str, count: int, issue: GameIssue, severity: str, refs: list[dict[str, str]]
) -> Row:
    domain = "comparison"
    if (
        "clock" in issue.code
        or "order" in issue.code
        or "period" in issue.code
        and "v3" not in issue.code
    ):
        domain = "chronology"
    elif "lineup" in issue.code or "substitution" in issue.code or "starters" in issue.code:
        domain = "lineup"
    elif "score" in issue.code:
        domain = "score"
    elif "possession" in issue.code or issue.code == "parser_error":
        domain = "possession"
    return {
        "game_id": game_id,
        "stream_revision": 1,
        "issue_seq": count,
        "domain": domain,
        "code": issue.code,
        "severity": severity,
        "event_seq": None,
        "detail": str(issue),
        "source_refs": refs,
    }


def _build_game(
    game: GameBox,
    roster: dict[int, PlayerBox],
    events: list[RawEvent],
    shots: dict[int, list[tuple[int, ...]]],
    reference: V3Game | None,
    sources: list[Artifact],
    scratch: Path,
    snapshot_hash: str,
    when: str,
) -> Rows:
    kind = GAME_PREFIXES[game.game_id[:3]]
    raw_source = sources[2]
    refs = [_ref(source, f"game_id={game.game_id}") for source in sources]
    issues: list[Row] = []
    raw: dict[int, RawEvent] = {}
    rows: Rows = {}
    failure = None
    periods_reconciled = 0
    periods_match = None
    substitutions_match = None
    periods = reference.periods if reference is not None else {}
    final_match = periods[max(periods)] == (game.home_points, game.away_points) if periods else None
    labels = _strata(events, periods)
    try:
        if not events:
            raise GameIssue("missing_v2_game", "Expected game is absent from V2 events")
        if reference is None or final_match is not True:
            raise GameIssue("v3_box_final_mismatch", "V3 terminal score differs from the team box")
        raw = deduplicate_events(events)
        if len(raw) != len(events):
            labels.append("source_repeat")
            duplicates = [
                located(raw_source["artifact_id"], line)
                for event in raw.values()
                if len(event.row_numbers) > 1
                for line in event.row_numbers
            ]
            warning = GameIssue(
                "exact_source_repeat", f"{len(events) - len(raw)} rows deduplicated"
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", duplicates))
        substitutions_match = v2_substitutions(raw) == reference.substitutions
        if not substitutions_match:
            raise GameIssue("v3_substitution_mismatch", "V2 and V3 substitution signatures differ")
        order = reference.order

        def attempt(starters: Starters) -> tuple[list[ParserEvent], Rows, bool, int]:
            with TemporaryDirectory(dir=scratch) as game_directory:
                result = parse_game(game, raw, shots, Path(game_directory), order, starters)
                match, reconciled = compare_periods(result.events, game, periods)
                if not match:
                    raise PeriodScoreMismatch(reconciled)
                rows = normalize_game(
                    game,
                    roster,
                    raw,
                    result.events,
                    result.possessions,
                    raw_source["artifact_id"],
                    result.unresolved_possessions,
                )
            return result.events, rows, result.v3_order, reconciled

        try:
            choice = choose_starters(
                attempt, roster, lambda result: json.dumps(result[1], sort_keys=True, default=str)
            )
        except PeriodScoreMismatch as mismatch:
            periods_match, periods_reconciled = False, mismatch.reconciled
            raise
        parsed, rows, v3_order, periods_reconciled = choice.result
        periods_match = True
        if v3_order:
            labels.append("v3_event_order")
            warning = GameIssue(
                "v3_event_order_applied",
                "Parser rebound repairs failed; archived V3 action order replaced V2 order",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
        unresolved = sum(row["status"] == "unresolved" for row in rows["possession"])
        if unresolved:
            labels.append("unresolved_possessions")
            warning = GameIssue(
                "unresolved_possessions",
                f"{unresolved} possessions have unresolved offense: consecutive possessions "
                "share an offense or a score contradicts the recorded control",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
        if choice.immaterial:
            labels.append("immaterial_starters")
            warning = GameIssue(
                "immaterial_starters",
                f"All {choice.candidates_tried} candidate starter sets gave one reconstruction",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
        elif choice.starters:
            labels.append("inferred_starters")
            chosen = "; ".join(
                f"period {period} team {team}: {','.join(map(str, ids))}"
                for (period, team), ids in sorted(choice.starters.items())
            )
            warning = GameIssue(
                "inferred_starters",
                f"Only one of {choice.candidates_tried} candidate starter sets reconciled ({chosen})",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
        if [event.event_num for event in parsed] != list(raw):
            warning = GameIssue(
                "same_clock_parser_reorder", "Pinned parser reordered same-clock events"
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
    except GameIssue as error:
        rows = {}
        failure = error.code
        raw_event = raw.get(error.event_num) if error.event_num is not None else None
        failures = (
            refs
            if raw_event is None
            else [located(raw_source["artifact_id"], line) for line in raw_event.row_numbers]
        )
        issues.append(_issue_row(game.game_id, len(issues) + 1, error, "quarantine", failures))

    rows.update(
        game=[_game_row(game, kind, sources[0], when)],
        game_stream=[
            {
                "game_id": game.game_id,
                **_version(when, sources, refs),
                "official_game_revision": 1,
                "parser_version": PARSER_VERSION,
                "reconciliation_view_id": f"pinned-pilot:{snapshot_hash}:{game.game_id}",
                "observed_date": game.played_date.isoformat(),
                "complete": failure is None,
                "quality": "accepted" if failure is None else "quarantined",
                "event_count": len(rows.get("event", [])),
            }
        ],
        quality_issue=issues,
        game_review=[
            {
                "game_id": game.game_id,
                "season_type": kind,
                "accepted": failure is None,
                "reason": failure,
                "strata": labels,
                "v3_periods_reconciled": periods_reconciled,
                "v3_box_final_match": final_match,
                "v3_periods_match": periods_match,
                "v3_substitutions_match": substitutions_match,
            }
        ],
    )
    return rows


def _season_games(
    connection: duckdb.DuckDBPyConnection,
    snapshot_dir: Path,
    sources: dict[str, Artifact],
    chosen: set[str],
    scratch: Path,
    snapshot_hash: str,
    when: str,
) -> Iterator[Rows]:
    games, players = box_scores(connection, snapshot_dir)
    expected = chosen or set(games)
    if expected - games.keys():
        raise ValueError("Requested games must exist in the regular season or playoff box logs")

    for season_type, suffix in SUFFIXES.items():
        wanted = {game_id for game_id in expected if GAME_PREFIXES[game_id[:3]] == season_type}
        if not wanted:
            continue
        raw_name = f"nbastats{suffix}_2022.tar.xz"
        shot_name = f"shotdetail{suffix}_2022.tar.xz"
        v3_name = f"nbastatsv3{suffix}_2022.tar.xz"
        shots = shot_rows(snapshot_dir / shot_name)
        reference_games = v3_games(snapshot_dir / v3_name)
        refs = [
            sources[key]
            for key in (
                "team_game_logs.parquet",
                "player_game_logs.parquet",
                raw_name,
                shot_name,
                v3_name,
            )
        ]
        remaining = set(wanted)
        for game_id, events in event_games(snapshot_dir / raw_name):
            if game_id not in games or GAME_PREFIXES[game_id[:3]] != season_type:
                raise ValueError(f"Unexpected V2 game for {season_type}: {game_id}")
            if game_id in wanted:
                yield _build_game(
                    games[game_id],
                    players[game_id],
                    events,
                    shots.get(game_id, {}),
                    reference_games.get(game_id),
                    refs,
                    scratch,
                    snapshot_hash,
                    when,
                )
                remaining.remove(game_id)
        for game_id in sorted(remaining):
            yield _build_game(
                games[game_id],
                players[game_id],
                [],
                {},
                reference_games.get(game_id),
                refs,
                scratch,
                snapshot_hash,
                when,
            )


def _tally_review(counts: Counter[str], row: Row) -> None:
    counts["expected"] += 1
    counts["accepted"] += int(row["accepted"] is True)
    counts["quarantined"] += int(row["accepted"] is False)
    counts["v3_periods_reconciled"] += cast(int, row["v3_periods_reconciled"])
    for name in ("v3_box_final", "v3_periods", "v3_substitutions"):
        match = row[f"{name}_match"]
        counts[f"{name}_checked"] += int(match is not None)
        counts[f"{name}_matched"] += int(match is True)
        counts[f"{name}_mismatched"] += int(match is False)
        counts[f"{name}_not_checked"] += int(match is None)


def summarize_reviews(reviews: list[Row]) -> dict[str, object]:
    coverage: dict[str, Counter[str]] = defaultdict(Counter)
    strata: dict[str, Counter[str]] = defaultdict(Counter)
    reasons: Counter[str] = Counter()
    for row in reviews:
        kind = str(row["season_type"])
        _tally_review(coverage[kind], row)
        if not row["accepted"]:
            reasons[str(row["reason"])] += 1
        for label in cast(list[str], row["strata"]):
            _tally_review(strata[f"{kind}:{label}"], row)
    return {
        "coverage": dict(coverage),
        "comparison_strata": dict(strata),
        "quarantine_reasons": dict(reasons),
    }


def build_pilot(
    snapshot_dir: Path, output: Path, code_commit: str, chosen: set[str] | None = None
) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise ValueError("Record a full Git commit for the pilot build")
    snapshot = load_snapshot(snapshot_dir)
    snapshot_hash = sha256_file(snapshot_dir / "snapshot.json")
    sources = {row["name"]: row for row in snapshot["artifacts"]}
    when = utc_now()
    output.mkdir(mode=0o700, parents=True)
    try:
        with TemporaryDirectory(dir=output.parent) as temp, duckdb.connect() as connection:
            connection.execute("SET TimeZone = 'UTC'")
            staging = Path(temp)
            connection.execute("SET temp_directory = ?", [str(staging / "duckdb-spill")])
            games = _season_games(
                connection, snapshot_dir, sources, chosen or set(), staging, snapshot_hash, when
            )
            artifacts = write_tables(connection, games, staging, output)
            results = summarize_reviews(read_game_reviews(connection, output))
        manifest: dict[str, object] = {
            "schema_version": 1,
            "season_start_year": 2022,
            "selected_game_ids": sorted(chosen) if chosen else None,
            "code_commit": code_commit,
            "generated_at": when,
            "parser": PARSER_VERSION,
            "duckdb_version": version("duckdb"),
            "source_snapshot_sha256": snapshot_hash,
            "source_artifacts": snapshot["artifacts"],
            "output_artifacts": artifacts,
            "attribution": ATTRIBUTION,
            "terms": NBA_TERMS,
            "availability": "retrospective_capture_bound",
            "minutes_tolerance_ms": MINUTES_TOLERANCE_MS,
            **results,
        }
        write_json(output / "manifest.json", manifest)
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    subcommands = cli.add_subparsers(dest="action", required=True)
    capture = subcommands.add_parser("capture", help="capture all pinned source bytes")
    capture.add_argument("snapshot_dir", type=Path)
    build = subcommands.add_parser("build", help="create a new, independently reconciled dataset")
    build.add_argument("snapshot_dir", type=Path)
    build.add_argument("output_dir", type=Path)
    build.add_argument("--code-commit", required=True)
    build.add_argument("--game-id", action="append", type=nba_game_id)
    args = cli.parse_args()
    if args.action == "capture":
        snapshot = capture_snapshot(args.snapshot_dir)
        print(f"Verified {len(snapshot['artifacts'])} private inputs. {ATTRIBUTION}.")
    else:
        manifest = build_pilot(
            args.snapshot_dir, args.output_dir, args.code_commit, set(args.game_id or [])
        )
        print(json.dumps(manifest["coverage"], sort_keys=True))


if __name__ == "__main__":
    main()
