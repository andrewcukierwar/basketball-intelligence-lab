"""Checkpointed refresh, warm and cold equality, and late-revision detection (#144)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_expected_impact import CUTOFF, synthetic
from test_refresh import inputs

from bil.refresh import (
    RATINGS,
    REVISIONS,
    RevisionConflict,
    prune_checkpoints,
    refresh_origin,
)


def test_warm_and_cold_builds_are_identical(tmp_path: Path) -> None:
    store = tmp_path / "checkpoints"
    cold = refresh_origin(tmp_path / "cold", CUTOFF, inputs(), checkpoints=store)
    warm = refresh_origin(tmp_path / "warm", CUTOFF, inputs(), checkpoints=store)
    plain = refresh_origin(tmp_path / "plain", CUTOFF, inputs())
    assert (cold.checkpoint, warm.checkpoint, plain.checkpoint) == ("computed", "reused", "none")
    assert cold.artifact_id == warm.artifact_id == plain.artifact_id
    ratings = {(p.path / RATINGS).read_bytes() for p in (cold, warm, plain)}
    assert len(ratings) == 1
    again = refresh_origin(tmp_path / "again", CUTOFF, inputs(), checkpoints=store, reuse=False)
    assert again.checkpoint == "computed" and (again.path / RATINGS).read_bytes() in ratings


def test_a_checkpoint_is_reused_only_when_every_id_matches(tmp_path: Path) -> None:
    store = tmp_path / "checkpoints"
    first = refresh_origin(tmp_path / "a", CUTOFF, inputs(), checkpoints=store)
    [meta] = store.glob("*.json")
    record = json.loads(meta.read_text(encoding="utf-8"))
    record["identity"]["parents"] = {"spm": "other", "penalty_selection": "test"}
    meta.write_text(json.dumps(record), encoding="utf-8")
    tampered = refresh_origin(tmp_path / "b", CUTOFF, inputs(), checkpoints=store)
    assert tampered.checkpoint == "computed"  # rewritten from scratch, then valid again
    [npz] = store.glob("*.npz")
    npz.write_bytes(npz.read_bytes()[:-8] + b"\0" * 8)
    corrupt = refresh_origin(tmp_path / "c", CUTOFF, inputs(), checkpoints=store)
    assert corrupt.checkpoint == "computed"
    assert (corrupt.path / RATINGS).read_bytes() == (first.path / RATINGS).read_bytes()
    # A different configuration is a different identity, so the checkpoint never applies.
    other = replace(inputs(), config={**inputs().config, "offense_ridge": 31.0})
    assert refresh_origin(tmp_path / "d", CUTOFF, other, checkpoints=store).checkpoint == "computed"


def test_retention_keeps_only_the_latest_origins(tmp_path: Path) -> None:
    for day in range(1, 21):
        for suffix in (".json", ".npz"):
            (tmp_path / f"2024-01-{day:02d}-{'a' * 64}{suffix}").write_text("x")
    removed = prune_checkpoints(tmp_path, keep=14)
    assert len(removed) == 6 and all(r < "2024-01-07" for r in removed)
    assert len(list(tmp_path.glob("*.npz"))) == 14 == len(list(tmp_path.glob("*.json")))


def test_a_late_revision_of_an_eligible_game_is_recorded_not_republished(tmp_path: Path) -> None:
    first = refresh_origin(tmp_path, CUTOFF, inputs())
    rows, box = synthetic()
    target = next(r for r in box if r.game_date < CUTOFF)
    corrected = [replace(r, fga=r.fga + 3) if r is target else r for r in box]
    late = inputs(box=corrected)
    with pytest.raises(RevisionConflict, match="not published"):
        refresh_origin(tmp_path, CUTOFF, late)
    [record] = [json.loads(line) for line in (tmp_path / CUTOFF.isoformat() / REVISIONS).open()]
    assert record["previous_artifact_id"] == first.artifact_id
    assert record["action"] == "refused" and record["games_changed"] == 1
    assert record["examples"]["changed"] == [f"box_logs/2021:{target.game_id}"]
    assert record["changed_inputs"] == ["source_resolution"]
    assert [p.name for p in (tmp_path / CUTOFF.isoformat()).iterdir() if p.is_dir()] == [
        first.artifact_id
    ]
