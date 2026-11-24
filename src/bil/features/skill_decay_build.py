"""Run the frozen #32 skill decay evaluation on the pinned 2022–23 logs (private outputs).

Protocol: docs/research/skill-decay-protocol.md. Reads only the pinned `issue-5-v2` logs (through
the #62 loader) and the #31 build's `skill_baselines.parquet` for reconciliation. Refuses any
appearance outside the 2022 season key or dated on or after 2023-07-01. Writes a new directory and
removes it on any failed gate. Source data are for private, noncommercial research only.
"""

from __future__ import annotations

import argparse
import json
import re
import resource
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb
import numpy as np

from bil.data.pilot_sources import (
    ATTRIBUTION,
    NBA_TERMS,
    load_snapshot,
    sha256_file,
    utc_now,
    write_json,
)
from bil.features.box import Appearance
from bil.features.box_build import PLAYER_LOG, TEAM_LOG, _write_parquet, load_appearances
from bil.features.skill_decay import (
    BLOCKS,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    CLOCKS,
    COMMON_BASELINES,
    COMPARED_BASELINES,
    DATA_END,
    FIT_INDICES,
    LAYOFF_DAYS,
    LOG10_HALF_LIFE_BOUNDS,
    LOG10_K_BOUNDS,
    LOW_MINUTE_THRESHOLD,
    OUTER_BLOCKS,
    PLAYOFF_BLOCK,
    SEASON_KEY,
    SPARSE_MAX_GAMES,
    Appearances,
    DESettings,
    FitResult,
    FloatArray,
    IntArray,
    Panel,
    StatTable,
    as_of_sums,
    assemble,
    bootstrap_counts,
    clustered_ratio,
    fit,
    league_as_of,
    nll,
    outer_plan,
    predict_fit,
    rows_in,
)
from bil.features.skill_history import history_bucket, season_start_year

DECAY_VERSION = "skill-decay-v1"
SCOPES = {"regular_outer": ("M3", "M4", "M5"), "playoffs": ("P",)}
GROUPS = (
    "all",
    "sparse_career",
    "low_minute",
    "post_layoff",
    "history_1-4",
    "history_5-19",
    "history_20+",
)
FORECASTERS = ("model", *(f"clock_{c}" for c in CLOCKS), *COMPARED_BASELINES)


def check_scope(rows: Iterable[Appearance]) -> None:
    """Refuse anything outside 2022–23 (outer folds and the holdout must never be read)."""
    for row in rows:
        if season_start_year(row.game_id) != SEASON_KEY or row.game_date >= DATA_END:
            raise ValueError(f"Appearance outside the 2022–23 scope: {row.key} {row.game_date}")


def fit_all(
    panel: Panel,
    appearances: Appearances,
    tables: Mapping[str, StatTable],
    settings: DESettings,
    log: Callable[[str], None] = lambda _: None,
) -> dict[tuple[str, str, int], FitResult]:
    fits: dict[tuple[str, str, int], FitResult] = {}
    for code, table in tables.items():
        for clock in CLOCKS:
            for j in FIT_INDICES:
                start = time.perf_counter()
                result = fit(panel, table, appearances, clock, j, settings)
                fits[(code, clock, j)] = result
                log(
                    f"{code} {clock} F{j}: h={result.half_life:.4g} k={result.k:.4g} "
                    f"loss={result.objective:.6g} nfev={result.nfev} "
                    f"{time.perf_counter() - start:.1f}s"
                )
    return fits


def _loss_on(
    panel: Panel,
    table: StatTable,
    appearances: Appearances,
    result: FitResult,
    rows: IntArray,
) -> tuple[float, float]:
    pred = predict_fit(panel, table, appearances, result, rows)
    losses = nll(table.feature, table.target_num[rows], table.target_den[rows], pred)
    return float(losses.sum()), float(table.weight[rows].sum())


