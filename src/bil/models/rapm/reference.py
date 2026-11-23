"""Sparse, possession-level reference verified on synthetic lineups."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, sqrt

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_matrix, eye, hstack, vstack  # type: ignore[import-untyped]
from scipy.sparse.linalg import lsqr  # type: ignore[import-untyped]

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
    player_count = len(design.player_ids)
    player_columns = 2 * player_count
    root_weights = np.sqrt(design.weights)
    data = design.matrix.multiply(root_weights[:, None])
    penalty = hstack((csr_matrix((player_columns, 1)), eye(player_columns) * sqrt(ridge)))
    system = vstack((data, penalty), format="csr")

    # Shift the origin of the response using the free intercept before solving.
    origin = design.response[0]
    with np.errstate(over="ignore"):
        weighted_response = root_weights * (design.response - origin)
    if not np.all(np.isfinite(weighted_response)):
        raise ValueError("weighted response must be representable in float64")
    target = np.concatenate((weighted_response, np.zeros(player_columns)))
    solution, stop, *_ = lsqr(system, target, atol=1e-12, btol=1e-12)
    if stop not in _CONVERGED or not np.all(np.isfinite(solution)):
        raise RuntimeError(f"sparse RAPM solve failed to converge (LSQR stop {stop})")

    offense = solution[1 : 1 + player_count]
    defense = solution[1 + player_count :]
    offense_mean = float(np.mean(offense))
    defense_mean = float(np.mean(defense))
    intercept = float(origin + solution[0] + _LINEUP_SIZE * (offense_mean - defense_mean))
    if not isfinite(intercept):
        raise RuntimeError("sparse RAPM intercept is not representable in float64")
    return RAPMFit(
        intercept,
        dict(zip(design.player_ids, map(float, offense - offense_mean), strict=True)),
        dict(zip(design.player_ids, map(float, defense - defense_mean), strict=True)),
    )
