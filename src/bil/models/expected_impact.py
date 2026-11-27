"""Expected impact v1: walk-forward RAPM centred on dated box-score SPM priors (#35).

The model at a cutoff ``C`` follows ``docs/research/expected-impact-protocol.md``: the ADR-0025
``W2`` window, a context-only offset, and a two-penalty ridge on the residual from the dated
SPM prior, so the rating is the prior plus an on-court deviation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.data.pilot_sources import sha256_file
from bil.features.box import Appearance
from bil.models.rapm.baseline import _peak_memory_mib
from bil.models.rapm.multiseason import (
    REPO_ROOT,
    TEMPORAL_BY_NAME,
    Analysis,
    Block,
    Design,
    PlayerFit,
    Rows,
    Scenario,
    _git_head,
    _prepare,
    _solver_summary,
    _versions,
    _write_json,
    paired_delta,
    predict,
    search_penalties,
    season_blocks,
    week_clusters,
)
from bil.models.rapm.targets import verify_protocol
from bil.models.spm import CODES, LinearPrior, completed_history, feature_matrix
from bil.models.spm_build import checked_file, checked_logs, read_json

FloatArray = NDArray[np.float64]
PriorPair = tuple[LinearPrior, LinearPrior]
VERSION = "issue-35-v1"
ARTIFACT_LABEL = "partial-history methodology replication"
EVIDENCE = "retrospective_capture_bound"
PROTOCOL = REPO_ROOT / "docs/research/expected-impact-protocol.md"
ROW_SEASONS = (2019, 2020, 2021, 2022)
BOX_SEASONS = (2020, 2021, 2022)
SCORED_SEASONS = (2021, 2022)
FINAL_CUTOFF = date(2023, 7, 1)
SPM_RUN = "issue-30-v2"
SPM_MANIFEST = "376d89ceb41ca8b90b1e36b3c6a6ad5d9ea09c32acd4e78114c16ec73f96786d"
SPM_FITS = {2021: "contiguous-2021/fit.json", 2022: "contiguous-2022/fit.json"}
FINAL_SPM_FIT = "final_contiguous_fit.json"
WINDOW = TEMPORAL_BY_NAME["W2"]
BASELINE_PENALTIES = (4000.0, 8000.0)
# Rating artifact versions. The frozen #35/#36/#39/#42 runners write the legacy export, whose
# roster is every globally indexed player. The as-of export (#135) keeps only players eligible
# at the cutoff and carries explicit cold priors.
LEGACY_ARTIFACT = "ei-ratings-v1"
AS_OF_ARTIFACT = "ei-ratings-as-of-v2"


# --- SPM prior snapshots ---------------------------------------------------------------


@dataclass(frozen=True)
class SpmFit:
    """One frozen #30 Full-candidate fit with its origin."""

    pair: PriorPair
    fit_id: str
    origin: str

    @property
    def origin_cutoff(self) -> date:
        return date.fromisoformat(self.origin.split("@", 1)[1])


def spm_fit(record: Mapping[str, Any], candidate: str = "full") -> SpmFit:
    """Rebuild a frozen linear prior pair from a #30 fit record."""
    sides = record["candidates"][candidate]
    pair = tuple(
        LinearPrior(
            tuple(CODES.index(code) for code in sides[side]["features"]),
            np.asarray(sides[side]["mean"], dtype=np.float64),
            np.asarray(sides[side]["scale"], dtype=np.float64),
            np.asarray(sides[side]["coefficients"], dtype=np.float64),
            float(sides[side]["intercept"]),
        )
        for side in ("offense", "defense")
    )
    return SpmFit((pair[0], pair[1]), str(record["fit_id"]), str(record["origin"]))


@dataclass(frozen=True)
class Prepared:
    """Everything at a cutoff that does not depend on the penalties."""

    cutoff: date
    index: NDArray[np.int64]
    weights: FloatArray
    context_intercept: float
    gamma: FloatArray
    player_ids: NDArray[np.int64]  # design players, then box-only players, sorted within each
    priors: FloatArray  # (len(player_ids), 2) points per 100, positive defense prevents points
    box_history: NDArray[np.bool_]
    offset: FloatArray  # per loaded row: signed lineup prior sum
    spm: SpmFit
    audit: dict[str, Any]