def select_clocks(
    panel: Panel,
    appearances: Appearances,
    tables: Mapping[str, StatTable],
    fits: Mapping[tuple[str, str, int], FitResult],
) -> list[dict[str, Any]]:
    """Inner-fold clock choice per statistic and outer block (never sees the outer block)."""
    selections = []
    for block in OUTER_BLOCKS:
        plan = outer_plan(block)
        for code, table in tables.items():
            inner: dict[str, float] = {}
            for clock in CLOCKS:
                total = weight = 0.0
                for fit_index, validation in plan.inner:
                    rows = rows_in(appearances, table, [validation])
                    loss, w = _loss_on(
                        panel, table, appearances, fits[(code, clock, fit_index)], rows
                    )
                    total, weight = total + loss, weight + w
                inner[clock] = total / weight
            chosen = min(CLOCKS, key=lambda c: (inner[c], CLOCKS.index(c)))
            final = fits[(code, chosen, plan.final_fit)]
            selections.append(
                {
                    "outer_block": block,
                    "feature_code": code,
                    "inner_fits": f"F{plan.inner[0][0]}->{plan.inner[0][1]};"
                    f"F{plan.inner[1][0]}->{plan.inner[1][1]}",
                    "final_fit": plan.final_fit,
                    **{f"inner_loss_{c}": inner[c] for c in CLOCKS},
                    "selected_clock": chosen,
                    "half_life": final.half_life,
                    "k": final.k,
                }
            )
    return selections


def _groups(appearances: Appearances, table: StatTable, rows: IntArray) -> dict[str, Any]:
    covered = table.covered_games[rows]
    minutes = appearances.prior_mean_minutes[rows]
    since = appearances.days_since_last[rows]
    return {
        "all": np.ones(rows.size, dtype=bool),
        "sparse_career": (covered >= 1) & (covered <= SPARSE_MAX_GAMES),
        "low_minute": np.nan_to_num(minutes, nan=np.inf) < LOW_MINUTE_THRESHOLD,
        "post_layoff": np.nan_to_num(since, nan=-1) >= LAYOFF_DAYS,
        **{
            f"history_{b}": np.array([c > 0 and history_bucket(int(c)) == b for c in covered])
            for b in ("1-4", "5-19", "20+")
        },
    }


