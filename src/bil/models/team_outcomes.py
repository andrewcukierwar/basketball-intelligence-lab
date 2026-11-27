"""Team margins and win probabilities from frozen Expected impact ratings (#39).

Retrospective rolling-origin evaluation under ``docs/research/team-outcomes-protocol.md``:
pregame minutes from strictly earlier box lines, a ridge team-rating baseline, and an
oracle-minutes diagnostic kept out of the main forecast path.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from numpy.typing import NDArray

from bil.data.pilot_sources import sha256_file
from bil.features.box import Appearance
from bil.features.box_build import TEAM_LOG
from bil.models.expected_impact import AS_OF_ARTIFACT
from bil.models.expected_impact_outer import ADDENDUM, outer_logs, parse_config
from bil.models.rapm.baseline import _peak_memory_mib
from bil.models.rapm.multiseason import REPO_ROOT, SEASON_PINS, _git_head, _versions, _write_json
from bil.models.rapm.targets import verify_protocol
from bil.models.spm_build import LOG_PINS, checked_file, checked_logs, read_json

FloatArray = NDArray[np.float64]
VERSION = "issue-39-v1"
PROTOCOL = REPO_ROOT / "docs/research/team-outcomes-protocol.md"
DEV_SEASONS = (2021, 2022)
EVAL_SEASONS = (2023, 2024)
LOG_SEASONS = (2020, 2021, 2022, 2023, 2024)
RATING_RUNS = {
    "issue-35-v1": "db254b8c450034a0142255c40301e74cd6ddc59d505ab6d7aef983f846fce5d1",
    "issue-36-v1": "f74fc2a5e76b7a22964ca8b96736344bc49f3611dd0acf37fbdaeb9ae130a131",
}
HISTORY_GAMES = 10
TEAM_MINUTES = 240.0
HALF_LIVES = (30.0, 60.0, 120.0, 240.0)
RIDGES = (1.0, 4.0, 16.0)
WINDOW_DAYS = 365
BOOTSTRAP = 2000
SEED = 39
MODELS = ("hca", "team_rating", "ei")


# --- inputs ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Game:
    game_id: str
    season: int
    day: date
    playoff: bool
    home: str | None  # None when the log has no single home team
    away: str | None
    teams: tuple[str, str]
    margin: float | None  # home minus away; None for unflagged games


def team_games(directory: Path, season: int) -> tuple[list[Game], dict[str, int]]:
    """Official regular and playoff games of one season from the team log."""
    with duckdb.connect() as connection:
        rows = connection.execute(
            "SELECT game_id, team_id, game_date, home, pts FROM read_parquet(?) ORDER BY 1, 2",
            [str(directory / TEAM_LOG)],
        ).fetchall()
    grouped: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for row in rows:
        grouped[row[0]].append(row)
    games, counts = [], {"excluded_prefix": 0, "malformed": 0, "unflagged_home": 0}
    for game_id, pair in grouped.items():
        if game_id[:3] not in ("002", "004"):
            counts["excluded_prefix"] += 1
            continue
        if len(pair) != 2 or pair[0][2] != pair[1][2] or any(r[4] is None for r in pair):
            counts["malformed"] += 1
            continue
        teams = (str(pair[0][1]), str(pair[1][1]))
        flags = [r[3] for r in pair]
        if None in flags or flags[0] == flags[1]:
            counts["unflagged_home"] += 1
            home = away = None
            margin = None
        else:
            h = 0 if flags[0] else 1
            home, away = teams[h], teams[1 - h]
            margin = float(pair[h][4] - pair[1 - h][4])
        games.append(
            Game(game_id, season, pair[0][2], game_id[:3] == "004", home, away, teams, margin)
        )
    return sorted(games, key=lambda g: (g.day, g.game_id)), counts


@dataclass(frozen=True)
class Snapshot:
    as_of: date
    total: dict[int, float]
    cold: float
    snapshot_id: str


def load_ratings(path: Path) -> list[Snapshot]:
    """Load rating snapshots and the total each assigns to a player absent from its roster.

    An as-of artifact (#135) states its per-side cold priors, which must agree within each
    snapshot. A legacy artifact has none: its cold total is inferred from an exported row with
    neither box history nor window possessions, or 0 when no such row exists. That inference
    depends on which future players the global design held, so it is kept only to reproduce
    the frozen #35/#36/#39/#42 artifacts.
    """
    by_day: dict[str, dict[int, float]] = defaultdict(dict)
    cold: dict[str, float] = {}
    ids: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        as_of = "artifact_version" in (reader.fieldnames or [])
        for row in reader:
            key = row["as_of"]
            total = float(row["rating_total"])
            by_day[key][int(row["player_id"])] = total
            ids[key] = row["snapshot_id"]
            if as_of:
                if row["artifact_version"] != AS_OF_ARTIFACT:
                    raise ValueError(f"unknown rating artifact {row['artifact_version']}")
                stated = float(row["cold_offense"]) + float(row["cold_defense"])
                if cold.setdefault(key, stated) != stated:
                    raise ValueError(f"cold priors differ within the {key} snapshot")
            elif row["box_history"] == "False" and float(row["window_possessions"]) == 0:
                cold[key] = total
    return [Snapshot(date.fromisoformat(k), v, cold.get(k, 0.0), ids[k]) for k, v in by_day.items()]


# --- pregame minutes -------------------------------------------------------------------


@dataclass
class BoxIndex:
    """Positive-minute box lines by team-game and by player, for strictly-earlier lookups."""

    team_games: dict[tuple[int, str], list[tuple[date, str]]] = field(default_factory=dict)
    minutes: dict[tuple[str, str], dict[int, float]] = field(default_factory=dict)
    player_days: dict[int, list[date]] = field(default_factory=dict)
    player_teams: dict[int, list[str]] = field(default_factory=dict)

    @classmethod
    def build(cls, logs: Mapping[int, Iterable[Appearance]]) -> BoxIndex:
        index = cls()
        games: dict[tuple[int, str], set[tuple[date, str]]] = defaultdict(set)
        minutes: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
        lines: dict[int, list[tuple[date, str]]] = defaultdict(list)
        for season, rows in logs.items():
            for row in rows:
                if row.minutes_ms <= 0:
                    continue
                player = int(row.player_id)
                games[season, row.team_id].add((row.game_date, row.game_id))
                minutes[row.game_id, row.team_id][player] = row.minutes_ms / 60_000
                lines[player].append((row.game_date, row.team_id))
        index.team_games = {key: sorted(value) for key, value in games.items()}
        index.minutes = dict(minutes)
        for player, values in lines.items():
            values.sort()
            index.player_days[player] = [d for d, _ in values]
            index.player_teams[player] = [t for _, t in values]
        return index

    def last_team(self, player: int, day: date) -> str | None:
        days = self.player_days.get(player, [])
        i = bisect.bisect_left(days, day)
        return self.player_teams[player][i - 1] if i else None


@dataclass(frozen=True)
class Projection:
    minutes: dict[int, float]
    games_used: int
    previous_season: bool
    roster_drops: int


def project_minutes(index: BoxIndex, season: int, team: str, day: date) -> Projection:
    """Average minutes over the team's last 10 earlier games, rescaled to 240."""
    history = index.team_games.get((season, team), [])
    earlier = history[: bisect.bisect_left(history, (day, ""))][-HISTORY_GAMES:]
    previous = not earlier
    if previous:
        earlier = [g for g in index.team_games.get((season - 1, team), []) if g[0] < day][
            -HISTORY_GAMES:
        ]
    totals: dict[int, float] = defaultdict(float)
    for _, game_id in earlier:
        for player, value in index.minutes.get((game_id, team), {}).items():
            totals[player] += value
    drops = 0
    for player in list(totals):
        if index.last_team(player, day) != team:
            del totals[player]
            drops += 1
    scale = sum(totals.values())
    projected = {p: v * TEAM_MINUTES / scale for p, v in totals.items()} if scale else {}
    return Projection(projected, len(earlier), previous, drops)


def oracle_minutes(index: BoxIndex, game_id: str, team: str) -> dict[int, float]:
    realized = index.minutes.get((game_id, team), {})
    scale = sum(realized.values())
    return {p: v * TEAM_MINUTES / scale for p, v in realized.items()} if scale else {}


def team_net(minutes: Mapping[int, float], snapshot: Snapshot) -> tuple[float, float]:
    """Minutes-weighted sum of total ratings per 100, and the minute share on cold ratings."""
    net = cold = 0.0
    for player, value in minutes.items():
        rating = snapshot.total.get(player)
        if rating is None:
            rating, cold = snapshot.cold, cold + value
        net += value / 48 * rating
    return net, cold / TEAM_MINUTES


# --- team-rating baseline --------------------------------------------------------------


def ridge_team_ratings(
    history: Sequence[Game], day: date, teams: Sequence[str], half_life: float, ridge: float
) -> tuple[float, dict[str, float]]:
    """Weighted ridge of margins on an unpenalized home term and ±1 team columns."""
    column = {t: i + 1 for i, t in enumerate(teams)}
    rows, response, weights = [], [], []
    for g in history:
        age = (day - g.day).days
        if not 1 <= age <= WINDOW_DAYS or g.margin is None or g.home is None or g.away is None:
            continue
        x = np.zeros(len(teams) + 1)
        x[0], x[column[g.home]], x[column[g.away]] = 1.0, 1.0, -1.0
        rows.append(x)
        response.append(g.margin)
        weights.append(0.5 ** (age / half_life))
    if not rows:
        return 0.0, dict.fromkeys(teams, 0.0)
    design, y, w = np.asarray(rows), np.asarray(response), np.asarray(weights)
    penalty = ridge * np.eye(len(teams) + 1)
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(design.T @ (design * w[:, None]) + penalty, design.T @ (w * y))
    return float(beta[0]), {t: float(beta[column[t]]) for t in teams}


# --- metrics ---------------------------------------------------------------------------


def normal_cdf(values: FloatArray) -> FloatArray:
    erf = np.vectorize(math.erf)
    result: FloatArray = 0.5 * (1 + erf(values / math.sqrt(2)))
    return np.clip(result, 1e-12, 1 - 1e-12)


def calibration(prob: FloatArray, won: FloatArray) -> dict[str, Any]:
    order = np.argsort(prob, kind="stable")
    bins = [
        {"mean_prob": float(prob[i].mean()), "win_rate": float(won[i].mean()), "games": len(i)}
        for i in np.array_split(order, 10)
        if len(i)
    ]
    logit = np.log(prob / (1 - prob))
    beta = np.zeros(2)
    design = np.column_stack([np.ones_like(logit), logit])
    for _ in range(50):  # Newton steps for logistic recalibration
        p = 1 / (1 + np.exp(-(design @ beta)))
        hessian = design.T @ (design * (p * (1 - p))[:, None]) + 1e-9 * np.eye(2)
        step = np.linalg.solve(hessian, design.T @ (won - p))
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return {"bins": bins, "intercept": float(beta[0]), "slope": float(beta[1])}


def metrics(margin: FloatArray, pred: FloatArray, prob: FloatArray) -> dict[str, Any]:
    won = (margin > 0).astype(np.float64)
    return {
        "games": len(margin),
        "margin_mae": float(np.mean(np.abs(pred - margin))),
        "margin_rmse": float(np.sqrt(np.mean((pred - margin) ** 2))),
        "log_loss": float(-np.mean(won * np.log(prob) + (1 - won) * np.log(1 - prob))),
        "brier": float(np.mean((prob - won) ** 2)),
        "accuracy": float(np.mean((prob > 0.5) == (won == 1))),
        "calibration": calibration(prob, won),
    }


def paired(
    margin: FloatArray,
    model: tuple[FloatArray, FloatArray],
    other: tuple[FloatArray, FloatArray],
    clusters: Mapping[str, NDArray[np.int64]],
) -> dict[str, Any]:
    """Model minus comparator: margin RMSE and log loss, with cluster-bootstrap intervals."""
    won = (margin > 0).astype(np.float64)

    def loss(prob: FloatArray) -> FloatArray:
        values: FloatArray = -(won * np.log(prob) + (1 - won) * np.log(1 - prob))
        return values

    parts = np.column_stack(
        [(model[0] - margin) ** 2, (other[0] - margin) ** 2, loss(model[1]), loss(other[1])]
    )
    out: dict[str, Any] = {
        "rmse_delta": float(np.sqrt(parts[:, 0].mean()) - np.sqrt(parts[:, 1].mean())),
        "log_loss_delta": float(parts[:, 2].mean() - parts[:, 3].mean()),
    }
    rng = np.random.default_rng(SEED)
    for name, cluster in clusters.items():
        _, index = np.unique(cluster, return_inverse=True)
        size = int(np.max(index)) + 1
        sums = np.zeros((size, 5))
        np.add.at(sums, index, np.column_stack([np.ones(len(parts)), parts]))
        pick = rng.integers(0, size, size=(BOOTSTRAP, size))
        draws = sums[pick].sum(axis=1)
        mean = draws[:, 1:] / draws[:, :1]
        rmse = np.sqrt(mean[:, 0]) - np.sqrt(mean[:, 1])
        logloss = mean[:, 2] - mean[:, 3]
        out[f"rmse_ci95_{name}"] = np.percentile(rmse, [2.5, 97.5]).tolist()
        out[f"log_loss_ci95_{name}"] = np.percentile(logloss, [2.5, 97.5]).tolist()
    return out


def verdict(entry: Mapping[str, Any], seasons: Sequence[Mapping[str, Any]], key: str) -> str:
    low, high = entry[f"{key}_ci95_game"]
    signs = [s[f"{key}_delta"] for s in seasons]
    if high < 0 and all(v < 0 for v in signs):
        return "ei_better"
    if low > 0 and all(v > 0 for v in signs):
        return "ei_worse"
    return "inconclusive"


# --- runner ----------------------------------------------------------------------------


@dataclass
class Inputs:
    games: list[Game]
    raw: dict[str, FloatArray]  # per game: ei, ei_oracle, team_rating raw inputs
    detail: list[dict[str, Any]]


def build_inputs(
    games: Sequence[Game],
    history: Sequence[Game],
    index: BoxIndex,
    snapshots: Mapping[int, Sequence[Snapshot]],
    pace: float,
    teams: Sequence[str],
    team_config: tuple[float, float],
) -> Inputs:
    scored = [g for g in games if g.home is not None and g.away is not None]
    ei, oracle, team = [], [], []
    detail: list[dict[str, Any]] = []
    fits: dict[date, tuple[float, dict[str, float]]] = {}
    for g in scored:
        assert g.home is not None and g.away is not None
        eligible = [s for s in snapshots[g.season] if s.as_of <= g.day]
        if not eligible:
            raise ValueError(f"no rating snapshot on or before {g.day}")
        snap = max(eligible, key=lambda s: s.as_of)
        home = project_minutes(index, g.season, g.home, g.day)
        away = project_minutes(index, g.season, g.away, g.day)
        (h_net, h_cold), (a_net, a_cold) = (team_net(p.minutes, snap) for p in (home, away))
        ei.append((h_net - a_net) * pace / 100)
        oh, _ = team_net(oracle_minutes(index, g.game_id, g.home), snap)
        oa, _ = team_net(oracle_minutes(index, g.game_id, g.away), snap)
        oracle.append((oh - oa) * pace / 100)
        if g.day not in fits:
            fits[g.day] = ridge_team_ratings(history, g.day, teams, *team_config)
        ratings = fits[g.day][1]
        team.append(ratings[g.home] - ratings[g.away])
        detail.append(
            {
                "game_id": g.game_id,
                "as_of": snap.as_of.isoformat(),
                "snapshot_id": snap.snapshot_id,
                "cold_minute_share": (h_cold + a_cold) / 2,
                "history_games": min(home.games_used, away.games_used),
                "previous_season_fallback": home.previous_season or away.previous_season,
                "roster_drops": home.roster_drops + away.roster_drops,
            }
        )
    return Inputs(
        scored,
        {"ei": np.asarray(ei), "ei_oracle": np.asarray(oracle), "team_rating": np.asarray(team)},
        detail,
    )


def select_team_config(
    dev: Sequence[Game], history: Sequence[Game], teams: Sequence[str]
) -> tuple[tuple[float, float], dict[str, float]]:
    """Grid choice by development regular-season RMSE of uncalibrated predictions."""
    targets = [g for g in dev if not g.playoff and g.margin is not None and g.home is not None]
    scores = {}
    for half_life in HALF_LIVES:
        for ridge in RIDGES:
            errors, fits = [], {}
            for g in targets:
                assert g.home is not None and g.away is not None and g.margin is not None
                if g.day not in fits:
                    fits[g.day] = ridge_team_ratings(history, g.day, teams, half_life, ridge)
                home_term, ratings = fits[g.day]
                errors.append(home_term + ratings[g.home] - ratings[g.away] - g.margin)
            scores[f"{half_life:g}/{ridge:g}"] = float(np.sqrt(np.mean(np.square(errors))))
    best = min(
        ((h, r) for h in HALF_LIVES for r in RIDGES),
        key=lambda c: (scores[f"{c[0]:g}/{c[1]:g}"], c),
    )
    return best, scores


def fit_calibration(raw: FloatArray, margin: FloatArray) -> dict[str, float]:
    design = np.column_stack([np.ones_like(raw), raw])
    (a, b), *_ = np.linalg.lstsq(design, margin, rcond=None)
    sigma = float(np.sqrt(np.mean((margin - a - b * raw) ** 2)))
    return {"a": float(a), "b": float(b), "sigma": sigma}


def predict_all(inputs: Inputs, calib: Mapping[str, Mapping[str, float]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    n = len(inputs.games)
    hca = calib["hca"]
    out["hca"] = (np.full(n, hca["a"]), normal_cdf(np.full(n, hca["a"] / hca["sigma"])))
    for name, source in (("team_rating", "team_rating"), ("ei", "ei"), ("ei_oracle", "ei")):
        c = calib[source]
        margin = c["a"] + c["b"] * inputs.raw[name]
        out[name] = (margin, normal_cdf(margin / c["sigma"]))
    return out


def score(
    inputs: Inputs, predictions: Mapping[str, tuple[FloatArray, FloatArray]], seasons: Sequence[int]
) -> dict[str, Any]:
    games = inputs.games
    margin = np.asarray([g.margin for g in games], dtype=np.float64)
    season = np.asarray([g.season for g in games])
    playoff = np.asarray([g.playoff for g in games])
    week = np.asarray([(g.day.toordinal() - 1) // 7 for g in games], dtype=np.int64)
    game = np.arange(len(games), dtype=np.int64)
    results: dict[str, Any] = {}
    for role, flag in (("regular", False), ("playoffs", True)):
        role_out: dict[str, Any] = {}
        for label, keep in [("pooled", np.isin(season, seasons) & (playoff == flag))] + [
            (str(s), (season == s) & (playoff == flag)) for s in seasons
        ]:
            if not keep.any():
                continue
            entry: dict[str, Any] = {
                name: metrics(margin[keep], p[0][keep], p[1][keep])
                for name, p in predictions.items()
            }
            entry["ei_minus"] = {
                name: paired(
                    margin[keep],
                    (predictions["ei"][0][keep], predictions["ei"][1][keep]),
                    (p[0][keep], p[1][keep]),
                    {"game": game[keep], "week": week[keep]},
                )
                for name, p in predictions.items()
                if name not in ("ei", "ei_oracle")
            }
            role_out[label] = entry
        results[role] = role_out
    return results


def run(raw: Path, processed: Path, output: Path, protocol_sha256: str) -> dict[str, Any]:
    started = time.perf_counter()
    protocol = verify_protocol(PROTOCOL, protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    addendum = parse_config(ADDENDUM.read_text(encoding="utf-8"))
    logs: dict[int, list[Appearance]] = {}
    log_inputs: dict[str, Any] = {}
    games: list[Game] = []
    game_counts: dict[str, Any] = {}
    for season in LOG_SEASONS:
        if season in LOG_PINS:
            logs[season], log_inputs[str(season)] = checked_logs(raw, season)
            directory = raw / SEASON_PINS[season].label / LOG_PINS[season][0]
        else:
            pin = addendum["box_logs"][str(season)]
            logs[season], log_inputs[str(season)] = outer_logs(raw, season, pin)
            directory = raw / SEASON_PINS[season].label / pin["snapshot"]
        season_games, game_counts[str(season)] = team_games(directory, season)
        games.extend(season_games)
    snapshots: dict[int, list[Snapshot]] = {}
    rating_inputs = {}
    for run_name, digest in RATING_RUNS.items():
        directory = processed / "expected_impact" / run_name
        manifest = read_json(checked_file(directory / "manifest.json", digest))
        path = checked_file(directory / "ratings.csv", manifest["outputs"]["ratings.csv"])
        rating_inputs[run_name] = {"manifest_sha256": digest}
        for snap in load_ratings(path):
            # Block cutoffs of a season run from 1 October to the first playoff date.
            season = snap.as_of.year if snap.as_of.month >= 10 else snap.as_of.year - 1
            if (run_name == "issue-35-v1") == (season in DEV_SEASONS) and snap.as_of.month != 7:
                snapshots.setdefault(season, []).append(snap)
    index = BoxIndex.build(logs)
    teams = sorted({t for g in games for t in g.teams})
    target = [g for g in games if g.season in DEV_SEASONS + EVAL_SEASONS]
    dev = [g for g in target if g.season in DEV_SEASONS]
    with duckdb.connect() as connection:
        pace = float(
            connection.execute(
                "SELECT avg(poss) FROM read_parquet(?) WHERE left(game_id, 3) = '002'",
                [
                    [
                        str(raw / SEASON_PINS[s].label / LOG_PINS[s][0] / TEAM_LOG)
                        for s in DEV_SEASONS
                    ]
                ],
            ).fetchone()[0]  # type: ignore[index]
        )
    team_config, grid = select_team_config(dev, games, teams)
    inputs = build_inputs(target, games, index, snapshots, pace, teams, team_config)
    margin = np.asarray([g.margin for g in inputs.games], dtype=np.float64)
    dev_regular = np.asarray([g.season in DEV_SEASONS and not g.playoff for g in inputs.games])
    calib = {
        "hca": {
            "a": float(margin[dev_regular].mean()),
            "b": 0.0,
            "sigma": float(margin[dev_regular].std()),
        },
        **{
            name: fit_calibration(inputs.raw[name][dev_regular], margin[dev_regular])
            for name in ("team_rating", "ei")
        },
    }
    predictions = predict_all(inputs, calib)
    output.mkdir(parents=True)
    with (output / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        names = list(predictions)
        writer.writerow(
            ["game_id", "season", "date", "playoff", "home", "away", *inputs.detail[0].keys()]
            + [f"{n}_{k}" for n in names for k in ("margin", "home_win_prob")]
        )
        for i, g in enumerate(inputs.games):
            writer.writerow(
                [g.game_id, g.season, g.day.isoformat(), g.playoff, g.home, g.away]
                + list(inputs.detail[i].values())
                + [f"{predictions[n][k][i]:.6f}" for n in names for k in (0, 1)]
            )
    # Predictions are frozen above; evaluation-fold outcomes are scored below.
    results: dict[str, Any] = {
        "selected_team_config": {"half_life": team_config[0], "ridge": team_config[1]},
        "team_grid_dev_rmse": grid,
        "pace": pace,
        "calibration": calib,
        "evaluation": score(inputs, predictions, EVAL_SEASONS),
        "development_in_sample": score(inputs, predictions, DEV_SEASONS),
        "coverage": {
            "games": game_counts,
            "scored_games": len(inputs.games),
            "previous_season_fallback": sum(d["previous_season_fallback"] for d in inputs.detail),
            "mean_cold_minute_share": float(
                np.mean([d["cold_minute_share"] for d in inputs.detail])
            ),
            "roster_drops": sum(d["roster_drops"] for d in inputs.detail),
        },
        "evidence": "retrospective rolling-origin; strict pregame unavailable",
    }
    pooled = results["evaluation"]["regular"]
    seasons = [pooled[str(s)]["ei_minus"]["team_rating"] for s in EVAL_SEASONS]
    results["verdicts"] = {
        key: verdict(pooled["pooled"]["ei_minus"]["team_rating"], seasons, key)
        for key in ("rmse", "log_loss")
    }
    _write_json(output / "results.json", results)
    head, clean = _git_head()
    manifest = {
        "schema_version": 1,
        "version": VERSION,
        "protocol": protocol,
        "code_commit": head,
        "working_tree_clean_at_end": clean,
        "inputs": {"box_logs": log_inputs, "ratings": rating_inputs},
        "versions": _versions(),
        "runtime_seconds": time.perf_counter() - started,
        "peak_memory_mib": _peak_memory_mib(),
        "outputs": {p.name: sha256_file(p) for p in sorted(output.iterdir()) if p.is_file()},
        "private_outputs": ["predictions.csv"],
    }
    _write_json(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    manifest = run(
        args.raw.resolve(), args.processed.resolve(), args.output.resolve(), args.protocol_sha256
    )
    print(json.dumps({"outputs": manifest["outputs"]}))


if __name__ == "__main__":
    main()
