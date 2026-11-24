from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from bil.features.box import Appearance
from bil.models.rapm.multiseason import Rows
from bil.models.spm import (
    CANDIDATES,
    CODES,
    fit_candidate,
    fit_prior,
    signed_lineup_sum,
)
from bil.models.spm_build import Label, checked_logs, fit_models, freeze_fold, label_scores, opening
from bil.models.spm_evaluation import (
    ages_at,
    clustered_interval,
    court_scores,
    fit_court_baselines,
    predict_court,
)

FEATURE = CODES.index("fga_per_36")


def appearance(player, day, fga):
    return Appearance.from_record(
        {
            "game_id": "0022100001",
            "game_date": day,
            "player_id": player,
            "team_id": 100,
            "opp_team_id": 200,
            "min": 36,
            "fga": fga,
        }
    )


def court_rows(days):
    count = 2 * len(days)
    offense, defense = np.arange(1, 6), np.arange(6, 11)
    return Rows(
        season=np.full(count, days[0].year),
        playoff=np.zeros(count, dtype=bool),
        day=np.repeat([day.toordinal() for day in days], 2),
        game=np.repeat(np.arange(len(days)), 2),
        game_ids=tuple(f"game-{i}" for i in range(len(days))),
        team_game=np.arange(count),
        possession_seq=np.tile([1, 2], len(days)),
        period=np.ones(count, dtype=np.int64),
        y=np.tile([100.0, 210.0], len(days)),
        offense=np.tile([offense, defense], (len(days), 1)),
        defense=np.tile([defense, offense], (len(days), 1)),
        context=np.tile([[1.0, 0.0], [-1.0, 0.0]], (len(days), 1)),
        no_livedata=np.zeros(count, dtype=bool),
    )


def test_weighted_ridge_matches_direct_normal_equations():
    values = np.full((4, len(CODES)), np.nan)
    values[:, FEATURE] = [1.0, 4.0, 8.0, np.nan]
    weights = np.array([1.0, 2.0, 3.0, 4.0])
    labels = np.array([-1.0, 1.0, 4.0, 3.0])
    model = fit_prior(values, labels, weights, (FEATURE,))
    mu = (1 + 8 + 24) / 6
    imputed = np.array([1.0, 4.0, 8.0, mu])
    scale = np.sqrt(np.average((imputed - mu) ** 2, weights=weights))
    design = np.column_stack((np.ones(4), (imputed - mu) / scale))
    gram = design.T @ (weights[:, None] * design) + np.diag([0, 0.05 * weights.sum()])
    expected = np.linalg.solve(gram, design.T @ (weights * labels))
    assert model.mean == pytest.approx([mu])
    assert model.scale == pytest.approx([scale])
    assert np.r_[model.intercept, model.coefficients] == pytest.approx(expected)
    assert model.predict(values)[-1] == model.intercept


def test_constant_and_all_null_columns_contribute_zero():
    values = np.full((3, len(CODES)), np.nan)
    values[:, FEATURE] = 0.1
    models = fit_candidate(
        values,
        np.array([[1.0, 2.0], [4.0, 5.0], [2.0, 3.0]]),
        np.full((3, 2), 250.0),
        np.ones(3, dtype=bool),
        CANDIDATES["full"],
    )
    future = np.full((2, len(CODES)), 12.0)
    assert all(np.count_nonzero(model.coefficients) == 0 for model in models)
    for model in models:
        assert model.predict(future) == pytest.approx(np.full(2, model.intercept))


def test_reliability_uses_side_specific_exposure_and_one_sided_rule():
    x = np.full((2, len(CODES)), np.nan)
    y = np.array([[0.0, 0.0], [10.0, 10.0]])
    exposure = np.array([[250.0, 4000.0], [4000.0, 250.0]])
    support = np.array([True, False])
    for name, expected in (
        ("full", [8, 2]),
        ("full_unweighted", [5, 5]),
        ("full_one_sided", [20 / 3, 10 / 9]),
        ("zero", [0, 0]),
    ):
        models = fit_candidate(x, y, exposure, support, CANDIDATES[name])
        assert [model.intercept for model in models] == pytest.approx(expected)


