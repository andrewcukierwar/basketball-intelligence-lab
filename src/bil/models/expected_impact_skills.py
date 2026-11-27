"""Expected impact with an as-of Estimated Skills SPM prior (#125).

Registered protocol: ``docs/research/skill-prior-protocol.md``. The model is #35 v1 with one
change: the frozen #30 SPM is **applied** to as-of skill estimates from a chronologically fitted
Skills bundle (`bil.features.skill_bundle`) instead of the raw dated box snapshot. Windows,
context offset, penalties (8,000/8,000), SPM fits and blocks are those of #35 (development seasons
2021–22 and 2022–23) and #36 (outer seasons 2023–24 and 2024–25). Every block also refits v1
with the raw prior, which must reproduce the published #35/#36 EI predictions, so the primary
contrast is matched on rows, folds, cadence, SPM and penalties.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.data.pilot_sources import sha256_file
from bil.features.box import Appearance
from bil.features.skill_bundle import SkillBundle, bundle_values, check_bundle, fit_bundle
from bil.models.expected_impact import ROW_SEASONS as DEV_ROW_SEASONS
from bil.models.expected_impact import SCORED_SEASONS as DEV_SEASONS
from bil.models.expected_impact import (
    SPM_FITS,
    SPM_MANIFEST,
    SPM_RUN,
    WINDOW,
    Prepared,
    SpmFit,
    fit_informed,
    predict_informed,
    prepare,
    ratings,
    score_set,
    spm_fit,
    spm_only,
)
from bil.models.expected_impact_outer import (
    ADDENDUM,
    EXPOSURE_FLOOR,
    OUTER_SEASONS,
    lineup_min,
    outer_logs,
    parse_config,
)
from bil.models.expected_impact_outer import ROW_SEASONS as OUTER_ROW_SEASONS
from bil.models.rapm.baseline import _peak_memory_mib
from bil.models.rapm.multiseason import (
    REPO_ROOT,
    TEMPORAL_BY_NAME,
    Analysis,
    Block,
    Design,
    Rows,
    Scenario,
    _git_head,
    _prepare,
    _versions,
    _write_json,
    season_blocks,
)
from bil.models.rapm.targets import verify_protocol
from bil.models.spm import LinearPrior
from bil.models.spm_build import checked_file, checked_logs, read_json

FloatArray = NDArray[np.float64]

VERSION = "issue-125-v1"
PROTOCOL = REPO_ROOT / "docs/research/skill-prior-protocol.md"
PENALTIES = (8000.0, 8000.0)  # the #35 selection, used unchanged in both fold groups
ZERO_PRIOR = (8000.0, 8000.0)
BASELINE = (4000.0, 8000.0)
SCORING_SEASONS = (*DEV_SEASONS, *OUTER_SEASONS)  # 2021..2024
LOG_SEASONS = tuple(range(min(SCORING_SEASONS) - 3, max(SCORING_SEASONS) + 1))  # 2018..2024
DEV_RUN = "issue-35-v1"
OUTER_RUN = "issue-36-v1"
REPRODUCTION_TOLERANCE = 1e-6


def skill_prepared(
    prepared: Prepared,
    analysis: Analysis,
    rows: Sequence[Appearance],
    bundle: SkillBundle,
    season: int,
) -> tuple[Prepared, dict[str, Any]]:
    """The v1 preparation with the SPM applied to as-of skill estimates instead of raw rates."""
    check_bundle(bundle, prepared.cutoff, season)
    skills = bundle_values(rows, bundle, prepared.cutoff, prepared.player_ids.tolist())
    priors = np.column_stack([model.predict(skills.values) for model in prepared.spm.pair])
    m = analysis.design.size
    offset = np.asarray(analysis.design.players @ np.concatenate([priors[:m, 0], priors[:m, 1]]))
    known = prepared.box_history & skills.has_history
    audit = {
        **prepared.audit,
        **skills.audit,
        "raw_history_without_skill_history": int(
            (prepared.box_history & ~skills.has_history).sum()
        ),
        "skill_history_without_raw_history": int(
            (skills.has_history & ~prepared.box_history).sum()
        ),
        "prior_correlation_vs_raw": {
            side: float(np.corrcoef(priors[known, i], prepared.priors[known, i])[0, 1])
            for i, side in enumerate(("offense", "defense"))
        },
        "prior_sd": {
            side: {
                "skills": float(priors[known, i].std()),
                "raw": float(prepared.priors[known, i].std()),
            }
            for i, side in enumerate(("offense", "defense"))
        },
    }
    return (
        replace(
            prepared, priors=priors, offset=offset, box_history=skills.has_history, audit=audit
        ),
        audit,
    )


def block_predictions(
    analysis: Analysis,
    block: Block,
    raw: Prepared,
    skilled: Prepared,
    comparators: Mapping[str, Any],
) -> tuple[dict[str, FloatArray], dict[str, FloatArray]]:
    rows = analysis.rows
    scored = analysis.scored(block)
    overlap = np.intersect1d(rows.game[raw.index], rows.game[scored])
    if overlap.size or int(np.min(rows.day[scored])) < block.cutoff.toordinal():
        raise ValueError(f"block {block.label} scores a game inside its fit window")
    fit_s = fit_informed(analysis, skilled, *PENALTIES, f"{block.label}:skills")
    fit_r = fit_informed(analysis, raw, *PENALTIES, f"{block.label}:raw")
    out = predict_informed(analysis, skilled, fit_s, scored)
    out["ei_raw"] = predict_informed(analysis, raw, fit_r, scored)["ei"]
    out["spm_only"] = spm_only(analysis, skilled, scored)
    out["spm_only_raw"] = spm_only(analysis, raw, scored)
    out["ei_zero_prior"] = analysis.rapm_context(block, WINDOW, *ZERO_PRIOR)
    out["rapm"] = analysis.rapm(block, WINDOW, *BASELINE)[1]["rapm"]
    out["rapm_context"] = analysis.rapm_context(block, WINDOW, *BASELINE)
    league_window = TEMPORAL_BY_NAME[comparators["league"]]
    context_window = TEMPORAL_BY_NAME[comparators["context"]]
    out["league"] = analysis.league(block, league_window)
    out["context"] = analysis.context(block, context_window)
    snap_s = ratings(skilled, fit_s, analysis.design, {"cutoff": block.cutoff})
    snap_r = ratings(raw, fit_r, analysis.design, {"cutoff": block.cutoff})
    ids = analysis.design.player_ids
    coverage = {
        "min_window_possessions": lineup_min(snap_s.exposure, rows, scored, ids),
        "all_skill_history": lineup_min(snap_s.box_history.astype(np.float64), rows, scored, ids),
        "all_raw_history": lineup_min(snap_r.box_history.astype(np.float64), rows, scored, ids),
    }
    return out, coverage


def fold_results(
    rows: Rows,
    analysis: Analysis,
    blocks: Sequence[Block],
    frozen: Mapping[str, Mapping[str, FloatArray]],
    coverage: Mapping[str, Mapping[str, FloatArray]],
    seasons: Sequence[int],
) -> dict[str, Any]:
    results: dict[str, Any] = {"blocks": {}}
    for b in blocks:
        results["blocks"][b.label] = score_set(rows, analysis.scored(b), frozen[b.label])
    for role in ("regular", "playoffs"):
        chosen = [b for b in blocks if b.role == role]
        index = np.concatenate([analysis.scored(b) for b in chosen])
        merged = {
            name: np.concatenate([frozen[b.label][name] for b in chosen])
            for name in frozen[chosen[0].label]
        }
        cov = {
            name: np.concatenate([coverage[b.label][name] for b in chosen])
            for name in coverage[chosen[0].label]
        }
        pooled = score_set(rows, index, merged)
        slices = {
            **{str(s): rows.season[index] == s for s in seasons},
            "all_ten_exposed_1000": cov["min_window_possessions"] >= EXPOSURE_FLOOR,
            "some_player_under_1000": cov["min_window_possessions"] < EXPOSURE_FLOOR,
            "all_ten_skill_history": cov["all_skill_history"] == 1,
            "some_player_skill_cold": cov["all_skill_history"] == 0,
            "all_ten_raw_history": cov["all_raw_history"] == 1,
            "some_player_raw_cold": cov["all_raw_history"] == 0,
        }
        pooled["slice_possessions"] = {name: int(keep.sum()) for name, keep in slices.items()}
        for name, keep in slices.items():
            if keep.any():
                pooled[name] = score_set(rows, index[keep], {k: v[keep] for k, v in merged.items()})
        results[f"pooled_{role}"] = pooled
    return results


def verdict(pooled: Mapping[str, Any], seasons: Sequence[int], name: str) -> str:
    """#36 addendum rule: game interval excludes 0 and the sign holds in every season."""
    entry = pooled["ei_delta_vs"][name]
    per_season = [pooled[str(s)]["ei_delta_vs"][name]["delta"] for s in seasons]
    low, high = entry["ci95_game"]
    if high < 0 and all(d < 0 for d in per_season):
        return "skills_better"
    if low > 0 and all(d > 0 for d in per_season):
        return "skills_worse"
    return "inconclusive"