def evaluate(
    panel: Panel,
    appearances: Appearances,
    tables: Mapping[str, StatTable],
    fits: Mapping[tuple[str, str, int], FitResult],
    selections: list[dict[str, Any]],
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, list[dict[str, Any]]]:
    """Outer predictions, scores with game-clustered intervals, exclusions and snapshots."""
    chosen = {(s["outer_block"], s["feature_code"]): s["selected_clock"] for s in selections}
    games = sorted(set(appearances.game))
    game_index = {g: i for i, g in enumerate(games)}
    cluster_all = np.array([game_index[g] for g in appearances.game], dtype=np.int64)
    blocks = np.array([b or "" for b in appearances.block])
    predictions: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    for scope, scope_blocks in SCOPES.items():
        scope_games = sorted(
            {cluster_all[i] for i in np.flatnonzero(np.isin(blocks, scope_blocks))}
        )
        local = {g: i for i, g in enumerate(scope_games)}
        counts = bootstrap_counts(len(scope_games), replicates, BOOTSTRAP_SEED)
        for code, table in tables.items():
            parts: list[tuple[IntArray, dict[str, FloatArray], str]] = []
            for block in scope_blocks:
                rows = rows_in(appearances, table, [block])
                final = outer_plan(block).final_fit
                preds = {
                    f"clock_{c}": predict_fit(
                        panel, table, appearances, fits[(code, c, final)], rows
                    )
                    for c in CLOCKS
                }
                preds["model"] = preds[f"clock_{chosen[(block, code)]}"]
                for name in COMMON_BASELINES:
                    preds[name] = table.baselines[name][rows]
                parts.append((rows, preds, block))
                exclusions += _exclusions(appearances, table, block)
            rows = np.concatenate([p[0] for p in parts])
            preds = {k: np.concatenate([p[1][k] for p in parts]) for k in parts[0][1]}
            block_of_row = np.concatenate([np.full(p[0].size, p[2]) for p in parts])
            common = np.all([~np.isnan(preds[b]) for b in COMMON_BASELINES], axis=0)
            cold = table.covered_games[rows] == 0
            groups = _groups(appearances, table, rows)
            cluster = np.array([local[c] for c in cluster_all[rows]], dtype=np.int64)
            weight = table.weight[rows]
            rate = table.rate[rows]
            loss = {
                k: np.where(
                    np.isnan(v),
                    np.nan,
                    nll(
                        table.feature,
                        table.target_num[rows],
                        table.target_den[rows],
                        np.nan_to_num(v),
                    ),
                )
                for k, v in preds.items()
            }
            sq = {k: weight * (v - rate) ** 2 for k, v in preds.items()}
            for i, r in enumerate(rows):
                predictions.append(
                    {
                        "outer_block": str(block_of_row[i]),
                        "season_type": appearances.season_type[r],
                        "game_id": appearances.game[r],
                        "player_id": appearances.player[r],
                        "game_date": appearances.played[r],
                        "feature_code": code,
                        "target_numerator": float(table.target_num[r]),
                        "target_denominator": float(table.target_den[r]),
                        "target_rate": float(rate[i]),
                        "target_weight": float(weight[i]),
                        "history_status": table.history[r],
                        "covered_games": int(table.covered_games[r]),
                        "prior_mean_minutes": _f(appearances.prior_mean_minutes[r]),
                        "days_since_last": _f(appearances.days_since_last[r]),
                        "primary_common": bool(common[i]),
                        "selected_clock": chosen[(str(block_of_row[i]), code)],
                        **{
                            f"pred_{k}": _f(v[i]) for k, v in preds.items() if k != "season_to_date"
                        },
                    }
                )
            cohorts = {f"common/{g}": common & m for g, m in groups.items()}
            cohorts["rookie_cold/all"] = cold
            for block in (*scope_blocks, "pooled"):
                in_block = (
                    np.ones(rows.size, dtype=bool) if block == "pooled" else block_of_row == block
                )
                if block != "pooled" and len(scope_blocks) == 1:
                    continue
                for name, mask in cohorts.items():
                    select = mask & in_block
                    if not select.any():
                        continue
                    scores += _score_cells(
                        scope,
                        block,
                        name,
                        code,
                        select,
                        loss,
                        sq,
                        weight,
                        cluster,
                        counts if block == "pooled" else None,
                    )
        for block in scope_blocks:
            cutoff = (
                PLAYOFF_BLOCK[1] if block == "P" else next(b[1] for b in BLOCKS if b[0] == block)
            )
            for code, table in tables.items():
                result = fits[(code, chosen[(block, code)], outer_plan(block).final_fit)]
                sums = as_of_sums(panel, table.x, result.clock, result.half_life, cutoff)
                league = league_as_of(table, panel, cutoff)
                for p, player in enumerate(panel.players):
                    days = panel.day[p, : panel.lengths[p]]
                    n_before = int(np.searchsorted(days, cutoff.toordinal()))
                    if n_before == 0 or league is None:
                        continue
                    numerator, denominator = float(sums[0, p]), float(sums[1, p])
                    snapshots.append(
                        {
                            "outer_block": block,
                            "cutoff_date": cutoff,
                            "feature_code": code,
                            "player_id": player,
                            "prior_appearances": n_before,
                            "clock": result.clock,
                            "half_life": result.half_life,
                            "k": result.k,
                            "discounted_numerator": numerator,
                            "discounted_exposure": denominator,
                            "league_rate": league,
                            "skill_estimate": (numerator + result.k * league)
                            / (denominator + result.k),
                        }
                    )
    return {
        "predictions": predictions,
        "scores": scores,
        "exclusions": _count_exclusions(exclusions),
        "snapshots": snapshots,
    }


