"""Write typed Parquet tables and a content-addressed output inventory."""

from __future__ import annotations

import json
from collections.abc import Iterable
from contextlib import ExitStack
from pathlib import Path
from typing import TypedDict

import duckdb

from bil.data.pilot_normalize import Row, Rows
from bil.data.pilot_sources import sha256_file

REFS = "STRUCT(artifact_id VARCHAR, locator VARCHAR)[]"
SCOPE = {"game_id": "VARCHAR", "stream_revision": "INTEGER"}
VERSIONS = {
    "revision": "INTEGER",
    "available_at": "TIMESTAMPTZ",
    "availability_basis": "VARCHAR",
    "ingested_at": "TIMESTAMPTZ",
    "source_refs": REFS,
    "change": "VARCHAR",
}

TABLES = {
    "game": {
        "game_id": "VARCHAR",
        **VERSIONS,
        "league": "VARCHAR",
        "season_start_year": "SMALLINT",
        "season_type": "VARCHAR",
        "game_date": "DATE",
        "date_basis": "VARCHAR",
        "home_team_id": "VARCHAR",
        "away_team_id": "VARCHAR",
        "neutral_site": "BOOLEAN",
        "status": "VARCHAR",
        "scheduled_tip_at": "TIMESTAMPTZ",
        "actual_tip_at": "TIMESTAMPTZ",
        "finalized_at": "TIMESTAMPTZ",
        "home_final": "SMALLINT",
        "away_final": "SMALLINT",
    },
    "game_stream": {
        "game_id": "VARCHAR",
        **VERSIONS,
        "official_game_revision": "INTEGER",
        "parser_version": "VARCHAR",
        "reconciliation_view_id": "VARCHAR",
        "observed_date": "DATE",
        "complete": "BOOLEAN",
        "quality": "VARCHAR",
        "event_count": "INTEGER",
    },
    "event": {
        **SCOPE,
        "seq": "INTEGER",
        "period": "SMALLINT",
        "remaining_ms": "INTEGER",
        "elapsed_ms": "INTEGER",
        "observed_at": "TIMESTAMPTZ",
        "kind": "VARCHAR",
        "team_id": "VARCHAR",
        "home_delta": "SMALLINT",
        "away_delta": "SMALLINT",
        "revises_seq": "INTEGER",
        "source_event_id": "VARCHAR",
        "source_refs": REFS,
    },
    "event_actor": {
        **SCOPE,
        "seq": "INTEGER",
        "slot": "SMALLINT",
        "role": "VARCHAR",
        "player_id": "VARCHAR",
        "team_id": "VARCHAR",
        "source_slot": "VARCHAR",
        "raw_actor_id": "VARCHAR",
    },
    "lineup": {
        **SCOPE,
        "lineup_id": "VARCHAR",
        "team_id": "VARCHAR",
        "player_ids": "VARCHAR[]",
    },
    "stint": {
        **SCOPE,
        "stint_seq": "INTEGER",
        "period": "SMALLINT",
        "start_seq": "INTEGER",
        "end_seq": "INTEGER",
        "start_elapsed_ms": "INTEGER",
        "end_elapsed_ms": "INTEGER",
        "home_lineup_id": "VARCHAR",
        "away_lineup_id": "VARCHAR",
    },
    "possession": {
        **SCOPE,
        "possession_seq": "INTEGER",
        "period": "SMALLINT",
        "start_seq": "INTEGER",
        "end_seq": "INTEGER",
        "offense_team_id": "VARCHAR",
        "defense_team_id": "VARCHAR",
        "end_reason": "VARCHAR",
        "status": "VARCHAR",
    },
    "score_allocation": {
        **SCOPE,
        "seq": "INTEGER",
        "scoring_team_id": "VARCHAR",
        "points_delta": "SMALLINT",
        "possession_seq": "INTEGER",
        "credited_stint_seq": "INTEGER",
        "possession_reason": "VARCHAR",
        "attribution_rule": "VARCHAR",
    },
    "quality_issue": {
        **SCOPE,
        "issue_seq": "INTEGER",
        "domain": "VARCHAR",
        "code": "VARCHAR",
        "severity": "VARCHAR",
        "event_seq": "INTEGER",
        "detail": "VARCHAR",
        "source_refs": REFS,
    },
    "game_review": {
        "game_id": "VARCHAR",
        "season_type": "VARCHAR",
        "accepted": "BOOLEAN",
        "reason": "VARCHAR",
        "strata": "VARCHAR[]",
        "v3_periods_reconciled": "INTEGER",
        "v3_box_final_match": "BOOLEAN",
        "v3_periods_match": "BOOLEAN",
        "v3_substitutions_match": "BOOLEAN",
    },
}


class OutputArtifact(TypedDict):
    filename: str
    sha256: str
    size_bytes: int
    row_count: int


def write_tables(
    connection: duckdb.DuckDBPyConnection,
    tables_by_game: Iterable[Rows],
    staging: Path,
    output: Path,
) -> list[OutputArtifact]:
    counts = dict.fromkeys(TABLES, 0)
    with ExitStack() as stack:
        files = {
            name: stack.enter_context((staging / f"{name}.jsonl").open("x", encoding="utf-8"))
            for name in TABLES
        }
        for batch in tables_by_game:
            for name, rows in batch.items():
                expected = TABLES[name].keys()
                for row in rows:
                    if row.keys() != expected:
                        raise ValueError(f"Invalid output fields for {name}")
                    files[name].write(json.dumps(row, ensure_ascii=False) + "\n")
                counts[name] += len(rows)

    artifacts: list[OutputArtifact] = []
    for name, columns in TABLES.items():
        destination = output / f"{name}.parquet"
        if counts[name]:
            column_types = ", ".join(f"'{key}': '{value}'" for key, value in columns.items())
            connection.execute(
                f"COPY (SELECT * FROM read_json(?, format='newline_delimited', "
                f"columns={{{column_types}}})) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                [str(staging / f"{name}.jsonl"), str(destination)],
            )
        else:
            fields = ", ".join(
                f"CAST(NULL AS {sql_type}) AS {key}" for key, sql_type in columns.items()
            )
            connection.execute(
                f"COPY (SELECT {fields} WHERE false) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                [str(destination)],
            )
        artifacts.append(
            OutputArtifact(
                filename=destination.name,
                sha256=sha256_file(destination),
                size_bytes=destination.stat().st_size,
                row_count=counts[name],
            )
        )
    return artifacts


def read_game_reviews(connection: duckdb.DuckDBPyConnection, output: Path) -> list[Row]:
    cursor = connection.execute(
        "SELECT * FROM read_parquet(?) ORDER BY game_id",
        [str(output / "game_review.parquet")],
    )
    columns = list(TABLES["game_review"])
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
