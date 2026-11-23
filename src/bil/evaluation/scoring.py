"""Recompute local scalar scores against mature, pinned outcomes."""

from collections import Counter
from math import fsum, isclose, sqrt

from bil.evaluation.eligibility import instant, require
from bil.evaluation.manifest import (
    ArtifactReader,
    FrozenBatch,
    Manifest,
    Record,
    count,
    day,
    forecast_batches,
    index,
    json_record,
    number,
    reasons,
    verify_bytes,
)

METRICS = {
    "margin_mae": ("absolute", "points"),
    "margin_rmse": ("root_mean_squared", "points"),
    "possession_mse": ("mean_squared", "points_squared"),
}


def _metric(code: str, errors: list[float]) -> float | None:
    if not errors:
        return None
    operation, _ = METRICS[code]
    if operation == "absolute":
        return fsum(abs(error) for error in errors) / len(errors)
    mean_square = fsum(error * error for error in errors) / len(errors)
    return sqrt(mean_square) if operation == "root_mean_squared" else mean_square


def _match_number(actual: object, expected: float | None, field: str) -> None:
    if expected is None:
        require(actual is None, f"{field}: expected null for an unscorable result")
    else:
        require(
            isclose(number(actual), expected, rel_tol=1e-12, abs_tol=1e-12),
            f"{field}: score does not match recomputed value {expected}",
        )


def validate_forecast(content: bytes, read_artifact: ArtifactReader) -> list[FrozenBatch]:
    """Validate a historical forecast and its row-selection evidence."""
    return forecast_batches(Manifest.parse(content, "forecast", read_artifact))


def validate_score(
    score_bytes: bytes,
    read_artifact: ArtifactReader,
    forecast_bytes: bytes,
    read_forecast_artifact: ArtifactReader,
) -> list[Record]:
    """Validate a linked score and recompute its metrics without modifying either stage."""
    manifest = Manifest.parse(score_bytes, "score", read_artifact)
    payload = manifest.record["score"]
    require(
        payload["score_kind"]
        in {"synthetic", "independent_basketball", "realized_lineup_diagnostic"},
        "local scoring supports synthetic and scalar basketball outcomes",
    )
    receipt = manifest.artifact(payload["forecast_manifest_artifact_id"], "forecast_manifest")
    verify_bytes(receipt, forecast_bytes)
    forecast = Manifest.parse(forecast_bytes, "forecast", read_forecast_artifact)
    require(
        payload["forecast_run_id"] == forecast.record["run_id"]
        and manifest.record["run_id"] != forecast.record["run_id"],
        "score run does not identify a distinct frozen forecast",
    )
    require(
        manifest.mode == forecast.mode
        and manifest.splits == forecast.splits
        and manifest.record["protocol_id"] == forecast.record["protocol_id"]
        and manifest.record["registered_at"] == forecast.record["registered_at"],
        "score protocol differs from frozen forecast",
    )
    registration = manifest.artifact(manifest.record["registration_artifact_id"], "registration")
    forecast_registration = forecast.artifact(
        forecast.record["registration_artifact_id"],
        "registration",
    )
    require(
        registration["sha256"] == forecast_registration["sha256"],
        "score registration differs from frozen forecast",
    )
    require(forecast.created_at <= manifest.created_at, "score predates the linked forecast")

    batches = forecast_batches(forecast)
    cutoff = instant(payload["scoring_as_of_at"])
    require(cutoff <= manifest.created_at, "scoring cutoff follows manifest creation")
    view_id = payload["outcome_view_id"]
    require(manifest.views.keys() == {view_id}, "score has an unlinked or non-outcome view")
    outcome_view = manifest.select(view_id, "outcomes", cutoff)
    outcome_records = index(outcome_view.proof["outcomes"], "key")
    selected = {row.key: row for row in outcome_view.rows}
    require(
        outcome_records.keys() == selected.keys(), "outcomes disagree with the visible revisions"
    )
    for key, outcome in outcome_records.items():
        row = selected[key]
        require(
            type(outcome["revision"]) is int and outcome["revision"] == row.revision,
            f"{key}: outcome value belongs to another revision",
        )
        number(outcome["value"])
        outcome["played_date"] = row.observed_date
        outcome["finalized_at"] = row.finalized_at

    manifest.artifact(payload["access_log_artifact_id"], "access_log")
    metrics_file = json_record(manifest.content(payload["metrics_artifact_id"], "metrics"))
    results = payload["results"]
    require(
        bool(results) and metrics_file["results"] == results,
        "score results disagree with pinned metrics file",
    )
    expected_cohorts = {
        (batch.split_id, target["cohort_id"])
        for batch in batches
        for target in batch.targets.values()
    }
    result_cohorts = {(result["split_id"], result["cohort_id"]) for result in results}
    require(result_cohorts == expected_cohorts, "score does not cover every frozen cohort")
    result_keys = {
        (
            result["split_id"],
            result["cohort_id"],
            result["metric_code"],
            result["model_id"],
            result["baseline_id"],
        )
        for result in results
    }
    require(len(result_keys) == len(results), "duplicate score result")
    for result in results:
        _check_result(manifest, batches, outcome_records, result)
    return list(results)