def _f(value: Any) -> float | None:
    return None if value is None or np.isnan(value) else float(value)


def _score_cells(
    scope: str,
    block: str,
    cohort: str,
    code: str,
    select: Any,
    loss: Mapping[str, FloatArray],
    sq: Mapping[str, FloatArray],
    weight: FloatArray,
    cluster: IntArray,
    counts: IntArray | None,
) -> list[dict[str, Any]]:
    w = weight[select]
    cells = []
    comparisons = [(f, "model") for f in FORECASTERS if f != "model"]
    comparisons += [("clock_possessions", "clock_day"), ("clock_games", "clock_day")]
    for name in FORECASTERS:
        if np.isnan(loss[name][select]).any():
            continue
        cells.append(
            {
                "scope": scope,
                "block": block,
                "cohort": cohort,
                "feature_code": code,
                "forecaster": name,
                "reference": None,
                "value_kind": "level",
                "rows": int(select.sum()),
                "games": int(np.unique(cluster[select]).size),
                "weight_sum": float(w.sum()),
                "log_loss": float(loss[name][select].sum() / w.sum()),
                "weighted_mse": float(sq[name][select].sum() / w.sum()),
                **dict.fromkeys(
                    ("delta_log_loss_low", "delta_log_loss_high", "delta_mse_low", "delta_mse_high")
                ),
            }
        )
    for reference, name in comparisons:
        if np.isnan(loss[reference][select]).any() or np.isnan(loss[name][select]).any():
            continue
        row: dict[str, Any] = {
            "scope": scope,
            "block": block,
            "cohort": cohort,
            "feature_code": code,
            "forecaster": name,
            "reference": reference,
            "value_kind": "delta_forecaster_minus_reference",
            "rows": int(select.sum()),
            "games": int(np.unique(cluster[select]).size),
            "weight_sum": float(w.sum()),
        }
        for metric, values in (("log_loss", loss), ("mse", sq)):
            diff = values[name][select] - values[reference][select]
            key = "log_loss" if metric == "log_loss" else "weighted_mse"
            if counts is None:
                row[key] = float(diff.sum() / w.sum())
                row[f"delta_{metric}_low"] = row[f"delta_{metric}_high"] = None
            else:
                point, low, high = clustered_ratio(cluster[select], diff, w, counts)
                row[key], row[f"delta_{metric}_low"], row[f"delta_{metric}_high"] = point, low, high
        cells.append(row)
    return cells


def _exclusions(appearances: Appearances, table: StatTable, block: str) -> list[dict[str, Any]]:
    out = []
    for r in np.flatnonzero(np.array([b == block for b in appearances.block])):
        status = table.status[r]
        if status != "observed":
            reason = f"target_{status}"
        elif np.isnan(table.league[r]):
            reason = "no_league_reference"
        elif table.covered_games[r] == 0:
            reason = "rookie_cold"
        elif table.history[r] == "zero_exposure_history":
            reason = "zero_exposure_history"
        elif all(not np.isnan(table.baselines[b][r]) for b in COMMON_BASELINES):
            reason = "primary_common"
        elif np.isnan(table.baselines["last_10"][r]):
            reason = "last_10_zero_exposure"
        else:
            reason = "other_baseline_undefined"
        out.append(
            {
                "season_type": appearances.season_type[r],
                "outer_block": block,
                "feature_code": table.feature.code,
                "reason": reason,
            }
        )
    return out


def _count_exclusions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(
        (r["season_type"], r["outer_block"], r["feature_code"], r["reason"]) for r in rows
    )
    return [
        {"season_type": s, "outer_block": b, "feature_code": c, "reason": reason, "rows": n}
        for (s, b, c, reason), n in sorted(counts.items())
    ]


