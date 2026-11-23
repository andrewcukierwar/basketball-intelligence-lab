"""Exercise evaluation against exact-byte synthetic artifacts."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import date
from functools import lru_cache
from pathlib import Path

import pytest

from bil.evaluation.eligibility import (
    Revision,
    ValidationError,
    digest,
    eastern_origin,
    instant,
    resolve_revisions,
)
from bil.evaluation.scoring import validate_forecast, validate_score

FIXTURES = Path(__file__).parent / "fixtures" / "evaluation"
FORECAST = "synthetic_forecast.json"
SCORE = "synthetic_score.json"


def encode(record):
    return (json.dumps(record, indent=2) + "\n").encode()


class Run:
    def __init__(self):
        self.forecast_bytes = self.read(FORECAST)
        self.forecast = json.loads(self.forecast_bytes)
        self.score = json.loads(self.read(SCORE))
        self.overrides = {}

    def read(self, name):
        return (FIXTURES / name).read_bytes()

    def artifact(self, name):
        if name in self.overrides:
            return self.overrides[name]
        return self.read(name)

    def artifact_entry(self, stage, artifact_id):
        manifest = self.forecast if stage == "forecast" else self.score
        return next(item for item in manifest["artifacts"] if item["artifact_id"] == artifact_id)

    def update(self, stage, artifact_id, edit):
        artifact = self.artifact_entry(stage, artifact_id)
        record = json.loads(self.artifact(artifact["uri"]))
        edit(record)
        content = encode(record)
        self.overrides[artifact["uri"]] = content
        artifact.update(sha256=digest(content), size_bytes=len(content))

    def check_forecast(self):
        return validate_forecast(encode(self.forecast), self.artifact)

    def check_score(self, forecast_bytes=None):
        return validate_score(
            encode(self.score), self.artifact, forecast_bytes or self.forecast_bytes, self.artifact
        )


def test_local_validation_command_runs_both_stages():
    env = dict(os.environ)
    repo = FIXTURES.parents[2]
    env["PYTHONPATH"] = str(repo / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bil.evaluation",
            str(FIXTURES / FORECAST),
            "--score",
            str(FIXTURES / SCORE),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert "recomputed 1 scoring results" in result.stdout


def test_strict_versions_dst_cutoff_retractions_and_unknown():
    run = Run()
    record = json.loads(run.read("synthetic/features-keys.json"))
    game, schedule = map(Revision.from_json, record["revisions"])
    rating_date = date(2025, 11, 3)
    cutoff = eastern_origin(rating_date)
    assert cutoff == instant("2025-11-03T05:00:00Z")
    assert eastern_origin(date(2025, 7, 1)) == instant("2025-07-01T04:00:00Z")
    correction = replace(game, revision=2, available_at=instant("2025-11-03T05:01:00Z"))
    unknown = replace(game, revision=3, available_at=None, availability_basis="unknown")
    rows = [game, schedule, correction, unknown]
    strict = resolve_revisions(
        rows, cutoff=cutoff, mode="strict_rolling", role="features", rating_date=rating_date
    )
    historical = resolve_revisions(
        rows, cutoff=cutoff, mode="retrospective", role="features", rating_date=rating_date
    )
    assert strict.rows == (game, schedule)
    assert dict(strict.exclusions) == {"available_after_cutoff": 1, "availability_unknown": 1}
    assert historical.rows == (unknown, schedule)
    retraction = replace(correction, revision=4, change="retract")
    later = resolve_revisions(
        rows + [retraction],
        cutoff=correction.available_at,
        mode="strict_rolling",
        role="features",
        rating_date=rating_date,
    )
    assert later.rows == (schedule,)
    assert dict(later.exclusions) == {"availability_unknown": 1, "retracted": 1}

    same_day_game = replace(game, observed_date=rating_date, observed_at=cutoff)
    same_day = resolve_revisions(
        [same_day_game],
        cutoff=correction.available_at,
        mode="strict_rolling",
        role="fit",
        rating_date=rating_date,
    )
    assert not same_day.rows
    assert dict(same_day.exclusions) == {"same_or_later_played_date": 1}

    boundary = replace(game, kind="outcome", finalized_at=cutoff)
    mature = resolve_revisions([boundary], cutoff=cutoff, mode="strict_rolling", role="fit")
    assert not mature.rows
    assert dict(mature.exclusions) == {"observed_at_or_after_cutoff": 1}


def test_future_perturbation_and_cached_inputs_are_isolated():
    run = Run()
    game, schedule = map(
        Revision.from_json, json.loads(run.read("synthetic/features-keys.json"))["revisions"]
    )
    cutoff = eastern_origin(date(2025, 11, 3))
    later = instant("2025-11-03T05:01:00Z")
    correction = replace(game, revision=2, available_at=later, content_sha256=digest(b"later"))
    changed = replace(correction, content_sha256=digest(b"perturbed"))

    @lru_cache
    def transform(selected):
        return digest("".join(row.content_sha256 for row in selected).encode())

    def project(row, when):
        selected = resolve_revisions(
            [schedule, game, row], cutoff=when, mode="strict_rolling", role="features"
        )
        return transform(selected.rows)

    assert project(correction, cutoff) == project(changed, cutoff)
    assert transform.cache_info().hits == 1
    assert project(correction, later) != project(changed, later)
    assert transform.cache_info().misses == 3


def test_future_feature_revision_leaves_frozen_predictions_identical():
    run = Run()
    predictions = run.check_forecast()[0].predictions

    def append_future(proof):
        previous = proof["revisions"][0]
        proof["revisions"].append(
            dict(
                previous,
                revision=2,
                available_at="2025-11-03T05:01:00Z",
                content_sha256=digest(b"future-correction"),
            )
        )

    run.update("forecast", "features-keys", append_future)
    run.forecast["input_views"][0]["exclusions"] = [
        {"reason": "available_after_cutoff", "count": 1}
    ]
    assert run.check_forecast()[0].predictions == predictions


def test_retrospective_manifest_reports_selected_unknown_revision():
    run = Run()

    def change(proof):
        proof["revisions"][0].update(
            available_at=None, availability_basis="unknown", evidence_ref=None
        )

    run.update("forecast", "features-keys", change)
    features = run.forecast["input_views"][0]
    features["unknown_availability_count"] = 1
    with pytest.raises(ValidationError, match="selected revisions differ"):
        run.check_forecast()
    run.forecast["evaluation_mode"] = "retrospective"
    assert len(run.check_forecast()) == 1
    features["unknown_availability_count"] = 0
    with pytest.raises(ValidationError, match="unknown availability count"):
        run.check_forecast()


def test_fit_rejects_label_window_that_closes_at_cutoff():
    run = Run()

    def change(proof):
        proof["revisions"][1]["finalized_at"] = run.forecast["forecast"]["fits"][1]["fit_as_of_at"]

    run.update("forecast", "spm-fit-keys", change)
    with pytest.raises(ValidationError, match="spm-fit: selected revisions differ"):
        run.check_forecast()


def test_forward_training_uses_example_cutoff_for_features_and_calibration_parents():
    run = Run()
    fit = run.forecast["forecast"]["fits"][1]
    fit["component"] = "calibration"
    forward_example = {
        "label": ["rapm-label", 1],
        "origin_at": "2023-06-30T04:00:00Z",
        "rating_date": "2023-06-30",
        "features": [["spm-stat", 1]],
        "parent_fit_ids": ["rapm-target-fit"],
    }

    def configure(proof):
        proof.update(
            training_mode="forward",
            training_examples=[forward_example],
            prediction_parent_fit_ids=["rapm-target-fit"],
        )
        corrected = proof["revisions"][0]
        corrected["revision"] = 2
        old = dict(corrected, revision=1, available_at="2023-06-15T14:00:00Z")
        proof["revisions"].append(old)
        proof["selected"][1] = ["spm-stat", 2]

    run.update("forecast", "spm-fit-keys", configure)
    with pytest.raises(ValidationError, match="parent fit rapm-target-fit is ineligible"):
        run.check_forecast()

    # Move the parent cutoff earlier while preserving its legitimate training evidence.
    run.forecast["forecast"]["fits"][0]["fit_as_of_at"] = "2023-06-30T04:00:00Z"
    run.forecast["input_views"][1]["as_of_at"] = "2023-06-30T04:00:00Z"
    run.update(
        "forecast",
        "rapm-fit-keys",
        lambda p: p.update(calibration_window=["2022-07-01", "2023-06-30"]),
    )
    assert len(run.check_forecast()) == 1
    run.update(
        "forecast",
        "spm-fit-keys",
        lambda p: p["training_examples"][0].update(features=[["spm-stat", 2]]),
    )
    with pytest.raises(ValidationError, match="training feature is ineligible"):
        run.check_forecast()


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda fit: fit.update(fit_as_of_at="2025-07-01T04:00:01Z"), "exceeds child cutoff"),
        (lambda fit: fit.update(generated_at="2026-11-23T13:55:01Z"), "exceeds child cutoff"),
    ],
)
def test_transitive_fit_dependencies_cannot_exceed_child_time(edit, message):
    run = Run()
    edit(run.forecast["forecast"]["fits"][0])
    with pytest.raises(ValidationError, match=message):
        run.check_forecast()


def test_forecast_checks_fit_dependency_cycles_and_score_only_roles():
    run = Run()
    run.forecast["input_views"][0]["role"] = "external_epm"
    with pytest.raises(ValidationError, match="score-only view"):
        run.check_forecast()

    run = Run()
    first, second = run.forecast["forecast"]["fits"]
    first.update(
        parent_fit_ids=["spm-fit"],
        fit_as_of_at=second["fit_as_of_at"],
        generated_at=second["generated_at"],
    )
    with pytest.raises(ValidationError, match="cyclic fit lineage"):
        run.check_forecast()


def test_score_verifies_prediction_and_forecast_bytes_and_recomputes_values():
    run = Run()
    first = run.check_score()
    assert first == run.check_score()
    assert first[0]["value"] == 4.0
    assert first[0]["paired_delta"] == -1.0
    assert first[0]["targets_scored"] == 1

    with pytest.raises(ValidationError, match="parent-forecast: exact artifact bytes"):
        run.check_score(run.forecast_bytes + b"\n")

    prediction_uri = run.artifact_entry("forecast", "predictions")["uri"]
    run.overrides[prediction_uri] = run.read(prediction_uri) + b" "
    with pytest.raises(ValidationError, match="predictions: exact artifact bytes"):
        run.check_score()

    del run.overrides[prediction_uri]
    run.score["score"]["results"][0]["value"] = 0
    run.update("score", "metrics", lambda p: p.update(results=run.score["score"]["results"]))
    with pytest.raises(ValidationError, match="score does not match recomputed value"):
        run.check_score()


def test_late_outcome_revision_can_be_rescored_without_changing_forecast():
    run = Run()
    original = run.check_score()
    available_at = "2026-11-23T14:22:00Z"

    def append_revision(proof):
        prior = proof["revisions"][0]
        proof["revisions"].append(
            dict(
                prior,
                revision=2,
                available_at=available_at,
                content_sha256=digest(b"revised-margin-12"),
            )
        )

    run.update("score", "outcomes-keys", append_revision)
    view = run.score["input_views"][0]
    view["exclusions"] = [{"reason": "available_after_cutoff", "count": 1}]
    assert run.check_score() == original

    def select_revision(proof):
        proof["selected"][0][1] = 2
        proof["outcomes"][0].update(revision=2, value=12.0)

    run.update("score", "outcomes-keys", select_revision)
    view.update(as_of_at=available_at, max_known_available_at=available_at, exclusions=[])
    run.score.update(run_id="synthetic-score-revision-2", parent_run_id="synthetic-score")
    run.score["score"].update(scoring_as_of_at=available_at)
    run.score["score"]["results"][0]["value"] = 2.0
    run.update("score", "metrics", lambda p: p.update(results=run.score["score"]["results"]))
    assert run.check_score()[0]["value"] == 2.0
    assert run.read(FORECAST) == run.forecast_bytes


def test_score_rejects_immature_outcome_and_late_origin():
    run = Run()
    run.update(
        "score",
        "outcomes-keys",
        lambda p: p["revisions"][0].update(finalized_at=run.score["score"]["scoring_as_of_at"]),
    )
    with pytest.raises(ValidationError, match="selected revisions differ"):
        run.check_score()

    run = Run()
    run.update(
        "score",
        "outcomes-keys",
        lambda p: p["outcomes"][0].update(
            actual_tip_at=run.forecast["forecast"]["batches"][0]["origin_at"]
        ),
    )
    with pytest.raises(ValidationError, match="origin must precede the actual target tip"):
        run.check_score()
