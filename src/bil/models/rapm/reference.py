"""Sparse, possession-level reference verified on synthetic lineups."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_matrix  # type: ignore[import-untyped]
from scipy.sparse.linalg import LinearOperator, lsqr  # type: ignore[import-untyped]

_LINEUP_SIZE = 5
_ROW_WIDTH = 1 + 2 * _LINEUP_SIZE
_CONVERGED = {0, 1, 2, 4, 5}


@dataclass(frozen=True, slots=True)
class Possession:
    """One synthetic possession, with optional weight and fractional expected points."""

    offense: tuple[int, ...]
    defense: tuple[int, ...]
    points: float
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class RAPMDesign:
    """CSR columns for intercept, sorted offensive IDs, then the same defensive IDs."""

    player_ids: tuple[int, ...]
    matrix: csr_matrix
    response: NDArray[np.float64]
    weights: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class RAPMFit:
    """Points per 100 possessions, with positive defensive effects preventing points."""

    intercept: float
    offense: dict[int, float]
    defense: dict[int, float]


def build_design(possessions: Sequence[Possession]) -> RAPMDesign:
    """Build one intercept, five +1 offensive and five -1 defensive entries per row."""
    if not possessions:
        raise ValueError("at least one possession is required")

    player_ids: set[int] = set()
    response = np.empty(len(possessions), dtype=np.float64)
    weights = np.empty(len(possessions), dtype=np.float64)
    for row, possession in enumerate(possessions):
        players = set(possession.offense + possession.defense)
        if (
            len(possession.offense) != _LINEUP_SIZE
            or len(possession.defense) != _LINEUP_SIZE
            or len(players) != 2 * _LINEUP_SIZE
        ):
            raise ValueError(f"possession {row} requires five distinct players on each side")
        if any(type(player) is not int or player <= 0 for player in players):
            raise ValueError(f"possession {row} player IDs must be positive integers")
        points_per_100 = 100.0 * possession.points
        if not isfinite(points_per_100) or points_per_100 < 0:
            raise ValueError(f"possession {row} points must be finite, nonnegative and scalable")
        if not isfinite(possession.weight) or possession.weight <= 0:
            raise ValueError(f"possession {row} weight must be positive and finite")
        player_ids.update(players)
        response[row] = points_per_100
        weights[row] = possession.weight

    ids = tuple(sorted(player_ids))
    column = {player: index for index, player in enumerate(ids, start=1)}
    indices = np.zeros((len(possessions), _ROW_WIDTH), dtype=np.int64)
    for row, possession in enumerate(possessions):
        indices[row, 1 : 1 + _LINEUP_SIZE] = [column[player] for player in possession.offense]
        indices[row, 1 + _LINEUP_SIZE :] = [
            len(ids) + column[player] for player in possession.defense
        ]
    offsets = np.arange(0, _ROW_WIDTH * (len(possessions) + 1), _ROW_WIDTH)
    signs = np.tile([1.0] * (1 + _LINEUP_SIZE) + [-1.0] * _LINEUP_SIZE, len(possessions))
    matrix = csr_matrix(
        (signs, indices.ravel(), offsets), shape=(len(possessions), 1 + 2 * len(ids))
    )
    matrix.sort_indices()
    return RAPMDesign(ids, matrix, response, weights)


def fit_rapm(possessions: Sequence[Possession], *, ridge: float) -> RAPMFit:
    """Fit weighted zero-prior ridge with an unpenalized intercept and centered player blocks."""
    if not isfinite(ridge) or ridge <= 0:
        raise ValueError("ridge must be positive and finite")
    return _solve_rapm(build_design(possessions), ridge, ridge)


def fit_prior_rapm(
    possessions: Sequence[Possession],
    *,
    offense_ridge: float,
    defense_ridge: float,
    offense_prior: Mapping[int, float] | None = None,
    defense_prior: Mapping[int, float] | None = None,
) -> RAPMFit:
    """Fit separate role priors in points per 100 possessions with positive defense preventing points.

    Missing prior entries use zero. Players absent from all input lineups have no output
    coefficient. A player appearing in only one role retains the supplied prior in the other.
    """
    for role, ridge in (("offense", offense_ridge), ("defense", defense_ridge)):
        if not isfinite(ridge) or ridge <= 0:
            raise ValueError(f"{role}_ridge must be positive and finite")
    design = build_design(possessions)
    prior = np.concatenate(
        [_align_prior(values, design.player_ids) for values in (offense_prior, defense_prior)]
    )
    return _solve_rapm(design, offense_ridge, defense_ridge, prior if np.any(prior) else None)


def _align_prior(
    values: Mapping[int, float] | None, player_ids: tuple[int, ...]
) -> NDArray[np.float64]:
    values = values if values is not None else {}
    for player, effect in values.items():
        if type(player) is not int or player <= 0:
            raise ValueError("prior player IDs must be positive integers")
        try:
            finite = isfinite(effect)
        except (OverflowError, TypeError) as exc:
            raise ValueError(f"prior for player {player} must be finite") from exc
        if not finite:
            raise ValueError(f"prior for player {player} must be finite")
    return np.array([values.get(player, 0.0) for player in player_ids], dtype=np.float64)


def _solve_rapm(
    design: RAPMDesign,
    offense_ridge: float,
    defense_ridge: float,
    prior: NDArray[np.float64] | None = None,
) -> RAPMFit:
    row_count = len(design.response)
    player_count = len(design.player_ids)
    player_columns = 2 * player_count
    root_weights = np.sqrt(design.weights)
    # Project out the free intercept without materializing dense centered player columns.
    max_root_weight = float(root_weights.max())
    intercept_direction = root_weights / max_root_weight
    intercept_direction /= np.linalg.norm(intercept_direction)
    # Scale each role's columns when its penalty would otherwise dominate the operator.
    # Equal penalties recover the shared scale and coordinates of the zero-prior fit.
    root_penalties = np.sqrt([offense_ridge, defense_ridge])
    role_scales = np.maximum(max_root_weight, root_penalties)
    system_scale = float(role_scales.min())
    column_scales = np.repeat(system_scale / role_scales, player_count)
    scaled_penalties = np.repeat(root_penalties / role_scales, player_count)
    scaled_weights = root_weights / system_scale
    players = design.matrix[:, 1:]
    used = np.bincount(players.indices, minlength=player_columns) > 0
    offense_used = used[:player_count]
    defense_used = used[player_count:]
    weighted_players = players.multiply(scaled_weights[:, None]).tocsr()
    if offense_ridge != defense_ridge:
        weighted_players = weighted_players.multiply(column_scales).tocsr()

    def project(values: NDArray[np.float64]) -> NDArray[np.float64]:
        return values - intercept_direction * (intercept_direction @ values)

    def matvec(coefficients: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.concatenate(
            (project(weighted_players @ coefficients), scaled_penalties * coefficients)
        )

    def rmatvec(values: NDArray[np.float64]) -> NDArray[np.float64]:
        projected: NDArray[np.float64] = weighted_players.T @ project(values[:row_count])
        return projected + scaled_penalties * values[row_count:]

    system = LinearOperator(
        (row_count + player_columns, player_columns),
        matvec=matvec,
        rmatvec=rmatvec,
        dtype=np.float64,
    )
    response_scale = float(np.max(design.response))
    # A common offset on all observed role coefficients contributes 5a - 5a = 0, even
    # if the two sets of observed players differ. Keep that offset out of response scaling.
    active_prior = prior[used] if prior is not None else None
    normalized_prior = None
    if active_prior is not None and np.any(active_prior != active_prior[0]):
        response_scale = max(response_scale, float(np.max(np.abs(active_prior))))
        normalized_prior = np.zeros(player_columns)
        normalized_prior[used] = active_prior / response_scale
    response_scale = response_scale or 1.0
    shifted_response = design.response / response_scale
    prior_intercept_shift = 0.0
    target_scale = 1.0
    if normalized_prior is not None:
        # The two role constants affect only the intercept. Remove them before projecting
        # the target so a large constant prior cannot mask variation in the observed rates.
        role_levels = normalized_prior[
            [int(np.argmax(offense_used)), player_count + int(np.argmax(defense_used))]
        ]
        shifted_response -= players @ (normalized_prior - np.repeat(role_levels, player_count))
        prior_intercept_shift = _LINEUP_SIZE * float(role_levels[0] - role_levels[1])
        target_scale = float(np.max(np.abs(shifted_response))) or 1.0
    target = np.concatenate(
        (project(scaled_weights * (shifted_response / target_scale)), np.zeros(player_columns))
    )
    solution, stop, *_ = lsqr(system, target, atol=1e-12, btol=1e-12)
    if stop not in _CONVERGED or not np.all(np.isfinite(solution)):
        raise RuntimeError(f"sparse RAPM solve failed to converge (LSQR stop {stop})")
    with np.errstate(over="ignore", invalid="ignore"):
        solution *= column_scales * target_scale
        offense = solution[:player_count]
        defense = solution[player_count:]
        # An unobserved role has an exact zero deviation. Remove numerical drift only
        # from the observed columns so the deviations still sum to zero in each block.
        for block, active in ((offense, offense_used), (defense, defense_used)):
            block[active] -= np.mean(block[active])
            block[~active] = 0.0
        intercept = (
            float((intercept_direction**2) @ (shifted_response - players @ solution))
            - prior_intercept_shift
        )
        if normalized_prior is not None:
            solution += normalized_prior
        solution *= response_scale
        intercept *= response_scale
        if prior is not None:
            if normalized_prior is None:
                solution += prior
            else:
                solution[~used] = prior[~used]
    if not isfinite(intercept) or not np.all(np.isfinite(solution)):
        raise RuntimeError("sparse RAPM coefficients are not representable in float64")
    return RAPMFit(
        intercept,
        dict(zip(design.player_ids, map(float, offense), strict=True)),
        dict(zip(design.player_ids, map(float, defense), strict=True)),
    )