def reconcile_with_31(
    connection: duckdb.DuckDBPyConnection,
    skill_parquet: Path,
    engine: list[tuple[str, str, dict[str, Any]]],
    playoff_keys: set[str],
) -> dict[str, Any]:
    """Regular-season pooled engine rows must equal the #31 build exactly."""
    names = [*COMMON_BASELINES, "target_rate"]
    theirs = {
        (f"{g}:{p}", c): v
        for g, p, c, *v in connection.execute(
            f"SELECT game_id, player_id, feature_code, {', '.join(f'pred_{n}' for n in COMMON_BASELINES)}, "
            "target_rate FROM read_parquet(?) WHERE season_type = 'regular'",
            [str(skill_parquet)],
        ).fetchall()
    }
    mismatches = compared = 0
    for key, code, values in engine:
        if key in playoff_keys:
            continue
        compared += 1
        other = theirs.get((key, code))
        if other is None or any(
            (a is None) != (b is None) or (a is not None and b is not None and abs(a - b) > 1e-12)
            for a, b in zip((values[n] for n in names), other, strict=True)
        ):
            mismatches += 1
    return {
        "regular_rows_compared": compared,
        "regular_rows_in_31": len(theirs),
        "regular_row_mismatches": mismatches + abs(len(theirs) - compared),
    }


def classify_31_unscored(
    connection: duckdb.DuckDBPyConnection, skill_parquet: Path
) -> list[dict[str, Any]]:
    """Reasons for #31 observed targets outside its `common` and `cold` sets (keyed history)."""
    every = " AND ".join(f"pred_{b} IS NOT NULL" for b in COMMON_BASELINES)
    return [
        {"season_type": s, "reason": reason, "rows": n}
        for s, reason, n in connection.execute(
            "SELECT season_type, CASE "
            "WHEN pred_league_to_date IS NULL AND career_covered_games = 0 "
            "THEN 'no_history_and_no_league_reference' "
            "WHEN pred_league_to_date IS NULL THEN 'no_league_reference' "
            "WHEN history_status = 'zero_exposure_history' THEN 'zero_exposure_history' "
            "WHEN pred_last_10 IS NULL THEN 'last_10_zero_exposure' "
            "ELSE 'other_baseline_undefined' END AS reason, count(*) "
            f"FROM read_parquet(?) WHERE target_status = 'observed' AND NOT ({every}) "
            "AND NOT (career_covered_games = 0 AND pred_league_to_date IS NOT NULL) "
            "GROUP BY 1, 2 ORDER BY 1, 2",
            [str(skill_parquet)],
        ).fetchall()
    ]


def _schema(
    rows: list[dict[str, Any]], overrides: Mapping[str, str] | None = None
) -> dict[str, str]:
    kinds = {bool: "BOOLEAN", int: "BIGINT", float: "DOUBLE", str: "VARCHAR"}
    schema: dict[str, str] = {}
    for key in rows[0]:
        sample = next((r[key] for r in rows if r[key] is not None), "")
        schema[key] = "DATE" if hasattr(sample, "isoformat") else kinds.get(type(sample), "VARCHAR")
    schema.update(overrides or {})
    return schema


def write_tables(
    connection: duckdb.DuckDBPyConnection,
    tables: Mapping[str, list[dict[str, Any]]],
    staging: Path,
    output: Path,
) -> dict[str, dict[str, Any]]:
    artifacts = {}
    for name, table_rows in tables.items():
        schema = _schema(table_rows, {"reference": "VARCHAR"} if name == "scores" else None)
        for key in schema:
            if key.startswith(("delta_", "pred_", "prior_mean", "days_since")):
                schema[key] = "DOUBLE"
        artifacts[name] = _write_parquet(connection, name, table_rows, staging, output, schema)
    return artifacts


