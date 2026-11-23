"""Check local evaluation manifests and their pinned row selections."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from graphlib import CycleError, TopologicalSorter
from math import isfinite
from typing import Any, cast

from bil.evaluation.eligibility import (
    Mode,
    Revision,
    Role,
    ValidationError,
    digest,
    eastern_origin,
    instant,
    is_digest,
    require,
    resolve_revisions,
)

Record = dict[str, Any]
ArtifactReader = Callable[[str], bytes]


def json_record(content: bytes) -> Record:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> Record:
        record = dict(pairs)
        require(len(record) == len(pairs), "duplicate JSON field")
        return record

    value = json.loads(content, object_pairs_hook=unique_pairs)
    require(isinstance(value, dict), "expected a JSON object")
    return cast(Record, value)


def index(records: list[Record], field: str) -> dict[str, Record]:
    require(isinstance(records, list), f"{field}: expected an array of records")
    indexed = {}
    for record in records:
        key = record[field]
        require(
            isinstance(key, str) and key and key not in indexed,
            f"missing or duplicate {field}: {key!r}",
        )
        indexed[key] = record
    return indexed


def count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValidationError(f"expected a nonnegative count, got {value!r}")
    return value


def number(value: object, field: str = "value") -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            parsed = float(value)
        except OverflowError:
            pass
        else:
            if isfinite(parsed):
                return parsed
    raise ValidationError(f"{field}: expected a finite numeric value")


def reasons(records: list[Record]) -> dict[str, int]:
    return {key: count(row["count"]) for key, row in index(records, "reason").items()}


def day(value: str) -> date:
    parsed = date.fromisoformat(value)
    require(parsed.isoformat() == value, f"expected an ISO played date, got {value!r}")
    return parsed


@dataclass
class Manifest:
    """A validated manifest header with indexed local references."""

    record: Record
    mode: Mode
    created_at: datetime
    artifacts: dict[str, Record]
    views: dict[str, Record]
    splits: dict[str, Record]
    read_artifact: ArtifactReader

    @classmethod
    def parse(cls, content: bytes, stage: str, read_artifact: ArtifactReader) -> "Manifest":
        record = json_record(content)
        require(
            type(record["schema_version"]) is int and record["schema_version"] == 1,
            "expected manifest schema version 1",
        )
        require(
            record["stage"] == stage and isinstance(record[stage], dict),
            f"expected a completed {stage} manifest",
        )
        require(
            record["status"] == "completed" and record["reason"] is None,
            "only completed manifests can be validated for evaluation",
        )
        other_stage = "score" if stage == "forecast" else "forecast"
        require(record[other_stage] is None, f"{stage} manifest contains {other_stage} payload")
        mode = record["evaluation_mode"]
        require(
            mode in {"retrospective", "strict_rolling"},
            "local validation supports retrospective and strict rolling-origin runs",
        )
        git_sha = record["code_git_sha"]
        require(
            isinstance(git_sha, str) and re.fullmatch(r"[0-9a-f]{40}", git_sha),
            "invalid code Git SHA",
        )
        for field in ("run_id", "experiment_id", "protocol_id"):
            require(isinstance(record[field], str) and record[field], f"missing {field}")
        created_at = instant(record["created_at"])
        require(
            instant(record["registered_at"]) <= created_at,
            "protocol registration follows manifest creation",
        )
        splits = index(record["splits"], "split_id")
        require(bool(splits), "manifest declares no splits")
        for split_id, split in splits.items():
            require(
                day(split["start_date"]) < day(split["end_date"]),
                f"{split_id}: empty or reversed dates",
            )
            require(
                split["role"] in {"fit", "validation", "holdout", "prospective"},
                f"{split_id}: invalid split role",
            )
            require(
                isinstance(split["season_start_years"], list)
                and split["season_start_years"]
                and all(type(year) is int for year in split["season_start_years"]),
                f"{split_id}: invalid season start years",
            )
            require(
                isinstance(split["season_types"], list)
                and split["season_types"]
                and all(isinstance(kind, str) and kind for kind in split["season_types"]),
                f"{split_id}: invalid season types",
            )
        for seed in index(record["seeds"], "scope").values():
            require(type(seed["seed"]) is int, "seed must be an integer")

        artifacts = index(record["artifacts"], "artifact_id")
        for artifact_id, artifact in artifacts.items():
            require(is_digest(artifact["sha256"]), f"{artifact_id}: invalid artifact SHA-256")
            require(
                isinstance(artifact["uri"], str) and artifact["uri"],
                f"{artifact_id}: empty artifact URI",
            )
            count(artifact["size_bytes"])
            if artifact["kind"] == "source":
                for field in ("source_artifact_id", "rights_ref"):
                    require(
                        isinstance(artifact[field], str) and artifact[field],
                        f"{artifact_id}: source artifact requires {field}",
                    )
        manifest = cls(
            record,
            mode,
            created_at,
            artifacts,
            index(record["input_views"], "view_id"),
            splits,
            read_artifact,
        )
        for kind in ("config", "environment", "registration"):
            manifest.artifact(record[f"{kind}_artifact_id"], kind)
        return manifest

    def artifact(self, artifact_id: str, kind: str) -> Record:
        artifact = self.artifacts.get(artifact_id)
        require(
            artifact is not None and artifact["kind"] == kind,
            f"{artifact_id!r}: expected {kind} artifact",
        )
        return self.artifacts[artifact_id]

    def content(self, artifact_id: str, kind: str) -> bytes:
        artifact = self.artifact(artifact_id, kind)
        content = self.read_artifact(artifact["uri"])
        verify_bytes(artifact, content)
        return content

    def select(
        self, view_id: str, role: Role, cutoff: datetime, rating_date: date | None = None
    ) -> View:
        view = self.views.get(view_id)
        if view is None or view["role"] != role or instant(view["as_of_at"]) != cutoff:
            raise ValidationError(f"{view_id!r}: expected {role} input view at its declared cutoff")
        sources = set(view["source_artifact_ids"])
        for source_id in sources:
            self.artifact(source_id, "source")
        proof = json_record(self.content(view["selection_artifact_id"], "selection"))
        candidates = tuple(Revision.from_json(row) for row in proof["revisions"])
        require(
            all(row.source_artifact_id in sources for row in candidates),
            f"{view_id}: revision source is absent from the view",
        )
        selected = resolve_revisions(
            candidates,
            cutoff=cutoff,
            mode=self.mode,
            role=role,
            rating_date=rating_date,
        )
        require(
            all(
                row.available_at is None or row.available_at <= self.created_at
                for row in candidates
            ),
            f"{view_id}: availability evidence follows manifest creation",
        )
        expected = [list(row.identity) for row in selected.rows]
        require(proof["selected"] == expected, f"{view_id}: selected revisions differ from cutoff")
        require(
            count(view["selected_count"]) == len(selected.rows),
            f"{view_id}: selected count does not match evidence",
        )
        known = [row.available_at for row in selected.rows if row.available_at is not None]
        reported = view["max_known_available_at"]
        require(
            (instant(reported) if reported is not None else None) == max(known, default=None),
            f"{view_id}: maximum availability does not match evidence",
        )
        require(
            count(view["unknown_availability_count"]) == len(selected.rows) - len(known),
            f"{view_id}: unknown availability count does not match evidence",
        )
        require(
            reasons(view["exclusions"]) == dict(selected.exclusions),
            f"{view_id}: exclusion counts do not match evidence",
        )
        return View(proof, candidates, selected.rows)


@dataclass(frozen=True)
class View:
    proof: Record
    candidates: tuple[Revision, ...]
    rows: tuple[Revision, ...]


def verify_bytes(artifact: Record, content: bytes) -> None:
    require(
        len(content) == artifact["size_bytes"] and digest(content) == artifact["sha256"],
        f"{artifact['artifact_id']}: exact artifact bytes differ from manifest",
    )


@dataclass(frozen=True)
class FrozenBatch:
    split_id: str
    origin: datetime
    rating_date: date | None
    targets: dict[str, Record]
    predictions: dict[str, dict[str, float]]


def forecast_batches(manifest: Manifest) -> list[FrozenBatch]:
    """Verify fit lineage and return predictions from the checked artifact bytes."""
    for view_record in manifest.views.values():
        require(view_record["role"] in {"features", "fit"}, "score-only view in forecast lineage")
    forecast = manifest.record["forecast"]
    fits = index(forecast["fits"], "fit_id")
    cutoffs = {fit_id: instant(fit["fit_as_of_at"]) for fit_id, fit in fits.items()}
    generated = {fit_id: instant(fit["generated_at"]) for fit_id, fit in fits.items()}
    graph: TopologicalSorter[str] = TopologicalSorter()
    for fit_id, fit in fits.items():
        cutoff = cutoffs[fit_id]
        require(
            cutoff <= generated[fit_id] <= manifest.created_at,
            f"{fit_id}: invalid fit generation time",
        )
        manifest.artifact(fit["state_artifact_id"], "fitted_state")
        manifest.artifact(fit["config_artifact_id"], "config")
        parents = fit["parent_fit_ids"]
        for parent in parents:
            require(parent in fits, f"{fit_id}: unknown parent fit {parent}")
            require(
                cutoffs[parent] <= cutoff and generated[parent] <= generated[fit_id],
                f"{fit_id}: parent fit {parent} exceeds child cutoff or generation time",
            )
        graph.add(fit_id, *parents)
    try:
        ordered_fits = tuple(graph.static_order())
    except CycleError as exc:
        raise ValidationError("cyclic fit lineage") from exc

    validated_views = set()
    for fit_id in ordered_fits:
        fit = fits[fit_id]
        view_id = fit["fit_view_id"]
        view = manifest.select(view_id, "fit", cutoffs[fit_id])
        _check_training(manifest.mode, view, cutoffs[fit_id], set(fit["parent_fit_ids"]), cutoffs)
        validated_views.add(view_id)

    batches = []
    game_splits: dict[str, str] = {}
    for batch_id, batch in index(forecast["batches"], "batch_id").items():
        split_id = batch["split_id"]
        split = manifest.splits[split_id]
        origin = instant(batch["origin_at"])
        rating_date = day(batch["rating_date"]) if batch["rating_date"] is not None else None
        if rating_date is not None:
            require(
                origin == eastern_origin(rating_date),
                f"{batch_id}: origin must be Eastern midnight",
            )
            require(
                day(split["start_date"]) <= rating_date < day(split["end_date"]),
                f"{batch_id}: rating date outside split",
            )
        require(
            batch["frozen_at"] is None and batch["freeze_receipt_artifact_id"] is None,
            f"{batch_id}: historical batch cannot assert a prospective freeze",
        )
        target_id = batch["target_artifact_id"]
        targets = _batch_targets(manifest, target_id, split_id, game_splits)
        if batch["status"] == "missing":
            require(
                batch["missing_reason"]
                and batch["predictions_artifact_id"] is None
                and not batch["fit_ids"]
                and batch["feature_view_id"] is None
                and batch["generated_at"] is None,
                f"{batch_id}: invalid missing forecast",
            )
            require(
                all(row["status"] == "missing" for row in targets.values()),
                f"{batch_id}: missing batch contains generated targets",
            )
            require(target_id is not None, f"{batch_id}: expected target denominator is unknown")
            batches.append(FrozenBatch(split_id, origin, rating_date, targets, {}))
            continue
        require(
            batch["status"] == "generated" and batch["missing_reason"] is None,
            f"{batch_id}: invalid batch status",
        )
        prediction_time = instant(batch["generated_at"])
        require(
            origin <= prediction_time <= manifest.created_at, f"{batch_id}: invalid generation time"
        )
        view_id = batch["feature_view_id"]
        manifest.select(view_id, "features", origin, rating_date)
        validated_views.add(view_id)
        for fit_id in batch["fit_ids"]:
            require(
                fit_id in fits
                and cutoffs[fit_id] <= origin
                and generated[fit_id] <= prediction_time,
                f"{batch_id}: fit {fit_id} exceeds origin or generation time",
            )
        require(target_id is not None, f"{batch_id}: missing target cohort artifact")
        content = manifest.content(batch["predictions_artifact_id"], "predictions")
        prediction_records = index(json_record(content)["predictions"], "key")
        expected_keys = {key for key, target in targets.items() if target["status"] == "generated"}
        require(
            prediction_records.keys() == expected_keys,
            f"{batch_id}: predictions disagree with the frozen target roster",
        )
        predictions = {
            key: _prediction_values(key, row.get("values"))
            for key, row in prediction_records.items()
        }
        batches.append(FrozenBatch(split_id, origin, rating_date, targets, predictions))
    require(manifest.views.keys() == validated_views, "forecast has an unlinked input view")
    require(bool(batches), "forecast has no planned or generated batches")
    return batches


def _prediction_values(key: str, values: object) -> dict[str, float]:
    if not isinstance(values, dict) or not values:
        raise ValidationError(f"{key}: expected a nonempty prediction model map")
    predictions = {}
    for model_id, value in values.items():
        require(
            isinstance(model_id, str) and model_id.strip(), f"{key}: missing prediction model ID"
        )
        predictions[model_id] = number(value, f"{key} prediction for {model_id}")
    return predictions


def _batch_targets(
    manifest: Manifest, target_id: str | None, split_id: str, game_splits: dict[str, str]
) -> dict[str, Record]:
    if target_id is None:
        return {}
    content = manifest.content(target_id, "cohort")
    targets = index(json_record(content)["targets"], "key")
    split = manifest.splits[split_id]
    for key, target in targets.items():
        require(target["status"] in {"generated", "missing"}, f"{key}: invalid target status")
        game_id = target["game_id"]
        require(
            isinstance(game_id, str)
            and game_id
            and game_splits.setdefault(game_id, split_id) == split_id,
            f"{key}: game occurs in multiple scored splits or has no identity",
        )
        require(
            isinstance(target["cohort_id"], str) and target["cohort_id"],
            f"{key}: target cohort is missing",
        )
        require(
            target["season_start_year"] in split["season_start_years"]
            and target["season_type"] in split["season_types"],
            f"{key}: target outside split season scope",
        )
    return targets


def _check_training(
    mode: Mode, view: View, cutoff: datetime, parents: set[str], fit_cutoffs: dict[str, datetime]
) -> None:
    proof = view.proof
    training_mode = proof["training_mode"]
    if training_mode == "historical_estimator":
        start_date, end_date = map(day, proof["calibration_window"])
        require(
            start_date < end_date and eastern_origin(end_date) <= cutoff,
            "historical calibration window exceeds fit cutoff",
        )
        require(
            all(
                row.observed_date is not None and start_date <= row.observed_date < end_date
                for row in view.rows
                if row.kind in {"observation", "outcome"}
            ),
            "historical calibration row falls outside the declared co-window",
        )
        return
    require(training_mode == "forward", "fit selection must declare its training mode")
    label_rows = {row.identity: row for row in view.rows if row.kind == "outcome"}
    used_labels = set()
    used_parents = set()
    eligible_features: dict[tuple[datetime, date | None], set[tuple[str, int]]] = {}
    prediction_parents = set(proof["prediction_parent_fit_ids"])
    require(prediction_parents <= parents, "undeclared prediction parent in fit selection")
    for example in proof["training_examples"]:
        label = tuple(example["label"])
        require(
            label in label_rows and label not in used_labels,
            f"{label}: missing, late or duplicate training label",
        )
        used_labels.add(label)
        origin = instant(example["origin_at"])
        label_row = label_rows[label]
        require(
            label_row.finalized_at is not None and origin < label_row.finalized_at,
            f"{label}: origin does not precede the label horizon close",
        )
        rating_date = day(example["rating_date"]) if example.get("rating_date") else None
        if rating_date is not None:
            require(origin == eastern_origin(rating_date), f"{label}: invalid example origin")
        view_key = (origin, rating_date)
        if view_key not in eligible_features:
            selected = resolve_revisions(
                view.candidates,
                cutoff=origin,
                mode=mode,
                role="features",
                rating_date=rating_date,
            )
            eligible_features[view_key] = {row.identity for row in selected.rows}
        require(
            all(tuple(feature) in eligible_features[view_key] for feature in example["features"]),
            f"{label}: training feature is ineligible at the example origin",
        )
        for parent in example["parent_fit_ids"]:
            require(
                parent in prediction_parents and fit_cutoffs[parent] <= origin,
                f"{label}: parent fit {parent} is ineligible at the example origin",
            )
            used_parents.add(parent)
    require(used_labels == label_rows.keys(), "forward fit has unlinked training labels")
    require(used_parents == prediction_parents, "forward fit has unlinked parent predictions")
