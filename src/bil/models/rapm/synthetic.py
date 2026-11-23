"""Generate known player effects and report synthetic RAPM sensitivity."""

from __future__ import annotations

from collections.abc import Sequence
from math import sqrt
from random import Random

from bil.models.rapm.reference import Possession, RAPMFit, fit_rapm

INTERCEPT = 112.0
OFFENSE = dict(enumerate((-6, 5, -5, 4, -4, 3, -3, 2, -2, 1, -1, 6), start=1))
DEFENSE = dict(enumerate((5, -6, -1, 6, 2, -3, 3, -5, 1, -4, -2, 4), start=1))


def expected_rate(offense: tuple[int, ...], defense: tuple[int, ...]) -> float:
    """Return the synthetic scoring expectation in points per 100 possessions."""
    return (
        INTERCEPT
        + sum(OFFENSE[player] for player in offense)
        - sum(DEFENSE[player] for player in defense)
    )


def generate_possessions(
    size: int, *, seed: int, noisy: bool = False, paired: bool = False
) -> list[Possession]:
    """Draw ten different players, optionally keeping players 1 and 2 together."""
    lineup_rng = Random(seed)
    scoring_rng = Random(seed + 1)
    possessions: list[Possession] = []
    while len(possessions) < size:
        lineup = lineup_rng.sample(tuple(OFFENSE), 12)
        if paired and lineup.index(1) // 5 != lineup.index(2) // 5:
            continue
        offense, defense = tuple(lineup[:5]), tuple(lineup[5:10])
        points = expected_rate(offense, defense) / 100
        if noisy:
            points = float(sum(scoring_rng.random() < points / 3 for _ in range(3)))
        possessions.append(Possession(offense, defense, points))
    return possessions


def _effect_rmse(fit: RAPMFit) -> float:
    errors = [
        (estimate[player] - truth[player]) ** 2
        for estimate, truth in ((fit.offense, OFFENSE), (fit.defense, DEFENSE))
        for player in truth
    ]
    return sqrt(sum(errors) / len(errors))


def _rate_rmse(fit: RAPMFit, observations: Sequence[Possession]) -> float:
    errors = []
    for row in observations:
        prediction = (
            fit.intercept
            + sum(fit.offense[player] for player in row.offense)
            - sum(fit.defense[player] for player in row.defense)
        )
        errors.append((prediction - 100 * row.points) ** 2)
    return sqrt(sum(errors) / len(errors))


def main() -> None:
    recovery = fit_rapm(generate_possessions(800, seed=6014), ridge=1e-4)
    print(f"Noiseless full rotation effect RMSE: {_effect_rmse(recovery):.9f}")

    train = generate_possessions(4000, seed=6440, noisy=True)
    held_out = generate_possessions(1200, seed=6992)
    print("Training rows | ridge | effect RMSE | held-out expected-rate RMSE")
    for size in (48, 4000):
        baseline = sum(100 * row.points for row in train[:size]) / size
        baseline_fit = RAPMFit(baseline, dict.fromkeys(OFFENSE, 0.0), dict.fromkeys(DEFENSE, 0.0))
        print(f"{size} | intercept only | - | {_rate_rmse(baseline_fit, held_out):.3f}")
        for ridge in (0.01, 100.0, 1000.0):
            fit = fit_rapm(train[:size], ridge=ridge)
            print(f"{size} | {ridge:g} | {_effect_rmse(fit):.3f} | {_rate_rmse(fit, held_out):.3f}")

    paired = fit_rapm(generate_possessions(800, seed=6014, paired=True), ridge=1e-4)
    print(f"Paired noiseless effect RMSE: {_effect_rmse(paired):.3f}")
    print(f"Paired noiseless held-out rate RMSE: {_rate_rmse(paired, held_out):.3f}")
    print(f"Paired offense 1, 2: {paired.offense[1]:.3f}, {paired.offense[2]:.3f}")
    print(f"Paired defense 1, 2: {paired.defense[1]:.3f}, {paired.defense[2]:.3f}")


if __name__ == "__main__":
    main()
