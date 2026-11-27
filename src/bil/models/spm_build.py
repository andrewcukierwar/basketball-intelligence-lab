"""Run the frozen #30 partial-history SPM experiment on private pinned inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import resource
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb
import numpy as np

from bil.data.pilot_sources import ATTRIBUTION, sha256_file, utc_now, write_json
from bil.features.box import Appearance
from bil.features.box_build import PLAYER_LOG, TEAM_LOG, load_appearances
from bil.models.rapm.multiseason import REPO_ROOT, Rows, assemble, load_season
from bil.models.rapm.targets import (
    ARTIFACT_LABEL,
    AUTHORIZED_SEASONS,
    DATA_END,
    ERA,
    EVALUATION_SCENARIO,
    REFERENCES,
    TARGET_PINS,
    TARGET_VERSION,
    VERIFICATION_GROUP,
    chronological_registration,
    origin_schedule,
    verify_protocol,
)
from bil.models.spm import (
    CANDIDATES,
    CODES,
    MIN_POSSESSIONS,
    RIDGE,
    Candidate,
    FloatArray,
    completed_history,
    feature_matrix,
    fit_candidate,
)
from bil.models.spm_evaluation import (
    COURT_NAMES,
    SNAPSHOT_CANDIDATES,
    VOLUME,
    BoolArray,
    CourtBaselines,
    CourtPredictions,
    IntArray,
    PriorPair,
    age_bands,
    ages_at,
    clustered_interval,
    court_scores,
    fit_court_baselines,
    lookup,
    minutes_bands,
    pair_fallback,
    predict_court,
    predict_pair,
    sum_by,
    volume_bands,
)

VERSION = "issue-30-v2"
EVIDENCE = "retrospective_capture_bound"
TARGET_MANIFEST = "40fcfba98a3a243377612292d59860541a710a5be902011ec03ec276118fe043"
AGE_MANIFEST = "5a6f26e3b8b2dad9b0ef1e3400b561a9955a4e138abc2a165afa588f36502e76"
LOG_PINS = {
    2005: ("issue-97-v1", "78b57d0481f95b9c0c54d6d0670480c4d3ef607129f92b7180c85cf240a3e824"),
    2006: ("issue-97-v1", "9433786ea2eaac54ba948127274bbe9626c4eb59eb159dee287cf486098c3098"),
    2007: ("issue-97-v1", "7e3189d65ba78fb37a07b302e9dddae9646021a4d2432263863781d28fa1ae49"),
    2015: ("issue-98-v1", "1a49c70c29cc45ecd9bb87aa824716e1071c4524c3eaeb6d894bbf276ed24fdd"),
    2016: ("issue-96-v1", "7489dc412ef5a36ca7d7748c0b5035ebe432ad8421864913a3c1906e434a8d88"),
    2018: ("issue-25-v1", "3dddf8dd0731630f838b1375fc4f494e27cf8aecb4895618ba07154defdabfe1"),
    2019: ("issue-25-v1", "b3d131f42a5588b9b39a2d2ee4a034c85a0addc10ce68ee04c728099baa8827b"),
    2020: ("issue-25-v1", "45a78182453945572e404418c411b1490a7f20a21d4a00124ffaa94017e293df"),
    2021: ("issue-25-v1", "d634e22e6db4bcfcf4b0933b13835f034e32de62c564db9a4e5934ebd4c4570c"),
    2022: ("issue-5-v2", "348eb8a072534659956082fd64cf3106c2d07092c87b5aca6f9d0ca056ae6611"),
}
COMMON = (2019, 2020, 2021, 2022)


def checked_file(path: Path, digest: str) -> Path:
    if sha256_file(path) != digest:
        raise ValueError(f"unexpected input digest for {path}")
    return path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def checked_logs(raw: Path, season: int) -> tuple[list[Appearance], dict[str, Any]]:
    if season not in LOG_PINS:
        raise ValueError(f"SPM season is outside the authorized scope: {season}")
    snapshot, digest = LOG_PINS[season]
    directory = raw / TARGET_PINS[season].label / snapshot
    return checked_log_snapshot(directory, season, digest)


def checked_log_snapshot(
    directory: Path, season: int, digest: str
) -> tuple[list[Appearance], dict[str, Any]]:
    """Verify a caller-registered historical box snapshot and load its appearances."""
    record = read_json(checked_file(directory / "snapshot.json", digest))
    if record["season_start_year"] != season or record["attribution"] != ATTRIBUTION:
        raise ValueError("box log snapshot season or attribution mismatch")
    assets = {asset["name"]: asset for asset in record["artifacts"]}
    for name in (PLAYER_LOG, TEAM_LOG):
        path = checked_file(directory / name, assets[name]["sha256"])
        if path.stat().st_size != assets[name]["size_bytes"]:
            raise ValueError("box log snapshot size mismatch")
    with duckdb.connect() as connection:
        rows, profile = load_appearances(connection, directory, season_start_year=season)
    if not rows or any(row.game_date >= DATA_END for row in rows):
        raise ValueError("box log rows fall outside the registered dates")
    return rows, {
        "snapshot": directory.name,
        "snapshot_sha256": digest,
        **profile,
        "assets": {name: assets[name]["sha256"] for name in (PLAYER_LOG, TEAM_LOG)},
        "games": len({row.game_id for row in rows}),
        "positive_minute_appearances": sum(row.minutes_ms > 0 for row in rows),
    }


def checked_ages(raw: Path) -> tuple[dict[int, dict[int, date]], dict[str, Any]]:
    directory = raw / "spm-age-audit" / "2026-11-24"
    metadata = read_json(checked_file(directory / "manifest.json", AGE_MANIFEST))
    assets = {asset["name"]: asset for asset in metadata["assets"]}
    output = {}
    with duckdb.connect() as connection:
        for season in AUTHORIZED_SEASONS:
            name = f"rosters_{season + 1}.parquet"
            asset = assets[name]
            path = checked_file(directory / name, asset["sha256"])
            if path.stat().st_size != asset["size"]:
                raise ValueError("roster asset size mismatch")
            rows = connection.execute(
                "SELECT try_cast(player_id AS BIGINT) AS id, "
                "min(cast(try_strptime(birth_date, '%b %d, %Y') as date)) AS birth FROM read_parquet(?) "
                "WHERE try_cast(player_id AS BIGINT) > 0 GROUP BY 1 "
                "HAVING count(DISTINCT cast(try_strptime(birth_date, '%b %d, %Y') as date)) = 1",
                [str(path)],
            ).fetchall()
            output[season] = dict(rows)
    return output, {"manifest_sha256": AGE_MANIFEST, "assets": assets, "use": "scorer_only"}


@dataclass(frozen=True)
class Label:
    values: tuple[float, float]
    exposure: tuple[float, float]
    forward: bool

    def enough(self) -> bool:
        return min(self.exposure) >= MIN_POSSESSIONS


Labels = dict[tuple[int, int], Label]


def load_labels(path: Path, *, evaluation: bool) -> dict[str, Labels]:
    result: dict[str, Labels] = defaultdict(dict)
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            reference, origin = row["reference"], row["origin"]
            if evaluation and row["scenario"] != EVALUATION_SCENARIO:
                raise ValueError("the evaluation input contains a non-K0 label")
            season = int(row["evaluation_season" if evaluation else "target_season"])
            if (
                reference not in REFERENCES
                or season not in REFERENCES[reference]
                or not origin.startswith(reference + "@")
                or row["version"] != TARGET_VERSION
                or row["artifact_label"] != ARTIFACT_LABEL
                or row["forward_support"] not in ("True", "False")
            ):
                raise ValueError("label lineage is outside the registered target contract")
            player = int(row["player_id"])
            key = (season, player)
            if player <= 0 or key in result[origin]:
                raise ValueError("invalid or duplicate label identity")
            exposure = (float(row["offense_possessions"]), float(row["defense_possessions"]))
            values = (float(row["offense"]), float(row["defense"]))
            if not np.isfinite((*values, *exposure)).all() or min(exposure) <= 0:
                raise ValueError("nonfinite label or invalid exposure")
            result[origin][key] = Label(values, exposure, row["forward_support"] == "True")
    return dict(result)


def fit_models(
    labels: Labels,
    seasons: Sequence[int],
    logs: Mapping[int, list[Appearance]],
    cutoff: date,
    candidates: Mapping[str, Candidate],
) -> tuple[dict[str, PriorPair], dict[str, Any]]:
    training_values = []
    training_labels: list[tuple[float, float]] = []
    exposure: list[tuple[float, float]] = []
    support: list[bool] = []
    coverage = {}
    for season in seasons:
        if any(row.game_date >= cutoff for row in logs[season]):
            raise ValueError("the calibration box window is incomplete at the fit cutoff")
        history = completed_history(logs[season], cutoff)
        by_player = {player: label for (s, player), label in labels.items() if s == season}
        eligible = sorted(
            player for player, label in by_player.items() if label.enough() and player in history
        )
        values, _ = feature_matrix(history, eligible)
        training_values.append(values)
        training_labels.extend(by_player[player].values for player in eligible)
        exposure.extend(by_player[player].exposure for player in eligible)
        support.extend(by_player[player].forward for player in eligible)
        coverage[str(season)] = {
            "joined_training_rows": len(eligible),
            "verification_group": VERIFICATION_GROUP[season],
            "era": ERA[season],
            "target_only": len(set(by_player) - set(history)),
            "box_only": len(set(history) - set(by_player)),
            "labels_below_minimum": sum(not label.enough() for label in by_player.values()),
            "one_sided_training_rows": sum(not by_player[player].forward for player in eligible),
            "missing_features": dict(
                zip(CODES, np.isnan(values).sum(axis=0).tolist(), strict=True)
            ),
        }
    x, y = np.concatenate(training_values), np.asarray(training_labels, dtype=np.float64)
    n, forward = np.asarray(exposure, dtype=np.float64), np.asarray(support, dtype=np.bool_)
    models = {
        name: fit_candidate(x, y, n, forward, candidate) for name, candidate in candidates.items()
    }
    return models, coverage


def model_records(
    models: Mapping[str, PriorPair],
    origin: str,
    target: Mapping[str, Any],
    coverage: Mapping[str, Any],
    log_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    record = {
        "artifact_label": ARTIFACT_LABEL,
        "evidence_tier": EVIDENCE,
        "origin": origin,
        "target_input_digest": target["input_digest"],
        "target_label_digests": target["label_digests"],
        "coverage": coverage,
        "box_snapshot_sha256": {
            season: log_inputs[season]["snapshot_sha256"] for season in coverage
        },
        "ridge": RIDGE,
        "candidates": {
            name: {
                side: model.record()
                for side, model in zip(("offense", "defense"), pair, strict=True)
            }
            for name, pair in models.items()
        },
    }
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    record["fit_id"] = hashlib.sha256(encoded).hexdigest()
    return record


@dataclass(frozen=True)
class Opening:
    season: int
    day: date
    players: IntArray
    minutes: FloatArray
    volume: FloatArray
    predictions: dict[str, FloatArray]
    fallback: dict[str, FloatArray]
    uses_fallback: dict[str, BoolArray]


def opening(
    season: int,
    day: date,
    previous: Sequence[Appearance],
    models: Mapping[str, PriorPair],
) -> Opening:
    history = completed_history(previous, day)
    keys = np.asarray(sorted(history), dtype=np.int64)
    values, minutes = feature_matrix(history, keys.tolist())
    return Opening(
        season,
        day,
        keys,
        minutes,
        values[:, VOLUME],
        {name: predict_pair(pair, values) for name, pair in models.items()},
        {name: np.array([model.intercept for model in pair]) for name, pair in models.items()},
        {name: pair_fallback(pair, values) for name, pair in models.items()},
    )


def freeze_fold(
    directory: Path,
    start: Opening,
    rows: Rows,
    court: CourtPredictions,
    metadata: dict[str, Any],
) -> None:
    directory.mkdir()
    common = {
        "artifact_label": ARTIFACT_LABEL,
        "evidence_tier": EVIDENCE,
        "fit_id": metadata["fit_id"],
    }
    candidates = tuple(start.predictions)
    np.savez_compressed(
        directory / "opening.npz",
        player_id=start.players,
        minutes=start.minutes,
        volume=start.volume,
        origin=start.day.isoformat(),
        candidates=candidates,
        priors=np.stack([start.predictions[name] for name in candidates], axis=1),
        fallback_priors=np.stack([start.fallback[name] for name in candidates]),
        uses_fallback=np.stack([start.uses_fallback[name] for name in candidates], axis=1),
        **common,
    )
    dated = court.dated
    np.savez_compressed(
        directory / "dated_priors.npz",
        **common,
        candidates=SNAPSHOT_CANDIDATES,
        day=np.concatenate([np.full(len(view.players), view.day) for view in dated]),
        player_id=np.concatenate([view.players for view in dated]),
        minutes=np.concatenate([view.minutes for view in dated]),
        volume=np.concatenate([view.volume for view in dated]),
        priors=np.concatenate([view.priors for view in dated]),
        uses_fallback=np.concatenate([view.fallback for view in dated]),
        has_current_history=np.concatenate([view.has_current_history for view in dated]),
    )
    np.savez_compressed(
        directory / "court_predictions.npz",
        **common,
        game_ids=rows.game_ids,
        game=rows.game,
        possession_seq=rows.possession_seq,
        day=rows.day,
        candidate_names=COURT_NAMES,
        points_per_100=court.values,
        missing_history=court.missing_history,
    )
    write_json(directory / "fit.json", metadata)


def label_scores(
    prediction: Opening,
    labels: Labels,
    births: Mapping[int, date],
    *,
    common: set[int] | None = None,
) -> tuple[dict[str, Any], IntArray, dict[str, FloatArray]]:
    available = {
        player: label
        for (season, player), label in labels.items()
        if season == prediction.season and label.enough() and (common is None or player in common)
    }
    players = np.asarray(sorted(available), dtype=np.int64)
    indices = lookup(prediction.players, players)
    known = indices < len(prediction.players)
    actual = np.asarray([available[int(player)].values for player in players])
    exposure = np.asarray([min(available[int(player)].exposure) for player in players])
    if not len(players):
        raise ValueError("evaluation fold has no eligible K0 players")
    errors = {}
    fallback_with_history = {}
    for name, values in prediction.predictions.items():
        indexed = np.vstack((values, prediction.fallback[name]))[indices]
        difference = indexed - actual
        fallback_with_history[name] = (
            prediction.uses_fallback[name][indices[known]].sum(axis=0).tolist()
        )
        errors[name] = np.column_stack((difference, difference.sum(axis=1)))
    ages = ages_at(players, prediction.day, births)
    groups = {
        "minutes": minutes_bands(np.append(prediction.minutes, np.nan)[indices]),
        "shot_volume_role": volume_bands(np.append(prediction.volume, np.nan)[indices]),
        "age": age_bands(ages),
        "label_exposure": {
            "250_to_999": exposure < 1000,
            "1000_to_1999": (exposure >= 1000) & (exposure < 2000),
            "2000_plus": exposure >= 2000,
        },
    }
    summary = label_slice(errors, np.ones(len(players), dtype=bool))
    summary.update(
        eligible=len(available),
        opened_players=len(prediction.players),
        scored_with_opening_history=int(known.sum()),
        scored_with_cold_fallback=int((~known).sum()),
        intercept_fallback_with_history=fallback_with_history,
        missing_prediction=0,
        roster_position={"status": "unavailable", "players": len(players)},
    )
    for group, masks in groups.items():
        summary[group] = {name: label_slice(errors, mask) for name, mask in masks.items()}
    return summary, players, errors


def label_slice(errors: Mapping[str, FloatArray], mask: Any) -> dict[str, Any]:
    metrics = {}
    if mask.any():
        for name, residuals in errors.items():
            residual = residuals[mask]
            metrics[name] = {
                "rmse": np.sqrt(np.mean(residual**2, axis=0)).tolist(),
                "mae": np.mean(np.abs(residual), axis=0).tolist(),
                "bias": np.mean(residual, axis=0).tolist(),
            }
    return {
        "players": int(mask.sum()),
        "side_order": ["offense", "defense", "total"],
        "metrics": metrics,
    }


def summarize_label_pool(
    scored: Sequence[tuple[IntArray, dict[str, FloatArray]]],
) -> dict[str, Any]:
    names = tuple(scored[0][1])
    errors = {name: np.concatenate([arrays[name] for _, arrays in scored]) for name in names}
    keys = np.concatenate([keys for keys, _ in scored])
    players, inverse = np.unique(keys, return_inverse=True)
    summary = label_slice(errors, np.ones(len(keys), dtype=bool))
    summary["player_seasons"] = summary.pop("players")
    summary["distinct_players"] = len(players)
    summary["full_rmse_delta_vs"] = {}
    for name in ("zero", "one_stat"):
        contrasts = []
        for side in range(3):
            values = np.column_stack(
                (np.ones(len(keys)), errors["full"][:, side] ** 2, errors[name][:, side] ** 2)
            )
            cluster = sum_by(inverse, values, len(players))
            estimate = np.sqrt(values[:, 1].mean()) - np.sqrt(values[:, 2].mean())
            contrasts.append(
                {
                    "delta": float(estimate),
                    "interval": clustered_interval([cluster], 0, 1, rmse=True),
                }
            )
        summary["full_rmse_delta_vs"][name] = contrasts
    return summary


def target_inputs(
    processed: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[int, tuple[date, date]], dict[str, Any]]:
    directory = processed / "rapm_targets" / TARGET_VERSION
    manifest = read_json(checked_file(directory / "manifest.json", TARGET_MANIFEST))
    if manifest["version"] != TARGET_VERSION or manifest["artifact_label"] != ARTIFACT_LABEL:
        raise ValueError("unexpected #28 manifest")
    digests = {
        name: manifest["outputs"][name]
        for name in ("targets.csv", "evaluation_labels.csv", "frozen_targets.json", "results.json")
    }
    for name, digest in digests.items():
        checked_file(directory / name, digest)
    registration = read_json(directory / "results.json")
    calendar = {
        int(year): (date.fromisoformat(pair[0]), date.fromisoformat(pair[1]))
        for year, pair in registration["calendar"].items()
    }
    if set(calendar) != set(AUTHORIZED_SEASONS) or any(
        first > last or last >= DATA_END for first, last in calendar.values()
    ):
        raise ValueError("target calendar is outside the authorized season/date scope")
    expected = chronological_registration(calendar)
    if expected != registration["chronological_registration"]:
        raise ValueError("the #28 chronological registration changed")
    frozen = {}
    for entry in read_json(directory / "frozen_targets.json"):
        key = f"{entry['reference']}@{entry['cutoff']}"
        if (
            key in frozen
            or entry["version"] != TARGET_VERSION
            or entry["artifact_label"] != ARTIFACT_LABEL
            or entry["kernel"] != "K365"
        ):
            raise ValueError("unexpected frozen origin")
        frozen[key] = entry
    for reference in REFERENCES:
        schedule = origin_schedule(reference, calendar)
        for i, origin in enumerate(schedule):
            record = frozen[origin.key]
            if record["closes_season"] != origin.closes_season or record["seasons"] != list(
                REFERENCES[reference][: i + 1]
            ):
                raise ValueError(f"unexpected frozen calibration seasons for {origin.key}")
    return directory, expected, frozen, calendar, digests


def pool_court(weekly: Sequence[FloatArray]) -> dict[str, Any]:
    total = np.concatenate(weekly).sum(axis=0)
    mse = total[1:] / total[0]
    full = COURT_NAMES.index("context_full")
    return {
        "possessions": int(total[0]),
        "mse": dict(zip(COURT_NAMES, mse.tolist(), strict=True)),
        "context_full_delta_vs": {
            name: {
                "delta": float(mse[full] - mse[COURT_NAMES.index(name)]),
                "interval": clustered_interval(weekly, full, COURT_NAMES.index(name), rmse=False),
            }
            for name in ("context", "rapm", "rapm_context")
        },
    }


def verify_row_dates(rows: Rows, season: int, calendar: Mapping[int, tuple[date, date]]) -> None:
    first, last = calendar[season]
    if (
        not len(rows)
        or not np.all(rows.season == season)
        or np.min(rows.day) < first.toordinal()
        or np.max(rows.day) > last.toordinal()
    ):
        raise ValueError(f"invalid canonical row dates or years for {season}")


def calibration_updates(previous: Labels, current: Labels) -> dict[str, int]:
    """Compare eligible target records from successive pre-evaluation origins."""
    before = {key for key, label in previous.items() if label.enough()}
    after = {key for key, label in current.items() if label.enough()}
    continuing = before & after
    changed = sum(previous[key] != current[key] for key in continuing)
    return {
        "newly_eligible": len(after - before),
        "no_longer_eligible": len(before - after),
        "revised": changed,
        "unchanged": len(continuing) - changed,
    }


def audit_overlap(
    season: int,
    opening_day: date,
    scored: Rows,
    comparison_fit: Rows,
    opening_history: Sequence[Appearance],
    calibration_box: Mapping[int, Sequence[Appearance]],
    calibration_rows: Mapping[int, Rows],
) -> dict[str, int]:
    scored_ids = set(scored.game_ids)
    overlaps = {
        "evaluation_season_in_calibration": int(season in calibration_rows),
        "scored_games_in_calibration_target_rowsets": len(
            scored_ids.intersection(
                game for rows in calibration_rows.values() for game in rows.game_ids
            )
        ),
        "scored_games_in_calibration_box_logs": len(
            scored_ids.intersection(
                row.game_id for appearances in calibration_box.values() for row in appearances
            )
        ),
        "scored_games_in_comparator_fit": len(scored_ids.intersection(comparison_fit.game_ids)),
        "scored_games_in_opening_history": len(
            scored_ids.intersection(
                row.game_id for row in opening_history if row.game_date < opening_day
            )
        ),
        "comparator_rows_on_or_after_opening": int(
            (comparison_fit.day >= opening_day.toordinal()).sum()
        ),
        "target_source_rows_on_or_after_opening": sum(
            int((rows.day >= opening_day.toordinal()).sum()) for rows in calibration_rows.values()
        ),
    }
    if any(overlaps.values()):
        raise ValueError(f"calibration and scoring overlap: {overlaps}")
    return overlaps


def run(raw: Path, processed: Path, output: Path, protocol_sha256: str) -> None:
    start_time = time.monotonic()
    protocol = verify_protocol(REPO_ROOT / "docs/research/box-spm-protocol.md", protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    target_dir, registration, frozen, calendar, digests = target_inputs(processed)
    training = load_labels(target_dir / "targets.csv", evaluation=False)
    if set(training) != set(frozen):
        raise ValueError("training targets differ from the frozen origins")
    for key, record in frozen.items():
        if {season for season, _ in training[key]} != set(record["seasons"]):
            raise ValueError("training rows differ from the frozen season set")

    report: dict[str, Any] = {
        "artifact_label": ARTIFACT_LABEL,
        "evidence_tier": EVIDENCE,
        "version": VERSION,
        "strict": {
            "status": "unavailable",
            "eligible": 0,
            "reason": "post-origin source capture bounds",
        },
        "prospective": {"status": "unavailable", "eligible": 0},
        "folds": {},
        "label_common_contiguous_truth": {},
    }
    histories, log_inputs, row_inputs = {}, {}, {}
    opening_predictions: dict[tuple[str, int], Opening] = {}
    court_weekly: dict[tuple[str, int], FloatArray] = {}
    with TemporaryDirectory(prefix=".spm-build-", dir=output.parent) as sandbox:
        stage = Path(sandbox) / "results"
        stage.mkdir()
        current_rows = {}
        baselines: dict[int, CourtBaselines] = {}

        def canonical(season: int) -> Rows:
            if season not in current_rows:
                load = load_season(
                    processed, season, AUTHORIZED_SEASONS, Path(sandbox), TARGET_PINS
                )
                row_inputs[str(season)] = {
                    "verification_group": VERIFICATION_GROUP[season],
                    "row_manifest_sha256": load.pin.row_manifest_sha256,
                    "pilot_manifest_sha256": load.pin.pilot_manifest_sha256,
                    "coverage": load.coverage,
                    "timing_audit": load.audit,
                }
                rows = assemble([load])
                verify_row_dates(rows, season, calendar)
                current_rows[season] = rows
            return current_rows[season]

        for season in AUTHORIZED_SEASONS:
            histories[season], log_inputs[str(season)] = checked_logs(raw, season)
        # Age is only joined in the scoring calls, following each prediction write.
        births, age_inputs = checked_ages(raw)
        for reference, rules in registration.items():
            last_target: Labels = {}
            first = rules["first_season_unavailable"]
            report["folds"][reference] = {str(first["season"]): {"status": "unavailable", **first}}
            for fold in rules["folds"]:
                season = fold["evaluation_season"]
                cut = calendar[season][0]
                origin = fold["training_target_set"]
                record = frozen[origin]
                cutoff = date.fromisoformat(record["cutoff"])
                earlier = record["closes_season"]
                seasons = fold["training_seasons"]
                if (
                    cutoff > cut
                    or earlier >= season
                    or seasons != record["seasons"]
                    or max(seasons) != earlier
                ):
                    raise ValueError("a fit origin overlaps the evaluation-season calendar")
                models, coverage = fit_models(
                    training[origin], seasons, histories, cutoff, CANDIDATES
                )
                fit = model_records(models, origin, record, coverage, log_inputs)
                updates = calibration_updates(last_target, training[origin])
                last_target = training[origin]
                details = {
                    **fit,
                    "evaluation_season": season,
                    "evaluation_first_date": cut.isoformat(),
                }
                if reference == "extended" and season in COMMON:
                    retained = [year for year in seasons if year > 2007]
                    sensitivity, sensitivity_coverage = fit_models(
                        training[origin],
                        retained,
                        histories,
                        cutoff,
                        {"full": CANDIDATES["full"]},
                    )
                    details["without_2005_08_fit"] = model_records(
                        sensitivity, origin, record, sensitivity_coverage, log_inputs
                    )
                    models["full_without_2005_08"] = sensitivity["full"]
                rows = canonical(season)
                previous_rows = canonical(earlier)
                if earlier not in baselines:
                    baselines[earlier] = fit_court_baselines(previous_rows, cut)
                previous = histories[season - 1] if season - 1 in REFERENCES[reference] else []
                start = opening(season, cut, previous, models)
                overlap = audit_overlap(
                    season,
                    cut,
                    rows,
                    previous_rows,
                    previous,
                    {year: histories[year] for year in seasons},
                    {year: canonical(year) for year in seasons},
                )
                court = predict_court(rows, previous, histories[season], baselines[earlier], models)
                details["court_baselines"] = baselines[earlier].fit_metadata
                freeze_fold(stage / f"{reference}-{season}", start, rows, court, details)
                metrics, weekly = court_scores(rows, court, births[season])
                opening_predictions[reference, season] = start
                court_weekly[reference, season] = weekly
                report["folds"][reference][str(season)] = {
                    "status": "scored",
                    "fit_id": fit["fit_id"],
                    "origin": origin,
                    "earlier_calendar_season": season - 1 if previous else None,
                    "fit_cutoff_to_opening_days": (cut - cutoff).days,
                    "last_comparator_game_to_opening_days": (cut - calendar[earlier][1]).days,
                    "crosses_gap": earlier != season - 1,
                    "start": cut.isoformat(),
                    "last_scored_date": date.fromordinal(int(np.max(rows.day))).isoformat(),
                    "court": metrics,
                    "training": coverage,
                    "calibration_target_updates": updates,
                    "verification_group": VERIFICATION_GROUP[season],
                    "era": ERA[season],
                    "overlap_audit": overlap,
                }
                del court

        origin = registration["contiguous"]["outer_seasons_use"]
        record = frozen[origin]
        final, final_coverage = fit_models(
            training[origin],
            record["seasons"],
            histories,
            date.fromisoformat(record["cutoff"]),
            {"full": CANDIDATES["full"]},
        )
        write_json(
            stage / "final_contiguous_fit.json",
            model_records(final, origin, record, final_coverage, log_inputs),
        )

        evaluation = load_labels(target_dir / "evaluation_labels.csv", evaluation=True)
        common_scored = defaultdict(list)
        for (reference, season), prediction in opening_predictions.items():
            truth = evaluation[registration[reference]["outer_seasons_use"]]
            metrics, _, _ = label_scores(prediction, truth, births[season])
            report["folds"][reference][str(season)]["k0"] = metrics
            if season not in COMMON:
                continue
            contiguous_truth = evaluation[registration["contiguous"]["outer_seasons_use"]]
            extended_truth = evaluation[registration["extended"]["outer_seasons_use"]]
            common = {
                player
                for (year, player), label in contiguous_truth.items()
                if year == season
                and label.enough()
                and (year, player) in extended_truth
                and extended_truth[year, player].enough()
            }
            metrics, players, errors = label_scores(
                prediction,
                contiguous_truth,
                births[season],
                common=common,
            )
            report["label_common_contiguous_truth"].setdefault(reference, {})[str(season)] = metrics
            common_scored[reference].append((players, errors))

        report["label_common_modern_pool"] = {
            reference: summarize_label_pool(scored) for reference, scored in common_scored.items()
        }
        report["court_common_modern_pool"] = {
            reference: pool_court([court_weekly[reference, season] for season in COMMON])
            for reference in REFERENCES
        }
        write_json(stage / "results.json", report)
        outputs = {
            str(path.relative_to(stage)): sha256_file(path)
            for path in sorted(stage.rglob("*"))
            if path.is_file()
        }
        manifest = {
            "schema_version": 1,
            "version": VERSION,
            "generated_at": utc_now(),
            "artifact_label": ARTIFACT_LABEL,
            "evidence_tier": EVIDENCE,
            "data_attribution": ATTRIBUTION,
            "protocol": protocol,
            "outputs": outputs,
            "authorized_seasons": AUTHORIZED_SEASONS,
            "target_manifest_sha256": TARGET_MANIFEST,
            "inputs": {
                "target_outputs": digests,
                "box_logs": log_inputs,
                "canonical_rows": row_inputs,
                "age": age_inputs,
                "chronological_registration": registration,
            },
            "versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scipy": version("scipy"),
                "duckdb": duckdb.__version__,
            },
            "runtime_seconds": time.monotonic() - start_time,
            "peak_rss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
        write_json(stage / "manifest.json", manifest)
        stage.rename(output)


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
