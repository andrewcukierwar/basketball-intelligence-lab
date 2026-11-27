"""Replayable origin refresh: cutoff, identity, idempotence and atomic publication (#142)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from test_expected_impact import CUTOFF, ROOKIE, analysis, spm, synthetic

from bil.features.box import Appearance
from bil.models.team_outcomes import load_ratings
from bil.refresh import (
    MANIFEST,
    RATINGS,
    Inputs,
    RefreshError,
    publish,
    refresh_origin,
)

CONFIG = {"window": "W2", "offense_ridge": 30.0, "defense_ridge": 60.0}
IDS = {"rows": {"2021-22": "r" * 64}, "box_logs": {"2021": "b" * 64}}
PARENTS = {"spm": "fit-x", "penalty_selection": "test"}


def inputs(rows=None, box=None, ids=IDS) -> Inputs:  # type: ignore[no-untyped-def]
    base_rows, base_box = synthetic()
    rows = base_rows if rows is None else rows
    box = base_box if box is None else box
    return Inputs(analysis(rows), spm(), {2020: [], 2021: box}, CONFIG, ids, PARENTS, (2021,))


def test_later_inputs_cannot_change_the_published_artifact(tmp_path: Path) -> None:
    rows, box = synthetic()
    first = refresh_origin(tmp_path / "a", CUTOFF, inputs())
    later = rows.day >= CUTOFF.toordinal()
    poisoned_rows = replace(rows, y=np.where(later, 999.0, rows.y))
    poisoned_box = [replace(r, fga=60) if r.game_date >= CUTOFF else r for r in box] + [
        Appearance.from_record(
            {
                "game_id": "0022199999",
                "game_date": CUTOFF,
                "player_id": ROOKIE,
                "team_id": 1,
                "opp_team_id": 2,
                "min": 40,
                "fga": 30,
                "stl": 5,
            }
        )
    ]
    second = refresh_origin(tmp_path / "b", CUTOFF, inputs(poisoned_rows, poisoned_box))
    assert first.artifact_id == second.artifact_id
    assert (first.path / RATINGS).read_bytes() == (second.path / RATINGS).read_bytes()
    [snap] = load_ratings(first.path / RATINGS)
    assert snap.as_of == CUTOFF and ROOKIE not in snap.total


def test_rerun_is_a_no_op_and_changed_inputs_get_a_new_artifact(tmp_path: Path) -> None:
    first = refresh_origin(tmp_path, CUTOFF, inputs())
    assert first.created
    stamp = (first.path / RATINGS).stat().st_mtime_ns
    again = refresh_origin(tmp_path, CUTOFF, inputs())
    assert not again.created and again.path == first.path
    assert (first.path / RATINGS).stat().st_mtime_ns == stamp
    changed = refresh_origin(tmp_path, CUTOFF, inputs(ids={**IDS, "box_logs": {"2021": "c" * 64}}))
    assert changed.created and changed.artifact_id != first.artifact_id
    assert sorted(p.name for p in (tmp_path / CUTOFF.isoformat()).iterdir()) == sorted(
        [first.artifact_id, changed.artifact_id]
    )
    record = json.loads((first.path / MANIFEST).read_text(encoding="utf-8"))
    assert record["artifact_id"] == first.artifact_id and record["parents"] == PARENTS
    assert record["eligibility"]["cutoff"] == CUTOFF.isoformat()


def test_interrupted_publication_leaves_nothing(tmp_path: Path) -> None:
    def broken(stage: Path) -> dict[str, str]:
        (stage / RATINGS).write_text("partial", encoding="utf-8")
        raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError, match="interrupted"):
        publish(tmp_path, CUTOFF, "a" * 64, broken)
    assert list((tmp_path / CUTOFF.isoformat()).iterdir()) == []
    done = refresh_origin(tmp_path, CUTOFF, inputs())
    assert done.created


def test_inconsistent_existing_artifacts_and_out_of_scope_origins_are_refused(
    tmp_path: Path,
) -> None:
    done = refresh_origin(tmp_path, CUTOFF, inputs())
    (done.path / RATINGS).write_text("tampered", encoding="utf-8")
    with pytest.raises(RefreshError, match="do not match"):
        refresh_origin(tmp_path, CUTOFF, inputs())
    (done.path / MANIFEST).unlink()
    with pytest.raises(RefreshError, match="without a manifest"):
        refresh_origin(tmp_path, CUTOFF, inputs())
    with pytest.raises(RefreshError, match="outside the replay seasons"):
        refresh_origin(tmp_path, date(2022, 10, 1), inputs())
    with pytest.raises(RefreshError, match="outside the replay seasons"):
        refresh_origin(tmp_path, date(2025, 10, 1), replace(inputs(), seasons=(2025,)))
