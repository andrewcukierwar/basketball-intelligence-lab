"""Predict and score the first #168 chronological contrast in separate commands."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.data.pilot_sources import sha256_file
from bil.models.rapm.expanded_inputs import (
    REGISTRATION_SHA256,
    _load_registered_season,
    _verify_file,
)
from bil.models.rapm.expanded_targets import ORIGIN_CUTOFFS
from bil.models.rapm.multiseason import REPO_ROOT, pre_possession_features
from bil.models.rapm.targets import label_digest, verify_protocol

ORIGIN = 2005
EVALUATION = 2006
KEYS = ("game_id", "stream_revision", "possession_seq")
PROTOCOL_SHA = "45b43b2783e1d75da6ddfd489adea0f5b8efb29ba7b6fb2bed21d51311484712"
CHECKPOINTS = {
    "matched_10": "eb117064ad959aa0446a5bb1489d252525d0946e718af4b2d97571a91eb354c7",
    "expanded_15": "bdb18ef7ac1c4f7fa21cb78a2e7c1578dd2d255bc193e5aebe2a5b67e2cdb97a",
}


def _evaluation_view(data_root: Path, repo: Path, *, scores: bool) -> dict[str, NDArray[Any]]:
    registration = repo / "docs/research/expanded-rapm-cohort-v1.json"
    _verify_file(registration, REGISTRATION_SHA256)
    manifest = json.loads(registration.read_bytes())
    season = next(record for record in manifest["seasons"] if record["year"] == EVALUATION)
    with TemporaryDirectory(prefix="bil-heldout-") as temp:
        result = _load_registered_season(
            data_root, Path(temp), season, include_model_points=scores
        ).data
    if np.any(result["game_date"].astype("datetime64[D]") < np.datetime64(ORIGIN_CUTOFFS[ORIGIN])):
        raise ValueError("evaluation dates overlap the registered fit origin")
    result["game_id"] = result["game_id"].astype(str)
    order = np.lexsort(tuple(reversed([result[key] for key in KEYS])))
    return {field: values[order] for field, values in result.items()}


def _checkpoint(root: Path, cohort: str) -> tuple[dict[str, NDArray[Any]], dict[str, Any]]:
    directory = root / cohort
    manifest_path = directory / "manifest.json"
    _verify_file(manifest_path, CHECKPOINTS[cohort])
    manifest = json.loads(manifest_path.read_bytes())
    if (
        manifest["cohort"] != cohort
        or manifest["closes_season"] != ORIGIN
        or manifest["cutoff_exclusive"] != ORIGIN_CUTOFFS[ORIGIN].isoformat()
        or manifest["kernel"] != "K365"
        or manifest["protocol"]["sha256"] != PROTOCOL_SHA
        or manifest["registration_sha256"] != REGISTRATION_SHA256
    ):
        raise ValueError("checkpoint does not match the registered comparison")
    item = manifest["artifacts"][str(ORIGIN)]
    expected_seasons = [ORIGIN] if cohort == "matched_10" else [2004, ORIGIN]
    if item["kernel_seasons"] != expected_seasons:
        raise ValueError("the expected added-season kernel support was not verified")
    path = directory / f"labels-{ORIGIN}.npz"
    _verify_file(path, item["file_sha256"])
    with np.load(path, allow_pickle=False) as archive:
        table = {field: archive[field] for field in archive.files}
    if label_digest(table) != item["label_digest"]:
        raise ValueError("checkpoint label digest changed")
    return table, item


def _eligible(table: dict[str, NDArray[Any]]) -> NDArray[np.int64]:
    enough = (table["offense_possessions"] >= 250) & (table["defense_possessions"] >= 250)
    ids: NDArray[np.int64] = table["player_id"][enough]
    return ids


def _role(
    players: NDArray[np.int64], table: dict[str, NDArray[Any]], common: NDArray[np.int64], role: str
) -> tuple[NDArray[np.float64], int]:
    present = np.isin(players, common)
    values = np.zeros(players.shape)
    values[present] = table[role][np.searchsorted(table["player_id"], players[present])]
    return np.sum(values, axis=1), int(np.count_nonzero(~present))


def predict(
    data_root: Path, checkpoints: Path, output: Path, repo: Path = REPO_ROOT
) -> dict[str, Any]:
    research = repo / "docs/research"
    freeze = verify_protocol(research / "expanded-rapm-target-protocol.md", PROTOCOL_SHA, repo)
    if output.exists():
        raise FileExistsError(f"forecast already exists: {output}")
    baseline, base_item = _checkpoint(checkpoints, "matched_10")
    expanded, _ = _checkpoint(checkpoints, "expanded_15")
    view = _evaluation_view(data_root, repo, scores=False)
    if "model_points" in view:
        raise ValueError("prediction stage received an outcome vector")
    common = np.intersect1d(_eligible(baseline), _eligible(expanded))
    offense = np.column_stack([view[f"o{i}"] for i in range(1, 6)])
    defense = np.column_stack([view[f"d{i}"] for i in range(1, 6)])
    offset = base_item["offset"]
    common_offset = float(offset["intercept"]) + pre_possession_features(view) @ np.asarray(
        offset["context"]
    )
    common_offset += 5 * (
        np.mean(baseline["offense_raw"] - baseline["offense"])
        - np.mean(baseline["defense_raw"] - baseline["defense"])
    )
    level = 2 * ORIGIN + (view["season_type"] == "playoffs").astype(int)
    for code, value in zip(offset["levels"][1:], offset["level_effects"], strict=True):
        common_offset += value * (level == code)
    data: dict[str, Any] = {key: view[key] for key in KEYS}
    for arm, table in (("matched_10", baseline), ("expanded_15", expanded)):
        off, off_cold = _role(offense, table, common, "offense")
        dfn, def_cold = _role(defense, table, common, "defense")
        data[arm] = common_offset + off - dfn
    receipt = {
        "version": 1,
        "evaluation": EVALUATION,
        "origin": ORIGIN,
        "fit_checkpoint_sha256": CHECKPOINTS,
        "protocol": freeze,
        "rows": len(view["game_id"]),
        "games": int(np.unique(view["game_id"]).size),
        "common_players": len(common),
        "cold_offense_slots": off_cold,
        "cold_defense_slots": def_cold,
    }
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".bil-forecast-stage-", dir=output.parent) as temp:
        stage = Path(temp) / "forecast"
        stage.mkdir(mode=0o700)
        path = stage / "predictions.npz"
        np.savez_compressed(path, **data)
        receipt["predictions_sha256"] = sha256_file(path)
        (stage / "receipt.json").write_text(json.dumps(receipt, sort_keys=True) + "\n")
        stage.rename(output)
    return receipt


def _comparison(
    reference: NDArray[np.float64],
    candidate: NDArray[np.float64],
    actual: NDArray[np.float64],
    games: NDArray[Any],
) -> dict[str, Any]:
    inverse = np.unique(games, return_inverse=True)[1]
    n = np.bincount(inverse)
    draws = np.random.default_rng(168).integers(len(n), size=(2000, len(n)))
    samples = n[draws].sum(axis=1)
    result: dict[str, Any] = {}
    for name, loss, finish in (("rmse", np.square, np.sqrt), ("mae", np.abs, np.asarray)):
        ref = np.bincount(inverse, weights=loss(reference - actual))
        cand = np.bincount(inverse, weights=loss(candidate - actual))
        base = float(finish(ref.sum() / n.sum()))
        trial = float(finish(cand.sum() / n.sum()))
        deltas = finish(cand[draws].sum(axis=1) / samples) - finish(
            ref[draws].sum(axis=1) / samples
        )
        result[name] = {
            "matched_10": base,
            "expanded_15": trial,
            "delta": trial - base,
            "interval_95": np.percentile(deltas, [2.5, 97.5]).tolist(),
        }
    return result


def score(
    data_root: Path, forecast: Path, receipt_sha256: str, repo: Path = REPO_ROOT
) -> dict[str, Any]:
    freeze = verify_protocol(
        repo / "docs/research/expanded-rapm-target-protocol.md", PROTOCOL_SHA, repo
    )
    receipt_path = forecast / "receipt.json"
    _verify_file(receipt_path, receipt_sha256)
    receipt = json.loads(receipt_path.read_bytes())
    if (
        receipt["origin"] != ORIGIN
        or receipt["evaluation"] != EVALUATION
        or receipt["fit_checkpoint_sha256"] != CHECKPOINTS
        or receipt["protocol"] != freeze
    ):
        raise ValueError("forecast receipt is outside the registered comparison")
    path = forecast / "predictions.npz"
    _verify_file(path, receipt["predictions_sha256"])
    with np.load(path, allow_pickle=False) as archive:
        predictions = {field: archive[field] for field in archive.files}
    if any(
        predictions[arm].shape != (receipt["rows"],) or not np.isfinite(predictions[arm]).all()
        for arm in CHECKPOINTS
    ):
        raise ValueError("forecast arrays do not match the receipt")
    view = _evaluation_view(data_root, repo, scores=True)
    if (
        any(not np.array_equal(predictions[key], view[key]) for key in KEYS)
        or np.unique(view["game_id"]).size != receipt["games"]
    ):
        raise ValueError("forecast and outcome row identities differ")
    outcome: NDArray[np.float64] = 100.0 * view["model_points"]
    by_type = {}
    for kind in ("regular", "playoffs"):
        selected = view["season_type"] == kind
        by_type[kind] = {
            "rows": int(np.count_nonzero(selected)),
            "games": int(np.unique(view["game_id"][selected]).size),
            "results": _comparison(
                predictions["matched_10"][selected],
                predictions["expanded_15"][selected],
                outcome[selected],
                view["game_id"][selected],
            ),
        }
    return {
        "rows": int(outcome.size),
        "games": int(np.unique(view["game_id"]).size),
        "forecast_receipt_sha256": receipt_sha256,
        "prediction_sha256": receipt["predictions_sha256"],
        "outcome_sha256": sha256(outcome.astype("<f8").tobytes()).hexdigest(),
        "by_game_type": by_type,
        "results": _comparison(
            predictions["matched_10"], predictions["expanded_15"], outcome, view["game_id"]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    generate = commands.add_parser("predict")
    generate.add_argument("data_root", type=Path)
    generate.add_argument("checkpoints", type=Path)
    generate.add_argument("forecast", type=Path)
    evaluate = commands.add_parser("score")
    evaluate.add_argument("data_root", type=Path)
    evaluate.add_argument("forecast", type=Path)
    evaluate.add_argument("receipt_sha256")
    args = parser.parse_args()
    if args.action == "predict":
        result = predict(args.data_root, args.checkpoints, args.forecast)
        result["receipt_sha256"] = sha256_file(args.forecast / "receipt.json")
    else:
        result = score(args.data_root, args.forecast, args.receipt_sha256)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
