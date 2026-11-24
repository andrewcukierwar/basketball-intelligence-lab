"""Zero-prior ridge RAPM with unpenalized context columns or a fixed context offset.

Extends the verified #6 estimator for issue #24. Context columns ``Z`` (home court, score state,
game time) enter beside the intercept without a penalty. The player blocks keep the shared ridge
penalty, so a fit with no context columns and no offset is the #23 baseline. The solve projects
the weighted span of ``[1, Z]`` out of the player design and the response (Frisch-Waugh-Lovell),
runs sparse LSQR on the penalized player problem, then recovers the intercept and context
coefficients by weighted least squares on the player residual.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.sparse.linalg import LinearOperator, lsqr  # type: ignore[import-untyped]

from bil.models.rapm.reference import Possession, RAPMFit, build_design

_CONVERGED = {0, 1, 2, 4, 5}
_RANK_TOLERANCE = 1e-10


@dataclass(frozen=True, slots=True)
class ContextFit:
    """Points per 100 possessions. Positive defensive effects prevent points.

    ``context`` holds one coefficient per supplied context column, in column order. The
    prediction for a possession is ``intercept + context @ z + offense - defense`` plus any
    offset the caller subtracted before fitting.
    """

    intercept: float
    context: tuple[float, ...]
    offense: dict[int, float]
    defense: dict[int, float]

    def players(self) -> RAPMFit:
        return RAPMFit(self.intercept, self.offense, self.defense)


def _context_array(context: NDArray[np.float64] | None, rows: int) -> NDArray[np.float64]:
    if context is None:
        return np.zeros((rows, 0), dtype=np.float64)
    array = np.asarray(context, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] != rows:
        raise ValueError(f"context must have shape ({rows}, k)")
    if not np.all(np.isfinite(array)):
        raise ValueError("context values must be finite")
    return array


def _basis(
    root_weights: NDArray[np.float64], context: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Orthonormal basis of the weighted unpenalized columns ``sqrt(w) * [1, Z]``."""
    columns = np.column_stack((np.ones(len(root_weights)), context)) * root_weights[:, None]
    q, r = np.linalg.qr(columns)
    diagonal = np.abs(np.diag(r))
    if diagonal.min() <= _RANK_TOLERANCE * diagonal.max():
        raise ValueError("context columns are collinear with each other or the intercept")
    return q, r


def fit_context_only(
    response: NDArray[np.float64],
    context: NDArray[np.float64] | None,
    weights: NDArray[np.float64] | None = None,
) -> tuple[float, NDArray[np.float64]]:
    """Weighted least squares of a points-per-100 response on ``[1, Z]``, with no players."""
    y = np.asarray(response, dtype=np.float64)
    if y.ndim != 1 or y.size == 0 or not np.all(np.isfinite(y)):
        raise ValueError("response must be a nonempty finite vector")
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=np.float64)
    if w.shape != y.shape or not np.all(np.isfinite(w)) or np.any(w <= 0):
        raise ValueError("weights must be positive, finite and match the response")
    z = _context_array(context, y.size)
    root = np.sqrt(w)
    q, r = _basis(root, z)
    coefficients = np.linalg.solve(r, q.T @ (root * y))
    return float(coefficients[0]), coefficients[1:]


def fit_context_rapm(
    possessions: Sequence[Possession],
    context: NDArray[np.float64] | None = None,
    *,
    ridge: float,
    offset: NDArray[np.float64] | None = None,
    info: dict[str, float] | None = None,
) -> ContextFit:
    """Fit ridge player effects with unpenalized intercept and context columns.

    ``offset`` (points per 100, one value per possession) is subtracted from the response before
    fitting and is not estimated; the caller adds it back when predicting. With ``context`` and
    ``offset`` both absent this is the zero-prior fit of ``reference.fit_rapm``.
    """
    if not np.isfinite(ridge) or ridge <= 0:
        raise ValueError("ridge must be positive and finite")
    design = build_design(possessions)
    rows = len(design.response)
    z = _context_array(context, rows)
    y = design.response.copy()
    if offset is not None:
        shift = np.asarray(offset, dtype=np.float64)
        if shift.shape != (rows,) or not np.all(np.isfinite(shift)):
            raise ValueError(f"offset must be a finite vector of length {rows}")
        y -= shift
    player_count = len(design.player_ids)
    player_columns = 2 * player_count
    root = np.sqrt(design.weights)
    q, r = _basis(root, z)
    # Dividing the whole system by one constant leaves the minimizer unchanged and keeps
    # the operator norm near one for the solver tolerance.
    scale = max(float(root.max()), float(np.sqrt(ridge)))
    players = design.matrix[:, 1:]
    weighted = players.multiply((root / scale)[:, None]).tocsr()
    penalty = float(np.sqrt(ridge)) / scale
    used = np.bincount(players.indices, minlength=player_columns) > 0

    def project(values: NDArray[np.float64]) -> NDArray[np.float64]:
        projected: NDArray[np.float64] = values - q @ (q.T @ values)
        return projected

    def matvec(coefficients: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.concatenate((project(weighted @ coefficients), penalty * coefficients))

    def rmatvec(values: NDArray[np.float64]) -> NDArray[np.float64]:
        back: NDArray[np.float64] = weighted.T @ project(values[:rows])
        return back + penalty * values[rows:]

    system = LinearOperator(
        (rows + player_columns, player_columns), matvec=matvec, rmatvec=rmatvec, dtype=np.float64
    )
    response_scale = float(np.max(np.abs(y))) or 1.0
    target = np.concatenate(
        (project((root / scale) * (y / response_scale)), np.zeros(player_columns))
    )
    result = lsqr(system, target, atol=1e-12, btol=1e-12)
    solution, stop = result[0], result[1]
    if info is not None:
        info.update(
            stop=float(stop),
            iterations=float(result[2]),
            scaled_residual_norm=float(result[3]),
            condition_estimate=float(result[6]),
        )
    if stop not in _CONVERGED or not np.all(np.isfinite(solution)):
        raise RuntimeError(f"context RAPM solve failed to converge (LSQR stop {stop})")
    effects = solution * response_scale
    offense = effects[:player_count]
    defense = effects[player_count:]
    # The intercept absorbs a common shift of either block, so the penalized optimum has
    # zero mean over observed columns. Remove numerical drift and zero unobserved roles.
    for block, active in ((offense, used[:player_count]), (defense, used[player_count:])):
        block[active] -= np.mean(block[active])
        block[~active] = 0.0
    residual = y - players @ effects
    coefficients = np.linalg.solve(r, q.T @ (root * residual))
    if not np.all(np.isfinite(coefficients)) or not np.all(np.isfinite(effects)):
        raise RuntimeError("context RAPM coefficients are not representable in float64")
    return ContextFit(
        float(coefficients[0]),
        tuple(float(value) for value in coefficients[1:]),
        dict(zip(design.player_ids, map(float, offense), strict=True)),
        dict(zip(design.player_ids, map(float, defense), strict=True)),
    )
