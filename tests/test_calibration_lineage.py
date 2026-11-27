"""Chronological lineage of margin-calibration examples (#136)."""

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from bil.models.calibration_lineage import (
    PARENTS,
    Example,
    LineageError,
    Parent,
    check_example,
    fit_post_freeze,
    load_calibration,
    write_examples,
)
from bil.models.rapm.multiseason import _write_json

CUTOFF = date(2024, 7, 1)
FROZEN = Parent("ei:x", "run-x", "a" * 64, "sel-x", date(2023, 6, 30))
TEAM = Parent("team_rating:x", "run-t", "b" * 64, "sel-t", date(2023, 6, 30))
REGISTRY = {FROZEN.parent_id: FROZEN, TEAM.parent_id: TEAM}


def examples(seed: int = 5, days: int = 400) -> list[Example]:
    rng = np.random.default_rng(seed)
    out = []
    start = date(2023, 10, 24)
    for i in range(days):
        day = start + timedelta(days=i)
        raw = float(rng.normal(0, 5))
        margin = float(round(2 + 0.9 * raw + rng.normal(0, 12)))
        as_of = date(2023, 10, 1) if day < date(2024, 10, 1) else date(2024, 10, 1)
        for source, parent, value in (("ei", FROZEN, raw), ("team_rating", TEAM, raw * 1.1)):
            out.append(
                Example(source, f"g{i}", day, value, margin, parent.parent_id, as_of, "s", "v")
            )
    return out


def test_later_outcomes_cannot_change_an_earlier_calibration() -> None:
    base = fit_post_freeze(examples(), REGISTRY, CUTOFF)
    mutated = [
        replace(e, margin=-e.margin * 3, raw=e.raw + 40) if e.game_day >= CUTOFF else e
        for e in examples()
    ]
    later = fit_post_freeze(list(reversed(mutated)), REGISTRY, CUTOFF)
    assert later == base
    assert (
        base["sources"]["ei"]["examples"]
        == len([e for e in examples() if e.game_day < CUTOFF]) // 2
    )
    earlier = [replace(e, margin=e.margin + 1) if e.game_id == "g0" else e for e in examples()]
    assert fit_post_freeze(earlier, REGISTRY, CUTOFF)["examples_sha256"] != base["examples_sha256"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"parent_id": "ei:unregistered"}, "not registered"),
        ({"snapshot_as_of": date(2023, 6, 1)}, "not before its snapshot"),
        ({"snapshot_as_of": date(2023, 11, 2)}, "follows the game"),
        ({"game_day": CUTOFF}, "not final"),
    ],
)
def test_each_lineage_condition_is_enforced(change: dict[str, object], message: str) -> None:
    example = Example("ei", "g", date(2023, 11, 1), 1.0, 3.0, "ei:x", date(2023, 10, 1), "s", "v")
    check_example(example, REGISTRY, CUTOFF)
    with pytest.raises(LineageError, match=message):
        check_example(replace(example, **change), REGISTRY, CUTOFF)  # type: ignore[arg-type]


def _artifact(tmp_path: Path, registry: dict[str, Parent]) -> Path:
    directory = tmp_path / "calibration"
    directory.mkdir(parents=True)
    eligible = [e for e in examples() if e.game_day < CUTOFF]
    write_examples(directory / "examples.csv", eligible)
    _write_json(directory / "calibration.json", fit_post_freeze(eligible, registry, CUTOFF))
    return directory


def test_normal_loading_path_rejects_late_parents_and_tampering(tmp_path: Path) -> None:
    directory = _artifact(tmp_path, REGISTRY)
    loaded = load_calibration(directory, date(2024, 10, 1), REGISTRY)
    assert set(loaded["sources"]) == {"ei", "team_rating", "hca"}
    with pytest.raises(LineageError, match="follows the origin"):
        load_calibration(directory, date(2024, 6, 1), REGISTRY)

    # A parent whose selection read outcomes past its snapshots: the same artifact is refused
    # once the registry records when that selection actually froze.
    late = {**REGISTRY, "ei:x": replace(FROZEN, outcomes_through=date(2024, 6, 30))}
    with pytest.raises(LineageError, match="differs from its registration"):
        load_calibration(directory, date(2024, 10, 1), late)
    with pytest.raises(LineageError, match="not before its snapshot"):
        load_calibration(_artifact(tmp_path / "late", late), date(2024, 10, 1), late)
    # An honest artifact whose parents block was rewritten to match the late registry is
    # refused by the loader itself, through the example re-check.
    forged = json.loads((directory / "calibration.json").read_text(encoding="utf-8"))
    forged["parents"]["ei:x"]["outcomes_through"] = "2024-06-30"
    tampered = tmp_path / "forged"
    tampered.mkdir()
    (tampered / "examples.csv").write_bytes((directory / "examples.csv").read_bytes())
    _write_json(tampered / "calibration.json", forged)
    with pytest.raises(LineageError, match="not before its snapshot"):
        load_calibration(tampered, date(2024, 10, 1), late)
    # A dropped parents block, or a post-cutoff row added to the examples, is refused too.
    del forged["parents"]["ei:x"]
    _write_json(tampered / "calibration.json", forged)
    with pytest.raises(LineageError, match="recorded parents differ"):
        load_calibration(tampered, date(2024, 10, 1), REGISTRY)
    rows = (directory / "examples.csv").read_text(encoding="utf-8").splitlines()
    extra = rows[1].split(",")
    extra[2] = CUTOFF.isoformat()
    (tampered / "examples.csv").write_text("\n".join([*rows, ",".join(extra)]) + "\n")
    with pytest.raises(LineageError, match="not final by the fit cutoff"):
        load_calibration(tampered, date(2024, 10, 1), REGISTRY)

    text = (directory / "examples.csv").read_text(encoding="utf-8").splitlines()
    first = text[1].split(",")
    first[4] = str(float(first[4]) + 1)
    (directory / "examples.csv").write_text("\n".join([text[0], ",".join(first), *text[2:]]))
    with pytest.raises(LineageError, match="digest"):
        load_calibration(directory, date(2024, 10, 1), REGISTRY)


def test_frozen_39_examples_are_ineligible_under_the_registered_parents() -> None:
    # #39 fit on 2021–23 games scored with #35 snapshots selected on those seasons.
    example = Example(
        "ei",
        "0022100001",
        date(2021, 10, 19),
        1.0,
        5.0,
        "ei:issue-35-v1",
        date(2021, 10, 1),
        "d8b7",
        "v",
    )
    with pytest.raises(LineageError, match="not before its snapshot"):
        check_example(example, PARENTS, date(2023, 7, 1))
    post = replace(
        example,
        parent_id="ei:issue-36-v1",
        game_day=date(2023, 10, 25),
        snapshot_as_of=date(2023, 10, 1),
    )
    check_example(post, PARENTS, CUTOFF)