def _check_result(
    manifest: Manifest,
    batches: list[FrozenBatch],
    outcomes: dict[str, Record],
    result: Record,
) -> None:
    split_id = result["split_id"]
    split = manifest.splits[split_id]
    code = result["metric_code"]
    require(
        code in METRICS and result["unit"] == METRICS[code][1],
        f"{code}: unsupported metric or incompatible unit",
    )
    errors = []
    baseline_errors = []
    games = set()
    keys = set()
    excluded: Counter[str] = Counter()
    for batch in batches:
        if batch.split_id != split_id:
            continue
        for key, target in batch.targets.items():
            if target["cohort_id"] != result["cohort_id"]:
                continue
            require(key not in keys, f"{key}: target appears more than once in the scored cohort")
            keys.add(key)
            prediction = batch.predictions.get(key)
            outcome = outcomes.get(key)
            if prediction is None:
                excluded["prediction_missing"] += 1
                continue
            if outcome is None:
                excluded["outcome_unavailable"] += 1
                continue
            _check_match(batch, target, outcome, split)
            if manifest.mode == "strict_rolling" and outcome.get("actual_tip_at") is None:
                excluded["actual_tip_unavailable"] += 1
                continue
            actual = number(outcome["value"])
            errors.append(prediction[result["model_id"]] - actual)
            baseline_id = result["baseline_id"]
            if baseline_id is not None:
                baseline_errors.append(prediction[baseline_id] - actual)
            games.add(target["game_id"])

    require(count(result["targets_expected"]) == len(keys), "expected target count differs")
    require(count(result["targets_scored"]) == len(errors), "scored target count differs")
    require(count(result["games_scored"]) == len(games), "scored game count differs")
    require(reasons(result["exclusions"]) == dict(excluded), "score exclusion counts differ")
    _match_number(result["sum_weights"], float(len(errors)), "sum_weights")
    candidate = _metric(code, errors)
    baseline = _metric(code, baseline_errors)
    delta = candidate - baseline if candidate is not None and baseline is not None else None
    _match_number(result["value"], candidate, "value")
    _match_number(result["paired_delta"], delta, "paired_delta")
    interval = result["interval"]
    if interval is not None:
        low, high = map(number, interval)
        require(low <= high, "invalid interval ordering")


def _check_match(batch: FrozenBatch, target: Record, outcome: Record, split: Record) -> None:
    key = target["key"]
    for field in ("game_id", "season_start_year", "season_type"):
        require(
            target[field] == outcome[field], f"{key}: {field} differs between target and outcome"
        )
    played = outcome["played_date"]
    require(
        played is not None and day(split["start_date"]) <= played < day(split["end_date"]),
        f"{key}: outcome played date is outside the frozen split",
    )
    require(
        batch.rating_date is None or played == batch.rating_date,
        f"{key}: outcome played date differs from the frozen rating date",
    )
    origin = batch.origin
    require(origin < outcome["finalized_at"], f"{key}: forecast origin fails outcome chronology")
    actual_tip = outcome.get("actual_tip_at")
    if actual_tip is not None:
        require(
            origin < instant(actual_tip) < outcome["finalized_at"],
            f"{key}: forecast origin must precede the actual target tip",
        )
