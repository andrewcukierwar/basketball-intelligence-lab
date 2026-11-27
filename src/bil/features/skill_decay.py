"""Stat-specific exponential decay and league shrinkage for Estimated Skills (issue #32).

Pure functions: no file access, no EPM outputs. The frozen protocol is
docs/research/skill-decay-protocol.md. Targets, exposures, history and the six baselines come from
the #31 engine (`bil.features.skill_history.skill_rows`), run on a stream in which playoff
appearances pool with regular-season history (the registered playoff convention).

For player p, statistic s and target appearance t, with covered earlier appearances g:

    N = sum_g exp(-lam * age(g, t)) * n_g,   D = sum_g exp(-lam * age(g, t)) * d_g
    prediction = (N + k * m) / (D + k)

with `d` in exposure weight units (attempts, or minutes / 36), `m` the #31 `league_to_date` rate,
`lam = ln 2 / h`, `h` the half-life in clock units and `k` the shrinkage strength.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from math import log
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import differential_evolution  # type: ignore[import-untyped]

from bil.features.box import FEATURES, Appearance, Feature
from bil.features.skill_history import LEAGUE_BASELINE, LOSS_EPSILON, skill_rows

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]

CLOCKS = ("day", "games", "possessions")
LOG10_HALF_LIFE_BOUNDS = {"day": (0.0, 3.5), "games": (0.0, 3.0), "possessions": (1.5, 5.0)}
LOG10_K_BOUNDS = (-2.0, 4.0)
BOUND_TOLERANCE = 0.01
SEED_BASE = 32_000
BOOTSTRAP_SEED = 32_032
BOOTSTRAP_REPLICATES = 2_000
FALLBACK_POSSESSIONS_PER_48 = 100.0
POSSESSION_FTA_FACTOR = 0.44
SEASON_KEY = 2022
DATA_END = date(2023, 7, 1)
BLOCKS: tuple[tuple[str, date, date], ...] = (
    ("M0", date(2022, 10, 18), date(2022, 11, 1)),
    ("M1", date(2022, 11, 1), date(2022, 12, 1)),
    ("M2", date(2022, 12, 1), date(2023, 1, 1)),
    ("M3", date(2023, 1, 1), date(2023, 2, 1)),
    ("M4", date(2023, 2, 1), date(2023, 3, 1)),
    ("M5", date(2023, 3, 1), date(2023, 4, 10)),
)
PLAYOFF_BLOCK = ("P", date(2023, 4, 10), DATA_END)
BLOCK_NAMES = (*(b[0] for b in BLOCKS), PLAYOFF_BLOCK[0])
OUTER_BLOCKS = ("M3", "M4", "M5", "P")
FIT_INDICES = tuple(range(len(BLOCKS)))
COMPARED_BASELINES = ("career_to_date", "last_10", "decay_30d", "decay_90d", LEAGUE_BASELINE)
COMMON_BASELINES = (
    "career_to_date",
    "season_to_date",
    "last_10",
    "decay_30d",
    "decay_90d",
    LEAGUE_BASELINE,
)
SPARSE_MAX_GAMES = 9
LOW_MINUTE_THRESHOLD = 15.0
LAYOFF_DAYS = 10


@dataclass(frozen=True)
class DESettings:
    """Frozen Differential Evolution settings; tests may shrink `popsize` and `maxiter`."""

    strategy: str = "best1bin"
    popsize: int = 15
    maxiter: int = 200
    tol: float = 1e-7
    mutation: tuple[float, float] = (0.5, 1.0)
    recombination: float = 0.7
    init: str = "latinhypercube"
    polish: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "popsize": self.popsize,
            "maxiter": self.maxiter,
            "tol": self.tol,
            "mutation": list(self.mutation),
            "recombination": self.recombination,
            "init": self.init,
            "polish": self.polish,
            "updating": "deferred",
            "vectorized": True,
        }


def seed_for(stat_index: int, clock: str, fit_index: int) -> int:
    return SEED_BASE + 100 * stat_index + 10 * CLOCKS.index(clock) + fit_index


def block_of(played: date, season_type: str) -> str | None:
    """Registered block of a target, or None outside every block (never scored or tuned)."""
    if season_type == "playoffs":
        return PLAYOFF_BLOCK[0] if PLAYOFF_BLOCK[1] <= played < PLAYOFF_BLOCK[2] else None
    for name, start, end in BLOCKS:
        if start <= played < end:
            return name
    return None


def fit_blocks(fit_index: int) -> tuple[str, ...]:
    """Regular-season blocks whose targets enter the tuning loss of fit F_j."""
    return tuple(name for name, _, _ in BLOCKS[: fit_index + 1])


@dataclass(frozen=True)
class OuterPlan:
    block: str
    inner: tuple[tuple[int, str], tuple[int, str]]
    final_fit: int


def outer_plan(block: str) -> OuterPlan:
    """Nested plan: two inner (fit, validation block) pairs for clock choice, then the final fit."""
    k = BLOCK_NAMES.index(block)
    if k < 3:
        raise ValueError(f"{block} is a tuning-only block")
    return OuterPlan(block, ((k - 3, BLOCK_NAMES[k - 2]), (k - 2, BLOCK_NAMES[k - 1])), k - 1)


def pooled(rows: Iterable[Appearance]) -> list[Appearance]:
    """Registered playoff convention: one history and league pool per player across season types."""
    return [replace(row, season_type="regular") for row in rows]


def possession_exposure(rows: Sequence[Appearance]) -> tuple[dict[str, float], int]:
    """Estimated on-court possessions per appearance key, and the number of fallback team-games.

    Team-game possessions are FGA + 0.44 FTA - OREB + TOV over that team's player rows, game
    possessions the mean of both teams, and a player's share their milliseconds over one fifth of
    the team's summed milliseconds. A missing component uses 100 possessions per 48 minutes.
    """
    teams: dict[tuple[str, str], list[Appearance]] = defaultdict(list)
    for row in rows:
        teams[(row.game_id, row.team_id)].append(row)
    estimate: dict[tuple[str, str], float | None] = {}
    for key, members in teams.items():
        total = 0.0
        for r in members:
            if r.fga is None or r.fta is None or r.oreb is None or r.tov is None:
                estimate[key] = None
                break
            total += r.fga + POSSESSION_FTA_FACTOR * r.fta - r.oreb + r.tov
        else:
            estimate[key] = total
    by_game: dict[str, list[tuple[str, float | None]]] = defaultdict(list)
    for (game, team), value in estimate.items():
        by_game[game].append((team, value))
    result: dict[str, float] = {}
    fallbacks = 0
    for (game, team), members in teams.items():
        values = [v for _, v in by_game[game]]
        team_ms = sum(r.minutes_ms for r in members)
        if len(values) != 2 or any(v is None for v in values) or team_ms <= 0:
            fallbacks += 1
            for r in members:
                result[r.key] = FALLBACK_POSSESSIONS_PER_48 * r.minutes_ms / (48 * 60_000)
            continue
        game_poss = sum(v for v in values if v is not None) / 2
        for r in members:
            result[r.key] = game_poss * r.minutes_ms / (team_ms / 5)
    return result, fallbacks


@dataclass
class Panel:
    """Per-player appearance panel (players x columns), padded with zeros.

    `inc[c][:, j]` and `ginc[c][:, j]` define the clock-c recursion
    S_j = exp(-lam inc_j) S_{j-1} + exp(-lam ginc_j) x_{j-1} for columns j >= 1.
    """

    players: tuple[str, ...]
    position: dict[str, tuple[int, int]]
    lengths: IntArray
    day: IntArray
    exposure: dict[str, FloatArray]
    inc: dict[str, FloatArray] = field(default_factory=dict)
    ginc: dict[str, FloatArray] = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.players), max([1, *(int(v) for v in self.lengths)])


def build_panel(rows: Sequence[Appearance], possessions: Mapping[str, float]) -> Panel:
    by_player: dict[str, list[Appearance]] = defaultdict(list)
    for row in rows:
        by_player[row.player_id].append(row)
    players = tuple(sorted(by_player))
    width = max((len(v) for v in by_player.values()), default=1)
    lengths = np.zeros(len(players), dtype=np.int64)
    day = np.zeros((len(players), width), dtype=np.int64)
    poss = np.zeros((len(players), width))
    position: dict[str, tuple[int, int]] = {}
    for p, player in enumerate(players):
        ordered = sorted(by_player[player], key=lambda r: (r.game_date, r.game_id))
        dates = [r.game_date for r in ordered]
        if len(set(dates)) != len(dates):
            raise ValueError(f"Player {player} has two appearances on one date")
        lengths[p] = len(ordered)
        for j, r in enumerate(ordered):
            position[r.key] = (p, j)
            day[p, j] = r.game_date.toordinal()
            poss[p, j] = possessions[r.key]
    panel = Panel(players, position, lengths, day, {"possessions": poss})
    valid = np.arange(width)[None, :] < lengths[:, None]
    step = np.zeros((len(players), width))
    step[:, 1:] = np.where(valid[:, 1:], day[:, 1:] - day[:, :-1], 0)
    previous_poss = np.zeros((len(players), width))
    previous_poss[:, 1:] = poss[:, :-1]
    games = np.zeros((len(players), width))
    games[:, 1:] = 1.0
    zero = np.zeros((len(players), width))
    panel.inc = {"day": step, "games": games, "possessions": previous_poss}
    panel.ginc = {"day": step, "games": zero, "possessions": zero}
    return panel


def discounted_sums(
    x: FloatArray, inc: FloatArray, ginc: FloatArray, lam: FloatArray
) -> FloatArray:
    """Discounted sums of strictly earlier columns: shape (len(lam), *x.shape).

    `x` has shape (channels, players, columns); the value at column j uses columns < j only.
    """
    out = np.zeros((lam.size, *x.shape))
    rate = lam[:, None, None]
    same, unit = ginc is inc, not ginc.any()
    for j in range(1, x.shape[-1]):
        f = np.exp(-rate * inc[None, None, :, j])
        if unit:
            out[..., j] = f * out[..., j - 1] + x[None, :, :, j - 1]
            continue
        g = f if same else np.exp(-rate * ginc[None, None, :, j])
        out[..., j] = f * out[..., j - 1] + g * x[None, :, :, j - 1]
    return out


@dataclass
class StatTable:
    """Per-appearance arrays for one statistic, aligned to `Appearances.keys`."""

    feature: Feature
    x: FloatArray  # (2, players, columns): covered numerators and weight-unit denominators
    target_num: FloatArray
    target_den: FloatArray
    weight: FloatArray
    observed: BoolArray
    status: tuple[str, ...]
    history: tuple[str, ...]
    covered_games: IntArray
    league: FloatArray
    baselines: dict[str, FloatArray]

    @property
    def scale(self) -> int:
        return self.feature.scale

    @property
    def rate(self) -> FloatArray:
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(self.observed, self.target_num * self.scale / self.target_den, np.nan)


@dataclass
class Appearances:
    keys: tuple[str, ...]
    game: tuple[str, ...]
    player: tuple[str, ...]
    played: tuple[date, ...]
    season_type: tuple[str, ...]
    block: tuple[str | None, ...]
    pidx: IntArray
    cidx: IntArray
    prior_mean_minutes: FloatArray
    days_since_last: FloatArray
    prior_appearances: IntArray


def _nan(value: float | None) -> float:
    return np.nan if value is None else value


def assemble(
    rows: Sequence[Appearance],
) -> tuple[Panel, Appearances, dict[str, StatTable], list[tuple[str, str, dict[str, Any]]], int]:
    """Run the #31 engine on the pooled stream and lay out arrays.

    Returns the panel, appearance arrays, per-statistic tables, the engine's per-row predictions
    (for reconciliation with the #31 build) and the number of possession fallbacks.
    """
    original = {r.key: r.season_type for r in rows}
    stream = pooled(rows)
    possessions, fallbacks = possession_exposure(rows)
    panel = build_panel(stream, possessions)
    shape = panel.shape
    keys: list[str] = []
    per_stat: dict[str, dict[str, list[Any]]] = {f.code: defaultdict(list) for f in FEATURES}
    x = {f.code: np.zeros((2, *shape)) for f in FEATURES}
    engine: list[tuple[str, str, dict[str, Any]]] = []
    for opportunity, skill in skill_rows(stream):
        row = opportunity.row
        keys.append(row.key)
        p, j = panel.position[row.key]
        for sk in skill:
            code = sk.feature.code
            columns = per_stat[code]
            if sk.target_status != "missing_component":
                assert sk.target_numerator is not None and sk.target_denominator is not None
                x[code][0, p, j] = sk.target_numerator
                x[code][1, p, j] = sk.target_denominator / sk.feature.scale
            columns["num"].append(_nan(sk.target_numerator))
            columns["den"].append(_nan(sk.target_denominator))
            columns["weight"].append(sk.weight)
            columns["observed"].append(sk.target_status == "observed")
            columns["status"].append(sk.target_status)
            columns["history"].append(sk.history_status)
            columns["covered"].append(sk.career_covered_games)
            for name in COMMON_BASELINES:
                columns[name].append(_nan(sk.predictions[name]))
            engine.append((row.key, code, {**sk.predictions, "target_rate": sk.target_rate}))
    position = [panel.position[k] for k in keys]
    by_key = {r.key: r for r in rows}
    played = tuple(by_key[k].game_date for k in keys)
    kinds = tuple(original[k] for k in keys)
    pidx = np.array([p for p, _ in position], dtype=np.int64)
    cidx = np.array([j for _, j in position], dtype=np.int64)
    minutes = np.zeros(shape)
    for k, (p, j) in zip(keys, position, strict=True):
        minutes[p, j] = by_key[k].minutes_ms / 60_000
    cumulative = np.cumsum(minutes, axis=1) - minutes
    prior_mean = np.where(cidx > 0, cumulative[pidx, cidx] / np.maximum(cidx, 1), np.nan)
    since = np.where(
        cidx > 0, panel.day[pidx, cidx] - panel.day[pidx, np.maximum(cidx - 1, 0)], np.nan
    )
    appearances = Appearances(
        tuple(keys),
        tuple(by_key[k].game_id for k in keys),
        tuple(by_key[k].player_id for k in keys),
        played,
        kinds,
        tuple(block_of(d, s) for d, s in zip(played, kinds, strict=True)),
        pidx,
        cidx,
        prior_mean.astype(np.float64),
        since.astype(np.float64),
        cidx.copy(),
    )
    tables: dict[str, StatTable] = {}
    for feature in FEATURES:
        c = per_stat[feature.code]
        tables[feature.code] = StatTable(
            feature,
            x[feature.code],
            np.array(c["num"], dtype=np.float64),
            np.array(c["den"], dtype=np.float64),
            np.array(c["weight"], dtype=np.float64),
            np.array(c["observed"], dtype=np.bool_),
            tuple(c["status"]),
            tuple(c["history"]),
            np.array(c["covered"], dtype=np.int64),
            np.array(c[LEAGUE_BASELINE], dtype=np.float64),
            {name: np.array(c[name], dtype=np.float64) for name in COMMON_BASELINES},
        )
    return panel, appearances, tables, engine, fallbacks


def predict(
    panel: Panel,
    table: StatTable,
    appearances: Appearances,
    clock: str,
    log10_half_life: FloatArray,
    log10_k: FloatArray,
    rows: IntArray,
) -> FloatArray:
    """Predictions (population x rows) for the given appearance indices."""
    lam = log(2) / np.power(10.0, log10_half_life)
    k = np.power(10.0, log10_k)[:, None]
    sums = discounted_sums(table.x, panel.inc[clock], panel.ginc[clock], lam)
    gathered = sums[:, :, appearances.pidx[rows], appearances.cidx[rows]]
    return np.asarray(
        (gathered[:, 0] + k * table.league[rows][None, :]) / (gathered[:, 1] + k), np.float64
    )


def nll(
    feature: Feature, numerator: FloatArray, denominator: FloatArray, pred: FloatArray
) -> FloatArray:
    """Vectorized `skill_history.loss_terms` (same clipping)."""
    if feature.scale == 1:
        p = np.clip(pred, LOSS_EPSILON, 1 - LOSS_EPSILON)
        return np.asarray(-(numerator * np.log(p) + (denominator - numerator) * np.log1p(-p)))
    mean = np.maximum(pred, LOSS_EPSILON) * denominator / feature.scale
    return np.asarray(mean - numerator * np.log(mean))


def squared_error(table: StatTable, rows: IntArray, pred: FloatArray) -> FloatArray:
    return np.asarray((pred - table.rate[rows]) ** 2)


def mean_loss(table: StatTable, rows: IntArray, pred: FloatArray) -> FloatArray:
    """Summed NLL over summed exposure weight, per population member."""
    losses = nll(table.feature, table.target_num[rows], table.target_den[rows], pred)
    return np.asarray(losses.sum(axis=-1) / table.weight[rows].sum())


def scorable(table: StatTable) -> BoolArray:
    return np.asarray(table.observed & ~np.isnan(table.league))


def rows_in(appearances: Appearances, table: StatTable, blocks: Iterable[str]) -> IntArray:
    wanted = set(blocks)
    mask = scorable(table) & np.array([b in wanted for b in appearances.block])
    return np.flatnonzero(mask).astype(np.int64)


@dataclass(frozen=True)
class FitResult:
    code: str
    clock: str
    fit_index: int
    seed: int
    log10_half_life: float
    log10_k: float
    objective: float
    nfev: int
    nit: int
    success: bool
    rows: int
    bound_hits: tuple[str, ...]

    @property
    def half_life(self) -> float:
        return float(10**self.log10_half_life)

    @property
    def k(self) -> float:
        return float(10**self.log10_k)


def fit(
    panel: Panel,
    table: StatTable,
    appearances: Appearances,
    clock: str,
    fit_index: int,
    settings: DESettings = DESettings(),
) -> FitResult:
    """Fit (log10 h, log10 k) by Differential Evolution on regular targets in M0..M_fit_index."""
    rows = rows_in(appearances, table, fit_blocks(fit_index))
    if rows.size == 0:
        raise ValueError(f"No tuning rows for {table.feature.code} F{fit_index}")
    stat_index = next(i for i, f in enumerate(FEATURES) if f.code == table.feature.code)
    seed = seed_for(stat_index, clock, fit_index)
    return fit_rows(panel, table, appearances, clock, rows, seed, fit_index, settings)


def fit_rows(
    panel: Panel,
    table: StatTable,
    appearances: Appearances,
    clock: str,
    rows: IntArray,
    seed: int,
    fit_index: int,
    settings: DESettings = DESettings(),
) -> FitResult:
    """The #32 Differential Evolution fit on explicit target rows with an explicit seed."""
    if rows.size == 0:
        raise ValueError(f"No tuning rows for {table.feature.code}")
    bounds = [LOG10_HALF_LIFE_BOUNDS[clock], LOG10_K_BOUNDS]

    def objective(theta: FloatArray) -> FloatArray | float:
        single = theta.ndim == 1
        population = theta.reshape(2, -1)
        pred = predict(panel, table, appearances, clock, population[0], population[1], rows)
        values = mean_loss(table, rows, pred)
        return float(values[0]) if single else values

    result = differential_evolution(
        objective,
        bounds,
        strategy=settings.strategy,
        popsize=settings.popsize,
        maxiter=settings.maxiter,
        tol=settings.tol,
        mutation=settings.mutation,
        recombination=settings.recombination,
        init=settings.init,
        polish=settings.polish,
        updating="deferred",
        vectorized=True,
        rng=seed,
    )
    theta = np.asarray(result.x, dtype=np.float64)
    hits = tuple(
        f"{name}_{side}"
        for name, value, (low, high) in zip(("half_life", "k"), theta, bounds, strict=True)
        for side, edge in (("lower", low), ("upper", high))
        if abs(value - edge) <= BOUND_TOLERANCE
    )
    return FitResult(
        table.feature.code,
        clock,
        fit_index,
        seed,
        float(theta[0]),
        float(theta[1]),
        float(result.fun),
        int(result.nfev),
        int(result.nit),
        bool(result.success),
        int(rows.size),
        hits,
    )


def predict_fit(
    panel: Panel, table: StatTable, appearances: Appearances, result: FitResult, rows: IntArray
) -> FloatArray:
    pred = predict(
        panel,
        table,
        appearances,
        result.clock,
        np.array([result.log10_half_life]),
        np.array([result.log10_k]),
        rows,
    )
    return np.asarray(pred[0])


def bootstrap_counts(clusters: int, replicates: int, seed: int) -> IntArray:
    """(replicates, clusters) resampling multiplicities for a cluster bootstrap."""
    rng = np.random.default_rng(seed)
    counts = np.zeros((replicates, clusters), dtype=np.int64)
    for b in range(replicates):
        counts[b] = np.bincount(rng.integers(0, clusters, size=clusters), minlength=clusters)
    return counts


def clustered_ratio(
    cluster: IntArray, numerator: FloatArray, weight: FloatArray, counts: IntArray
) -> tuple[float, float, float]:
    """Point estimate and 95% percentile interval of sum(numerator) / sum(weight)."""
    clusters = counts.shape[1]
    top = np.bincount(cluster, numerator, minlength=clusters)
    bottom = np.bincount(cluster, weight, minlength=clusters)
    point = float(top.sum() / bottom.sum())
    reps_bottom = counts @ bottom
    keep = reps_bottom > 0
    reps = (counts @ top)[keep] / reps_bottom[keep]
    low, high = np.percentile(reps, [2.5, 97.5])
    return point, float(low), float(high)


def as_of_sums(
    panel: Panel, x: FloatArray, clock: str, half_life: float, cutoff: date
) -> FloatArray:
    """Discounted (numerator, denominator) sums per player from appearances dated before `cutoff`.

    Day ages are `cutoff - played`; exposure-clock ages count appearances after g and before the
    cutoff. Equals the prediction state of a next appearance on the cutoff date.
    """
    lam = log(2) / half_life
    out = np.zeros((2, len(panel.players)))
    day = cutoff.toordinal()
    for p in range(len(panel.players)):
        n = int(np.searchsorted(panel.day[p, : panel.lengths[p]], day))
        if n == 0:
            continue
        if clock == "day":
            age = (day - panel.day[p, :n]).astype(np.float64)
        else:
            step = np.ones(n) if clock == "games" else panel.exposure["possessions"][p, :n]
            age = np.concatenate([np.cumsum(step[::-1])[::-1][1:], [0.0]])
        out[:, p] = (x[:, p, :n] * np.exp(-lam * age)[None, :]).sum(axis=1)
    return out


def league_as_of(table: StatTable, panel: Panel, cutoff: date) -> float | None:
    before = panel.day < cutoff.toordinal()
    valid = np.arange(panel.day.shape[1])[None, :] < panel.lengths[:, None]
    mask = before & valid
    denominator = float(table.x[1][mask].sum())
    return None if denominator <= 0 else float(table.x[0][mask].sum()) / denominator
