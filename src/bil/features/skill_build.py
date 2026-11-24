"""Build private player-game skill-history opportunities, baselines and scores (issue #31).

Reads the pinned `issue-5-v2` player and team game logs through the #62 loader, writes a new
private directory with a content-addressed manifest, and fails (removing the output) if the
written Parquet disagrees with independent DuckDB SQL over the raw logs. Inputs and outputs stay
outside Git. Source data are for private, noncommercial research only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections.abc import Mapping
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb

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
    Appearance,
    Provenance,
    capture_bound_revisions,
    snapshot_instant,
)
from bil.features.box_build import (
    EXPECTED,
    PLAYER_LOG,
    SEASON_TYPES,
    SQL_FEATURES,
    TEAM_LOG,
    _write_parquet,
    load_appearances,
)
from bil.features.skill_history import (
    BASELINES,
    HALF_LIVES_DAYS,
    LAST_N,
    LOSS_EPSILON,
    Scorer,
    SkillRow,
    skill_rows,
    strict_prior_counts,
)

SKILL_VERSION = "skill-v1"
EXPECTED_PROFILE = {
    key: EXPECTED[key]
    for key in (
        "appearances",
        "appearances_regular",
        "appearances_playoffs",
        "players_regular",
        "players_playoffs",
        "games",
    )
}
FRACTIONS = tuple(f.code for f in FEATURES if f.scale == 1)
PRED = {b: f"pred_{b}" for b in BASELINES}
OPPORTUNITY_SCHEMA = {
    "snapshot_id": "VARCHAR",
    "game_id": "VARCHAR",
    "player_id": "VARCHAR",
    "team_id": "VARCHAR",
    "season_type": "VARCHAR",
    "season_start_year": "INTEGER",
    "game_date": "DATE",
    "rating_date": "DATE",
    "cutoff_utc": "TIMESTAMPTZ",
    "minutes_ms": "BIGINT",
    "appearance_sha256": "VARCHAR",
    "career_prior_appearances": "INTEGER",
    "season_prior_appearances": "INTEGER",
    "history_status": "VARCHAR",
    "strict_prior_appearances": "INTEGER",
    "strict_cohort_status": "VARCHAR",
}
BASELINE_SCHEMA = {
    "snapshot_id": "VARCHAR",
    "feature_definition_version": "VARCHAR",
    "game_id": "VARCHAR",
    "player_id": "VARCHAR",
    "season_type": "VARCHAR",
    "season_start_year": "INTEGER",
    "game_date": "DATE",
    "feature_code": "VARCHAR",
    "target_numerator": "BIGINT",
    "target_denominator": "BIGINT",
    "target_status": "VARCHAR",
    "target_rate": "DOUBLE",
    "target_weight": "DOUBLE",
    "history_status": "VARCHAR",
    "career_covered_games": "INTEGER",
    "season_covered_games": "INTEGER",
    "career_numerator": "BIGINT",
    "career_denominator": "BIGINT",
    "season_numerator": "BIGINT",
    "season_denominator": "BIGINT",
    **dict.fromkeys(PRED.values(), "DOUBLE"),
}
SCORE_SCHEMA = {
    "snapshot_id": "VARCHAR",
    "season_type": "VARCHAR",
    "cohort_set": "VARCHAR",
    "dim": "VARCHAR",
    "dim_value": "VARCHAR",
    "feature_code": "VARCHAR",
    "baseline": "VARCHAR",
    "rows": "INTEGER",
    "weight_sum": "DOUBLE",
    "weighted_mse": "DOUBLE",
    "log_loss": "DOUBLE",
    "log_loss_kind": "VARCHAR",
}
TABLES = {
    "appearance_opportunities": OPPORTUNITY_SCHEMA,
    "skill_baselines": BASELINE_SCHEMA,
    "baseline_scores": SCORE_SCHEMA,
}
BOX_FIELDS = (
    "game_id",
    "player_id",
    "team_id",
    "opp_team_id",
    "season_type",
    "game_date",
    "minutes_ms",
    *COUNT_FIELDS,
)


def _prefixed(expression: str, alias: str) -> str:
    return re.sub(
        r"\b(fgm|fga|fg3m|fg3a|ftm|fta|ast|tov|oreb|dreb|stl|blk|pf|ms)\b",
        rf"{alias}.\1",
        expression,
    )


def _mismatch(actual: str, expected: str) -> str:
    return (
        f"(({actual} IS NULL) <> ({expected} IS NULL) "
        f"OR abs({actual} - {expected}) > 1e-9 * (1 + abs({expected})))"
    )


def _check_box_manifest(
    connection: duckdb.DuckDBPyConnection,
    box_manifest: Path,
    snapshot_sha: str,
    rows: list[Appearance],
) -> dict[str, Any]:
    """Compare the loaded appearances with the #62 build's written appearance table."""
    manifest = json.loads(box_manifest.read_text())
    appearances = box_manifest.parent / "appearances.parquet"
    entry = manifest["output_artifacts"]["appearances.parquet"]
    cursor = connection.execute(
        f"SELECT {', '.join(BOX_FIELDS)} FROM read_parquet(?)", [str(appearances)]
    )
    names = [d[0] for d in cursor.description]
    theirs = {
        (a := Appearance(**dict(zip(names, values, strict=True)))).key: a.content_sha256()
        for values in cursor.fetchall()
    }
    ours = {r.key: r.content_sha256() for r in rows}
    return {
        "box_manifest_sha256": sha256_file(box_manifest),
        "box_appearances_sha256": sha256_file(appearances),
        "box_appearances_sha256_matches_manifest": sha256_file(appearances) == entry["sha256"],
        "box_source_snapshot_matches": manifest["source_snapshot_sha256"] == snapshot_sha,
        "box_feature_version": manifest["feature_definition_version"],
        "box_appearance_mismatches": len(set(theirs.items()) ^ set(ours.items())),
    }


