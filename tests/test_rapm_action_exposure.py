from pathlib import Path

import duckdb
import pytest


def test_action_and_clock_shares_keep_zero_clock_and_ambiguous_cases_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from rapm_action_exposure import ACTION_EXPOSURE

    with duckdb.connect() as con:
        con.execute("""
            CREATE TABLE cohort AS
            SELECT row_id, 'g' AS game_id, 1 AS stream_revision, start_seq, end_seq,
                   'h' AS offense_team_id, true AS multi
            FROM (VALUES (0,1,3),(1,3,5),(2,5,7),(3,7,8),(4,8,9)) x(row_id,start_seq,end_seq);
            CREATE TABLE segments AS SELECT * FROM (VALUES
              (0,1,1000),(0,2,0),
              (1,3,800),(1,4,200),
              (2,5,0),(2,6,0),
              (3,7,0),(4,8,0)
            ) x(row_id,stint_seq,ms);
            CREATE TABLE stint AS
            SELECT 'g' AS game_id, 1 AS stream_revision, range AS stint_seq,
                   range AS start_seq, range+1 AS end_seq FROM range(1,9);
            CREATE TABLE event AS
            SELECT 'g' AS game_id, 1 AS stream_revision, 1 AS period, * FROM (VALUES
              (1,1,'free_throw','h'), (2,2,'shot','h'),
              (3,3,'turnover','a'), (4,3,'free_throw','h'),
              (5,4,'free_throw','h'), (6,4,'substitution','h'),
              (7,5,'shot','a'), (8,6,'shot',NULL)
            ) x(seq,elapsed_ms,kind,team_id);
        """)
        con.execute(ACTION_EXPOSURE)
        rows = con.execute("""
            SELECT row_id, stint_seq, disposition, share
            FROM action_pieces ORDER BY 1,2
        """).fetchall()
    assert rows == [
        (0, 1, "action", 0.0),
        (0, 2, "action", 1.0),
        (1, 3, "clock", 0.8),
        (1, 4, "clock", 0.2),
        (2, 5, "unsupported_zero_clock", 0.0),
        (2, 6, "unsupported_zero_clock", 0.0),
        (3, 7, "control_conflict", 0.0),
        (4, 8, "control_unknown", 0.0),
    ]


def test_fractional_design_and_sparse_fit_match_dense_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import numpy as np
    from rapm_lineup_exposure import fractional_rows

    from bil.models.rapm.reference import RAPMDesign, _solve_rapm

    players = tuple(range(1, 13))
    matrix = fractional_rows(
        players,
        np.array([0, 0, 1, 2, 2]),
        np.array([0.25, 0.75, 1.0, 0.4, 0.6]),
        np.array(
            [
                [1, 2, 3, 4, 5],
                [1, 2, 3, 4, 6],
                [1, 2, 3, 4, 5],
                [7, 8, 9, 10, 11],
                [7, 8, 9, 10, 12],
            ]
        ),
        np.array(
            [
                [7, 8, 9, 10, 11],
                [7, 8, 9, 10, 11],
                [7, 8, 9, 10, 12],
                [1, 2, 3, 4, 6],
                [1, 2, 3, 4, 5],
            ]
        ),
        3,
    )
    dense = matrix.toarray()
    assert dense[0, 5] == 0.25
    assert dense[0, 6] == 0.75
    assert dense[0, 1 + len(players) + 6] == -1.0
    target = np.array([101.0, 89.0, 112.0])
    fit = _solve_rapm(RAPMDesign(players, matrix, target, np.ones(3)), 4, 8)
    coef = np.array(
        [fit.intercept, *[fit.offense[p] for p in players], *[fit.defense[p] for p in players]]
    )
    penalty = np.diag([0.0, *[4.0] * len(players), *[8.0] * len(players)])
    expected = np.linalg.solve(dense.T @ dense + penalty, dense.T @ target)
    np.testing.assert_allclose(coef, expected, atol=1e-7, rtol=0)


def test_score_credit_precedes_shooting_substitution_without_adding_action_weight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from rapm_action_exposure import ACTION_EXPOSURE
    from rapm_lineup_exposure import LEDGER_AUDIT

    with duckdb.connect() as con:
        con.execute("""
            CREATE TABLE cohort AS SELECT 0 AS row_id, 'g' AS game_id, 1 AS stream_revision,
              1 AS start_seq, 5 AS end_seq, 'h' AS offense_team_id, true AS multi;
            CREATE TABLE segments AS SELECT 0 AS row_id, * FROM (VALUES (1,0),(2,0)) x(stint_seq,ms);
            CREATE TABLE stint AS SELECT 'g' AS game_id, 1 AS stream_revision, * FROM (VALUES
              (1,1,2),(2,2,5)
            ) x(stint_seq,start_seq,end_seq);
            CREATE TABLE event AS SELECT 'g' AS game_id, 1 AS stream_revision, 1 AS period,
              1200 AS elapsed_ms, * FROM (VALUES
                (1,'foul','a'),(2,'substitution','h'),(3,'free_throw','h'),(4,'shot','h')
              ) x(seq,kind,team_id);
            CREATE TABLE score_allocation AS SELECT 'g' AS game_id, 1 AS stream_revision,
              1 AS possession_seq, 'control_possession' AS possession_reason, 'h' AS scoring_team_id,
              * FROM (VALUES (3,1,1),(4,2,2)) x(seq,points_delta,credited_stint_seq);
            CREATE TABLE possession_disposition AS SELECT 'g' AS game_id, 1 AS stream_revision,
              1 AS possession_seq, 'multiple_lineups' AS reason, 3 AS control_points,
              'h' AS offense_team_id;
        """)
        con.execute(ACTION_EXPOSURE)
        assert con.execute(LEDGER_AUDIT).fetchall() == [(0,)]
        assert con.execute(
            "SELECT stint_seq, share FROM action_pieces ORDER BY stint_seq"
        ).fetchall() == [(1, 0.0), (2, 1.0)]
        assert con.execute(
            "SELECT credited_stint_seq FROM score_allocation WHERE seq = 3"
        ).fetchall() == [(1,)]
