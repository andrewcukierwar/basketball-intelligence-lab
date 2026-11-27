"""Chronological, versioned Estimated Skills bundles and their consumer checks (#125)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest
from test_skill_decay import _appearance

from bil.features.box import FEATURE_CODES, Appearance
from bil.features.skill_bundle import (
    SkillBundle,
    SkillLineageError,
    bundle_values,
    check_bundle,
    fit_bundle,
)
from bil.features.skill_decay import DESettings
from bil.features.skill_snapshot import SkillParams, skill_snapshot
from bil.models.spm import completed_history, feature_matrix

FAST = DESettings(popsize=5, maxiter=4, polish=False)


def seasons(first: int = 2018, last: int = 2021, seed: int = 3) -> list[Appearance]:
    """Four teams of three players per season; player 32 debuts in the second season."""
    rng = np.random.default_rng(seed)
    rows: list[Appearance] = []
    for year in range(first, last + 1):
        number = 0
        day = date(year, 10, 20)
        while day < date(year + 1, 4, 10):
            for team, opp in (("1", "2"), ("3", "4")):
                number += 1
                game = f"002{year % 100:02d}{number:05d}"
                for side, other in ((team, opp), (opp, team)):
                    for slot in range(3):
                        player = f"{side}{slot}"
                        if player == "32" and year == first:
                            continue
                        rows.append(_appearance(game, day, player, side, other, rng))
            day += timedelta(days=9)
    return rows


@pytest.fixture(scope="module")
def bundle() -> SkillBundle:
    return fit_bundle(seasons(), 2021, FAST)


def test_bundle_reads_only_earlier_seasons_and_records_its_lineage(bundle: SkillBundle) -> None:
    assert bundle.history_seasons == (2018, 2019, 2020)
    assert bundle.outcomes_through < date(2021, 7, 1)
    assert bundle.fit_cutoff == bundle.outcomes_through + timedelta(days=1)
    assert set(bundle.params) == set(FEATURE_CODES)
    for code, chosen in bundle.selection.items():
        assert chosen["chosen_clock"] == bundle.params[code].clock
        assert chosen["validation_loss"][chosen["chosen_clock"]] == min(
            chosen["validation_loss"].values()
        )
    # Scoring-season games cannot move the fit: the bundle is identical without them.
    again = fit_bundle([r for r in seasons() if r.game_id[3:5] != "21"], 2021, FAST)
    assert again.record() == bundle.record()
    with pytest.raises(SkillLineageError, match="covers"):
        fit_bundle([r for r in seasons() if r.game_id[3:5] != "18"], 2021, FAST)


def test_late_fitted_parent_is_refused_with_identical_pre_origin_rows(bundle: SkillBundle) -> None:
    rows = seasons()
    origin = date(2021, 10, 1)
    players = [10, 11, 32, 99]
    eligible = bundle_values(rows, bundle, origin, players)
    # Same pre-origin game rows, but a bundle whose fit read outcomes up to the origin itself.
    late = replace(
        bundle, outcomes_through=origin, fit_cutoff=origin + timedelta(days=1), fit_id="x"
    )
    with pytest.raises(SkillLineageError, match="not before the origin"):
        bundle_values(rows, late, origin, players)
    # An honest bundle used at an origin inside its own fit seasons is refused too.
    with pytest.raises(SkillLineageError, match="not before the origin"):
        bundle_values(rows, bundle, date(2021, 3, 1), players)
    assert np.isnan(eligible.values[3]).all() and not eligible.has_history[3]
    assert eligible.has_history[:3].all()


def test_later_games_cannot_change_an_earlier_feature(bundle: SkillBundle) -> None:
    rows = seasons()
    origin = date(2021, 12, 1)
    players = [10, 20, 32]
    before = bundle_values([r for r in rows if r.game_date < origin], bundle, origin, players)
    after = bundle_values(rows, bundle, origin, players)
    np.testing.assert_array_equal(before.values, after.values)
    assert after.audit["skill_box_last"] < origin.isoformat()


def test_tampered_or_misused_bundles_are_refused(bundle: SkillBundle) -> None:
    origin = date(2021, 10, 1)
    check_bundle(bundle, origin, 2021)
    with pytest.raises(SkillLineageError, match="scoring season"):
        check_bundle(bundle, origin, 2022)
    edited = {**bundle.params, "fg3_pct": SkillParams("day", 10.0, 1.0)}
    with pytest.raises(SkillLineageError, match="recorded contents"):
        check_bundle(replace(bundle, params=edited), origin, 2021)
    with pytest.raises(SkillLineageError, match="version"):
        check_bundle(replace(bundle, version="other"), origin, 2021)
    with pytest.raises(SkillLineageError, match="fit cutoff"):
        check_bundle(replace(bundle, fit_cutoff=bundle.outcomes_through), origin, 2021)


def test_skill_estimates_share_the_spm_feature_units() -> None:
    """With no decay and no shrinkage the skill estimate is the v1 raw box rate."""
    rows = seasons(2020, 2021)
    cutoff = date(2021, 2, 1)
    flat = dict.fromkeys(FEATURE_CODES, SkillParams("day", 1e12, 0.0))
    snapshot = skill_snapshot(rows, flat, cutoff)
    players = sorted({int(r.player_id) for r in rows if r.game_date < cutoff})
    raw, _ = feature_matrix(completed_history(rows, cutoff), players)
    column = {code: i for i, code in enumerate(FEATURE_CODES)}
    compared = 0
    for row in snapshot:
        if row.discounted_exposure <= 0:
            continue
        expected = raw[players.index(int(row.player_id)), column[row.feature_code]]
        assert row.estimate == pytest.approx(expected, rel=1e-9)
        compared += 1
    assert compared > 100
