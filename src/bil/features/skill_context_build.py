"""Run the frozen #33 context evaluation on the pinned 2022–23 logs (private outputs).

Protocol: docs/research/skill-context-protocol.md. Reads the pinned `issue-5-v2` logs (through the
#62 loader), the private #32 build (frozen fits, clock selections, predictions and snapshots) and
nothing else. Refuses any appearance outside the 2022 season key or dated on or after 2023-07-01.
Writes a new directory and removes it on any failed gate. Source data are for private,
noncommercial research only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import date
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
from bil.features.box import FEATURE_CODES, Appearance
from bil.features.box_build import PLAYER_LOG, TEAM_LOG, _write_parquet, load_appearances
from bil.features.skill_context import (
    FACTOR_COLUMNS,
    FACTORS,
    MISSING_INPUTS,
    OPP_K_TEAM_GAMES,
    REFERENCES,
    RIDGE,
    TREND_WINDOW_DAYS,
    VARIANTS,
    Adjustment,
    ContextInputs,
    FloatArray,
    IntArray,
    TeamGame,
    build_context,
    fit_adjustment,
    input_columns,
    inverse_link,
    link_values,
)
from bil.features.skill_decay import (
    BLOCKS,
    BOOTSTRAP_REPLICATES,
    COMMON_BASELINES,
    DATA_END,
    OUTER_BLOCKS,
    PLAYOFF_BLOCK,
    Appearances,
    FitResult,
    Panel,
    StatTable,
    assemble,
    bootstrap_counts,
    clustered_ratio,
    fit_blocks,
    nll,
    outer_plan,
    predict_fit,
    rows_in,
)
from bil.features.skill_decay_build import (
    SCOPES,
    _f,
    _groups,
    _peak_rss_mb,
    _schema,
    check_scope,
)
from bil.features.skill_history import season_start_year
from bil.features.skill_snapshot import SkillParams, skill_snapshot

CONTEXT_VERSION = "skill-context-v1"
PROTOCOL = Path("docs/research/skill-context-protocol.md")
GAME_SEED = 33_033
PLAYER_SEED = 33_034
SNAPSHOT_TOLERANCE = 1e-9
PREDICTION_TOLERANCE = 1e-9
UPSTREAM = ("fits", "clock_selection", "predictions", "snapshots")
DELTA_KEYS = tuple(
    f"delta_{metric}_{name}_{side}"
    for metric in ("ll", "mse")
    for name in ("game", "player")
    for side in ("low", "high")
)


def load_team_games(connection: duckdb.DuckDBPyConnection, directory: Path) -> list[TeamGame]:
    """Scheduled team-games (regular season and playoffs) with the home flag, in scope."""
    rows = connection.execute(
        "SELECT game_id, team_id, opp_team_id, game_date, home FROM read_parquet(?) "
        "WHERE left(game_id, 3) IN ('002', '004') ORDER BY game_id, team_id",
        [str(directory / TEAM_LOG)],
    ).fetchall()
    games = []
    for game_id, team_id, opp, played, home in rows:
        if home is None:
            raise ValueError(f"Team game {game_id}/{team_id} has no home flag")
        if season_start_year(game_id) != 2022 or played >= DATA_END:
            raise ValueError(f"Team game outside the 2022–23 scope: {game_id} {played}")
        games.append(TeamGame(game_id, str(team_id), str(opp), played, bool(home)))
    return games


def load_frozen(
    connection: duckdb.DuckDBPyConnection, decay_dir: Path
) -> tuple[dict[tuple[str, str, int], FitResult], dict[tuple[str, str], str]]:
    """The #32 fits and per (outer block, statistic) clock selections, digests verified."""
    manifest = json.loads((decay_dir / "manifest.json").read_text())
    for name in UPSTREAM:
        entry = manifest["output_artifacts"][f"{name}.parquet"]
        if sha256_file(decay_dir / entry["filename"]) != entry["sha256"]:
            raise ValueError(f"The #32 {name} table differs from its manifest")
    fits = {}
    for r in connection.execute(
        "SELECT feature_code, clock, fit_index, seed, log10_half_life, log10_k, objective, "
        "nfev, nit, success, rows, bound_hits FROM read_parquet(?)",
        [str(decay_dir / "fits.parquet")],
    ).fetchall():
        hits = tuple(h for h in str(r[11] or "").split(",") if h)
        fits[(r[0], r[1], int(r[2]))] = FitResult(
            r[0],
            r[1],
            int(r[2]),
            int(r[3]),
            r[4],
            r[5],
            r[6],
            int(r[7]),
            int(r[8]),
            bool(r[9]),
            int(r[10]),
            hits,
        )
    chosen = {
        (b, c): clock
        for b, c, clock in connection.execute(
            "SELECT outer_block, feature_code, selected_clock FROM read_parquet(?)",
            [str(decay_dir / "clock_selection.parquet")],
        ).fetchall()
    }
    return fits, chosen


