"""Refresh failure outcomes, rollback and the current artifact (#145)."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from test_expected_impact import CUTOFF
from test_refresh import inputs

import bil.refresh as refresh
from bil.models.calibration_lineage import LineageError
from bil.refresh import (
    OUTCOMES,
    RATINGS,
    RETIRED,
    Inputs,
    RefreshError,
    build,
    current,
    refresh_origin,
    retire,
)


def outcomes(root: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (root / OUTCOMES).open()]


def artifacts(root: Path, origin: date = CUTOFF) -> list[str]:
    parent = root / origin.isoformat()
    return sorted(p.name for p in parent.iterdir()) if parent.exists() else []


def test_a_load_failure_refuses_every_requested_origin(tmp_path: Path) -> None:
    def load() -> Inputs:
        raise ValueError("box log snapshot size mismatch")

    records, failures = build(tmp_path, [CUTOFF, date(2021, 12, 1)], load, {"addendum": "x"})
    assert failures == 2 and [r["stage"] for r in outcomes(tmp_path)] == ["load", "load"]
    assert records[0]["reason"] == "box log snapshot size mismatch"
    assert records[0]["inputs"] == {"addendum": "x"}
    assert artifacts(tmp_path) == []


def test_a_late_parent_is_refused_before_fitting(tmp_path: Path) -> None:
    base = inputs()
    late = replace(base, spm=replace(base.spm, origin=f"contiguous@{CUTOFF.isoformat()}"))
    _, failures = build(tmp_path, [CUTOFF], lambda: late)
    [record] = outcomes(tmp_path)
    assert failures == 1 and record["stage"] == "parent" and "late parent" in str(record["reason"])
    assert record["inputs"] == base.input_ids and artifacts(tmp_path) == []


def test_an_ineligible_calibration_is_refused_and_an_eligible_one_is_a_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calibration = tmp_path / "calibration"
    calibration.mkdir()
    (calibration / "calibration.json").write_text("{}", encoding="utf-8")

    def ineligible(directory: Path, origin: date) -> dict[str, str]:
        raise LineageError(f"calibration fit cutoff 2024-07-01 follows the origin {origin}")

    monkeypatch.setattr(refresh, "load_calibration", ineligible)
    with_calibration = replace(inputs(), calibration=calibration)
    _, failures = build(tmp_path / "a", [CUTOFF], lambda: with_calibration)
    [record] = outcomes(tmp_path / "a")
    assert failures == 1 and record["stage"] == "calibration" and record["error"] == "LineageError"
    assert artifacts(tmp_path / "a") == []

    monkeypatch.setattr(refresh, "load_calibration", lambda d, o: {"fit_cutoff": "2021-07-01"})
    done = refresh_origin(tmp_path / "b", CUTOFF, with_calibration)
    manifest = json.loads((done.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["parents"]["calibration"] == manifest["calibration"]["calibration_id"]
    assert done.artifact_id != refresh_origin(tmp_path / "c", CUTOFF, inputs()).artifact_id


def test_an_interrupted_publish_leaves_nothing_and_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = refresh.write_ratings

    def crash(path: Path, snapshots: object) -> None:
        path.write_text("partial", encoding="utf-8")
        raise OSError("interrupted")

    monkeypatch.setattr(refresh, "write_ratings", crash)
    _, failures = build(tmp_path, [CUTOFF], inputs)
    [record] = outcomes(tmp_path)
    assert failures == 1 and record["stage"] == "publish" and record["error"] == "OSError"
    assert artifacts(tmp_path) == []  # no artifact and no staging directory
    monkeypatch.setattr(refresh, "write_ratings", original)
    records, failures = build(tmp_path, [CUTOFF], inputs)
    assert failures == 0 and records[0]["outcome"] == "published"
    again, _ = build(tmp_path, [CUTOFF], inputs)
    assert again[0]["outcome"] == "unchanged"


def test_rollback_retires_an_accepted_revision_and_restores_the_current_artifact(
    tmp_path: Path,
) -> None:
    first = refresh_origin(tmp_path, CUTOFF, inputs())
    assert current(tmp_path, CUTOFF) == first.path
    other = replace(inputs(), config={**inputs().config, "offense_ridge": 31.0})
    second = refresh_origin(tmp_path, CUTOFF, other, accept_revision=True)
    assert current(tmp_path, CUTOFF) == second.path
    moved = retire(tmp_path, CUTOFF, second.artifact_id, "drill: bad ridge")
    assert moved == tmp_path / RETIRED / CUTOFF.isoformat() / second.artifact_id
    assert (moved / RATINGS).is_file() and current(tmp_path, CUTOFF) == first.path
    assert outcomes(tmp_path)[-1]["outcome"] == "retired"
    with pytest.raises(RefreshError, match="not a published artifact"):
        retire(tmp_path, CUTOFF, second.artifact_id, "again")
    assert current(tmp_path, date(2021, 12, 1)) is None


def test_inconsistent_artifacts_fail_closed_and_can_be_retired(tmp_path: Path) -> None:
    first = refresh_origin(tmp_path, CUTOFF, inputs())
    other = replace(inputs(), config={**inputs().config, "offense_ridge": 31.0})
    second = refresh_origin(tmp_path, CUTOFF, other, accept_revision=True)
    (second.path / RATINGS).write_text("tampered", encoding="utf-8")
    with pytest.raises(RefreshError, match="retire it"):
        current(tmp_path, CUTOFF)
    retire(tmp_path, CUTOFF, second.artifact_id, "drill: corrupted")
    assert current(tmp_path, CUTOFF) == first.path
    # An unrecorded extra artifact is never silently ignored.
    stray = tmp_path / CUTOFF.isoformat() / ("f" * 64)
    third = refresh_origin(tmp_path / "x", CUTOFF, other)
    shutil.copytree(third.path, stray)
    manifest = json.loads((stray / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_id"] = "f" * 64
    (stray / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RefreshError, match="unrecorded"):
        current(tmp_path, CUTOFF)


def test_an_interrupt_is_recorded_and_still_stops_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(refresh, "write_ratings", interrupt)
    with pytest.raises(KeyboardInterrupt):
        build(tmp_path, [CUTOFF, date(2021, 12, 1)], inputs)
    records = outcomes(tmp_path)
    assert [(r["outcome"], r.get("stage")) for r in records] == [
        ("refused", "publish"),
        ("skipped", None),
    ]
    assert artifacts(tmp_path) == []