def reconcile(
    connection: duckdb.DuckDBPyConnection,
    directory: Path,
    output: Path,
    rows: list[Appearance],
    expected: Mapping[str, int] | None,
    scores: list[dict[str, Any]],
    box_check: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Recompute every baseline, target and headline score from the raw logs with SQL."""
    skill = str(output / "skill_baselines.parquet")
    observed: dict[str, Any] = {
        "appearances": len(rows),
        "games": len({r.game_id for r in rows}),
        "skill_rows": connection.execute(
            "SELECT count(*) FROM read_parquet(?)", [skill]
        ).fetchall()[0][0],
        "expected_skill_rows": len(rows) * len(FEATURES),
    }
    for kind in SEASON_TYPES:
        subset = [r for r in rows if r.season_type == kind]
        observed[f"appearances_{kind}"] = len(subset)
        observed[f"players_{kind}"] = len({r.player_id for r in subset})
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE r AS SELECT *, CASE left(game_id, 3) WHEN '002' "
        "THEN 'regular' ELSE 'playoffs' END AS kind, round(min * 60000)::BIGINT AS ms, "
        "2000 + CAST(substr(game_id, 4, 2) AS INTEGER) AS sy "
        "FROM read_parquet(?) WHERE left(game_id, 3) IN ('002', '004')",
        [str(directory / PLAYER_LOG)],
    )
    observed["player_same_day_duplicates"] = connection.execute(
        "SELECT count(*) FROM (SELECT player_id, kind, game_date FROM r "
        "GROUP BY 1, 2, 3 HAVING count(*) > 1)"
    ).fetchall()[0][0]
    observed["seasons"] = connection.execute("SELECT count(DISTINCT sy) FROM r").fetchall()[0][0]
    observed["career_ne_season_rows"] = (
        connection.execute(
            "SELECT count(*) FROM read_parquet(?) WHERE pred_career_to_date IS DISTINCT FROM "
            "pred_season_to_date",
            [skill],
        ).fetchall()[0][0]
        if observed["seasons"] == 1
        else 0
    )
    half = {h: f"pow(0.5, date_diff('day', yd, xd) / {h}.0)" for h in HALF_LIVES_DAYS}
    baseline_bad = target_bad = league_bad = 0
    for code, (numerator, denominator, scale) in SQL_FEATURES.items():
        yn, yd = _prefixed(numerator, "y"), _prefixed(denominator, "y")
        decays = ", ".join(
            f"sum(n * {half[h]}) AS n{h}, sum(d * {half[h]}) AS d{h}" for h in HALF_LIVES_DAYS
        )
        connection.execute(
            "CREATE OR REPLACE TEMP TABLE h AS WITH pairs AS ("
            "SELECT x.game_id AS gid, x.player_id AS pid, x.game_date AS xd, y.game_date AS yd, "
            f"y.game_id AS ygid, x.sy AS xs, y.sy AS ys, ({yn}) AS n, ({yd}) AS d "
            "FROM r x JOIN r y ON x.player_id = y.player_id AND x.kind = y.kind "
            f"AND y.game_date < x.game_date WHERE ({yn}) IS NOT NULL AND ({yd}) IS NOT NULL), "
            "ranked AS (SELECT *, row_number() OVER (PARTITION BY gid, pid "
            "ORDER BY yd DESC, ygid DESC) AS rk FROM pairs) "
            "SELECT gid, pid, count(*) AS c, sum(n) AS cn, sum(d) AS cd, "
            "count(*) FILTER (WHERE ys = xs) AS sc, sum(n) FILTER (WHERE ys = xs) AS sn, "
            "sum(d) FILTER (WHERE ys = xs) AS sd, "
            f"sum(n) FILTER (WHERE rk <= {LAST_N}) AS ln, sum(d) FILTER (WHERE rk <= {LAST_N}) AS ld, "
            f"{decays} FROM ranked GROUP BY 1, 2"
        )
        sn, sd = _prefixed(numerator, "r"), _prefixed(denominator, "r")
        connection.execute(
            "CREATE OR REPLACE TEMP TABLE lg AS WITH d AS (SELECT kind, sy, game_date, "
            f"sum({numerator}) AS n, sum({denominator}) AS d FROM r WHERE ({numerator}) IS NOT NULL "
            f"AND ({denominator}) IS NOT NULL GROUP BY 1, 2, 3) "
            "SELECT x.kind, x.sy, x.game_date, sum(d.n) AS n, sum(d.d) AS d FROM "
            "(SELECT DISTINCT kind, sy, game_date FROM r) x LEFT JOIN d ON d.kind = x.kind "
            "AND d.sy = x.sy AND d.game_date < x.game_date GROUP BY 1, 2, 3"
        )
        predictions = [
            ("o.pred_career_to_date", "CASE WHEN h.cd > 0 THEN h.cn * {s}::DOUBLE / h.cd END"),
            ("o.pred_season_to_date", "CASE WHEN h.sd > 0 THEN h.sn * {s}::DOUBLE / h.sd END"),
            (f"o.pred_last_{LAST_N}", "CASE WHEN h.ld > 0 THEN h.ln * {s}::DOUBLE / h.ld END"),
            *(
                (
                    f"o.pred_decay_{k}d",
                    f"CASE WHEN h.cd > 0 THEN h.n{k} * {{s}}::DOUBLE / h.d{k} END",
                )
                for k in HALF_LIVES_DAYS
            ),
        ]
        clauses = " OR ".join(
            _mismatch(actual, expected_sql.format(s=scale)) for actual, expected_sql in predictions
        )
        baseline_bad += connection.execute(
            "SELECT count(*) FROM (SELECT * FROM read_parquet(?) WHERE feature_code = ?) o "
            "LEFT JOIN h ON h.gid = o.game_id AND h.pid = o.player_id "
            "WHERE o.career_covered_games IS DISTINCT FROM coalesce(h.c, 0) "
            "OR o.season_covered_games IS DISTINCT FROM coalesce(h.sc, 0) "
            "OR o.career_numerator IS DISTINCT FROM coalesce(h.cn, 0) "
            "OR o.career_denominator IS DISTINCT FROM coalesce(h.cd, 0) "
            "OR o.season_numerator IS DISTINCT FROM coalesce(h.sn, 0) "
            "OR o.season_denominator IS DISTINCT FROM coalesce(h.sd, 0) "
            f"OR {clauses}",
            [skill, code],
        ).fetchall()[0][0]
        league_bad += connection.execute(
            "SELECT count(*) FROM (SELECT * FROM read_parquet(?) WHERE feature_code = ?) o "
            "JOIN r ON r.game_id = o.game_id AND r.player_id = o.player_id "
            "LEFT JOIN lg ON lg.kind = r.kind AND lg.sy = r.sy AND lg.game_date = r.game_date "
            f"WHERE {_mismatch('o.pred_league_to_date', f'CASE WHEN lg.d > 0 THEN lg.n * {scale}::DOUBLE / lg.d END')}",
            [skill, code],
        ).fetchall()[0][0]
        target_bad += connection.execute(
            "SELECT count(*) FROM r FULL JOIN (SELECT * FROM read_parquet(?) WHERE feature_code = ?) o "
            "ON r.game_id = o.game_id AND r.player_id = o.player_id "
            "WHERE r.game_id IS NULL OR o.game_id IS NULL "
            f"OR o.target_numerator IS DISTINCT FROM ({sn}) "
            f"OR o.target_denominator IS DISTINCT FROM ({sd}) "
            f"OR o.target_status IS DISTINCT FROM CASE WHEN ({sn}) IS NULL OR ({sd}) IS NULL "
            f"THEN 'missing_component' WHEN ({sd}) = 0 THEN 'zero_exposure' ELSE 'observed' END "
            f"OR {_mismatch('o.target_rate', f'CASE WHEN ({sd}) > 0 THEN ({sn}) * {scale}::DOUBLE / ({sd}) END')}",
            [skill, code],
        ).fetchall()[0][0]
    observed["baseline_sql_mismatches"] = baseline_bad
    observed["league_sql_mismatches"] = league_bad
    observed["target_sql_mismatches"] = target_bad

    fractions = ", ".join(f"'{c}'" for c in FRACTIONS)
    scale_case = " ".join(f"WHEN '{c}' THEN {k}" for c, (_, _, k) in SQL_FEATURES.items())
    every = " AND ".join(f"{p} IS NOT NULL" for p in PRED.values())
    score_bad = 0
    python = {
        (s["season_type"], s["feature_code"], s["baseline"]): s
        for s in scores
        if s["cohort_set"] == "common" and s["dim"] == "all"
    }
    sql_cells = 0
    for baseline, column in PRED.items():
        p = f"least(greatest({column}, {LOSS_EPSILON}), 1 - {LOSS_EPSILON})"
        mean = f"greatest({column}, {LOSS_EPSILON}) * target_denominator / (CASE feature_code {scale_case} END)"
        nll = (
            f"CASE WHEN feature_code IN ({fractions}) THEN -(target_numerator * ln({p}) "
            f"+ (target_denominator - target_numerator) * ln(1 - {p})) "
            f"ELSE {mean} - target_numerator * ln({mean}) END"
        )
        for kind, code, n, w, wse, loss in connection.execute(
            "SELECT season_type, feature_code, count(*), sum(target_weight), "
            f"sum(target_weight * pow({column} - target_rate, 2)), sum({nll}) "
            f"FROM read_parquet(?) WHERE target_status = 'observed' AND {every} GROUP BY 1, 2",
            [skill],
        ).fetchall():
            sql_cells += 1
            mine = python.get((kind, code, baseline))
            if (
                mine is None
                or mine["rows"] != n
                or abs(mine["weight_sum"] - w) > 1e-9 * w
                or abs(mine["weighted_mse"] - wse / w) > 1e-9 * (1 + wse / w)
                or abs(mine["log_loss"] - loss / w) > 1e-9 * (1 + abs(loss / w))
            ):
                score_bad += 1
    observed["score_sql_cells"] = sql_cells
    observed["score_python_cells"] = len(python)
    observed["score_sql_mismatches"] = score_bad
    observed["strict_rows_with_history"] = connection.execute(
        "SELECT count(*) FROM read_parquet(?) WHERE strict_prior_appearances > 0",
        [str(output / "appearance_opportunities.parquet")],
    ).fetchall()[0][0]
    if box_check is not None:
        observed["box_appearance_mismatches"] = box_check["box_appearance_mismatches"]
    failures = [
        key
        for key in (
            "baseline_sql_mismatches",
            "league_sql_mismatches",
            "target_sql_mismatches",
            "score_sql_mismatches",
            "player_same_day_duplicates",
            "career_ne_season_rows",
            "strict_rows_with_history",
        )
        if observed[key]
    ]
    if observed["skill_rows"] != observed["expected_skill_rows"]:
        failures.append("skill_rows_vs_appearances")
    if observed["score_sql_cells"] != observed["score_python_cells"]:
        failures.append("score_cells")
    if box_check is not None:
        if observed["box_appearance_mismatches"]:
            failures.append("box_appearance_mismatches")
        if not box_check["box_source_snapshot_matches"]:
            failures.append("box_source_snapshot")
        if not box_check["box_appearances_sha256_matches_manifest"]:
            failures.append("box_appearances_sha256")
    mismatched = sorted(k for k, v in (expected or {}).items() if observed.get(k) != v)
    return {
        "observed": observed,
        "expected": dict(expected or {}),
        "mismatched_expectations": mismatched,
        "failed_checks": failures,
    }


def _coverage(connection: duckdb.DuckDBPyConnection, output: Path) -> dict[str, Any]:
    """Cohort coverage by season type, computed from the written Parquet."""
    opportunities = str(output / "appearance_opportunities.parquet")
    skill = str(output / "skill_baselines.parquet")
    result: dict[str, Any] = {}
    for kind in SEASON_TYPES:
        rows, players, cold, history_players = connection.execute(
            "SELECT count(*), count(DISTINCT player_id), "
            "count(*) FILTER (WHERE career_prior_appearances = 0), "
            "count(DISTINCT player_id) FILTER (WHERE career_prior_appearances > 0) "
            "FROM read_parquet(?) WHERE season_type = ?",
            [opportunities, kind],
        ).fetchall()[0]
        games, games_cold = connection.execute(
            "SELECT count(*), count(*) FILTER (WHERE with_history = 0) FROM (SELECT game_id, "
            "count(*) FILTER (WHERE career_prior_appearances > 0) AS with_history "
            "FROM read_parquet(?) WHERE season_type = ? GROUP BY 1)",
            [opportunities, kind],
        ).fetchall()[0]
        statuses = {
            f"{history}/{target}": n
            for history, target, n in connection.execute(
                "SELECT history_status, target_status, count(*) FROM read_parquet(?) "
                "WHERE season_type = ? GROUP BY 1, 2 ORDER BY 1, 2",
                [skill, kind],
            ).fetchall()
        }
        result[kind] = {
            "appearances": rows,
            "players": players,
            "appearances_without_prior_history": cold,
            "appearances_with_prior_history": rows - cold,
            "players_with_any_prior_history": history_players,
            "players_only_without_history": players - history_players,
            "games": games,
            "games_where_no_player_has_history": games_cold,
            "feature_rows_by_history_and_target_status": statuses,
        }
    return result


def _summary(scores: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for s in scores:
        if s["dim"] != "all":
            continue
        cell = summary.setdefault(s["season_type"], {}).setdefault(s["cohort_set"], {})
        cell.setdefault(s["feature_code"], {})[s["baseline"]] = {
            "rows": s["rows"],
            "weighted_mse": s["weighted_mse"],
            "log_loss": s["log_loss"],
        }
    return summary


def _digest(lines: list[str]) -> str:
    return sha256("\n".join(sorted(lines)).encode()).hexdigest()


def _snapshot_id(logs: list[Any], snapshot_sha: str, view: str, policy: str) -> str:
    payload = {
        "skill_version": SKILL_VERSION,
        "feature_version": FEATURE_VERSION,
        "source_snapshot_sha256": snapshot_sha,
        "sources": sorted((row["name"], row["sha256"]) for row in logs),
        "view": view,
        "policy": policy,
        "last_n": LAST_N,
        "half_lives_days": list(HALF_LIVES_DAYS),
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


VIEW_POLICY = {
    "appearance_opportunities": (
        "retrospective;history=earlier played dates of same season type and player;"
        "strict=resolve_revisions at NY midnight"
    ),
    "skill_baselines": (
        "retrospective;target=own game observed rate;predictors from game_date<target date;"
        "career/season/last-N/decay/league"
    ),
}


def build_skill_histories(
    snapshot_dir: Path,
    output: Path,
    code_commit: str,
    *,
    snapshot: Snapshot | None = None,
    expected: Mapping[str, int] | None = EXPECTED_PROFILE,
    box_manifest: Path | None = None,
) -> dict[str, Any]:
    """Create a new output directory, or remove it and raise if any reconciliation check fails.

    `snapshot` is only injected by tests; the CLI verifies the pinned source hashes.
    """
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise ValueError("Record a full Git commit for the skill-history build")
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
    ids = {view: _snapshot_id(logs, snapshot_sha, view, p) for view, p in VIEW_POLICY.items()}
    output.mkdir(mode=0o700, parents=True)
    try:
        with TemporaryDirectory(dir=output.parent) as temp, duckdb.connect() as connection:
            connection.execute("SET TimeZone = 'UTC'")
            staging = Path(temp)
            rows, _ = load_appearances(connection, snapshot_dir)
            box_check = (
                None
                if box_manifest is None
                else _check_box_manifest(connection, box_manifest, snapshot_sha, rows)
            )
            strict = strict_prior_counts(rows, capture_bound_revisions(rows, provenance))
            opportunity_rows: list[dict[str, Any]] = []
            baseline_rows: list[dict[str, Any]] = []
            scorer = Scorer()
            freeze: list[str] = []
            for opportunity, skill in skill_rows(rows):
                row = opportunity.row
                sha = row.content_sha256()
                strict_prior = strict[row.key]
                status = (
                    "unavailable_historical_strict"
                    if strict_prior < opportunity.career_prior_appearances
                    else "matches_retrospective"
                )
                opportunity_rows.append(
                    {
                        "snapshot_id": ids["appearance_opportunities"],
                        "game_id": row.game_id,
                        "player_id": row.player_id,
                        "team_id": row.team_id,
                        "season_type": row.season_type,
                        "season_start_year": opportunity.season,
                        "game_date": row.game_date,
                        "rating_date": row.game_date,
                        "cutoff_utc": eastern_origin(row.game_date).isoformat(),
                        "minutes_ms": row.minutes_ms,
                        "appearance_sha256": sha,
                        "career_prior_appearances": opportunity.career_prior_appearances,
                        "season_prior_appearances": opportunity.season_prior_appearances,
                        "history_status": opportunity.history_status,
                        "strict_prior_appearances": strict_prior,
                        "strict_cohort_status": status,
                    }
                )
                freeze.append(
                    f"{row.key}|{sha}|{opportunity.career_prior_appearances}|"
                    f"{opportunity.season_prior_appearances}|{strict_prior}"
                )
                baseline_rows += [_baseline_row(sk, ids["skill_baselines"]) for sk in skill]
                scorer.add(skill)
            scores = [{"snapshot_id": ids["skill_baselines"], **s} for s in scorer.table()]
            tables = {
                "appearance_opportunities": opportunity_rows,
                "skill_baselines": baseline_rows,
                "baseline_scores": scores,
            }
            artifacts = {
                name: _write_parquet(connection, name, tables[name], staging, output, TABLES[name])
                for name in TABLES
            }
            reconciliation = reconcile(
                connection, snapshot_dir, output, rows, expected, scores, box_check
            )
            coverage = _coverage(connection, output)
            if reconciliation["failed_checks"] or reconciliation["mismatched_expectations"]:
                raise ValueError(
                    "Reconciliation failed: "
                    f"{reconciliation['failed_checks'] + reconciliation['mismatched_expectations']}"
                )
        content_id = sha256(
            json.dumps(
                {
                    "artifacts": {n: a["sha256"] for n, a in sorted(artifacts.items())},
                    "snapshot_ids": ids,
                    "source_snapshot_sha256": snapshot_sha,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "season_start_year": 2022,
            "skill_definition_version": SKILL_VERSION,
            "feature_definition_version": FEATURE_VERSION,
            "content_id": content_id,
            "snapshot_ids": ids,
            "source_pins_verified": pins_verified,
            "code_commit": code_commit,
            "generated_at": utc_now(),
            "duckdb_version": version("duckdb"),
            "source_snapshot_sha256": snapshot_sha,
            "source_artifacts": logs,
            "attribution": ATTRIBUTION,
            "terms": NBA_TERMS,
            "contract": "docs/research/skill-histories.md",
            "baselines": {
                "players": list(BASELINES[:-1]),
                "reference": BASELINES[-1],
                "last_n": LAST_N,
                "half_lives_days": list(HALF_LIVES_DAYS),
                "tuned": False,
                "note": "Career equals season-to-date while one season is loaded.",
            },
            "freeze": {
                "opportunity_digest": _digest(freeze),
                "appearance_digest": _digest([f"{r.key}|{r.content_sha256()}" for r in rows]),
                "box_check": box_check,
                "strict": {
                    "cohort_status": "unavailable_historical_strict",
                    "rule": "available_at <= C, finalized_at < C and game_date < rating_date",
                    "note": "Source gives only a 2026 capture bound and no finalization instants.",
                },
            },
            "reconciliation": reconciliation,
            "coverage": coverage,
            "scores_all_dim": _summary(scores),
            "output_artifacts": {a["filename"]: a for a in artifacts.values()},
        }
        write_json(output / "manifest.json", manifest)
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest


def _baseline_row(sk: SkillRow, snapshot_id: str) -> dict[str, Any]:
    row = sk.opportunity.row
    return {
        "snapshot_id": snapshot_id,
        "feature_definition_version": FEATURE_VERSION,
        "game_id": row.game_id,
        "player_id": row.player_id,
        "season_type": row.season_type,
        "season_start_year": sk.opportunity.season,
        "game_date": row.game_date,
        "feature_code": sk.feature.code,
        "target_numerator": sk.target_numerator,
        "target_denominator": sk.target_denominator,
        "target_status": sk.target_status,
        "target_rate": sk.target_rate,
        "target_weight": sk.weight,
        "history_status": sk.history_status,
        "career_covered_games": sk.career_covered_games,
        "season_covered_games": sk.season_covered_games,
        "career_numerator": sk.career_numerator,
        "career_denominator": sk.career_denominator,
        "season_numerator": sk.season_numerator,
        "season_denominator": sk.season_denominator,
        **{PRED[b]: sk.predictions[b] for b in BASELINES},
    }


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("snapshot_dir", type=Path)
    cli.add_argument("output_dir", type=Path)
    cli.add_argument("--code-commit", required=True)
    cli.add_argument("--box-manifest", type=Path, help="manifest.json of the #62 build to match")
    args = cli.parse_args()
    try:
        manifest = build_skill_histories(
            args.snapshot_dir, args.output_dir, args.code_commit, box_manifest=args.box_manifest
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(manifest["reconciliation"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