def base_fit(
    fits: Mapping[tuple[str, str, int], FitResult],
    chosen: Mapping[tuple[str, str], str],
    block: str,
    code: str,
) -> FitResult:
    return fits[(code, chosen[(block, code)], outer_plan(block).final_fit)]


def fit_rows_for(appearances: Appearances, table: StatTable, block: str) -> IntArray:
    """Regular-season targets in M0..M_{k-1}: strictly before the outer block's start date."""
    rows = rows_in(appearances, table, fit_blocks(outer_plan(block).final_fit))
    start = next(b[1] for b in BLOCKS if b[0] == block) if block != "P" else PLAYOFF_BLOCK[1]
    if any(appearances.played[i] >= start for i in rows):
        raise ValueError(f"A fit row for {block} is dated on or after its start")
    return rows


def adjust_block(
    panel: Panel,
    appearances: Appearances,
    table: StatTable,
    inputs: ContextInputs,
    base: FitResult,
    block: str,
    score_rows: IntArray,
) -> tuple[dict[str, FloatArray], list[dict[str, Any]]]:
    """Predictions for every variant on `score_rows`, with coefficients fitted on earlier blocks."""
    feature = table.feature
    code = feature.code
    fit_rows = fit_rows_for(appearances, table, block)
    columns = input_columns(inputs, code)
    base_fit_pred = predict_fit(panel, table, appearances, base, fit_rows)
    base_score = predict_fit(panel, table, appearances, base, score_rows)
    offset_fit = link_values(feature, base_fit_pred)
    offset_score = link_values(feature, base_score)
    numerator = table.target_num[fit_rows]
    exposure = table.weight[fit_rows]
    preds: dict[str, FloatArray] = {"agnostic": base_score}
    coefficients: list[dict[str, Any]] = []
    for variant, factors in VARIANTS.items():
        if variant == "agnostic":
            continue
        terms = tuple(c for f in factors for c in _factor_terms(f))
        adjustment = fit_adjustment(
            feature, terms, columns, fit_rows, offset_fit, numerator, exposure
        )
        preds[variant] = inverse_link(feature, adjustment.eta(offset_score, columns, score_rows))
        coefficients += _coefficient_rows(block, code, variant, adjustment)
    return preds, coefficients


def _factor_terms(factor: str) -> tuple[str, ...]:
    return FACTOR_COLUMNS[factor]


def _coefficient_rows(
    block: str, code: str, variant: str, adjustment: Adjustment
) -> list[dict[str, Any]]:
    common = {
        "outer_block": block,
        "feature_code": code,
        "variant": variant,
        "fit_rows": adjustment.rows,
        "converged": adjustment.success,
        "nfev": adjustment.nfev,
    }
    rows = [
        {**common, "term": "intercept", "coefficient": adjustment.beta0, "mean": 0.0, "std": 1.0}
    ]
    for name, b, mu, sd in zip(
        adjustment.terms, adjustment.beta, adjustment.mean, adjustment.std, strict=True
    ):
        rows.append({**common, "term": name, "coefficient": b, "mean": mu, "std": sd})
    return rows


