"""Sparse, possession-level reference verified on synthetic lineups."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
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
    played_date: date | None = None  # Eastern calendar date; read only by dated fits


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


def fit_rapm_diagnostics(
    possessions: Sequence[Possession], *, ridge: float
) -> tuple[RAPMFit, dict[str, float]]:
    """Run ``fit_rapm`` and also return the LSQR stop code, iterations, norms and condition."""
    if not isfinite(ridge) or ridge <= 0:
        raise ValueError("ridge must be positive and finite")
    info: dict[str, float] = {}
    return _solve_rapm(build_design(possessions), ridge, ridge, info=info), info


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
    info: dict[str, float] | None = None,
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
    offense_level = defense_level = 0.0
    if prior is not None:
        offense_level = float(prior[int(np.argmax(offense_used))])
        defense_level = float(prior[player_count + int(np.argmax(defense_used))])
        prior_levels = np.repeat([offense_level, defense_level], player_count)
        # Uniform role levels change only the intercept. Size the solve from the
        # observed rates and within-role contrasts so a large level cannot erase a
        # small but representable scoring response or variation in the other role.
        with np.errstate(over="ignore"):
            contrasts = np.subtract(prior, prior_levels, out=np.zeros(player_columns), where=used)
        response_scale = max(
            response_scale, min(float(np.max(np.abs(contrasts))), np.finfo(np.float64).max)
        )
    response_scale = response_scale or 1.0
    shifted_response = design.response / response_scale
    if prior is not None:
        finite = np.isfinite(contrasts)
        scaled_contrasts = np.empty_like(contrasts)
        np.divide(contrasts, response_scale, out=scaled_contrasts, where=finite)
        # Opposite-sign float64 priors can have an unrepresentable raw contrast.
        scaled_contrasts[~finite] = prior[~finite] / response_scale - (
            prior_levels[~finite] / response_scale
        )
        shifted_response -= players @ scaled_contrasts
    target_scale = float(np.max(np.abs(shifted_response))) or 1.0
    target = np.concatenate(
        (project(scaled_weights * (shifted_response / target_scale)), np.zeros(player_columns))
    )
    result = lsqr(system, target, atol=1e-12, btol=1e-12)
    solution, stop, iterations, residual, condition = (
        result[0],
        result[1],
        result[2],
        result[3],
        result[6],
    )
    if info is not None:
        info.update(
            stop=float(stop),
            iterations=float(iterations),
            scaled_residual_norm=float(residual),
            condition_estimate=float(condition),
        )
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
        intercept = _unscale_intercept(
            float((intercept_direction**2) @ (shifted_response - players @ solution)),
            response_scale,
            offense_level,
            defense_level,
        )
        effects = solution * response_scale
        if prior is not None:
            effects += prior
            overflow = ~np.isfinite(effects)
            # A deviation can overflow before adding an opposite-sign prior even when
            # the combined effect is representable. Combine those terms before unscaling.
            common_scale = np.maximum(response_scale, np.abs(prior[overflow]))
            effects[overflow] = (
                solution[overflow] * (response_scale / common_scale)
                + prior[overflow] / common_scale
            ) * common_scale
    if not isfinite(intercept) or not np.all(np.isfinite(effects)):
        raise RuntimeError("sparse RAPM coefficients are not representable in float64")
    return RAPMFit(
        intercept,
        dict(zip(design.player_ids, map(float, effects[:player_count]), strict=True)),
        dict(zip(design.player_ids, map(float, effects[player_count:]), strict=True)),
    )


def _unscale_intercept(
    intercept: float, response_scale: float, offense_level: float, defense_level: float
) -> float:
    unscaled = intercept * response_scale
    prior_shift = _LINEUP_SIZE * (offense_level - defense_level)
    if isfinite(unscaled) and isfinite(prior_shift):
        return unscaled - prior_shift
    # Moving the role levels into the intercept can cancel an intermediate overflow.
    scale = max(response_scale, abs(offense_level), abs(defense_level))
    return (
        intercept * (response_scale / scale)
        - _LINEUP_SIZE * (offense_level / scale - defense_level / scale)
    ) * scale
