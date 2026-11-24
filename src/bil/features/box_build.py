"""Build private 2022–23 box-score feature views from the pinned `issue-5-v2` game logs.

Writes same-window (retrospective), dated retrospective and strict as-of views plus a manifest.
Inputs and outputs stay outside Git. Source data are for private, noncommercial research only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from datetime import date
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb

from bil.data.pilot_inputs import nba_game_id
from bil.data.pilot_sources import (
    ATTRIBUTION,
    NBA_TERMS,
    Snapshot,
    load_snapshot,
    sha256_file,
    utc_now,
    write_json,
)
from bil.evaluation.eligibility import eastern_origin
from bil.features.box import (
    COUNT_FIELDS,
    FEATURE_VERSION,
    FEATURES,
    MS_PER_36,
    Appearance,
    FeatureValue,
    Provenance,
    aggregate,
    capture_bound_revisions,
    history_rows,
    same_window,
    snapshot_instant,
    strict_history,
)

PLAYER_LOG = "player_game_logs.parquet"
TEAM_LOG = "team_game_logs.parquet"
SEASON_TYPES = ("regular", "playoffs")
# Measured by the #63 DuckDB profile of the pinned logs (contract "Measured inputs").
EXPECTED = {
    "appearances": 27_622,
    "appearances_regular": 25_894,
    "appearances_playoffs": 1_728,
    "players_regular": 539,
    "players_playoffs": 217,
    "multi_team_players": 71,
    "games": 1_314,
    "zero_fga": 1_378,
    "zero_fg3a": 6_016,
    "zero_fta": 12_102,
    "zero_minutes": 2,
}
NULLABLE = ("fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pts", "oreb", "dreb", "ast", "tov")
FEATURE_SCHEMA = {
    "snapshot_id": "VARCHAR",
    "feature_code": "VARCHAR",
    "feature_definition_version": "VARCHAR",
    "player_id": "VARCHAR",
    "numerator": "BIGINT",
    "denominator": "BIGINT",
    "value": "DOUBLE",
    "covered_appearances": "INTEGER",
    "eligible_appearances": "INTEGER",
    "coverage": "DOUBLE",
}
TABLES: dict[str, dict[str, str]] = {
    "appearances": {
        "game_id": "VARCHAR",
        "player_id": "VARCHAR",
        "team_id": "VARCHAR",
        "opp_team_id": "VARCHAR",
        "season_type": "VARCHAR",
        "game_date": "DATE",
        "minutes_ms": "BIGINT",
        **dict.fromkeys(COUNT_FIELDS, "INTEGER"),
    },
    "same_window_features": {
        "window_id": "VARCHAR",
        "season_types": "VARCHAR",
        "start_date": "DATE",
        "end_date": "DATE",
        "minutes_ms": "BIGINT",
        "points": "BIGINT",
        "games_with_time": "INTEGER",
        **FEATURE_SCHEMA,
    },
    "asof_retrospective_features": {
        "game_id": "VARCHAR",
        "game_date": "DATE",
        "rating_date": "DATE",
        "cutoff_utc": "TIMESTAMPTZ",
        "history_season_type": "VARCHAR",
        "minutes_ms": "BIGINT",
        "points": "BIGINT",
        "games_with_time": "INTEGER",
        **FEATURE_SCHEMA,
    },
    "asof_strict_features": {
        "game_id": "VARCHAR",
        "game_date": "DATE",
        "rating_date": "DATE",
        "cutoff_utc": "TIMESTAMPTZ",
        "history_season_type": "VARCHAR",
        "cohort_status": "VARCHAR",
        "minutes_ms": "BIGINT",
        "points": "BIGINT",
        "games_with_time": "INTEGER",
        **FEATURE_SCHEMA,
    },
}


def load_appearances(
    connection: duckdb.DuckDBPyConnection, directory: Path
) -> tuple[list[Appearance], dict[str, int]]:
    """Read, scope and validate player appearances. Raises on any identity violation."""
    teams = {
        (game_id, team_id): (game_date, opp, home)
        for game_id, team_id, opp, game_date, home in connection.execute(
            "SELECT game_id, team_id, opp_team_id, game_date, home FROM read_parquet(?) "
            "WHERE left(game_id, 3) IN ('002', '004')",
            [str(directory / TEAM_LOG)],
        ).fetchall()
    }
    columns = ", ".join(
        (
            "season",
            "game_id",
            "player_id",
            "team_id",
            "opp_team_id",
            "game_date",
            "min",
            "reb",
            *COUNT_FIELDS,
        )
    )
    cursor = connection.execute(
        f"SELECT {columns} FROM read_parquet(?) WHERE left(game_id, 3) IN ('002', '004') "
        "ORDER BY game_id, player_id",
        [str(directory / PLAYER_LOG)],
    )
    names = [d[0] for d in cursor.description]
    rows: list[Appearance] = []
    seen: set[tuple[str, str]] = set()
    problems: Counter[str] = Counter()
    for values in cursor.fetchall():
        raw = dict(zip(names, values, strict=True))
        game_id = nba_game_id(raw["game_id"])
        key = (game_id, raw["player_id"])
        if key in seen or int(raw["player_id"]) <= 0:
            problems["invalid_or_duplicate_key"] += 1
        seen.add(key)
        if raw["season"] != 2023:
            problems["season"] += 1
        own = teams.get((game_id, raw["team_id"]))
        other = teams.get((game_id, raw["opp_team_id"]))
        if (
            own is None
            or other is None
            or own[0] != raw["game_date"]
            or other[0] != raw["game_date"]
            or own[1] != raw["opp_team_id"]
            or other[1] != raw["team_id"]
            or own[2] == other[2]
        ):
            problems["team_join"] += 1
        minutes = raw["min"]
        if minutes is None or not math.isfinite(minutes) or minutes < 0:
            problems["minutes"] += 1
            continue
        for name in COUNT_FIELDS:
            if raw[name] is not None and raw[name] < 0:
                problems["negative_count"] += 1
        _identities(raw, problems)
        rows.append(Appearance.from_record({**raw, "game_id": game_id, "min": minutes}))
    if problems:
        raise ValueError(f"Box-score appearances violate the feature contract: {dict(problems)}")
    return rows, {"source_rows": len(seen)}


def _identities(raw: dict[str, Any], problems: Counter[str]) -> None:
    def known(*names: str) -> bool:
        return all(raw[name] is not None for name in names)

    checks: tuple[tuple[tuple[str, ...], Callable[[], bool]], ...] = (
        (("fgm", "fga"), lambda: raw["fgm"] <= raw["fga"]),
        (("fg3m", "fg3a"), lambda: raw["fg3m"] <= raw["fg3a"]),
        (("fgm", "fg3m"), lambda: raw["fg3m"] <= raw["fgm"]),
        (("fga", "fg3a"), lambda: raw["fg3a"] <= raw["fga"]),
        (
            ("fgm", "fga", "fg3m", "fg3a"),
            lambda: raw["fgm"] - raw["fg3m"] <= raw["fga"] - raw["fg3a"],
        ),
        (("ftm", "fta"), lambda: raw["ftm"] <= raw["fta"]),
        (
            ("pts", "fgm", "fg3m", "ftm"),
            lambda: raw["pts"] == 2 * raw["fgm"] + raw["fg3m"] + raw["ftm"],
        ),
        (("reb", "oreb", "dreb"), lambda: raw["reb"] == raw["oreb"] + raw["dreb"]),
    )
    for names, holds in checks:
        if known(*names) and not holds():
            problems["identity:" + "/".join(names)] += 1


# Independent SQL restatement of the contract table: (numerator, denominator, scale).
SQL_FEATURES: dict[str, tuple[str, str, int]] = {
    "fg2_pct": ("fgm - fg3m", "fga - fg3a", 1),
    "fg3_pct": ("fg3m", "fg3a", 1),
    "ft_pct": ("ftm", "fta", 1),
    "fg3_share": ("fg3a", "fga", 1),
    **{f"{k}_per_36": (k, "ms", MS_PER_36) for k in ("fga", "fta", "ast", "tov", "oreb")},
    **{f"{k}_per_36": (k, "ms", MS_PER_36) for k in ("dreb", "stl", "blk", "pf")},
}


def reconcile(
    connection: duckdb.DuckDBPyConnection,
    directory: Path,
    output: Path,
    rows: list[Appearance],
    expected: Mapping[str, int] | None,
) -> dict[str, Any]:
    """Compare the written Parquet views, all features, with independent SQL over the raw logs."""
    observed: dict[str, Any] = {"appearances": len(rows), "games": len({r.game_id for r in rows})}
    for kind in SEASON_TYPES:
        subset = [r for r in rows if r.season_type == kind]
        observed[f"appearances_{kind}"] = len(subset)
        observed[f"players_{kind}"] = len({r.player_id for r in subset})
    teams_by_player: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        teams_by_player[r.player_id].add(r.team_id)
    observed["multi_team_players"] = sum(len(t) > 1 for t in teams_by_player.values())
    observed["zero_fga"] = sum(r.fga == 0 for r in rows)
    observed["zero_fg3a"] = sum(r.fg3a == 0 for r in rows)
    observed["zero_fta"] = sum(r.fta == 0 for r in rows)
    observed["zero_minutes"] = sum(r.minutes_ms == 0 for r in rows)

    connection.execute(
        "CREATE OR REPLACE TEMP TABLE r AS SELECT *, CASE left(game_id, 3) WHEN '002' "
        "THEN 'regular' ELSE 'playoffs' END AS kind, round(min * 60000)::BIGINT AS ms "
        "FROM read_parquet(?) WHERE left(game_id, 3) IN ('002', '004')",
        [str(directory / PLAYER_LOG)],
    )
    window_file = str(output / "same_window_features.parquet")
    asof_file = str(output / "asof_retrospective_features.parquet")
    # Same-window: totals per (player, season type, feature) over components both known.
    union = " UNION ALL ".join(
        f"SELECT player_id, kind, '{code}' AS code, "
        f"sum({n}) FILTER (WHERE ({n}) IS NOT NULL AND ({d}) IS NOT NULL)::BIGINT AS n, "
        f"sum({d}) FILTER (WHERE ({n}) IS NOT NULL AND ({d}) IS NOT NULL)::BIGINT AS d, "
        f"count(*) FILTER (WHERE ({n}) IS NOT NULL AND ({d}) IS NOT NULL) AS covered, "
        f"count(*) AS eligible FROM r GROUP BY 1, 2"
        for code, (n, d, _) in SQL_FEATURES.items()
    )
    scale = " ".join(f"WHEN '{c}' THEN {k}" for c, (_, _, k) in SQL_FEATURES.items())
    connection.execute(f"CREATE OR REPLACE TEMP TABLE e AS {union}")
    groups = connection.execute("SELECT count(*) FROM e").fetchall()[0][0]
    written = connection.execute("SELECT count(*) FROM read_parquet(?)", [window_file]).fetchall()[
        0
    ][0]
    bad = connection.execute(
        f"SELECT count(*) FROM e FULL JOIN read_parquet(?) o ON o.player_id = e.player_id "
        "AND o.feature_code = e.code AND o.window_id = e.kind || '-2022-23' "
        "WHERE o.player_id IS NULL OR e.player_id IS NULL "
        "OR o.numerator IS DISTINCT FROM e.n OR o.denominator IS DISTINCT FROM e.d "
        "OR o.covered_appearances <> e.covered OR o.eligible_appearances <> e.eligible "
        f"OR abs(coalesce(o.value, -1) - coalesce(CASE WHEN e.d > 0 THEN e.n * (CASE e.code {scale} END)::DOUBLE / e.d END, -1)) > 1e-9",
        [window_file],
    ).fetchall()[0][0]
    observed["same_window_sql_groups"] = groups
    observed["same_window_rows"] = written
    observed["same_window_sql_mismatches"] = bad

    # As-of: cumulative sums over strictly earlier played dates of the same season type.
    sums = ", ".join(
        f"sum({n}) FILTER (WHERE ({n}) IS NOT NULL AND ({d}) IS NOT NULL AND y.game_id IS NOT NULL)::BIGINT AS n_{c}, "
        f"sum({d}) FILTER (WHERE ({n}) IS NOT NULL AND ({d}) IS NOT NULL AND y.game_id IS NOT NULL)::BIGINT AS d_{c}, "
        f"count(*) FILTER (WHERE ({n}) IS NOT NULL AND ({d}) IS NOT NULL AND y.game_id IS NOT NULL) AS c_{c}"
        for c, (n, d, _) in SQL_FEATURES.items()
    )
    sums = re.sub(r"\b(fgm|fga|fg3m|fg3a|ftm|fta|ast|tov|oreb|dreb|stl|blk|pf|ms)\b", r"y.\1", sums)
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE h AS SELECT x.game_id, x.player_id, "
        f"count(y.game_id) AS cnt, {sums} FROM r x LEFT JOIN r y ON x.player_id = y.player_id "
        "AND x.kind = y.kind AND y.game_date < x.game_date GROUP BY 1, 2"
    )
    asof_bad = 0
    asof_rows = 0
    for code, (_, _, k) in SQL_FEATURES.items():
        asof_rows += connection.execute("SELECT count(*) FROM h").fetchall()[0][0]
        asof_bad += connection.execute(
            f"SELECT count(*) FROM h FULL JOIN (SELECT * FROM read_parquet(?) WHERE feature_code = '{code}') o "
            "ON o.game_id = h.game_id AND o.player_id = h.player_id "
            f"WHERE o.game_id IS NULL OR h.game_id IS NULL OR o.numerator IS DISTINCT FROM h.n_{code} "
            f"OR o.denominator IS DISTINCT FROM h.d_{code} OR o.covered_appearances <> h.c_{code} "
            "OR o.eligible_appearances <> h.cnt "
            f"OR abs(coalesce(o.value, -1) - coalesce(CASE WHEN h.d_{code} > 0 THEN h.n_{code} * {k}::DOUBLE / h.d_{code} END, -1)) > 1e-9",
            [asof_file],
        ).fetchall()[0][0]
    observed["asof_sql_rows_checked"] = asof_rows
    observed["asof_sql_mismatches"] = asof_bad
    observed["strict_rows_with_history"] = connection.execute(
        "SELECT count(*) FROM read_parquet(?) WHERE eligible_appearances > 0 OR value IS NOT NULL",
        [str(output / "asof_strict_features.parquet")],
    ).fetchall()[0][0]
    failures = [
        key
        for key in ("same_window_sql_mismatches", "asof_sql_mismatches", "strict_rows_with_history")
        if observed[key]
    ]
    if observed["same_window_sql_groups"] != observed["same_window_rows"]:
        failures.append("same_window_groups_vs_rows")
    mismatched = sorted(k for k, v in (expected or {}).items() if observed[k] != v)
    return {
        "observed": observed,
        "expected": dict(expected or {}),
        "mismatched_expectations": mismatched,
        "failed_checks": failures,
    }


def _feature_rows(
    base: dict[str, Any],
    snapshot_id: str,
    player_id: str,
    values: dict[str, FeatureValue],
    summary: dict[str, int | None],
) -> list[dict[str, Any]]:
    return [
        {
            **base,
            **summary,
            "snapshot_id": snapshot_id,
            "feature_code": feature.code,
            "feature_definition_version": FEATURE_VERSION,
            "player_id": player_id,
            "numerator": values[feature.code].numerator,
            "denominator": values[feature.code].denominator,
            "value": values[feature.code].value,
            "covered_appearances": values[feature.code].covered_appearances,
            "eligible_appearances": values[feature.code].eligible_appearances,
            "coverage": values[feature.code].coverage,
        }
        for feature in FEATURES
    ]


def _write_parquet(
    connection: duckdb.DuckDBPyConnection,
    name: str,
    rows: list[dict[str, Any]],
    staging: Path,
    output: Path,
) -> dict[str, Any]:
    columns = TABLES[name]
    source = staging / f"{name}.jsonl"
    with source.open("x", encoding="utf-8") as stream:
        for row in rows:
            if row.keys() != columns.keys():
                raise ValueError(f"Invalid output fields for {name}")
            stream.write(json.dumps(row, default=str) + "\n")
    destination = output / f"{name}.parquet"
    types = ", ".join(f"'{key}': '{value}'" for key, value in columns.items())
    connection.execute(
        f"COPY (SELECT * FROM read_json(?, format='newline_delimited', columns={{{types}}}) "
        "ORDER BY ALL) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
        [str(source), str(destination)],
    )
    return {
        "filename": destination.name,
        "sha256": sha256_file(destination),
        "size_bytes": destination.stat().st_size,
        "row_count": len(rows),
    }


def build_box_features(
    snapshot_dir: Path,
    output: Path,
    code_commit: str,
    *,
    snapshot: Snapshot | None = None,
    expected: Mapping[str, int] | None = EXPECTED,
) -> dict[str, Any]:
    """Create a new output directory, or remove it and raise if any reconciliation check fails.

    `snapshot` is only injected by tests; the CLI verifies the pinned source hashes.
    """
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise ValueError("Record a full Git commit for the feature build")
    pins_verified = snapshot is None
    snapshot = load_snapshot(snapshot_dir) if snapshot is None else snapshot
    sources = {row["name"]: row for row in snapshot["artifacts"]}
    logs = [sources[TEAM_LOG], sources[PLAYER_LOG]]
    capture = max(snapshot_instant(row["retrieved_at"]) for row in logs)
    provenance = Provenance(
        source_artifact_id="+".join(row["artifact_id"] for row in logs),
        available_at=capture,
        evidence_ref=f"snapshot.json#retrieved_at={capture.isoformat()}",
    )
    snapshot_sha = sha256_file(snapshot_dir / "snapshot.json")
    snapshot_ids = {
        view: _snapshot_id(logs, snapshot_sha, view, policy) for view, policy in VIEW_POLICY.items()
    }
    output.mkdir(mode=0o700, parents=True)
    try:
        with TemporaryDirectory(dir=output.parent) as temp, duckdb.connect() as connection:
            connection.execute("SET TimeZone = 'UTC'")
            staging = Path(temp)
            rows, _ = load_appearances(connection, snapshot_dir)
            tables = _views(rows, snapshot_ids, provenance)
            windows = tables.pop("_windows")
            strict_exclusions = tables.pop("_strict_exclusions")
            artifacts = [
                _write_parquet(connection, name, tables[name], staging, output) for name in TABLES
            ]
            reconciliation = reconcile(connection, snapshot_dir, output, rows, expected)
            coverage = _coverage(connection, output)
            if reconciliation["failed_checks"] or reconciliation["mismatched_expectations"]:
                raise ValueError(
                    "Reconciliation failed: "
                    f"{reconciliation['failed_checks'] + reconciliation['mismatched_expectations']}"
                )
        tables_by_name = {a["filename"]: a for a in artifacts}
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "season_start_year": 2022,
            "feature_definition_version": FEATURE_VERSION,
            "snapshot_ids": snapshot_ids,
            "source_pins_verified": pins_verified,
            "code_commit": code_commit,
            "generated_at": utc_now(),
            "duckdb_version": version("duckdb"),
            "source_snapshot_sha256": snapshot_sha,
            "source_artifacts": logs,
            "attribution": ATTRIBUTION,
            "terms": NBA_TERMS,
            "contract": "docs/research/box-score-feature-contract.md",
            "features": [
                {
                    "code": f.code,
                    "group": f.group,
                    "scale": "fraction" if f.scale == 1 else f"per 36 minutes ({MS_PER_36} ms)",
                }
                for f in FEATURES
            ],
            "views": {
                "same_window_features": {
                    "mode": "same_window",
                    "windows": windows,
                    "note": "Retrospective: includes every finalized game in the window.",
                },
                "asof_retrospective_features": {
                    "mode": "dated_retrospective",
                    "rule": "game_date < rating_date (America/New_York); same-day excluded",
                    "history_season_type": "same as the target game",
                    "availability": "retrospective_capture_bound",
                    "capture_bound": capture.isoformat(),
                    "note": "Frozen later snapshot; historical revision gap is unrecorded.",
                },
                "asof_strict_features": {
                    "mode": "strict_rolling",
                    "rule": "available_at <= C and finalized_at < C and game_date < rating_date",
                    "cohort_status": "unavailable_historical_strict",
                    "exclusions_by_reason": strict_exclusions,
                    "note": "Source gives only a 2026 capture bound and no finalization instants.",
                },
            },
            "reconciliation": reconciliation,
            "coverage": coverage,
            "output_artifacts": tables_by_name,
        }
        write_json(output / "manifest.json", manifest)
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest


VIEW_POLICY = {
    "same_window_features": "same_window;types=declared window;all finalized games in window",
    "asof_retrospective_features": (
        "dated_retrospective;history=same season type as target;game_date<rating_date"
    ),
    "asof_strict_features": (
        "strict_rolling;history=same season type as target;resolve_revisions;"
        "available_at<=C,finalized_at<C,game_date<rating_date"
    ),
}


def _snapshot_id(logs: list[Any], snapshot_sha: str, view: str, policy: str) -> str:
    payload = {
        "feature_version": FEATURE_VERSION,
        "source_snapshot_sha256": snapshot_sha,
        "sources": sorted((row["name"], row["sha256"]) for row in logs),
        "view": view,
        "cohort_and_history_policy": policy,
        "season_types": list(SEASON_TYPES),
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _coverage(connection: duckdb.DuckDBPyConnection, output: Path) -> dict[str, Any]:
    """Per-view, per-season-type player coverage, cold starts and per-feature missingness."""
    result: dict[str, Any] = {}
    for view, kind_column, key in (
        ("same_window_features", "season_types", "player_id"),
        ("asof_retrospective_features", "history_season_type", "game_id, player_id"),
        ("asof_strict_features", "history_season_type", "game_id, player_id"),
    ):
        path = str(output / f"{view}.parquet")
        per_kind: dict[str, Any] = {}
        for (kind,) in connection.execute(
            f"SELECT DISTINCT {kind_column} FROM read_parquet(?) ORDER BY 1", [path]
        ).fetchall():
            first = FEATURES[0].code
            rows, cold, players, with_history = connection.execute(
                f"SELECT count(*), count(*) FILTER (WHERE eligible_appearances = 0), "
                "count(DISTINCT player_id), count(DISTINCT player_id) "
                "FILTER (WHERE eligible_appearances > 0) FROM read_parquet(?) "
                f"WHERE {kind_column} = ? AND feature_code = ?",
                [path, kind, first],
            ).fetchall()[0]
            features = {}
            for code, n, eligible, covered, null_value, null_numerator in connection.execute(
                "SELECT feature_code, count(*), count(*) FILTER (WHERE eligible_appearances > 0), "
                "count(*) FILTER (WHERE covered_appearances > 0), "
                "count(*) FILTER (WHERE value IS NULL), count(*) FILTER (WHERE numerator IS NULL) "
                f"FROM read_parquet(?) WHERE {kind_column} = ? GROUP BY 1 ORDER BY 1",
                [path, kind],
            ).fetchall():
                features[code] = {
                    "rows": n,
                    "rows_with_eligible_history": eligible,
                    "rows_with_covered_components": covered,
                    "null_value_rows": null_value,
                    "null_numerator_rows": null_numerator,
                }
            per_kind[kind] = {
                "key": key,
                "rows": rows,
                "cold_start_rows": cold,
                "players": players,
                "players_with_history": with_history,
                "features": features,
            }
        result[view] = per_kind
    return result


def _views(rows: list[Appearance], ids: dict[str, str], provenance: Provenance) -> dict[str, Any]:
    tables: dict[str, Any] = {name: [] for name in TABLES}
    tables["appearances"] = [
        {
            "game_id": r.game_id,
            "player_id": r.player_id,
            "team_id": r.team_id,
            "opp_team_id": r.opp_team_id,
            "season_type": r.season_type,
            "game_date": r.game_date,
            "minutes_ms": r.minutes_ms,
            **{name: getattr(r, name) for name in COUNT_FIELDS},
        }
        for r in rows
    ]
    windows: list[dict[str, Any]] = []
    for kind in SEASON_TYPES:
        eligible = [r for r in rows if r.season_type == kind]
        if not eligible:
            continue
        start, end = min(r.game_date for r in eligible), max(r.game_date for r in eligible)
        windows.append(
            {
                "window_id": f"{kind}-2022-23",
                "season_types": [kind],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            }
        )
        by_player: dict[str, list[Appearance]] = defaultdict(list)
        for r in same_window(rows, start, end, [kind]):
            by_player[r.player_id].append(r)
        for player, group in sorted(by_player.items()):
            accumulator = aggregate(group)
            values, summary = accumulator.values(), accumulator.summary()
            base = {
                "window_id": f"{kind}-2022-23",
                "season_types": kind,
                "start_date": start,
                "end_date": end,
            }
            tables["same_window_features"] += _feature_rows(
                base, ids["same_window_features"], player, values, summary
            )
    for row, values, summary in history_rows(rows):
        rating = row.game_date
        base = {
            "game_id": row.game_id,
            "game_date": row.game_date,
            "rating_date": rating,
            "cutoff_utc": eastern_origin(rating).isoformat(),
            "history_season_type": row.season_type,
        }
        tables["asof_retrospective_features"] += _feature_rows(
            base, ids["asof_retrospective_features"], row.player_id, values, summary
        )
    revisions = capture_bound_revisions(rows, provenance)
    exclusions: Counter[str] = Counter()
    cutoffs: dict[tuple[date, str], int] = {}
    for row in rows:
        key = (row.game_date, row.season_type)
        if key not in cutoffs:
            usable, reasons = strict_history(rows, revisions, row.game_date, [row.season_type])
            cutoffs[key] = len(usable)
            exclusions.update(reasons)
    if any(cutoffs.values()):
        raise ValueError("Strict cohort unexpectedly has eligible history; build real strict view")
    empty = aggregate([])
    for row in rows:
        base = {
            "game_id": row.game_id,
            "game_date": row.game_date,
            "rating_date": row.game_date,
            "cutoff_utc": eastern_origin(row.game_date).isoformat(),
            "history_season_type": row.season_type,
            "cohort_status": "unavailable_historical_strict",
        }
        tables["asof_strict_features"] += _feature_rows(
            base, ids["asof_strict_features"], row.player_id, empty.values(), empty.summary()
        )
    tables["_windows"] = windows
    tables["_strict_exclusions"] = dict(sorted(exclusions.items()))
    return tables


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("snapshot_dir", type=Path)
    cli.add_argument("output_dir", type=Path)
    cli.add_argument("--code-commit", required=True)
    args = cli.parse_args()
    try:
        manifest = build_box_features(args.snapshot_dir, args.output_dir, args.code_commit)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(manifest["reconciliation"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
