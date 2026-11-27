"""Chronological calibration for the Skills-trained SPM."""

from dataclasses import replace
from datetime import date, timedelta

import pytest
from test_skill_bundle import FAST, seasons

from bil.features.skill_bundle import SkillLineageError, fit_bundle
from bil.features.skill_history import season_start_year
from bil.models.spm_build import Label
from bil.models.spm_skills import fit_origin


def test_skill_calibration_preserves_season_cutoff_and_joint_exposure() -> None:
    rows = seasons()
    logs = {
        y: [row for row in rows if season_start_year(row.game_id) == y] for y in range(2018, 2022)
    }
    bundle = fit_bundle(rows, 2021, FAST, min_rows=100)
    origin = {
        "cutoff": "2022-06-30",
        "seasons": [2021],
        "input_digest": "target",
        "label_digests": {},
    }
    end = date(2022, 4, 10)
    calendar = {2021: (date(2021, 10, 20), end)}
    labels = {
        (2021, 10): Label((1.0, 2.0), (250, 300), False),
        (2021, 11): Label((1.0, 2.0), (249, 900), True),
        (2021, 99): Label((1.0, 2.0), (500, 500), True),
    }
    pins = {"2021": {"snapshot_sha256": "box"}}
    _, fit = fit_origin(labels, origin, calendar, logs, {2021: bundle}, pins)
    coverage = fit["coverage"]["2021"]
    assert coverage["joined_training_rows"] == 1
    assert coverage["labels_below_minimum"] == 1
    assert coverage["target_only"] == 1
    assert coverage["one_sided_training_rows"] == 1
    assert coverage["feature_cutoff"] == "2022-04-11"
    assert coverage["skill_bundle"] == bundle.fit_id

    late_box = replace(logs[2021][0], game_date=end + timedelta(days=1))
    with_late_box = {**logs, 2021: [*logs[2021], late_box]}
    _, again = fit_origin(labels, origin, calendar, with_late_box, {2021: bundle}, pins)
    assert again == fit

    with pytest.raises(ValueError, match="follow the fit origin"):
        fit_origin(labels, {**origin, "cutoff": "2022-04-10"}, calendar, logs, {2021: bundle}, pins)
    late = replace(
        bundle, outcomes_through=end + timedelta(days=1), fit_cutoff=end + timedelta(days=2)
    )
    with pytest.raises(SkillLineageError, match="not before the origin"):
        fit_origin(labels, origin, calendar, logs, {2021: late}, pins)
