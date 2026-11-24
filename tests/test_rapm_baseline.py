"""Splitting, scoring, exclusion and selection checks for the zero-prior baseline."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

from bil.models.rapm.baseline import (  # noqa: E402
    PINNED_DIGESTS,
    Observation,
    bootstrap_delta,
    concat,
    estimate_shift,
    exclude_games,
    exposure,
    fit_observations,
    league_mean,
    score,
    select_penalty,
    split_fold,
    split_halves,
    summarize,
    verify_pins,
)
from bil.models.rapm.synthetic import generate_possessions  # noqa: E402

START = date(2023, 1, 1)
PER_GAME = 12


def observations(games=40, seed=5, noisy=True):
    rows = generate_possessions(games * PER_GAME, seed=seed, noisy=noisy)
    out = []
    for i, row in enumerate(rows):
        game = i // PER_GAME
        played = START + timedelta(days=game // 2)  # two games share each date
        out.append(
            Observation(f"g{game:03d}", f"t{game % 2}", "regular", replace(row, played_date=played))
        )
    return out


def test_split_is_strict_chronological_and_game_grouped():
    rows = observations()
    cutoff, end = START + timedelta(days=8), START + timedelta(days=14)
    fit, scored = split_fold(rows, cutoff, end)
    assert fit and scored
    assert max(o.possession.played_date for o in fit) < cutoff
    assert all(cutoff <= o.possession.played_date < end for o in scored)
    assert {o.game_id for o in fit}.isdisjoint(o.game_id for o in scored)
    # Rows from the cutoff date itself are scored, never fitted; rows past the block are dropped.
    assert any(o.possession.played_date == cutoff for o in scored)
    assert len(fit) + len(scored) < len(rows)
    _, tail = split_fold(rows, cutoff, None)
    assert max(o.possession.played_date for o in tail) >= end


def test_game_spanning_the_cutoff_is_rejected():
    rows = observations()
    cutoff = START + timedelta(days=8)
    late = next(o for o in rows if o.possession.played_date >= cutoff)
    early = replace(
        late, possession=replace(late.possession, played_date=cutoff - timedelta(days=1))
    )
    with pytest.raises(ValueError, match="both"):
        split_fold([*rows, early], cutoff, None)


def test_fit_does_not_depend_on_scored_outcomes():
    rows = observations()
    cutoff = START + timedelta(days=10)
    fit, scored = split_fold(rows, cutoff, None)
    first, _ = fit_observations(fit, 500.0)
    changed = [replace(o, possession=replace(o.possession, points=3.0)) for o in scored]
    fit_again, scored_again = split_fold([*fit, *changed], cutoff, None)
    second, _ = fit_observations(fit_again, 500.0)
    assert first.offense == second.offense and first.defense == second.defense
    assert scored_again == changed


def test_scoring_uses_zero_effect_for_unseen_players_and_reports_them():
    rows = observations()
    fit_rows = [o for o in rows if 1 not in o.possession.offense + o.possession.defense]
    fit, _ = fit_observations(fit_rows, 500.0)
    held = [o for o in rows if 1 in o.possession.offense + o.possession.defense][:20]
    scored = score(fit, league_mean(fit_rows), held)
    assert scored.unseen.all()
    expected = [
        fit.intercept
        + sum(fit.offense.get(p, 0.0) for p in o.possession.offense)
        - sum(fit.defense.get(p, 0.0) for p in o.possession.defense)
        for o in held
    ]
    np.testing.assert_allclose(scored.model, expected)
    np.testing.assert_allclose(scored.league, league_mean(fit_rows))


def test_model_beats_league_average_on_held_out_signal():
    rows = observations(games=120, seed=11, noisy=False)
    fit_rows, scored_rows = split_fold(rows, START + timedelta(days=40), None)
    fit, _ = fit_observations(fit_rows, 250.0)
    summary = summarize(score(fit, league_mean(fit_rows), scored_rows), resamples=200)
    assert summary["delta_vs_league"]["model"] < 0
    assert summary["delta_vs_league"]["model_ci95"][1] < 0
    assert summary["mse"]["model"] < summary["mse"]["league"]


def test_exclusion_removes_whole_games_only():
    rows = observations()
    kept = exclude_games(rows, {"g001", "g002"})
    assert {o.game_id for o in rows} - {o.game_id for o in kept} == {"g001", "g002"}
    assert len(kept) == len(rows) - 2 * PER_GAME


def test_penalty_selection_extends_a_boundary_minimum():
    # Parabola in log2(ridge) with its minimum at 125, below the 250 edge of the grid.
    def cost(ridge: float) -> float:
        return float((np.log2(ridge) - np.log2(125.0)) ** 2)

    chosen, scores = select_penalty(cost, (250.0, 500.0, 1000.0))
    assert chosen == 125.0
    assert min(scores) == 62.5  # one more value tried to confirm an interior minimum
    interior, _ = select_penalty(cost, (125.0, 250.0, 500.0))
    assert interior in {125.0, 62.5}


def test_bootstrap_is_deterministic_and_clustered():
    game = np.repeat(np.arange(10), 5)
    delta = np.repeat(np.linspace(-3, -1, 10), 5)
    low, high = bootstrap_delta(game, delta, resamples=500, seed=1)
    assert (low, high) == bootstrap_delta(game, delta, resamples=500, seed=1)
    assert low <= delta.mean() <= high < 0


def test_concat_keeps_game_indices_distinct():
    rows = observations()
    fit, _ = fit_observations(rows, 500.0)
    a = score(fit, 100.0, rows[:24])
    b = score(fit, 100.0, rows[24:48])
    pooled = concat([a, b])
    assert pooled.game.max() + 1 == a.game.max() + b.game.max() + 2
    assert pooled.y.size == 48


def test_halves_are_disjoint_and_exposure_counts_roles():
    rows = observations()
    first, second = split_halves(rows)
    assert {o.game_id for o in first}.isdisjoint(o.game_id for o in second)
    assert len(first) + len(second) == len(rows)
    table = exposure(rows)
    assert sum(v[0] for v in table.values()) == 5 * len(rows)
    assert sum(v[1] for v in table.values()) == 5 * len(rows)


def test_identical_fits_have_no_shift():
    fit, info = fit_observations(observations(), 500.0)
    shift = estimate_shift(fit, fit)
    assert shift["total"]["rms_shift"] == 0 and shift["total"]["correlation"] == pytest.approx(1)
    assert info["stop"] in {0, 1, 2, 4, 5} and info["iterations"] > 0


def test_pin_verification_rejects_a_changed_row_set(tmp_path: Path):
    for name in PINNED_DIGESTS:
        (tmp_path / name).write_text("{}")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_pins(tmp_path)


def test_later_row_set_is_pinned_by_manifest_digest(tmp_path: Path):
    import hashlib
    import json

    from bil.models.rapm.baseline import EVIDENCE_TIER, pin_from_manifest

    names = [n for n in PINNED_DIGESTS if n != "manifest.json"]
    for name in names:
        (tmp_path / name).write_text(name)
    listed = [{"filename": n, "sha256": hashlib.sha256(n.encode()).hexdigest()} for n in names]
    manifest = {"build_id": "b" * 64, "evidence_tier": EVIDENCE_TIER, "output_artifacts": listed}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    pin = pin_from_manifest(tmp_path, hashlib.sha256(path.read_bytes()).hexdigest())
    verify_pins(tmp_path, pin)
    with pytest.raises(ValueError, match="SHA-256"):
        verify_pins(tmp_path)
    with pytest.raises(ValueError, match="frozen"):
        pin_from_manifest(tmp_path, "0" * 64)
