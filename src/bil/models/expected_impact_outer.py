"""Frozen outer validation of Expected impact v1 on 2023–24 and 2024–25 (#36).

The runner refuses to start unless the committed addendum
``docs/research/expected-impact-outer-addendum.md`` matches its SHA-256 on a clean tree. It reads
every model choice from that file's frozen block and re-tunes nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb
import numpy as np
from numpy.typing import NDArray

from bil.data.pilot_sources import ATTRIBUTION, sha256_file
from bil.features.box import Appearance
from bil.features.box_build import PLAYER_LOG, TEAM_LOG, load_appearances
from bil.models.expected_impact import (
    ARTIFACT_LABEL,
    EVIDENCE,
    SPM_MANIFEST,
    SPM_RUN,
    FloatArray,
    Ratings,
    fit_informed,
    predict_informed,
    prepare,
    ratings,
    score_set,
    spm_fit,
    spm_only,
    write_ratings,
)
from bil.models.rapm.baseline import _peak_memory_mib
from bil.models.rapm.multiseason import (
    FROZEN_BLOCK,
    HOLDOUT_START_YEAR,
    REPO_ROOT,
    SEASON_PINS,
    TEMPORAL_BY_NAME,
    AddendumError,
    Analysis,
    Block,
    Rows,
    Scenario,
    _git_head,
    _prepare,
    _solver_summary,
    _versions,
    _write_json,
    outcome_digest,
    season_blocks,
    team_game_rmse,
    verify_addendum,
)
from bil.models.spm_build import checked_file, read_json

ADDENDUM = REPO_ROOT / "docs/research/expected-impact-outer-addendum.md"
VERSION = "issue-36-v1"
OUTER_SEASONS = (2023, 2024)
ROW_SEASONS = (2021, 2022, 2023, 2024)
FINAL_CUTOFF = date(HOLDOUT_START_YEAR, 7, 1)
EXPOSURE_FLOOR = 1000.0


def parse_config(text: str) -> dict[str, Any]:
    match = FROZEN_BLOCK.search(text)
    if match is None:
        raise AddendumError("the addendum has no frozen-config block")
    config: dict[str, Any] = json.loads(match.group(1))
    if config.get("issue") != 36 or config.get("outer_seasons") != list(OUTER_SEASONS):
        raise AddendumError("the frozen block must be for #36 and seasons 2023 and 2024 only")
    for key in ("dev_manifest_sha256", "protocol_sha256", "spm_fit_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(config.get(key, ""))):
            raise AddendumError(f"{key} must be a SHA-256")
    for name in ("ei", "rapm", "rapm_context", "ei_zero_prior", "league", "context"):
        spec = config["models"][name]
        if spec["window"] not in TEMPORAL_BY_NAME:
            raise AddendumError(f"unknown window for {name}")
        for key in ("offense_ridge", "defense_ridge"):
            if key in spec and not (np.isfinite(spec[key]) and spec[key] > 0):
                raise AddendumError(f"{name} {key} must be positive and finite")
    if set(map(int, config["box_logs"])) != {2022, *OUTER_SEASONS}:
        raise AddendumError("box log pins must cover 2022, 2023 and 2024")
    return config


def outer_logs(raw: Path, season: int, pin: Mapping[str, str]) -> tuple[list[Appearance], Any]:
    """Verify one pinned NBA.com log snapshot; holdout seasons and later dates refuse."""
    if season >= HOLDOUT_START_YEAR:
        raise ValueError(f"season {season} is the confirmatory holdout or later")
    directory = raw / SEASON_PINS[season].label / pin["snapshot"]
    record = read_json(checked_file(directory / "snapshot.json", pin["sha256"]))
    if record["season_start_year"] != season or record["attribution"] != ATTRIBUTION:
        raise ValueError("box log snapshot season or attribution mismatch")
    assets = {asset["name"]: asset for asset in record["artifacts"]}
    for name in (PLAYER_LOG, TEAM_LOG):
        path = checked_file(directory / name, assets[name]["sha256"])
        if path.stat().st_size != assets[name]["size_bytes"]:
            raise ValueError("box log snapshot size mismatch")
    with duckdb.connect() as connection:
        rows, profile = load_appearances(connection, directory, season_start_year=season)
    if not rows or any(row.game_date >= FINAL_CUTOFF for row in rows):
        raise ValueError("box log rows fall outside the authorized dates")
    return rows, {"snapshot": pin["snapshot"], "snapshot_sha256": pin["sha256"], **profile}


def lineup_min(
    values: FloatArray, rows: Rows, scored: NDArray[np.int64], design_ids: Sequence[int]
) -> FloatArray:
    """Smallest per-player value among the ten players of each scored row.

    ``values`` starts with the sorted design players; box-only players come after them and
    never appear in a row.
    """
    ids = np.asarray(design_ids, dtype=np.int64)
    both = np.concatenate([rows.offense[scored], rows.defense[scored]], axis=1)
    found: FloatArray = values[: ids.size][np.searchsorted(ids, both)].min(axis=1)
    return found


def stability(snapshots: Sequence[Ratings]) -> dict[str, Any]:
    """Correlation of total ratings between snapshots for players well exposed in both."""

    def corr(a: Ratings, b: Ratings) -> dict[str, Any]:
        common, ia, ib = np.intersect1d(a.player_ids, b.player_ids, return_indices=True)
        keep = (a.exposure[ia] >= EXPOSURE_FLOOR) & (b.exposure[ib] >= EXPOSURE_FLOOR)
        x, y = a.rating[ia][keep].sum(axis=1), b.rating[ib][keep].sum(axis=1)
        return {
            "players": int(keep.sum()),
            "total_r": float(np.corrcoef(x, y)[0, 1]) if keep.sum() > 2 else None,
            "rms_change": float(np.sqrt(np.mean((x - y) ** 2))) if keep.any() else None,
        }

    by_cutoff = {snap.cutoff: snap for snap in snapshots}
    ordered = sorted(by_cutoff)
    result = {
        f"{a.isoformat()}->{b.isoformat()}": corr(by_cutoff[a], by_cutoff[b])
        for a, b in zip(ordered, ordered[1:], strict=False)
    }
    year = (date(2023, 10, 1), date(2024, 10, 1))
    result["season_start_year_over_year"] = corr(by_cutoff[year[0]], by_cutoff[year[1]])
    return result


def evaluate(
    rows: Rows,
    analysis: Analysis,
    config: Mapping[str, Any],
    spm: Any,
    logs: Mapping[int, Sequence[Appearance]],
) -> tuple[dict[str, Any], list[Ratings], dict[str, Any]]:
    models = config["models"]
    ei, zero = models["ei"], models["ei_zero_prior"]
    window = TEMPORAL_BY_NAME[ei["window"]]
    if window.name != "W2":
        raise AddendumError("v1 prepare() uses the W2 window")
    blocks: list[Block] = [b for s in OUTER_SEASONS for b in season_blocks(rows, s)]
    frozen: dict[str, dict[str, FloatArray]] = {}
    exposure: dict[str, dict[str, FloatArray]] = {}
    snapshots: list[Ratings] = []
    audits: dict[str, Any] = {}
    for b in blocks:
        p = prepare(analysis, b.cutoff, spm, logs[b.season - 1], logs[b.season])
        scored = analysis.scored(b)
        overlap = np.intersect1d(rows.game[p.index], rows.game[scored])
        if overlap.size or int(np.min(rows.day[scored])) < b.cutoff.toordinal():
            raise ValueError(f"block {b.label} scores a game inside its fit window")
        fit = fit_informed(analysis, p, ei["offense_ridge"], ei["defense_ridge"], b.label)
        predictions = predict_informed(analysis, p, fit, scored)
        predictions["spm_only"] = spm_only(analysis, p, scored)
        predictions["ei_zero_prior"] = analysis.rapm_context(
            b, TEMPORAL_BY_NAME[zero["window"]], zero["offense_ridge"], zero["defense_ridge"]
        )
        rapm = models["rapm"]
        predictions["rapm"] = analysis.rapm(
            b, TEMPORAL_BY_NAME[rapm["window"]], rapm["offense_ridge"], rapm["defense_ridge"]
        )[1]["rapm"]
        rc = models["rapm_context"]
        predictions["rapm_context"] = analysis.rapm_context(
            b, TEMPORAL_BY_NAME[rc["window"]], rc["offense_ridge"], rc["defense_ridge"]
        )
        predictions["league"] = analysis.league(b, TEMPORAL_BY_NAME[models["league"]["window"]])
        predictions["context"] = analysis.context(b, TEMPORAL_BY_NAME[models["context"]["window"]])
        frozen[b.label] = predictions
        snap = ratings(p, fit, analysis.design, {**ei, "cutoff": b.cutoff, "spm": spm.fit_id})
        snapshots.append(snap)
        exposure[b.label] = {
            "min_window_possessions": lineup_min(
                snap.exposure, rows, scored, analysis.design.player_ids
            ),
            "all_box_history": lineup_min(
                snap.box_history.astype(np.float64), rows, scored, analysis.design.player_ids
            ),
        }
        audits[b.label] = p.audit
    final = prepare(analysis, FINAL_CUTOFF, spm, logs[2023], logs[2024])
    final_fit = fit_informed(analysis, final, ei["offense_ridge"], ei["defense_ridge"], "final")
    snapshots.append(
        ratings(
            final, final_fit, analysis.design, {**ei, "cutoff": FINAL_CUTOFF, "spm": spm.fit_id}
        )
    )
    audits["final"] = final.audit
    # Every prediction is fixed above; scoring follows.
    results: dict[str, Any] = {"eligibility": audits, "blocks": {}}
    for b in blocks:
        results["blocks"][b.label] = score_set(rows, analysis.scored(b), frozen[b.label])
    regular = [b for b in blocks if b.role == "regular"]
    playoffs = [b for b in blocks if b.role == "playoffs"]
    for role, chosen in (("regular", regular), ("playoffs", playoffs)):
        index = np.concatenate([analysis.scored(b) for b in chosen])
        merged = {
            name: np.concatenate([frozen[b.label][name] for b in chosen])
            for name in frozen[chosen[0].label]
        }
        lowest = np.concatenate([exposure[b.label]["min_window_possessions"] for b in chosen])
        history = np.concatenate([exposure[b.label]["all_box_history"] for b in chosen])
        pooled = score_set(rows, index, merged)
        pooled["team_game_rmse"] = {
            name: team_game_rmse(rows.team_game[index], rows.y[index], value)
            for name, value in merged.items()
        }
        slices = {
            **{str(s): rows.season[index] == s for s in OUTER_SEASONS},
            "no_livedata": rows.no_livedata[index],
            "livedata": ~rows.no_livedata[index],
            "all_ten_exposed_1000": lowest >= EXPOSURE_FLOOR,
            "some_player_under_1000": lowest < EXPOSURE_FLOOR,
            "all_ten_box_history": history == 1,
            "some_player_prior_fallback": history == 0,
        }
        for name, keep in slices.items():
            if keep.any():
                pooled[name] = score_set(rows, index[keep], {k: v[keep] for k, v in merged.items()})
        results[f"pooled_{role}"] = pooled
    results["stability"] = stability(snapshots)
    predictions_out = {
        "block": np.concatenate([np.full(analysis.scored(b).size, b.label) for b in blocks]),
        "game_id": np.asarray(
            [rows.game_ids[g] for b in blocks for g in rows.game[analysis.scored(b)]]
        ),
        "possession_seq": np.concatenate([rows.possession_seq[analysis.scored(b)] for b in blocks]),
        **{
            name: np.concatenate([frozen[b.label][name] for b in blocks])
            for name in frozen[blocks[0].label]
        },
    }
    return results, snapshots, predictions_out


def verdicts(results: Mapping[str, Any], primary: str) -> dict[str, Any]:
    """Addendum rule: pooled regular delta < 0 with the game interval excluding 0, same sign
    in both outer seasons."""
    pooled = results["pooled_regular"]
    out = {}
    for name, entry in pooled["ei_delta_vs"].items():
        seasons = [pooled[str(s)]["ei_delta_vs"][name]["delta"] for s in OUTER_SEASONS]
        high = entry["ci95_game"][1]
        low = entry["ci95_game"][0]
        if high < 0 and all(d < 0 for d in seasons):
            verdict = "ei_better"
        elif low > 0 and all(d > 0 for d in seasons):
            verdict = "ei_worse"
        else:
            verdict = "inconclusive"
        out[name] = verdict
    out["primary_comparator"] = primary
    return out


def run(raw: Path, processed: Path, output: Path, addendum_sha256: str) -> dict[str, Any]:
    started = time.perf_counter()
    freeze = verify_addendum(ADDENDUM, addendum_sha256, REPO_ROOT)
    config = parse_config(ADDENDUM.read_text(encoding="utf-8"))
    dev_manifest = processed / "expected_impact" / "issue-35-v1" / "manifest.json"
    checked_file(dev_manifest, config["dev_manifest_sha256"])
    if (
        sha256_file(REPO_ROOT / "docs/research/expected-impact-protocol.md")
        != (config["protocol_sha256"])
    ):
        raise AddendumError("the development protocol differs from the one the addendum names")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    spm_dir = processed / "spm" / SPM_RUN
    checked_file(spm_dir / "manifest.json", SPM_MANIFEST)
    spm = spm_fit(read_json(checked_file(spm_dir / config["spm_fit"], config["spm_fit_sha256"])))
    logs, log_inputs = {}, {}
    for key, pin in config["box_logs"].items():
        logs[int(key)], log_inputs[key] = outer_logs(raw, int(key), pin)
    with TemporaryDirectory(prefix=".ei-outer-", dir=output.parent) as sandbox:
        stage = Path(sandbox) / "results"
        stage.mkdir()
        _, rows, design, row_inputs = _prepare(processed, ROW_SEASONS, ROW_SEASONS, stage)
        log: list[dict[str, Any]] = []
        analysis = Analysis(
            rows, design, Scenario("primary", np.ones(len(rows), dtype=bool)), [], log
        )
        results, snapshots, predictions = evaluate(rows, analysis, config, spm, logs)
        np.savez_compressed(stage / "predictions.npz", **predictions)
        write_ratings(stage / "ratings.csv", snapshots)
        results.update(
            verdicts=verdicts(results, config["primary_comparator"]),
            frozen_configuration=config,
            artifact_label=ARTIFACT_LABEL,
            evidence_tier=EVIDENCE,
            solver=_solver_summary(log),
            outcomes={
                f"{s}_{role}": {
                    "scored_possessions": int(
                        ((rows.season == s) & (rows.playoff == (role == "playoffs"))).sum()
                    ),
                    "outcome_sha256": outcome_digest(
                        rows, (rows.season == s) & (rows.playoff == (role == "playoffs"))
                    ),
                }
                for s in OUTER_SEASONS
                for role in ("regular", "playoffs")
            },
        )
        _write_json(stage / "results.json", results)
        _write_json(stage / "fit_log.json", log)
        head, clean = _git_head()
        manifest = {
            "schema_version": 1,
            "version": VERSION,
            "artifact_label": ARTIFACT_LABEL,
            "evidence_tier": EVIDENCE,
            "addendum": freeze,
            "code_commit": head,
            "working_tree_clean_at_end": clean,
            "inputs": {"rows": row_inputs, "box_logs": log_inputs, "spm": config["spm_fit"]},
            "versions": _versions(),
            "runtime_seconds": time.perf_counter() - started,
            "peak_memory_mib": _peak_memory_mib(),
            "outputs": {
                path.name: sha256_file(path) for path in sorted(stage.iterdir()) if path.is_file()
            },
            "private_outputs": ["ratings.csv", "predictions.npz"],
        }
        _write_json(stage / "manifest.json", manifest)
        stage.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--addendum-sha256", required=True)
    args = parser.parse_args()
    run(args.raw.resolve(), args.processed.resolve(), args.output.resolve(), args.addendum_sha256)


if __name__ == "__main__":
    main()
