"""Focused reference cases for the development-only lineup research runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rapm_lineup_exposure.py"
spec = importlib.util.spec_from_file_location("rapm_lineup_exposure", SCRIPT)
assert spec is not None and spec.loader is not None
study = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = study
spec.loader.exec_module(study)


def test_clock_overlap_and_zero_clock_fallback():
    with duckdb.connect() as con:
        con.execute("""
        CREATE TABLE event(game_id VARCHAR, stream_revision INTEGER, seq INTEGER,
                           elapsed_ms INTEGER, home_delta INTEGER, away_delta INTEGER);
        INSERT INTO event VALUES ('g',1,1,6000,0,0), ('g',1,2,10000,2,0),
          ('g',1,3,10000,0,0), ('g',1,4,10000,0,1);
        CREATE TABLE game_stream(game_id VARCHAR, revision INTEGER, official_game_revision INTEGER,
                                 complete BOOLEAN, quality VARCHAR);
        INSERT INTO game_stream VALUES ('g',1,1,true,'accepted');
        CREATE TABLE game(game_id VARCHAR, revision INTEGER, game_date DATE, home_team_id VARCHAR);
        INSERT INTO game VALUES ('g',1,'2022-11-01','h');
        CREATE TABLE possession_disposition AS
          SELECT 'g' AS game_id, 1 AS stream_revision, 'regular' AS season_type, 1 AS period,
                 'multiple_lineups' AS reason, 'accepted' AS pilot_status, 2 AS lineup_pairs,
                 * FROM (VALUES (1,1,3,'h','a',2),(2,3,5,'a','h',1))
          AS rows(possession_seq,start_seq,end_seq,offense_team_id,defense_team_id,control_points);
        CREATE TABLE lineup AS
          SELECT 'g' AS game_id, 1 AS stream_revision, * FROM (
            VALUES ('h0',[1,2,3,4,5]), ('h1',[1,2,3,4,6]), ('h2',[1,2,3,4,7]),
                   ('a0',[11,12,13,14,15])
          ) AS rows(lineup_id,player_ids);
        CREATE TABLE stint AS
          SELECT 'g' AS game_id, 1 AS stream_revision, 1 AS period, 'a0' AS away_lineup_id,
                 * FROM (VALUES (1,1,2,0,6000,'h0'), (2,2,3,6000,10000,'h1'),
                         (3,3,4,10000,10000,'h1'), (4,4,5,10000,10000,'h2'))
          AS rows(stint_seq,start_seq,end_seq,start_elapsed_ms,end_elapsed_ms,home_lineup_id);
        """)
        con.execute(SCRIPT.with_suffix(".sql").read_text())
        assert con.execute("""
            SELECT row_id, share, offense[5], defense[5]
            FROM pieces_with_weight ORDER BY row_id, stint_seq
        """).fetchall() == [(0, 0.6, 5, 15), (0, 0.4, 6, 15), (1, 0.5, 15, 6), (1, 0.5, 15, 7)]
        assert con.execute("""
            SELECT margin, elapsed_from, covered_ms, control_points FROM cohort ORDER BY row_id
        """).fetchall() == [(0, 0, 10000, 2), (-2, 10000, 0, 1)]


def test_fractional_players_merge_repeated_columns_and_preserve_role_exposure():
    players = tuple(range(1, 12))
    index = np.array([0, 0])
    shares = np.array([0.6, 0.4])
    offense = np.array([[1, 2, 3, 4, 5], [1, 2, 3, 4, 6]])
    defense = np.array([[7, 8, 9, 10, 11], [7, 8, 9, 10, 11]])
    matrix = study.fractional_rows(players, index, shares, offense, defense, 1)
    np.testing.assert_allclose(
        matrix.toarray()[0], [1, 1, 1, 1, 1, 0.6, 0.4, *([0] * 11), *([-1] * 5)]
    )
    with pytest.raises(AssertionError):
        study.fractional_rows(players, index, shares / 2, offense, defense, 1)


def test_non_development_seasons_are_rejected_before_opening_files(tmp_path):
    for forbidden in (2018, 2023, 2024, 2025):
        with pytest.raises(ValueError):
            study.load(tmp_path / "nonexistent", forbidden, 0)