def prepare(
    analysis: Analysis,
    cutoff: date,
    spm: SpmFit,
    previous: Sequence[Appearance],
    current: Sequence[Appearance],
) -> Prepared:
    """Window, context fit and dated SPM prior at ``cutoff`` with the eligibility audit."""
    if spm.origin_cutoff >= cutoff:
        raise ValueError("the SPM fit origin is not strictly before the cutoff")
    rows, design = analysis.rows, analysis.design
    index, weights = analysis.window(cutoff, WINDOW)
    if not index.size:
        raise ValueError(f"no fit rows before {cutoff}")
    context_intercept, gamma = analysis.context_fit(cutoff, WINDOW)
    eligible = [row for row in (*previous, *current) if row.game_date < cutoff]
    history = completed_history(eligible, cutoff)
    design_ids = np.asarray(design.player_ids, dtype=np.int64)
    extra = np.asarray(sorted(set(history) - set(design.player_ids)), dtype=np.int64)
    player_ids = np.concatenate([design_ids, extra])
    values, _ = feature_matrix(history, player_ids.tolist())
    priors = np.column_stack([model.predict(values) for model in spm.pair])
    box_history = np.asarray([int(p) in history for p in player_ids], dtype=np.bool_)
    m = design.size
    offset = np.asarray(design.players @ np.concatenate([priors[:m, 0], priors[:m, 1]]))
    used_days = [row.game_date for row in eligible if row.minutes_ms > 0]
    audit = {
        "cutoff": cutoff.isoformat(),
        "window_rows": int(index.size),
        "window_first": date.fromordinal(int(np.min(rows.day[index]))).isoformat(),
        "window_last": date.fromordinal(int(np.max(rows.day[index]))).isoformat(),
        "box_last": max(used_days).isoformat() if used_days else None,
        "spm_origin": spm.origin,
        "spm_fit_id": spm.fit_id,
        "players": int(player_ids.size),
        "box_only_players": int(extra.size),
        "prior_fallback_players": int((~box_history).sum()),
        "context_zero_columns": int((gamma == 0).sum()),
    }
    if int(np.max(rows.day[index])) >= cutoff.toordinal() or (
        used_days and max(used_days) >= cutoff
    ):
        raise ValueError("an input row is not strictly before the cutoff")
    return Prepared(
        cutoff,
        index,
        weights,
        context_intercept,
        gamma,
        player_ids,
        priors,
        box_history,
        offset,
        spm,
        audit,
    )


def fit_informed(
    analysis: Analysis, prepared: Prepared, offense_ridge: float, defense_ridge: float, label: str
) -> PlayerFit:
    """Residual two-penalty ridge on ``y - Zγ - prior offset`` over the window rows."""
    rows, index = analysis.rows, prepared.index
    offset = rows.context[index] @ prepared.gamma + prepared.offset[index]
    return analysis.fit(
        prepared.cutoff, WINDOW, offense_ridge, defense_ridge, offset=offset, label=label
    )


def predict_informed(
    analysis: Analysis, prepared: Prepared, fit: PlayerFit, scored: NDArray[np.int64]
) -> dict[str, FloatArray]:
    base = analysis.rows.context[scored] @ prepared.gamma + prepared.offset[scored]
    return {
        name: predict(fit, analysis.design, scored, part) + base
        for name, part in (
            ("ei", "both"),
            ("ei_offense_only", "offense"),
            ("ei_defense_only", "defense"),
        )
    }


def spm_only(analysis: Analysis, prepared: Prepared, scored: NDArray[np.int64]) -> FloatArray:
    """Prior with no on-court update: window mean of the residual as the intercept."""
    rows, index = analysis.rows, prepared.index
    residual = rows.y[index] - rows.context[index] @ prepared.gamma - prepared.offset[index]
    intercept = float(np.average(residual, weights=prepared.weights))
    prediction: FloatArray = (
        intercept + rows.context[scored] @ prepared.gamma + prepared.offset[scored]
    )
    return prediction


@dataclass(frozen=True)
class Ratings:
    cutoff: date
    player_ids: NDArray[np.int64]
    prior: FloatArray  # (n, 2)
    deviation: FloatArray  # (n, 2)
    exposure: FloatArray
    box_history: NDArray[np.bool_]
    intercept: float
    snapshot_id: str
    spm_origin: str
    # Set only on an as-of artifact (#135): its version, the explicit per-side prior for a
    # player absent from the roster, and roster coverage counts.
    artifact_version: str = LEGACY_ARTIFACT
    cold: FloatArray | None = None
    coverage: Mapping[str, int] | None = None

    @property
    def rating(self) -> FloatArray:
        total: FloatArray = self.prior + self.deviation
        return total


