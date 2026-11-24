"""Integration cases from the pinned private 2022–23 snapshot, using real pbpstats."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
pytest.importorskip("pbpstats")

from bil.data.pilot import build_pilot  # noqa: E402
from bil.data.pilot_check import check_build  # noqa: E402

STARTER_SEARCH_GAME = "0022200772"
V3_PRIMARY_GAME = "0022201161"


@pytest.fixture(scope="module")
def archived_build(tmp_path_factory: pytest.TempPathFactory) -> Path:
    location = os.environ.get("BIL_PILOT_SNAPSHOT")
    if location is None:
        pytest.skip("Set BIL_PILOT_SNAPSHOT to a local pinned issue-5-v2 snapshot")
    snapshot = Path(location)
    output = tmp_path_factory.mktemp("archived-pilot") / "build"
    build_pilot(snapshot, output, "0" * 40, {STARTER_SEARCH_GAME, V3_PRIMARY_GAME})
    assert not any(check_build(output, snapshot).values())
    return output


@pytest.mark.parametrize(
    ("game_id", "stratum", "event_count", "counted_possessions"),
    [
        (STARTER_SEARCH_GAME, "inferred_starters", 398, 195),
        (V3_PRIMARY_GAME, "v3_primary_order", 414, 194),
    ],
    ids=["starter-search", "v3-primary-retry"],
)
def test_offline_archived_reconstruction(
    archived_build: Path,
    game_id: str,
    stratum: str,
    event_count: int,
    counted_possessions: int,
) -> None:
    with duckdb.connect() as connection:
        review = connection.execute(
            """
            select accepted, v3_periods_reconciled, list_contains(strata, ?)
            from read_parquet(?) where game_id = ?
            """,
            [stratum, str(archived_build / "game_review.parquet"), game_id],
        ).fetchone()
        counts = connection.execute(
            """
            select event_count, (
                select count(*) from read_parquet(?) p
                where p.game_id = s.game_id and p.status = 'accepted'
            )
            from read_parquet(?) s where game_id = ?
            """,
            [
                str(archived_build / "possession.parquet"),
                str(archived_build / "game_stream.parquet"),
                game_id,
            ],
        ).fetchone()
    assert review == (True, 4, True)
    assert counts == (event_count, counted_possessions)