def test_signed_lineup_uses_offense_and_subtracts_defense():
    priors = np.column_stack((np.arange(10), np.arange(10) + 20))
    offense, defense = signed_lineup_sum(priors, np.arange(5)[None], np.arange(5, 10)[None])
    assert offense == [10]
    assert defense == [-135]


def test_calendar_cutoff_and_same_day_box_and_outcome_poisoning():
    early = date(2021, 4, 1)
    days = [date(2022, 3, 1), date(2022, 3, 2)]
    label_data = {
        (2021, p): Label((float(p), float(11 - p)), (300, 500), False) for p in range(1, 11)
    }
    previous = [appearance(p, early, p) for p in range(1, 11)]
    models, _ = fit_models(label_data, [2021], {2021: previous}, days[0], CANDIDATES)
    prior = fit_court_baselines(court_rows([early, date(2021, 4, 2)]), days[0])
    rows = court_rows(days)
    actual = [appearance(1, days[0], 50), appearance(1, days[1], 50)]
    poisoned = [replace(actual[0], fga=500), replace(actual[1], fga=1000)]
    first = predict_court(rows, previous, actual, prior, models)
    changed = predict_court(replace(rows, y=rows.y * 200), previous, poisoned, prior, models)
    assert first.values[:2] == pytest.approx(changed.values[:2])
    assert not np.allclose(first.values[2:], changed.values[2:])
    assert first.dated[0].volume == pytest.approx(np.arange(1, 11))
    start = opening(2022, days[0], rows, previous + poisoned, models)
    assert start.volume == pytest.approx(np.arange(1, 11))
    with pytest.raises(ValueError, match="incomplete"):
        fit_models(label_data, [2021], {2021: previous + poisoned}, days[0], CANDIDATES)
    with pytest.raises(ValueError, match="strictly earlier"):
        fit_court_baselines(rows, days[0])
    court, weekly = court_scores(rows, first, {})
    assert court["games"] == 2
    assert court["represented_game_margins"] == 2
    assert court["age"]["unknown"]["possessions"] == 4
    assert weekly[:, 0].sum() == 4
    scores, players, _ = label_scores(
        start,
        {(2022, 1): label_data[(2021, 1)], (2022, 2): Label((1, 1), (249, 300), False)},
        {1: date(1999, 3, 2)},
    )
    assert players.tolist() == [1]
    assert scores["age"]["under_24"]["players"] == 1


def test_age_and_cluster_pairing():
    assert ages_at(
        np.array([3, 4, 5, 6]),
        date(2022, 10, 4),
        {3: date(1998, 10, 4), 4: date(1998, 10, 5), 6: date(2022, 10, 3)},
    ) == pytest.approx([24, 23, np.nan, np.nan], nan_ok=True)
    block = np.array([[10, 1, 1], [1, 10, 10]])
    assert clustered_interval([block, block], 0, 1, rmse=False) == [0, 0]


def test_unregistered_season_refuses_before_opening_raw_directory(tmp_path):
    with pytest.raises(ValueError, match="outside the authorized scope"):
        checked_logs(tmp_path / "does-not-exist", 2025)


def test_private_prediction_artifacts_are_outcome_free(tmp_path):
    first = date(2021, 4, 1)
    day = date(2022, 3, 1)
    history = [appearance(p, first, p) for p in range(1, 11)]
    labels = {(2021, p): Label((float(p), float(11 - p)), (300, 500), False) for p in range(1, 11)}
    models, _ = fit_models(labels, [2021], {2021: history}, day, CANDIDATES)
    prior = fit_court_baselines(court_rows([first]), day)
    rows = court_rows([day])
    court = predict_court(rows, history, [], prior, models)
    start = opening(2022, day, rows, history, models)
    target = tmp_path / "predictions"
    freeze_fold(target, start, rows, court, {"fit_id": "synthetic"})
    with np.load(target / "court_predictions.npz", allow_pickle=False) as artifact:
        assert artifact["points_per_100"] == pytest.approx(court.values)
        assert artifact["fit_id"] == "synthetic"
        assert "y" not in artifact.files
    with np.load(target / "dated_priors.npz", allow_pickle=False) as artifact:
        assert artifact["priors"].shape == (10, 2, 2)
        assert artifact["evidence_tier"] == "retrospective_capture_bound"