def ratings(
    prepared: Prepared, fit: PlayerFit, design: Design, config: Mapping[str, Any]
) -> Ratings:
    """Prior, deviation and rating per side; players outside the window keep deviation 0."""
    m, n = design.size, prepared.player_ids.size
    deviation = np.zeros((n, 2))
    deviation[:m, 0] = fit.effects[:m]
    deviation[:m, 1] = fit.effects[m:]
    exposure = np.zeros(n)
    exposure[:m] = fit.exposure
    digest = hashlib.sha256()
    digest.update(json.dumps(dict(config), sort_keys=True, default=str).encode())
    for array in (prepared.player_ids, prepared.priors, deviation, prepared.gamma):
        digest.update(np.ascontiguousarray(array).tobytes())
    digest.update(np.float64(fit.intercept).tobytes())
    digest.update(np.float64(prepared.context_intercept).tobytes())
    return Ratings(
        prepared.cutoff,
        prepared.player_ids,
        prepared.priors,
        deviation,
        exposure,
        prepared.box_history,
        fit.intercept,
        digest.hexdigest(),
        prepared.spm.origin,
    )


def cold_prior(spm: SpmFit) -> FloatArray:
    """Per-side SPM prior of a player with no completed box history: each side's intercept."""
    blank = np.full((1, len(CODES)), np.nan)
    return np.asarray([float(model.predict(blank)[0]) for model in spm.pair])


def as_of_ratings(
    prepared: Prepared, fit: PlayerFit, design: Design, config: Mapping[str, Any]
) -> Ratings:
    """Versioned snapshot whose roster is eligible at the cutoff (#135).

    A player is on the roster with completed box history before the cutoff or exposure in the
    fit window, which ends before it. Anyone else, including players who first appear later in
    a globally indexed design, scores at the explicit per-side ``cold`` prior. That is the value
    the legacy export gave them, so ratings are unchanged while the roster, coverage and digest
    no longer depend on future identities. Possession-level predictions still use ``prepared``
    and the full design.
    """
    full = ratings(prepared, fit, design, config)
    keep = np.flatnonzero(full.box_history | (full.exposure > 0))
    keep = keep[np.argsort(full.player_ids[keep], kind="stable")]
    ids, prior, deviation = full.player_ids[keep], full.prior[keep], full.deviation[keep]
    exposure, box_history = full.exposure[keep], full.box_history[keep]
    cold = cold_prior(prepared.spm)
    coverage = {
        "players": int(ids.size),
        "box_history_players": int(box_history.sum()),
        "no_history_players": int((~box_history).sum()),
        "window_players": int((exposure > 0).sum()),
    }
    # The digest covers the values at the precision the artifact writes them. A design that
    # also indexes later players solves a larger system, which moves the same fit by ~1e-15.
    digest = hashlib.sha256()
    digest.update(AS_OF_ARTIFACT.encode())
    digest.update(json.dumps(dict(config), sort_keys=True, default=str).encode())
    digest.update(json.dumps(coverage, sort_keys=True).encode())
    digest.update(ids.astype(np.int64).tobytes() + box_history.astype(np.bool_).tobytes())
    floats = (prior, deviation, exposure, prepared.gamma, cold)
    scalars = (fit.intercept, prepared.context_intercept)
    for value in (*(v for a in floats for v in np.ravel(a)), *scalars):
        # Adding 0.0 maps a rounded -0.0 to 0.0, so sign noise on zero cannot move the digest.
        digest.update(f"{round(float(value), 6) + 0.0:.6f}|".encode())
    return Ratings(
        prepared.cutoff,
        ids,
        prior,
        deviation,
        exposure,
        box_history,
        fit.intercept,
        digest.hexdigest(),
        prepared.spm.origin,
        AS_OF_ARTIFACT,
        cold,
        coverage,
    )


# --- development run -------------------------------------------------------------------


def score_set(
    rows: Rows, index: NDArray[np.int64], predictions: Mapping[str, FloatArray]
) -> dict[str, Any]:
    y = rows.y[index]
    clusters = {"game": rows.game[index], "week": week_clusters(rows.day[index])}
    model = predictions["ei"]
    return {
        "possessions": int(index.size),
        "games": int(np.unique(rows.game[index]).size),
        "mse": {name: float(np.mean((p - y) ** 2)) for name, p in predictions.items()},
        "ei_delta_vs": {
            name: paired_delta(y, model, p, clusters)
            for name, p in predictions.items()
            if name != "ei"
        },
    }


