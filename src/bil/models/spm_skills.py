"""Retrain the chronological SPM on its as-of Skills inputs (#148)."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np

from bil.data.pilot_sources import sha256_file
from bil.features.box import Appearance
from bil.features.skill_bundle import SkillBundle, bundle_values, check_bundle, fit_bundle
from bil.features.skill_snapshot import SkillParams
from bil.models.expected_impact import ROW_SEASONS as DEV_ROW_SEASONS
from bil.models.expected_impact import SCORED_SEASONS as DEV_SEASONS
from bil.models.expected_impact import fit_informed, predict_informed, prepare, ratings, spm_fit
from bil.models.expected_impact_outer import (
    ADDENDUM,
    OUTER_SEASONS,
    lineup_min,
    outer_logs,
    parse_config,
)
from bil.models.expected_impact_outer import ROW_SEASONS as OUTER_ROW_SEASONS
from bil.models.expected_impact_skills import PENALTIES, fold_results, skill_prepared, verdict
from bil.models.rapm.baseline import _peak_memory_mib
from bil.models.rapm.multiseason import (
    REPO_ROOT,
    Analysis,
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
from bil.models.spm import CANDIDATES, CODES, completed_history, feature_matrix, fit_candidate
from bil.models.spm_build import (
    Labels,
    Opening,
    checked_ages,
    checked_file,
    checked_log_snapshot,
    checked_logs,
    label_scores,
    load_labels,
    model_records,
    read_json,
    summarize_label_pool,
    target_inputs,
)
from bil.models.spm_evaluation import VOLUME, PriorPair, pair_fallback, predict_pair

VERSION = "issue-148-v1"
PROTOCOL = REPO_ROOT / "docs/research/skills-spm-retraining-protocol.md"
APPLIED_RUN = "issue-125-v1"
APPLIED_MANIFEST = "97e083eae593e922a65e36412adc9b1f218a38a34e1dba318c0056f68e5bf529"
BOX_2017_PIN = "b7df4c826d425723db81de1af117fb3cd533d0c7df68e1612b59fd81bcd9fc60"
CALIBRATION_SEASONS = tuple(range(2018, 2023))
BUNDLE_SEASONS = tuple(range(2018, 2025))
FIT_CANDIDATES = {name: CANDIDATES[name] for name in ("zero", "mean", "one_stat", "full")}
Calendar = Mapping[int, tuple[date, date]]


def applied_input(processed: Path, name: str) -> Path:
    directory = processed / "expected_impact" / APPLIED_RUN
    manifest = read_json(checked_file(directory / "manifest.json", APPLIED_MANIFEST))
    return checked_file(directory / name, manifest["outputs"][name])


def source_inputs(
    raw: Path, processed: Path
) -> tuple[dict[int, list[Appearance]], dict[str, Any], dict[int, SkillBundle]]:
    config = parse_config(ADDENDUM.read_text(encoding="utf-8"))
    logs, pins = {}, {}
    for year in range(2015, 2025):
        if year >= 2023:
            logs[year], pins[str(year)] = outer_logs(raw, year, config["box_logs"][str(year)])
        elif year == 2017:
            directory = raw / "2017-18" / "issue-25-v1"
            logs[year], pins[str(year)] = checked_log_snapshot(directory, year, BOX_2017_PIN)
        else:
            logs[year], pins[str(year)] = checked_logs(raw, year)
    archived = read_json(applied_input(processed, "results.json"))["bundles"]
    bundles = {}
    for year in BUNDLE_SEASONS:
        parents = {str(s): pins[str(s)]["snapshot_sha256"] for s in range(year - 3, year)}
        if year < 2021:
            history = [row for s in range(year - 3, year) for row in logs[s]]
            bundle = fit_bundle(history, year, source_pins=parents)
        else:
            record = dict(archived[str(year)])
            record["outcomes_through"] = date.fromisoformat(record["outcomes_through"])
            record["fit_cutoff"] = date.fromisoformat(record["fit_cutoff"])
            record["history_seasons"] = tuple(record["history_seasons"])
            record["params"] = {code: SkillParams(**p) for code, p in record["params"].items()}
            bundle = SkillBundle(**record)
        check_bundle(bundle, bundle.fit_cutoff, year)
        if bundle.source_pins != parents:
            raise ValueError(f"box pins differ for Skills bundle {year}")
        bundles[year] = bundle
    return logs, pins, bundles


def fit_origin(
    labels: Labels,
    origin: Mapping[str, Any],
    calendar: Calendar,
    logs: Mapping[int, Sequence[Appearance]],
    bundles: Mapping[int, SkillBundle],
    pins: Mapping[str, Any],
) -> tuple[dict[str, PriorPair], dict[str, Any]]:
    origin_day = date.fromisoformat(origin["cutoff"])
    seasons = origin["seasons"]
    if {s for s, _ in labels} != set(seasons) or not set(seasons) <= set(CALIBRATION_SEASONS):
        raise ValueError("target rows differ from the registered calibration seasons")
    values = []
    responses: list[tuple[float, float]] = []
    exposures: list[tuple[float, float]] = []
    forward: list[bool] = []
    coverage = {}
    for season in seasons:
        cutoff = calendar[season][1] + timedelta(days=1)
        if cutoff > origin_day:
            raise ValueError(f"calibration features for {season} follow the fit origin")
        box = completed_history(logs[season], cutoff)
        by_player = {p: label for (s, p), label in labels.items() if s == season}
        players = sorted(p for p, label in by_player.items() if p in box and label.enough())
        if not players:
            raise ValueError(f"no eligible SPM calibration rows in {season}")
        history = [row for s in range(season - 3, season + 1) for row in logs[s]]
        check_bundle(bundles[season], cutoff, season)
        skills = bundle_values(history, bundles[season], cutoff, players)
        if not skills.has_history.all():
            raise ValueError("matched calibration players must have positive-minute box history")
        values.append(skills.values)
        responses.extend(by_player[p].values for p in players)
        exposures.extend(by_player[p].exposure for p in players)
        forward.extend(by_player[p].forward for p in players)
        coverage[str(season)] = {
            **skills.audit,
            "feature_cutoff": cutoff.isoformat(),
            "joined_training_rows": len(players),
            "target_only": len(set(by_player) - set(box)),
            "box_only": len(set(box) - set(by_player)),
            "labels_below_minimum": sum(not label.enough() for label in by_player.values()),
            "one_sided_training_rows": sum(not by_player[p].forward for p in players),
            "missing_features": dict(
                zip(CODES, np.isnan(skills.values).sum(0).tolist(), strict=True)
            ),
        }
    x, y = np.concatenate(values), np.asarray(responses, dtype=np.float64)
    n, support = np.asarray(exposures, dtype=np.float64), np.asarray(forward, dtype=np.bool_)
    models = {
        name: fit_candidate(x, y, n, support, candidate)
        for name, candidate in FIT_CANDIDATES.items()
    }
    record = model_records(models, f"contiguous@{origin_day}", origin, coverage, pins)
    record["version"] = VERSION
    record["feature_representation"] = "as_of_estimated_skills"
    del record["fit_id"]
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    record["fit_id"] = hashlib.sha256(encoded).hexdigest()
    return models, record


def skills_opening(
    season: int,
    cutoff: date,
    logs: Mapping[int, Sequence[Appearance]],
    bundle: SkillBundle,
    models: Mapping[str, PriorPair],
) -> Opening:
    history = [row for s in range(season - 3, season + 1) for row in logs[s]]
    box = completed_history(history, cutoff)
    players = sorted(box)
    check_bundle(bundle, cutoff, season)
    snapshot = bundle_values(history, bundle, cutoff, players)
    _, minutes = feature_matrix(box, players)
    return Opening(
        season,
        cutoff,
        np.asarray(players, dtype=np.int64),
        minutes,
        snapshot.values[:, VOLUME],
        {name: predict_pair(pair, snapshot.values) for name, pair in models.items()},
        {name: np.array([model.intercept for model in pair]) for name, pair in models.items()},
        {name: pair_fallback(pair, snapshot.values) for name, pair in models.items()},
    )


def compare_fold(
    rows: Rows,
    design: Design,
    seasons: Sequence[int],
    logs: Mapping[int, Sequence[Appearance]],
    bundles: Mapping[int, SkillBundle],
    fits: Mapping[int, Mapping[str, Any]],
    archived: Path,
    output: Path,
    fit_log: list[dict[str, Any]],
) -> dict[str, Any]:
    blocks = [block for season in seasons for block in season_blocks(rows, season)]
    scenario = Scenario("primary", np.ones(len(rows), dtype=bool))
    analysis = Analysis(rows, design, scenario, blocks, fit_log)
    scored = {block.label: analysis.scored(block) for block in blocks}
    keys = {
        "block": np.concatenate([np.full(scored[b.label].size, b.label) for b in blocks]),
        "game_id": np.asarray(
            [rows.game_ids[g] for b in blocks for g in rows.game[scored[b.label]]]
        ),
        "possession_seq": np.concatenate([rows.possession_seq[scored[b.label]] for b in blocks]),
    }
    with np.load(archived) as stored:
        if any(not np.array_equal(values, stored[name]) for name, values in keys.items()):
            raise ValueError(
                "ordered possession identities differ from the frozen #125 predictions"
            )
        raw, applied = stored["ei_raw"], stored["ei"]
    if any(p.shape != keys["block"].shape or not np.isfinite(p).all() for p in (raw, applied)):
        raise ValueError("frozen #125 predictions have invalid shapes or nonfinite values")

    prior_fits = {year: spm_fit(record) for year, record in fits.items()}
    predictions, coverage, audits = {}, {}, {}
    cursor = 0
    for b in blocks:
        index = scored[b.label]
        base = prepare(analysis, b.cutoff, prior_fits[b.season], logs[b.season - 1], logs[b.season])
        if np.intersect1d(rows.game[base.index], rows.game[index]).size or (
            int(np.min(rows.day[index])) < b.cutoff.toordinal()
        ):
            raise ValueError(f"block {b.label} scores a game inside its fit window")
        history = [row for y in range(b.season - 3, b.season + 1) for row in logs[y]]
        prepared, audit = skill_prepared(base, analysis, history, bundles[b.season], b.season)
        fit = fit_informed(analysis, prepared, *PENALTIES, f"{b.label}:skills_retrained")
        prediction = predict_informed(analysis, prepared, fit, index)["ei"]
        if not np.isfinite(prediction).all():
            raise ValueError(f"block {b.label} has nonfinite predictions")
        end = cursor + index.size
        predictions[b.label] = {
            "ei": prediction,
            "ei_raw": raw[cursor:end],
            "ei_applied": applied[cursor:end],
        }
        cursor = end
        snap = ratings(prepared, fit, design, {"cutoff": b.cutoff, "spm": prepared.spm.fit_id})
        coverage[b.label] = {
            "min_window_possessions": lineup_min(snap.exposure, rows, index, design.player_ids),
            "all_skill_history": lineup_min(
                snap.box_history.astype(float), rows, index, design.player_ids
            ),
            "all_raw_history": lineup_min(
                base.box_history.astype(float), rows, index, design.player_ids
            ),
        }
        audits[b.label] = {
            k: v for k, v in audit.items() if k not in {"prior_correlation_vs_raw", "prior_sd"}
        }
    np.savez_compressed(
        output,
        block=keys["block"],
        game_id=keys["game_id"],
        possession_seq=keys["possession_seq"],
        ei_raw=raw,
        ei_applied=applied,
        ei=np.concatenate([predictions[b.label]["ei"] for b in blocks]),
    )
    result = fold_results(rows, analysis, blocks, predictions, coverage, seasons)
    result["eligibility"] = audits
    result["verdicts"] = {
        name: verdict(result["pooled_regular"], seasons, name) for name in ("ei_raw", "ei_applied")
    }
    return result


def run(raw: Path, processed: Path, output: Path, protocol_sha256: str) -> dict[str, Any]:
    started = time.perf_counter()
    protocol = verify_protocol(PROTOCOL, protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    target_dir, registration, frozen, calendar, digests = target_inputs(processed)
    training = load_labels(target_dir / "targets.csv", evaluation=False)
    rules = registration["contiguous"]
    season_fit_keys = {
        fold["evaluation_season"]: fold["training_target_set"] for fold in rules["folds"]
    }
    fit_keys = list(season_fit_keys.values())
    fit_keys.append(rules["outer_seasons_use"])
    logs, pins, bundles = source_inputs(raw, processed)
    with TemporaryDirectory(prefix=".skills-spm-", dir=output.parent) as scratch:
        stage = Path(scratch) / "results"
        stage.mkdir()
        openings: dict[int, Opening] = {}
        fits = {}
        for key in fit_keys:
            models, fits[key] = fit_origin(
                training[key], frozen[key], calendar, logs, bundles, pins
            )
            fold = next((f for f in rules["folds"] if f["training_target_set"] == key), None)
            if fold is not None:
                season = fold["evaluation_season"]
                cutoff = calendar[season][0]
                if date.fromisoformat(frozen[key]["cutoff"]) > cutoff:
                    raise ValueError(f"SPM fit {key} follows the {season} opening")
                openings[season] = skills_opening(season, cutoff, logs, bundles[season], models)
        _write_json(stage / "fits.json", fits)
        _write_json(stage / "bundles.json", {str(s): b.record() for s, b in bundles.items()})

        evaluation = load_labels(target_dir / "evaluation_labels.csv", evaluation=True)
        ages, age_inputs = checked_ages(raw)
        k0, pooled = {}, []
        for season, opening in openings.items():
            k0[str(season)], players, errors = label_scores(
                opening, evaluation[fit_keys[-1]], ages.get(season, {})
            )
            pooled.append((players, errors))
        _write_json(stage / "k0.json", {"folds": k0, "pooled": summarize_label_pool(pooled)})
        comparison, row_inputs = {}, {}
        fit_log: list[dict[str, Any]] = []
        folds = (
            ("development", DEV_ROW_SEASONS, DEV_SEASONS),
            ("outer", OUTER_ROW_SEASONS, OUTER_SEASONS),
        )
        for name, row_seasons, seasons in folds:
            with TemporaryDirectory(prefix=f".{name}-", dir=scratch) as row_scratch:
                _, rows, design, row_inputs[name] = _prepare(
                    processed, row_seasons, row_seasons, Path(row_scratch)
                )
                comparison[name] = compare_fold(
                    rows,
                    design,
                    seasons,
                    logs,
                    bundles,
                    {s: fits[season_fit_keys.get(s, fit_keys[-1])] for s in seasons},
                    applied_input(processed, f"predictions_{name}.npz"),
                    stage / f"predictions_{name}.npz",
                    fit_log,
                )
        _write_json(stage / "comparison.json", comparison)
        _write_json(stage / "fit_log.json", fit_log)
        head, clean = _git_head()
        manifest = {
            "version": VERSION,
            "protocol": protocol,
            "code_commit": head,
            "working_tree_clean": clean,
            "inputs": {
                "targets": digests,
                "box_logs": pins,
                "age": age_inputs,
                "rows": row_inputs,
                "applied_manifest_sha256": APPLIED_MANIFEST,
            },
            "versions": _versions(),
            "runtime_seconds": time.perf_counter() - started,
            "peak_memory_mib": _peak_memory_mib(),
            "outputs": {path.name: sha256_file(path) for path in sorted(stage.iterdir())},
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
    print(run(args.raw, args.processed, args.output, args.protocol_sha256)["outputs"])


if __name__ == "__main__":
    main()