def _fit_row(result: FitResult) -> dict[str, Any]:
    return {
        "feature_code": result.code,
        "clock": result.clock,
        "fit_index": result.fit_index,
        "fit_blocks": ",".join(b[0] for b in BLOCKS[: result.fit_index + 1]),
        "fit_cutoff": BLOCKS[result.fit_index][2],
        "seed": result.seed,
        "log10_half_life": result.log10_half_life,
        "log10_k": result.log10_k,
        "half_life": result.half_life,
        "k": result.k,
        "objective": result.objective,
        "nfev": result.nfev,
        "nit": result.nit,
        "success": result.success,
        "rows": result.rows,
        "bound_hits": ",".join(result.bound_hits),
    }


def run(
    snapshot_dir: Path,
    skill_manifest: Path,
    output: Path,
    code_commit: str,
    settings: DESettings = DESettings(),
) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise ValueError("Record a full Git commit for the decay evaluation")
    started = time.perf_counter()
    snapshot = load_snapshot(snapshot_dir)
    snapshot_sha = sha256_file(snapshot_dir / "snapshot.json")
    upstream = json.loads(skill_manifest.read_text())
    skill_parquet = skill_manifest.parent / "skill_baselines.parquet"
    if upstream["source_snapshot_sha256"] != snapshot_sha:
        raise ValueError("The #31 build used a different source snapshot")
    if (
        sha256_file(skill_parquet)
        != upstream["output_artifacts"]["skill_baselines.parquet"]["sha256"]
    ):
        raise ValueError("The #31 skill_baselines.parquet differs from its manifest")
    output.mkdir(mode=0o700, parents=True)
    log_lines: list[str] = []

    def log(line: str) -> None:
        log_lines.append(line)
        print(line, file=sys.stderr, flush=True)

    try:
        with TemporaryDirectory(dir=output.parent) as temp, duckdb.connect() as connection:
            connection.execute("SET TimeZone = 'UTC'")
            connection.execute(f"SET temp_directory = '{temp}'")
            rows, _ = load_appearances(connection, snapshot_dir)
            check_scope(rows)
            t0 = time.perf_counter()
            panel, appearances, tables, engine, fallbacks = assemble(rows)
            assembled_seconds = time.perf_counter() - t0
            playoff_keys = {r.key for r in rows if r.season_type == "playoffs"}
            reconciliation = reconcile_with_31(connection, skill_parquet, engine, playoff_keys)
            if reconciliation["regular_row_mismatches"]:
                raise ValueError(f"Pooled engine differs from #31: {reconciliation}")
            t0 = time.perf_counter()
            fits = fit_all(panel, appearances, tables, settings, log)
            fit_seconds = time.perf_counter() - t0
            selections = select_clocks(panel, appearances, tables, fits)
            t0 = time.perf_counter()
            results = evaluate(panel, appearances, tables, fits, selections)
            eval_seconds = time.perf_counter() - t0
            unscored_31 = classify_31_unscored(connection, skill_parquet)
            tables_out: dict[str, list[dict[str, Any]]] = {
                "fits": [_fit_row(f) for f in fits.values()],
                "clock_selection": selections,
                **results,
            }
            artifacts = write_tables(connection, tables_out, Path(temp), output)
        summary = _summary(tables_out)
        content_id = sha256(
            json.dumps(
                {n: a["sha256"] for n, a in sorted(artifacts.items())}, sort_keys=True
            ).encode()
        ).hexdigest()
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "decay_definition_version": DECAY_VERSION,
            "protocol": "docs/research/skill-decay-protocol.md",
            "mode": "retrospective replay (no strict cohort: no revision evidence)",
            "season_start_year": SEASON_KEY,
            "content_id": content_id,
            "code_commit": code_commit,
            "generated_at": utc_now(),
            "versions": {
                "python": sys.version.split()[0],
                "numpy": version("numpy"),
                "scipy": version("scipy"),
                "duckdb": version("duckdb"),
            },
            "inputs": {
                "source_snapshot_sha256": snapshot_sha,
                "source_artifacts": [
                    a for a in snapshot["artifacts"] if a["name"] in (PLAYER_LOG, TEAM_LOG)
                ],
                "skill_manifest_sha256": sha256_file(skill_manifest),
                "skill_content_id": upstream["content_id"],
                "skill_baselines_sha256": sha256_file(skill_parquet),
            },
            "attribution": ATTRIBUTION,
            "terms": NBA_TERMS,
            "frozen": {
                "clocks": list(CLOCKS),
                "log10_half_life_bounds": LOG10_HALF_LIFE_BOUNDS,
                "log10_k_bounds": list(LOG10_K_BOUNDS),
                "de": settings.as_dict(),
                "seed_rule": "32000 + 100*stat_index + 10*clock_index + fit_index",
                "blocks": [[n, s.isoformat(), e.isoformat()] for n, s, e in BLOCKS],
                "playoff_block": [
                    PLAYOFF_BLOCK[0],
                    PLAYOFF_BLOCK[1].isoformat(),
                    PLAYOFF_BLOCK[2].isoformat(),
                ],
                "bootstrap": {
                    "replicates": BOOTSTRAP_REPLICATES,
                    "seed": BOOTSTRAP_SEED,
                    "cluster": "game_id",
                },
                "groups": {
                    "sparse_career_max_games": SPARSE_MAX_GAMES,
                    "low_minute_threshold": LOW_MINUTE_THRESHOLD,
                    "layoff_days": LAYOFF_DAYS,
                },
                "playoff_pooling": "player history and league reference pool regular season and earlier playoffs",
            },
            "possession_fallback_team_games": fallbacks,
            "reconciliation_with_31": reconciliation,
            "unscored_31_targets": unscored_31,
            "summary": summary,
            "runtime": {
                "total_seconds": round(time.perf_counter() - started, 1),
                "assemble_seconds": round(assembled_seconds, 1),
                "fit_seconds": round(fit_seconds, 1),
                "evaluate_seconds": round(eval_seconds, 1),
                "fits": len(fits),
                "peak_rss_mb": round(_peak_rss_mb(), 1),
            },
            "fit_log": log_lines,
            "output_artifacts": {a["filename"]: a for a in artifacts.values()},
        }
        write_json(output / "manifest.json", manifest)
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 2**20 if sys.platform == "darwin" else peak / 2**10