def development(
    rows: Rows,
    design: Design,
    spm: Mapping[int, SpmFit],
    final_spm: SpmFit,
    logs: Mapping[int, Sequence[Appearance]],
    log: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Ratings], dict[str, Any]]:
    analysis = Analysis(rows, design, Scenario("primary", np.ones(len(rows), dtype=bool)), [], log)
    blocks: list[Block] = [b for s in SCORED_SEASONS for b in season_blocks(rows, s)]
    analysis.blocks = blocks
    analysis.regular = [b for b in blocks if b.role == "regular"]
    analysis.playoffs = [b for b in blocks if b.role == "playoffs"]
    prepared = {
        b.label: prepare(analysis, b.cutoff, spm[b.season], logs[b.season - 1], logs[b.season])
        for b in blocks
    }
    for b in blocks:
        scored = analysis.scored(b)
        overlap = np.intersect1d(rows.game[prepared[b.label].index], rows.game[scored])
        if overlap.size or int(np.min(rows.day[scored])) < b.cutoff.toordinal():
            raise ValueError(f"block {b.label} scores a game inside its fit window")

    def pooled(offense_ridge: float, defense_ridge: float) -> float:
        error = count = 0.0
        for b in analysis.regular:
            p = prepared[b.label]
            fit = fit_informed(analysis, p, offense_ridge, defense_ridge, f"{b.label}:search")
            scored = analysis.scored(b)
            pred = predict_informed(analysis, p, fit, scored)["ei"]
            error += float(((pred - rows.y[scored]) ** 2).sum())
            count += scored.size
        return error / count

    started = time.perf_counter()
    (offense_ridge, defense_ridge), trace = search_penalties(pooled)
    search_seconds = time.perf_counter() - started
    config = {
        "version": VERSION,
        "window": WINDOW.name,
        "offense_ridge": offense_ridge,
        "defense_ridge": defense_ridge,
    }

    snapshots: list[Ratings] = []
    frozen: dict[str, dict[str, FloatArray]] = {}
    for b in blocks:
        p = prepared[b.label]
        fit = fit_informed(analysis, p, offense_ridge, defense_ridge, f"{b.label}:selected")
        scored = analysis.scored(b)
        predictions = predict_informed(analysis, p, fit, scored)
        predictions["spm_only"] = spm_only(analysis, p, scored)
        predictions["league"] = analysis.league(b, WINDOW)
        predictions["context"] = analysis.context(b, WINDOW)
        predictions["rapm"] = analysis.rapm(b, WINDOW, *BASELINE_PENALTIES)[1]["rapm"]
        predictions["rapm_context"] = analysis.rapm_context(b, WINDOW, *BASELINE_PENALTIES)
        frozen[b.label] = predictions
        snapshots.append(
            ratings(p, fit, design, {**config, "cutoff": b.cutoff, "spm": p.spm.fit_id})
        )

    final_prepared = prepare(analysis, FINAL_CUTOFF, final_spm, logs[2021], logs[2022])
    final_fit = fit_informed(analysis, final_prepared, offense_ridge, defense_ridge, "final")
    snapshots.append(
        ratings(
            final_prepared,
            final_fit,
            design,
            {**config, "cutoff": FINAL_CUTOFF, "spm": final_spm.fit_id},
        )
    )
    # Every prediction above is fixed before any score below is computed.
    results: dict[str, Any] = {
        "selected": config,
        "search": {
            "trace": [{"offense": o, "defense": d, "pooled_mse": v} for (o, d), v in trace.items()],
            "seconds": search_seconds,
            "selection_blocks": [b.label for b in analysis.regular],
        },
        "eligibility": {label: p.audit for label, p in prepared.items()}
        | {"final": final_prepared.audit},
        "blocks": {},
    }
    for b in blocks:
        results["blocks"][b.label] = score_set(rows, analysis.scored(b), frozen[b.label])
    for role, chosen in (("regular", analysis.regular), ("playoffs", analysis.playoffs)):
        index = np.concatenate([analysis.scored(b) for b in chosen])
        merged = {
            name: np.concatenate([frozen[b.label][name] for b in chosen])
            for name in frozen[chosen[0].label]
        }
        results[f"pooled_{role}"] = score_set(rows, index, merged)
        for season in SCORED_SEASONS:
            keep = rows.season[index] == season
            results[f"pooled_{role}"][str(season)] = score_set(
                rows, index[keep], {k: v[keep] for k, v in merged.items()}
            )
        for name, mask in (("no_livedata", rows.no_livedata), ("livedata", ~rows.no_livedata)):
            keep = mask[index]
            if keep.any():
                results[f"pooled_{role}"][name] = score_set(
                    rows, index[keep], {k: v[keep] for k, v in merged.items()}
                )
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


AS_OF_COLUMNS = ["artifact_version", "cold_offense", "cold_defense"]


