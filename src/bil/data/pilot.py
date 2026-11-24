"""Capture and build the private possession pilot for one pinned season at a time."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import duckdb

from bil.data.pilot_check import check_build, check_seasons
from bil.data.pilot_evidence import compare as compare_evidence
from bil.data.pilot_inputs import (
    GAME_PREFIXES,
    CrossFeed,
    GameBox,
    GameIssue,
    PlayerBox,
    RawEvent,
    V3Game,
    box_scores,
    cross_feeds,
    deduplicate_events,
    designate_home,
    event_games,
    nba_game_id,
    shot_rows,
    v2_substitutions,
    v3_games,
)
from bil.data.pilot_normalize import MINUTES_TOLERANCE_MS, Row, Rows, located, normalize_game
from bil.data.pilot_order import OrderRepair, repair_order
from bil.data.pilot_output import read_game_reviews, write_tables
from bil.data.pilot_parser import PARSER_VERSION, ParserEvent, Starters, parse_game
from bil.data.pilot_sources import (
    ATTRIBUTION,
    LIVEDATA,
    NBA_TERMS,
    Artifact,
    capture_snapshot,
    datanba_has_order,
    has_datanba,
    has_livedata,
    load_snapshot,
    season_evidence_sources,
    sha256_file,
    utc_now,
    write_json,
)
from bil.data.pilot_starters import StarterChoice, choose_starters

SUFFIXES = {"regular": "", "playoffs": "_po"}


@dataclass(frozen=True)
class Reconstruction:
    events: list[ParserEvent]
    rows: Rows
    v3_order: bool
    periods_reconciled: int
    # True when V3 alone disagreed on period scores and liveData and data.nba agreed with V2.
    v3_period_defect: bool
    livedata_starters: frozenset[tuple[int, int]]
    relabeled_possessions: int


def period_scores(events: list[ParserEvent], game: GameBox) -> dict[int, tuple[int, int]]:
    return {
        event.period: (event.score.get(game.home_id, 0), event.score.get(game.away_id, 0))
        for event in events
    }


def v3_alone_differs(
    ours: dict[int, tuple[int, int]], reference: dict[int, tuple[int, int]], cross: CrossFeed
) -> bool:
    """True when every period V3 disputes is confirmed by both liveData and data.nba."""
    disputed = [period for period in reference if ours.get(period) != reference[period]]
    return bool(disputed) and all(
        ours.get(period) is not None
        and ours.get(period) == cross.live_periods.get(period) == cross.datanba_periods.get(period)
        for period in disputed
    )


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


def _game_row(
    game: GameBox, kind: str, source: Artifact, when: str, season_start_year: int = 2022
) -> Row:
    ref = _ref(source, f"game_id={game.game_id};home_and_away")
    return {
        "game_id": game.game_id,
        **_version(when, [source], [ref]),
        "league": "NBA",
        "season_start_year": season_start_year,
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


def _unresolved(rows: Rows) -> int:
    return sum(row["status"] == "unresolved" for row in rows["possession"])


def _offer_repair(
    choice: StarterChoice[Reconstruction],
    raw: dict[int, RawEvent],
    order: dict[int, int],
    reconstruct: Callable[[bool, dict[int, RawEvent], list[int]], StarterChoice[Reconstruction]],
) -> tuple[StarterChoice[Reconstruction], dict[int, RawEvent], OrderRepair] | None:
    """Reparse in data.nba entry order when that leaves strictly fewer unresolved possessions.

    Unresolved possessions are the hard-gate metric (ADR-0023 flags this selection).
    """
    current = _unresolved(choice.result.rows)
    candidate = repair_order(raw, order) if current else None
    if candidate is None:
        return None
    try:
        alternative = reconstruct(False, candidate.events, list(candidate.events))
    except GameIssue:
        return None
    if _unresolved(alternative.result.rows) < current:
        return alternative, candidate.events, candidate
    return None


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
    cross: CrossFeed | None = None,
    season_start_year: int = 2022,
    order_repair: bool = False,
) -> Rows:
    kind = GAME_PREFIXES[game.game_id[:3]]
    cross = cross or CrossFeed()
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
    labels = _strata(events, periods)
    if not cross.has_livedata:
        # Weaker-verification stratum: no liveData starters or V3 period-defect adjudication.
        labels.append("no_livedata")
    if not has_datanba(season_start_year):
        # Weaker-verification stratum: no data.nba offense relabels, period scores or order.
        labels.append("no_datanba")
    undesignated = not game.home_designated
    if undesignated:
        # The box log has no home flag for either team. V2's description columns designate
        # the sides, and the V3 terminal-score check below confirms them against the box.
        designated = designate_home(game, events)
        if designated is not None:
            game = designated
            labels.append("v2_home_designation")
            warning = GameIssue(
                "v2_home_designation",
                "Box log has no home flag; V2 description columns designated the home team",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
    final_match = periods[max(periods)] == (game.home_points, game.away_points) if periods else None
    try:
        if not events:
            raise GameIssue("missing_v2_game", "Expected game is absent from V2 events")
        if not game.home_designated:
            raise GameIssue(
                "unresolved_home_designation",
                "Box log has no home flag and V2 does not designate the home team",
            )
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

        def reconstruct(
            primary: bool,
            stream: dict[int, RawEvent] = raw,
            archived: list[int] = order,
        ) -> StarterChoice[Reconstruction]:
            def attempt(starters: Starters) -> Reconstruction:
                with TemporaryDirectory(dir=scratch) as game_directory:
                    result = parse_game(
                        game,
                        stream,
                        shots,
                        Path(game_directory),
                        archived,
                        starters,
                        primary_order=archived if primary else None,
                        between_periods=cross.between_periods if cross.has_livedata else None,
                    )
                    match, reconciled = compare_periods(result.events, game, periods)
                    defect = not match and v3_alone_differs(
                        period_scores(result.events, game), periods, cross
                    )
                    if not match and not defect:
                        raise PeriodScoreMismatch(reconciled)
                    report: dict[str, int] = {}
                    rows = normalize_game(
                        game,
                        roster,
                        stream,
                        result.events,
                        result.possessions,
                        raw_source["artifact_id"],
                        result.unresolved_possessions,
                        cross.offense or None,
                        report,
                    )
                return Reconstruction(
                    result.events,
                    rows,
                    result.v3_order,
                    reconciled,
                    defect,
                    result.livedata_starters,
                    report.get("relabeled_possessions", 0),
                )

            return choose_starters(
                attempt, roster, lambda result: json.dumps(result.rows, sort_keys=True, default=str)
            )

        v3_primary = False
        reordered: OrderRepair | None = None
        try:
            choice = reconstruct(primary=False)
        except GameIssue as first:
            # Last resort: parse in archived V3 action order. Every check still applies,
            # including the guard against moving events across V2 clocks.
            try:
                choice = reconstruct(primary=True)
                v3_primary = True
            except GameIssue:
                # Opt-in last resort (ADR-0023, proposed): follow data.nba's entry order and
                # re-clock late-entered events. Every check still applies to the new stream.
                repaired = repair_order(raw, cross.order) if order_repair else None
                if repaired is not None:
                    try:
                        choice = reconstruct(False, repaired.events, list(repaired.events))
                        raw = repaired.events
                        reordered = repaired
                    except GameIssue:
                        repaired = None
                if repaired is None:
                    if isinstance(first, PeriodScoreMismatch):
                        periods_match, periods_reconciled = False, first.reconciled
                    raise first from None
        if order_repair and reordered is None and cross.order:
            # Also offer data.nba entry order to accepted games with unresolved possessions.
            # All checks apply to both streams. The repaired stream replaces a V3-primary or
            # V2-order choice alike, so it also clears the V3-primary label.
            offered = _offer_repair(choice, raw, cross.order, reconstruct)
            if offered is not None:
                choice, raw, reordered = offered
                v3_primary = False
        built = choice.result
        parsed, rows, v3_order = built.events, built.rows, built.v3_order
        periods_reconciled = built.periods_reconciled
        periods_match = not built.v3_period_defect
        if built.v3_period_defect:
            labels.append("v3_period_defect")
            warning = GameIssue(
                "v3_period_defect",
                "V3 alone disagrees on period scores; liveData and data.nba agree with V2",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
        if built.livedata_starters:
            labels.append("livedata_starters")
            settled = "; ".join(
                f"period {period} team {team}" for period, team in sorted(built.livedata_starters)
            )
            warning = GameIssue(
                "livedata_starters",
                f"Starters from liveData between-period substitutions ({settled})",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
        if built.relabeled_possessions:
            labels.append("datanba_possession_labels")
            warning = GameIssue(
                "datanba_possession_labels",
                f"{built.relabeled_possessions} unresolved possessions labeled from data.nba "
                "offense on every shot, free throw and turnover",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
        if reordered is not None:
            labels.append("datanba_event_order")
            shifts = [abs(shift) for _, _, shift in reordered.clamped.values()]
            warning = GameIssue(
                "datanba_event_order",
                f"{len(shifts)} late-entered events placed in data.nba entry order and "
                f"re-clocked to their predecessor's clock (largest shift {max(shifts, default=0):g} s)",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
        if v3_primary:
            labels.append("v3_primary_order")
            warning = GameIssue(
                "v3_primary_order",
                "V2 file order failed acceptance; the game was parsed in archived V3 action order",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
        if v3_order:
            labels.append("v3_event_order")
            warning = GameIssue(
                "v3_event_order_applied",
                "Parser rebound repairs failed; archived V3 action order replaced V2 order",
            )
            issues.append(_issue_row(game.game_id, len(issues) + 1, warning, "warning", refs))
        recredited = sum(
            row["attribution_rule"] == "same_clock_box_credit" for row in rows["score_allocation"]
        )
        if recredited:
            labels.append("same_clock_box_credit")
            warning = GameIssue(
                "same_clock_box_credit",
                f"{recredited} scores credited to another lineup state at the same clock "
                "to match box plus-minus",
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

    game_row = _game_row(game, kind, sources[0], when, season_start_year)
    if not game.home_designated:
        # The orientation is only provisional (team-ID order), so do not export it as fact.
        for field in ("home_team_id", "away_team_id", "home_final", "away_final"):
            game_row[field] = None
    rows.update(
        game=[game_row],
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
    season_start_year: int = 2022,
    order_repair: bool = False,
) -> Iterator[Rows]:
    games, players = box_scores(connection, snapshot_dir)
    expected = chosen or set(games)
    if expected - games.keys():
        raise ValueError("Requested games must exist in the regular season or playoff box logs")
    year = season_start_year

    for season_type, suffix in SUFFIXES.items():
        wanted = {game_id for game_id in expected if GAME_PREFIXES[game_id[:3]] == season_type}
        if not wanted:
            continue
        raw_name = f"nbastats{suffix}_{year}.tar.xz"
        shot_name = f"shotdetail{suffix}_{year}.tar.xz"
        v3_name = f"nbastatsv3{suffix}_{year}.tar.xz"
        # liveData is absent from the pinned archive before 2020–21 (issue #51).
        live_name = f"{LIVEDATA}{suffix}_{year}.tar.xz" if has_livedata(year) else None
        # data.nba.com is likewise absent from the pinned archive before 2016–17.
        datanba_name = f"datanba{suffix}_{year}.tar.xz" if has_datanba(year) else None
        shots = shot_rows(snapshot_dir / shot_name)
        reference_games = v3_games(snapshot_dir / v3_name)
        feeds = cross_feeds(
            snapshot_dir / live_name if live_name else None,
            snapshot_dir / datanba_name if datanba_name else None,
            datanba_has_order(year),
        )
        refs = [
            sources[key]
            for key in (
                "team_game_logs.parquet",
                "player_game_logs.parquet",
                raw_name,
                shot_name,
                v3_name,
                live_name,
                datanba_name,
            )
            if key is not None
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
                    feeds.get(game_id),
                    year,
                    order_repair,
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
                feeds.get(game_id),
                year,
                order_repair,
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
    snapshot_dir: Path,
    output: Path,
    code_commit: str,
    chosen: set[str] | None = None,
    order_repair: bool = False,
) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise ValueError("Record a full Git commit for the pilot build")
    snapshot = load_snapshot(snapshot_dir)
    year = snapshot["season_start_year"]
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
                connection,
                snapshot_dir,
                sources,
                chosen or set(),
                staging,
                snapshot_hash,
                when,
                year,
                order_repair=order_repair,
            )
            artifacts = write_tables(connection, games, staging, output)
            results = summarize_reviews(read_game_reviews(connection, output))
        manifest: dict[str, object] = {
            "schema_version": 1,
            "season_start_year": year,
            "selected_game_ids": sorted(chosen) if chosen else None,
            "code_commit": code_commit,
            "generated_at": when,
            "parser": PARSER_VERSION,
            "duckdb_version": version("duckdb"),
            **({"order_repair": True} if order_repair else {}),
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
    build = subcommands.add_parser("build", help="create a new, independently reconciled dataset")
    build.add_argument("snapshot_dir", type=Path)
    build.add_argument("output_dir", type=Path)
    build.add_argument("--code-commit", required=True)
    build.add_argument("--game-id", action="append", type=nba_game_id)
    build.add_argument(
        "--order-repair",
        action="store_true",
        help="experimental: retry failed games in data.nba entry order (ADR-0023, proposed)",
    )
    evidence = subcommands.add_parser(
        "capture-evidence", help="capture pinned comparison feeds that never enter a build"
    )
    for parser in (capture, evidence):
        parser.add_argument("snapshot_dir", type=Path)
        parser.add_argument(
            "--season",
            type=int,
            default=2022,
            help="season start year with pinned sources (default 2022, meaning 2022–23)",
        )
        parser.add_argument(
            "--from-local",
            type=Path,
            help="copy and verify already captured bytes from this directory; no network",
        )
    compare = subcommands.add_parser(
        "evidence", help="compare an exported build with the pinned evidence feeds"
    )
    compare.add_argument("output_dir", type=Path)
    compare.add_argument("snapshot_dir", type=Path)
    compare.add_argument("evidence_dir", type=Path)
    compare.add_argument("--report", type=Path, help="write the full JSON report here")
    check = subcommands.add_parser("check", help="check an exported build's invariants")
    check.add_argument("output_dir", type=Path)
    check.add_argument("snapshot_dir", type=Path)
    seasons = subcommands.add_parser(
        "check-seasons", help="check identity and chronology across several season builds"
    )
    seasons.add_argument(
        "pairs", nargs="+", type=Path, help="each build directory followed by its snapshot"
    )
    args = cli.parse_args()
    if args.action == "check":
        results = check_build(args.output_dir, args.snapshot_dir)
        failed = {name: count for name, count in results.items() if count}
        for name, count in results.items():
            print(f"{'FAIL' if count else 'ok  '} {name}: {count}")
        print(f"{len(results) - len(failed)} of {len(results)} checks passed.")
        if failed:
            raise SystemExit(1)
    elif args.action == "check-seasons":
        if len(args.pairs) % 2:
            raise SystemExit("Pass a snapshot directory after each build directory")
        violations, roster = check_seasons(list(zip(args.pairs[::2], args.pairs[1::2])))
        for name, count in violations.items():
            print(f"{'FAIL' if count else 'ok  '} {name}: {count}")
        print(json.dumps(roster, sort_keys=True))
        if any(violations.values()):
            raise SystemExit(1)
    elif args.action == "evidence":
        recorded = json.loads((args.output_dir / "manifest.json").read_text(encoding="utf-8"))
        year = recorded["season_start_year"]
        load_snapshot(args.evidence_dir, season_evidence_sources(year), year)
        if recorded["source_snapshot_sha256"] != sha256_file(args.snapshot_dir / "snapshot.json"):
            raise SystemExit("The build was not made from this source snapshot")
        report = compare_evidence(args.output_dir, args.snapshot_dir, args.evidence_dir, year)
        if args.report:
            write_json(args.report, report)
        print(json.dumps(report, indent=2, default=str))
    elif args.action == "capture-evidence":
        snapshot = capture_snapshot(
            args.snapshot_dir,
            season_evidence_sources(args.season),
            args.season,
            args.from_local,
        )
        print(f"Verified {len(snapshot['artifacts'])} private evidence files. {ATTRIBUTION}.")
    elif args.action == "capture":
        snapshot = capture_snapshot(args.snapshot_dir, None, args.season, args.from_local)
        print(f"Verified {len(snapshot['artifacts'])} private inputs. {ATTRIBUTION}.")
    else:
        manifest = build_pilot(
            args.snapshot_dir,
            args.output_dir,
            args.code_commit,
            set(args.game_id or []),
            args.order_repair,
        )
        print(json.dumps(manifest["coverage"], sort_keys=True))


if __name__ == "__main__":
    main()
