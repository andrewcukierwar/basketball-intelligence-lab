"""Sparse, possession-level reference verified on synthetic lineups."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, sqrt

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
    design = build_design(possessions)
    row_count = len(possessions)
    player_count = len(design.player_ids)
    player_columns = 2 * player_count
    root_weights = np.sqrt(design.weights)
    # Project out the free intercept without materializing dense centered player columns.
    max_root_weight = float(root_weights.max())
    intercept_direction = root_weights / max_root_weight
    intercept_direction /= np.linalg.norm(intercept_direction)
    # Common system and response scalings keep LSQR's norms in range.
    root_penalty = sqrt(ridge)
    system_scale = max(max_root_weight, root_penalty)
    root_penalty /= system_scale
    scaled_weights = root_weights / system_scale
    players = design.matrix[:, 1:]
    weighted_players = players.multiply(scaled_weights[:, None]).tocsr()

    def project(values: NDArray[np.float64]) -> NDArray[np.float64]:
        return values - intercept_direction * (intercept_direction @ values)

    def matvec(coefficients: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.concatenate(
            (project(weighted_players @ coefficients), root_penalty * coefficients)
        )

    def rmatvec(values: NDArray[np.float64]) -> NDArray[np.float64]:
        projected: NDArray[np.float64] = weighted_players.T @ project(values[:row_count])
        return projected + root_penalty * values[row_count:]

    system = LinearOperator(
        (row_count + player_columns, player_columns),
        matvec=matvec,
        rmatvec=rmatvec,
        dtype=np.float64,
    )
    response_scale = float(np.max(design.response)) or 1.0
    normalized_response = design.response / response_scale
    target = np.concatenate(
        (project(scaled_weights * normalized_response), np.zeros(player_columns))
    )
    solution, stop, *_ = lsqr(system, target, atol=1e-12, btol=1e-12)
    if stop not in _CONVERGED or not np.all(np.isfinite(solution)):
        raise RuntimeError(f"sparse RAPM solve failed to converge (LSQR stop {stop})")

    offense = solution[:player_count]
    defense = solution[player_count:]
    offense -= np.mean(offense)
    defense -= np.mean(defense)
    intercept = float((intercept_direction**2) @ (normalized_response - players @ solution))
    with np.errstate(over="ignore"):
        solution *= response_scale
        intercept *= response_scale
    if not isfinite(intercept) or not np.all(np.isfinite(solution)):
        raise RuntimeError("sparse RAPM coefficients are not representable in float64")
    return RAPMFit(
        intercept,
        dict(zip(design.player_ids, map(float, offense), strict=True)),
        dict(zip(design.player_ids, map(float, defense), strict=True)),
    )