def _cells(
    scope: str,
    block: str,
    cohort: str,
    code: str,
    select: Any,
    loss: Mapping[str, FloatArray],
    sq: Mapping[str, FloatArray],
    weight: FloatArray,
    clusters: Mapping[str, tuple[IntArray, IntArray | None]],
) -> list[dict[str, Any]]:
    w = weight[select]
    base = {
        "scope": scope,
        "block": block,
        "cohort": cohort,
        "feature_code": code,
        "rows": int(select.sum()),
        "games": int(np.unique(clusters["game"][0][select]).size),
        "players": int(np.unique(clusters["player"][0][select]).size),
        "weight_sum": float(w.sum()),
    }
    cells = []
    for variant in VARIANTS:
        cells.append(
            {
                **base,
                "variant": variant,
                "reference": None,
                "value_kind": "level",
                "log_loss": float(loss[variant][select].sum() / w.sum()),
                "weighted_mse": float(sq[variant][select].sum() / w.sum()),
                **dict.fromkeys(DELTA_KEYS),
            }
        )
    for variant, references in REFERENCES.items():
        for reference in references:
            row: dict[str, Any] = {
                **base,
                "variant": variant,
                "reference": reference,
                "value_kind": "delta_variant_minus_reference",
            }
            for metric, values, key in (("ll", loss, "log_loss"), ("mse", sq, "weighted_mse")):
                diff = values[variant][select] - values[reference][select]
                row[key] = float(diff.sum() / w.sum())
                for name, (index, counts) in clusters.items():
                    if counts is None:
                        row[f"delta_{metric}_{name}_low"] = row[f"delta_{metric}_{name}_high"] = (
                            None
                        )
                    else:
                        _, low, high = clustered_ratio(index[select], diff, w, counts)
                        row[f"delta_{metric}_{name}_low"] = low
                        row[f"delta_{metric}_{name}_high"] = high
            cells.append(row)
    return cells