def evaluate_fold(
    rows: Rows,
    design: Design,
    seasons: Sequence[int],
    spm: Mapping[int, SpmFit],
    logs: Mapping[int, Sequence[Appearance]],
    bundles: Mapping[int, SkillBundle],
    comparators: Mapping[str, Any],
    published: Mapping[str, NDArray[Any]],
    log: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    analysis = Analysis(rows, design, Scenario("primary", np.ones(len(rows), dtype=bool)), [], log)
    blocks: list[Block] = [b for s in seasons for b in season_blocks(rows, s)]
    analysis.blocks = blocks
    analysis.regular = [b for b in blocks if b.role == "regular"]
    analysis.playoffs = [b for b in blocks if b.role == "playoffs"]
    every = [row for s in sorted(logs) for row in logs[s]]
    frozen: dict[str, dict[str, FloatArray]] = {}
    coverage: dict[str, dict[str, FloatArray]] = {}
    audits: dict[str, Any] = {}
    for b in blocks:
        raw = prepare(analysis, b.cutoff, spm[b.season], logs[b.season - 1], logs[b.season])
        skilled, audits[b.label] = skill_prepared(raw, analysis, every, bundles[b.season], b.season)
        frozen[b.label], coverage[b.label] = block_predictions(
            analysis, b, raw, skilled, comparators
        )
    # Every prediction is fixed above; reproduction and scoring follow.
    labels = np.concatenate([np.full(analysis.scored(b).size, b.label) for b in blocks])
    ours = np.concatenate([frozen[b.label]["ei_raw"] for b in blocks])
    if not np.array_equal(labels, published["block"]) or ours.shape != published["ei"].shape:
        raise ValueError("scored rows differ from the published run")
    gap = float(np.max(np.abs(ours - published["ei"])))
    if gap > REPRODUCTION_TOLERANCE:
        raise ValueError(f"v1 raw-prior EI does not reproduce the published run ({gap})")
    results = fold_results(rows, analysis, blocks, frozen, coverage, seasons)
    results["eligibility"] = audits
    results["reproduction"] = {"max_abs_ei_raw_vs_published": gap, "rows": int(ours.size)}
    pooled = results["pooled_regular"]
    results["verdicts"] = {name: verdict(pooled, seasons, name) for name in pooled["ei_delta_vs"]}
    predictions = {
        "block": labels,
        "game_id": np.asarray(
            [rows.game_ids[g] for b in blocks for g in rows.game[analysis.scored(b)]]
        ),
        "possession_seq": np.concatenate([rows.possession_seq[analysis.scored(b)] for b in blocks]),
        **{
            name: np.concatenate([frozen[b.label][name] for b in blocks])
            for name in frozen[blocks[0].label]
        },
    }
    return results, predictions


def _published(processed: Path, run: str) -> dict[str, NDArray[Any]]:
    directory = processed / "expected_impact" / run
    manifest = read_json(directory / "manifest.json")
    path = checked_file(directory / "predictions.npz", manifest["outputs"]["predictions.npz"])
    with np.load(path) as data:
        return {"block": data["block"], "ei": data["ei"]}


def _priors_record(prior: LinearPrior) -> dict[str, Any]:
    return dict(prior.record())


def run(raw: Path, processed: Path, output: Path, protocol_sha256: str) -> dict[str, Any]:
    started = time.perf_counter()
    protocol = verify_protocol(PROTOCOL, protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    config = parse_config(ADDENDUM.read_text(encoding="utf-8"))
    comparators = {
        "development": {"league": WINDOW.name, "context": WINDOW.name},
        "outer": {
            "league": config["models"]["league"]["window"],
            "context": config["models"]["context"]["window"],
        },
    }
    spm_dir = processed / "spm" / SPM_RUN
    spm_manifest = read_json(checked_file(spm_dir / "manifest.json", SPM_MANIFEST))
    dev_spm = {
        season: spm_fit(read_json(checked_file(spm_dir / name, spm_manifest["outputs"][name])))
        for season, name in SPM_FITS.items()
    }
    final = spm_fit(read_json(checked_file(spm_dir / config["spm_fit"], config["spm_fit_sha256"])))
    logs: dict[int, list[Appearance]] = {}
    log_inputs: dict[str, Any] = {}
    for season in LOG_SEASONS:
        pin = config["box_logs"].get(str(season))
        if season >= 2023:
            logs[season], log_inputs[str(season)] = outer_logs(raw, season, pin)
        else:
            logs[season], log_inputs[str(season)] = checked_logs(raw, season)
            if pin is not None and pin["sha256"] != log_inputs[str(season)]["snapshot_sha256"]:
                raise ValueError(f"box log pins for {season} disagree")
    every = [row for s in LOG_SEASONS for row in logs[s]]
    fit_started = time.perf_counter()
    bundles = {season: fit_bundle(every, season) for season in SCORING_SEASONS}
    fit_seconds = time.perf_counter() - fit_started
    with TemporaryDirectory(prefix=".ei-skills-", dir=output.parent) as sandbox:
        stage = Path(sandbox) / "results"
        stage.mkdir()
        log: list[dict[str, Any]] = []
        results: dict[str, Any] = {
            "version": VERSION,
            "spm_input": "applied",
            "penalties": list(PENALTIES),
            "bundles": {str(s): b.record() for s, b in bundles.items()},
            "bundle_fit_seconds": fit_seconds,
            "spm": {
                "development": {str(s): f.fit_id for s, f in dev_spm.items()},
                "outer": final.fit_id,
            },
        }
        row_inputs = {}
        folds = (
            ("development", DEV_ROW_SEASONS, DEV_SEASONS, dev_spm, DEV_RUN),
            (
                "outer",
                OUTER_ROW_SEASONS,
                OUTER_SEASONS,
                dict.fromkeys(OUTER_SEASONS, final),
                OUTER_RUN,
            ),
        )
        for name, row_seasons, seasons, spm, published in folds:
            fold_dir = stage / name
            fold_dir.mkdir()
            _, rows, design, row_inputs[name] = _prepare(
                processed, row_seasons, row_seasons, fold_dir
            )
            fold_logs = {s: logs[s] for s in LOG_SEASONS if s <= max(seasons)}
            results[name], predictions = evaluate_fold(
                rows,
                design,
                seasons,
                spm,
                fold_logs,
                bundles,
                comparators[name],
                _published(processed, published),
                log,
            )
            np.savez_compressed(stage / f"predictions_{name}.npz", **predictions)
            fold_dir.rmdir()
        _write_json(stage / "results.json", results)
        _write_json(stage / "fit_log.json", log)
        head, clean = _git_head()
        manifest = {
            "schema_version": 1,
            "version": VERSION,
            "protocol": protocol,
            "code_commit": head,
            "working_tree_clean_at_end": clean,
            "inputs": {
                "rows": row_inputs,
                "box_logs": log_inputs,
                "spm_manifest_sha256": SPM_MANIFEST,
                "published_runs": [DEV_RUN, OUTER_RUN],
            },
            "versions": _versions(),
            "runtime_seconds": time.perf_counter() - started,
            "peak_memory_mib": _peak_memory_mib(),
            "outputs": {
                path.name: sha256_file(path) for path in sorted(stage.iterdir()) if path.is_file()
            },
            "private_outputs": ["predictions_development.npz", "predictions_outer.npz"],
        }
        _write_json(stage / "manifest.json", manifest)
        stage.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    manifest = run(args.raw, args.processed, args.output, args.protocol_sha256)
    print(manifest["outputs"])


if __name__ == "__main__":
    main()