def _summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    pooled = [
        s
        for s in tables["scores"]
        if s["block"] == "pooled" and s["reference"] is not None and s["forecaster"] == "model"
    ] + [
        s
        for s in tables["scores"]
        if s["block"] == "pooled"
        and s["forecaster"] == "clock_day"
        and s["reference"] in ("clock_possessions", "clock_games")
    ]
    summary: dict[str, Any] = {}
    for s in pooled:
        cell = (
            summary.setdefault(s["scope"], {})
            .setdefault(s["cohort"], {})
            .setdefault(s["feature_code"], {})
        )
        cell[f"{s['forecaster']}-{s['reference']}"] = {
            "rows": s["rows"],
            "delta_log_loss": [s["log_loss"], s["delta_log_loss_low"], s["delta_log_loss_high"]],
            "delta_mse": [s["weighted_mse"], s["delta_mse_low"], s["delta_mse_high"]],
        }
    return summary


def _clean_commit() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
    )
    if status.stdout.strip():
        raise SystemExit("Run the evaluation from a clean tree")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("snapshot_dir", type=Path)
    cli.add_argument("skill_manifest", type=Path, help="manifest.json of the #31 build")
    cli.add_argument("output_dir", type=Path)
    args = cli.parse_args()
    try:
        manifest = run(args.snapshot_dir, args.skill_manifest, args.output_dir, _clean_commit())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps({"content_id": manifest["content_id"], "runtime": manifest["runtime"]}, indent=2)
    )


if __name__ == "__main__":
    main()