def evaluate(
    panel: Panel,
    appearances: Appearances,
    tables: Mapping[str, StatTable],
    inputs: ContextInputs,
    fits: Mapping[tuple[str, str, int], FitResult],
    chosen: Mapping[tuple[str, str], str],
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, list[dict[str, Any]]]:
    games = sorted(set(appearances.game))
    game_index = {g: i for i, g in enumerate(games)}
    players = sorted(set(appearances.player))
    player_index = {p: i for i, p in enumerate(players)}
    game_all = np.array([game_index[g] for g in appearances.game], dtype=np.int64)
    player_all = np.array([player_index[p] for p in appearances.player], dtype=np.int64)
    blocks = np.array([b or "" for b in appearances.block])
    predictions: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []
    coefficients: list[dict[str, Any]] = []
    for scope, scope_blocks in SCOPES.items():
        in_scope = np.flatnonzero(np.isin(blocks, scope_blocks))
        scope_games = sorted({int(game_all[i]) for i in in_scope})
        scope_players = sorted({int(player_all[i]) for i in in_scope})
        game_local = {g: i for i, g in enumerate(scope_games)}
        player_local = {p: i for i, p in enumerate(scope_players)}
        game_counts = bootstrap_counts(len(scope_games), replicates, GAME_SEED)
        player_counts = bootstrap_counts(len(scope_players), replicates, PLAYER_SEED)
        for code, table in tables.items():
            parts = []
            for block in scope_blocks:
                rows = rows_in(appearances, table, [block])
                preds, coef = adjust_block(
                    panel,
                    appearances,
                    table,
                    inputs,
                    base_fit(fits, chosen, block, code),
                    block,
                    rows,
                )
                coefficients += coef
                parts.append((rows, preds, block))
            rows = np.concatenate([p[0] for p in parts])
            preds = {v: np.concatenate([p[1][v] for p in parts]) for v in VARIANTS}
            block_of_row = np.concatenate([np.full(p[0].size, p[2]) for p in parts])
            for v, values in preds.items():
                if not np.isfinite(values).all():
                    raise ValueError(f"Non-finite {v} prediction for {code}")
            common = np.all([~np.isnan(table.baselines[b][rows]) for b in COMMON_BASELINES], axis=0)
            cold = table.covered_games[rows] == 0
            groups = _groups(appearances, table, rows)
            weight = table.weight[rows]
            rate = table.rate[rows]
            loss = {
                v: nll(table.feature, table.target_num[rows], table.target_den[rows], p)
                for v, p in preds.items()
            }
            sq = {v: weight * (p - rate) ** 2 for v, p in preds.items()}
            clusters_pooled = {
                "game": (np.array([game_local[int(g)] for g in game_all[rows]]), game_counts),
                "player": (
                    np.array([player_local[int(p)] for p in player_all[rows]]),
                    player_counts,
                ),
            }
            clusters_block = {k: (v[0], None) for k, v in clusters_pooled.items()}
            for i, r in enumerate(rows):
                predictions.append(
                    {
                        "outer_block": str(block_of_row[i]),
                        "season_type": appearances.season_type[r],
                        "game_id": appearances.game[r],
                        "player_id": appearances.player[r],
                        "game_date": appearances.played[r],
                        "feature_code": code,
                        "target_rate": float(rate[i]),
                        "target_weight": float(weight[i]),
                        "covered_games": int(table.covered_games[r]),
                        "primary_common": bool(common[i]),
                        "home": float(inputs.home[r]),
                        "b2b": float(inputs.b2b[r]),
                        "rest_days": float(inputs.rest_days[r]),
                        "trend": float(inputs.trend[code][r]),
                        "opp": float(inputs.opp[code][r]),
                        "team": float(inputs.team[code][r]),
                        **{f"pred_{v}": _f(p[i]) for v, p in preds.items()},
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
                    if select.any():
                        scores += _cells(
                            scope,
                            block,
                            name,
                            code,
                            select,
                            loss,
                            sq,
                            weight,
                            clusters_pooled if block == "pooled" else clusters_block,
                        )
    return {"predictions": predictions, "scores": scores, "coefficients": coefficients}


def reconcile_predictions(
    connection: duckdb.DuckDBPyConnection, decay_dir: Path, predictions: list[dict[str, Any]]
) -> dict[str, Any]:
    theirs = {
        (b, g, p, c): v
        for b, g, p, c, v in connection.execute(
            "SELECT outer_block, game_id, player_id, feature_code, pred_model FROM read_parquet(?)",
            [str(decay_dir / "predictions.parquet")],
        ).fetchall()
    }
    mismatches = 0
    for r in predictions:
        other = theirs.get((r["outer_block"], r["game_id"], r["player_id"], r["feature_code"]))
        if other is None or abs(other - r["pred_agnostic"]) > PREDICTION_TOLERANCE:
            mismatches += 1
    return {
        "rows_compared": len(predictions),
        "rows_in_32": len(theirs),
        "row_mismatches": mismatches + abs(len(theirs) - len(predictions)),
    }


def snapshot_table(
    connection: duckdb.DuckDBPyConnection,
    decay_dir: Path,
    rows: Sequence[Appearance],
    fits: Mapping[tuple[str, str, int], FitResult],
    chosen: Mapping[tuple[str, str], str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """API snapshots at each outer block start, checked against the #32 snapshots."""
    theirs = {
        (b, c, p): (e, n, d)
        for b, c, p, e, n, d in connection.execute(
            "SELECT outer_block, feature_code, player_id, skill_estimate, discounted_numerator, "
            "discounted_exposure FROM read_parquet(?)",
            [str(decay_dir / "snapshots.parquet")],
        ).fetchall()
    }
    out: list[dict[str, Any]] = []
    mismatches = compared = 0
    for block in OUTER_BLOCKS:
        cutoff = PLAYOFF_BLOCK[1] if block == "P" else next(b[1] for b in BLOCKS if b[0] == block)
        params = {
            code: SkillParams(f.clock, f.half_life, f.k)
            for code in FEATURE_CODES
            for f in [base_fit(fits, chosen, block, code)]
        }
        snapshot = skill_snapshot(rows, params, cutoff)
        for s in snapshot:
            out.append(
                {
                    "outer_block": block,
                    "as_of": s.as_of,
                    "player_id": s.player_id,
                    "feature_code": s.feature_code,
                    "feature_group": s.feature_group,
                    "unit": s.unit,
                    "estimate": s.estimate,
                    "discounted_numerator": s.discounted_numerator,
                    "discounted_exposure": s.discounted_exposure,
                    "league_rate": s.league_rate,
                    "covered_games": s.covered_games,
                    "prior_appearances": s.prior_appearances,
                    "clock": s.clock,
                    "half_life": s.half_life,
                    "k": s.k,
                }
            )
            compared += 1
            other = theirs.get((block, s.feature_code, s.player_id))
            if other is None or any(
                abs(a - b) > SNAPSHOT_TOLERANCE
                for a, b in zip((s.estimate, s.discounted_numerator, s.discounted_exposure), other)
            ):
                mismatches += 1
    return out, {
        "rows_compared": compared,
        "rows_in_32": len(theirs),
        "row_mismatches": mismatches + abs(len(theirs) - compared),
    }


def context_input_rows(
    appearances: Appearances, inputs: ContextInputs, team: Mapping[str, tuple[str, str]]
) -> list[dict[str, Any]]:
    latest = inputs.latest_source()
    rows = []
    for i, key in enumerate(appearances.keys):
        rows.append(
            {
                "game_id": appearances.game[i],
                "player_id": appearances.player[i],
                "game_date": appearances.played[i],
                "team_id": team[key][0],
                "opp_team_id": team[key][1],
                "home": bool(inputs.home[i]),
                "b2b": bool(inputs.b2b[i]),
                "rest_days": float(inputs.rest_days[i]),
                "rest_known": bool(inputs.rest_known[i]),
                "latest_source_date": date.fromordinal(int(latest[i])) if latest[i] else None,
            }
        )
    return rows


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
            if key.startswith(("delta_", "pred_")) or key in ("latest_source_date",):
                schema[key] = "DATE" if key == "latest_source_date" else "DOUBLE"
        artifacts[name] = _write_parquet(connection, name, table_rows, staging, output, schema)
    return artifacts


def _summary(scores: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for s in scores:
        if s["block"] != "pooled" or s["cohort"] != "common/all" or s["reference"] is None:
            continue
        if s["reference"] != "agnostic" and not (
            s["reference"] == "full" and s["variant"].startswith("drop_")
        ):
            continue
        cell = summary.setdefault(s["scope"], {}).setdefault(s["feature_code"], {})
        cell[f"{s['variant']}-{s['reference']}"] = {
            "rows": s["rows"],
            "delta_log_loss": [
                s["log_loss"],
                s["delta_ll_game_low"],
                s["delta_ll_game_high"],
                s["delta_ll_player_low"],
                s["delta_ll_player_high"],
            ],
        }
    return summary


def run(
    snapshot_dir: Path,
    decay_dir: Path,
    output: Path,
    code_commit: str,
    protocol_sha256: str,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise ValueError("Record a full Git commit for the context evaluation")
    started = time.perf_counter()
    snapshot = load_snapshot(snapshot_dir)
    snapshot_sha = sha256_file(snapshot_dir / "snapshot.json")
    upstream = json.loads((decay_dir / "manifest.json").read_text())
    if upstream["inputs"]["source_snapshot_sha256"] != snapshot_sha:
        raise ValueError("The #32 build used a different source snapshot")
    output.mkdir(mode=0o700, parents=True)
    try:
        with TemporaryDirectory(dir=output.parent) as temp, duckdb.connect() as connection:
            connection.execute("SET TimeZone = 'UTC'")
            connection.execute(f"SET temp_directory = '{temp}'")
            rows, _ = load_appearances(connection, snapshot_dir)
            check_scope(rows)
            team_games = load_team_games(connection, snapshot_dir)
            fits, chosen = load_frozen(connection, decay_dir)
            panel, appearances, tables, _, _ = assemble(rows)
            inputs = build_context(rows, team_games, appearances.keys)
            violations = inputs.cutoff_violations()
            if violations:
                raise ValueError(f"{violations} context rows use a source on or after the game")
            for code, table in tables.items():
                m = np.where(np.isnan(table.league), 0.0, table.league)
                if not np.isfinite(inputs.opp[code]).all() or not np.isfinite(m).all():
                    raise ValueError(f"Non-finite context for {code}")
            t0 = time.perf_counter()
            results = evaluate(panel, appearances, tables, inputs, fits, chosen, replicates)
            eval_seconds = time.perf_counter() - t0
            reconciliation = reconcile_predictions(connection, decay_dir, results["predictions"])
            if reconciliation["row_mismatches"]:
                raise ValueError(f"Frozen base differs from #32 predictions: {reconciliation}")
            snapshots, snapshot_check = snapshot_table(connection, decay_dir, rows, fits, chosen)
            if snapshot_check["row_mismatches"]:
                raise ValueError(f"Snapshot API differs from #32 snapshots: {snapshot_check}")
            team = {r.key: (r.team_id, r.opp_team_id) for r in rows}
            tables_out: dict[str, list[dict[str, Any]]] = {
                "context_inputs": context_input_rows(appearances, inputs, team),
                **results,
                "snapshots": snapshots,
            }
            artifacts = write_tables(connection, tables_out, Path(temp), output)
        content_id = sha256(
            json.dumps(
                {n: a["sha256"] for n, a in sorted(artifacts.items())}, sort_keys=True
            ).encode()
        ).hexdigest()
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "context_definition_version": CONTEXT_VERSION,
            "protocol": str(PROTOCOL),
            "protocol_sha256": protocol_sha256,
            "mode": "retrospective replay (no strict cohort: no revision evidence)",
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
                "decay_manifest_sha256": sha256_file(decay_dir / "manifest.json"),
                "decay_content_id": upstream["content_id"],
                "decay_tables": {
                    n: upstream["output_artifacts"][f"{n}.parquet"]["sha256"] for n in UPSTREAM
                },
            },
            "attribution": ATTRIBUTION,
            "terms": NBA_TERMS,
            "frozen": {
                "factors": list(FACTORS),
                "variants": {k: list(v) for k, v in VARIANTS.items()},
                "references": {k: list(v) for k, v in REFERENCES.items()},
                "ridge": RIDGE,
                "opp_k_team_games": OPP_K_TEAM_GAMES,
                "trend_window_days": TREND_WINDOW_DAYS,
                "bootstrap": {
                    "replicates": replicates,
                    "game_seed": GAME_SEED,
                    "player_seed": PLAYER_SEED,
                },
                "missing_inputs": list(MISSING_INPUTS),
            },
            "context_cutoff_violations": violations,
            "context_defaults": inputs.defaults,
            "team_games": len(team_games),
            "reconciliation_with_32_predictions": reconciliation,
            "reconciliation_with_32_snapshots": snapshot_check,
            "summary": _summary(tables_out["scores"]),
            "runtime": {
                "total_seconds": round(time.perf_counter() - started, 1),
                "evaluate_seconds": round(eval_seconds, 1),
                "peak_rss_mb": round(_peak_rss_mb(), 1),
            },
            "output_artifacts": {a["filename"]: a for a in artifacts.values()},
        }
        write_json(output / "manifest.json", manifest)
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest


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
    cli.add_argument("decay_dir", type=Path, help="the private #32 build directory")
    cli.add_argument("output_dir", type=Path)
    args = cli.parse_args()
    commit = _clean_commit()
    try:
        manifest = run(
            args.snapshot_dir, args.decay_dir, args.output_dir, commit, sha256_file(PROTOCOL)
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps({"content_id": manifest["content_id"], "runtime": manifest["runtime"]}, indent=2)
    )


if __name__ == "__main__":
    main()