def write_ratings(path: Path, snapshots: Iterable[Ratings]) -> None:
    """Write one CSV of snapshots, all legacy or all as-of (#135).

    The as-of version adds the artifact version and the explicit per-side cold priors to each
    row; a legacy file keeps its frozen columns.
    """
    snapshots = list(snapshots)
    versions = {snap.artifact_version for snap in snapshots}
    if len(versions) > 1:
        raise ValueError(f"cannot mix rating artifact versions in one file: {sorted(versions)}")
    as_of = versions == {AS_OF_ARTIFACT}
    for snap in snapshots:
        if as_of and (snap.cold is None or not snap.player_ids.size):
            raise ValueError(f"as-of snapshot {snap.cutoff} needs cold priors and a roster")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "as_of",
                "player_id",
                "prior_offense",
                "prior_defense",
                "deviation_offense",
                "deviation_defense",
                "rating_offense",
                "rating_defense",
                "rating_total",
                "window_possessions",
                "box_history",
                "snapshot_id",
                "spm_origin",
                *(AS_OF_COLUMNS if as_of else []),
            ]
        )
        for snap in snapshots:
            rating = snap.rating
            for i, player in enumerate(snap.player_ids):
                writer.writerow(
                    [
                        snap.cutoff.isoformat(),
                        int(player),
                        *(f"{v:.6f}" for v in snap.prior[i]),
                        *(f"{v:.6f}" for v in snap.deviation[i]),
                        *(f"{v:.6f}" for v in rating[i]),
                        f"{rating[i].sum():.6f}",
                        f"{snap.exposure[i]:.0f}",
                        bool(snap.box_history[i]),
                        snap.snapshot_id,
                        snap.spm_origin,
                        *(
                            [snap.artifact_version, *(f"{v:.6f}" for v in snap.cold)]
                            if as_of and snap.cold is not None
                            else []
                        ),
                    ]
                )


def load_spm(processed: Path) -> tuple[dict[int, SpmFit], SpmFit, dict[str, str]]:
    directory = processed / "spm" / SPM_RUN
    manifest = read_json(checked_file(directory / "manifest.json", SPM_MANIFEST))
    digests = {}
    fits = {}
    for season, name in (*SPM_FITS.items(), (0, FINAL_SPM_FIT)):
        digests[name] = manifest["outputs"][name]
        fits[season] = spm_fit(read_json(checked_file(directory / name, digests[name])))
    final = fits.pop(0)
    return fits, final, digests


def run(raw: Path, processed: Path, output: Path, protocol_sha256: str) -> dict[str, Any]:
    started = time.perf_counter()
    protocol = verify_protocol(PROTOCOL, protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    spm, final_spm, spm_digests = load_spm(processed)
    logs: dict[int, list[Appearance]] = {}
    log_inputs = {}
    for season in BOX_SEASONS:
        logs[season], log_inputs[str(season)] = checked_logs(raw, season)
    with TemporaryDirectory(prefix=".ei-build-", dir=output.parent) as sandbox:
        stage = Path(sandbox) / "results"
        stage.mkdir()
        _, rows, design, row_inputs = _prepare(processed, ROW_SEASONS, ROW_SEASONS, stage)
        log: list[dict[str, Any]] = []
        results, snapshots, predictions = development(rows, design, spm, final_spm, logs, log)
        np.savez_compressed(stage / "predictions.npz", **predictions)
        write_ratings(stage / "ratings.csv", snapshots)
        results.update(
            artifact_label=ARTIFACT_LABEL,
            evidence_tier=EVIDENCE,
            solver=_solver_summary(log),
            rows={"possessions": len(rows), "games": len(rows.game_ids), "players": design.size},
            estimated_skills_input={"status": "unavailable", "reason": "ADR-0030"},
        )
        _write_json(stage / "results.json", results)
        _write_json(stage / "fit_log.json", log)
        head, clean = _git_head()
        manifest = {
            "schema_version": 1,
            "version": VERSION,
            "artifact_label": ARTIFACT_LABEL,
            "evidence_tier": EVIDENCE,
            "protocol": protocol,
            "code_commit": head,
            "working_tree_clean_at_end": clean,
            "inputs": {
                "rows": row_inputs,
                "box_logs": log_inputs,
                "spm_manifest_sha256": SPM_MANIFEST,
                "spm_outputs": spm_digests,
            },
            "selected": results["selected"],
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
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    run(args.raw.resolve(), args.processed.resolve(), args.output.resolve(), args.protocol_sha256)


if __name__ == "__main__":
    main()
