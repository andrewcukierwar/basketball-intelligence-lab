"""Run the registered #38 tracking-enhanced defensive SPM comparison on private pinned inputs."""

from __future__ import annotations

import argparse
import csv
import platform
import resource
import time
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb
import numpy as np

from bil.data.pilot_sources import ATTRIBUTION, sha256_file, utc_now, write_json
from bil.features.box import Appearance
from bil.models.rapm.multiseason import REPO_ROOT, Rows, assemble, fit_context, load_season
from bil.models.rapm.targets import (
    ARTIFACT_LABEL,
    AUTHORIZED_SEASONS,
    REFERENCES,
    TARGET_PINS,
    verify_protocol,
)
from bil.models.spm import (
    CANDIDATES,
    CODES,
    DEFENSE,
    OFFENSE,
    Candidate,
    FloatArray,
    completed_history,
    dated_histories,
    feature_matrix,
    fit_candidate,
    signed_lineup_sum,
)
from bil.models.spm_build import (
    EVIDENCE,
    Labels,
    Opening,
    checked_ages,
    checked_file,
    checked_logs,
    label_scores,
    load_labels,
    read_json,
    target_inputs,
    verify_row_dates,
)
from bil.models.spm_evaluation import (
    VOLUME,
    BoolArray,
    IntArray,
    PriorPair,
    clustered_interval,
    lookup,
    minutes_bands,
    pair_fallback,
    predict_pair,
    sum_by,
)

VERSION = "issue-38-v1"
PROTOCOL = REPO_ROOT / "docs/research/tracking-spm-protocol.md"
ASSETS = REPO_ROOT / "docs/research/nba-tracking-audit-assets.csv"
TRACKING_DIR = Path("defensive-tracking-audit") / "2026-11-23"
SPM_VERSION = "issue-30-v2"
SPM_MANIFEST = "376d89ceb41ca8b90b1e36b3c6a6ad5d9ea09c32acd4e78114c16ec73f96786d"
REFERENCE = "contiguous"
SEASONS = REFERENCES[REFERENCE]
EVALUATED = SEASONS[1:]
GAME_TYPES = ("002", "004")
TRACKING_CODES = (
    "mtov_per_100",
    "mfga_per_100",
    "mfg_pct",
    "mtov_per_100_regular",
    "mfga_per_100_regular",
    "mfg_pct_regular",
)
ALL_CODES = CODES + TRACKING_CODES
TRACK = tuple(range(len(CODES), len(CODES) + 3))
TRACK_REGULAR = tuple(range(len(CODES) + 3, len(ALL_CODES)))
REGULAR_ONLY = "full_tracking_regular_only"
MODELS = {
    "zero": CANDIDATES["zero"],
    "one_stat": CANDIDATES["one_stat"],
    "full": CANDIDATES["full"],
    "full_tracking": Candidate(OFFENSE, DEFENSE + TRACK),
    "tracking_defense_only": Candidate(OFFENSE, TRACK),
    REGULAR_ONLY: Candidate(OFFENSE, DEFENSE + TRACK_REGULAR),
}
TRACKED = {"full_tracking": TRACK, "tracking_defense_only": TRACK, REGULAR_ONLY: TRACK_REGULAR}
COURT_MODELS = ("full", "full_tracking", REGULAR_ONLY)
COURT_NAMES = (
    "context",
    *(f"context_{name}" for name in COURT_MODELS),
    *(f"context_{name}_defense" for name in COURT_MODELS),
)
CONTRASTS = (
    ("context_full_tracking", "context_full"),
    (f"context_{REGULAR_ONLY}", "context_full"),
    ("context_full_tracking_defense", "context_full_defense"),
    ("context_full", "context"),
)


Quad = tuple[float, float, float, float]


def number(value: Any) -> float:
    return float("nan") if value is None else float(value)


@dataclass(frozen=True)
class TrackingGame:
    day: date
    player: int
    playoff: bool
    totals: Quad  # partial possessions, turnovers, FGA, FGM


def tracking_pins(path: Path = ASSETS) -> dict[int, tuple[str, str, int]]:
    """Season start year -> (file, SHA-256, bytes) for the SportsDataverse matchup revisions."""
    pins: dict[int, tuple[str, str, int]] = {}
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row["feed"] == "matchups" and row["provider"] == "SportsDataverse":
                entry = (row["file"], row["sha256"], int(row["bytes"]))
                if pins.setdefault(int(row["start_year"]), entry) != entry:
                    raise ValueError("conflicting tracking pins")
    return pins


def link_tracking(
    totals: Iterable[tuple[str, int, int, Quad]],
    appearances: Sequence[Appearance],
) -> tuple[list[TrackingGame], dict[str, int]]:
    """Join defender-game totals to positive-minute box lines of the same game, player and team."""
    box = {(row.game_id, int(row.player_id)): row for row in appearances if row.minutes_ms > 0}
    games: list[TrackingGame] = []
    drops = {"unlinked": 0, "invalid_quantities": 0}
    for game_id, player, team, values in totals:
        quantities = np.asarray(values, dtype=np.float64)
        if not np.isfinite(quantities).all() or (quantities < 0).any() or values[3] > values[2]:
            drops["invalid_quantities"] += 1
            continue
        row = box.get((game_id, player))
        if row is None or row.team_id != str(team):
            drops["unlinked"] += 1
            continue
        playoff = game_id.startswith("004")
        games.append(TrackingGame(row.game_date, player, playoff, values))
    return games, drops


def checked_tracking(
    raw: Path, season: int, appearances: Sequence[Appearance]
) -> tuple[list[TrackingGame], dict[str, Any]]:
    if season not in SEASONS:
        raise ValueError(f"tracking season is outside the registered scope: {season}")
    name, digest, size = tracking_pins()[season]
    if name != f"game_matchups_{season + 1}.parquet":
        raise ValueError("unexpected tracking asset name")
    path = checked_file(raw / TRACKING_DIR / name, digest)
    if path.stat().st_size != size:
        raise ValueError("tracking asset size mismatch")
    with duckdb.connect() as connection:
        rows = connection.execute(
            """
            select game_id, def_person_id, def_team_id,
                   sum(partial_possessions), sum(matchup_turnovers),
                   sum(matchup_field_goals_attempted), sum(matchup_field_goals_made),
                   count(*)
            from read_parquet(?)
            where substr(game_id, 1, 3) in ('002', '004')
            group by all
            order by game_id, def_person_id, def_team_id
            """,
            [str(path)],
        ).fetchall()
        excluded = connection.execute(
            "select count(*) from read_parquet(?) where substr(game_id, 1, 3) not in ('002', '004')",
            [str(path)],
        ).fetchone()
    games, drops = link_tracking(
        (
            (str(g), int(p), int(t), (number(a), number(b), number(c), number(d)))
            for g, p, t, a, b, c, d, _ in rows
        ),
        appearances,
    )
    box_games: dict[bool, int] = defaultdict(int)
    for row in appearances:
        if row.minutes_ms > 0 and row.game_id[:3] in GAME_TYPES:
            box_games[row.game_id.startswith("004")] += 1
    linked: dict[bool, int] = defaultdict(int)
    for game in games:
        linked[game.playoff] += 1
    return games, {
        "file": name,
        "sha256": digest,
        "pair_rows": sum(int(row[-1]) for row in rows),
        "other_game_type_rows": int(excluded[0]) if excluded else 0,
        "defender_games": len(rows),
        "dropped": drops,
        "linked_defender_games": {"regular": linked[False], "playoffs": linked[True]},
        "positive_minute_box_appearances": {
            "regular": box_games[False],
            "playoffs": box_games[True],
        },
    }


TrackingHistory = dict[int, FloatArray]


def add_tracking(history: TrackingHistory, games: Iterable[TrackingGame]) -> None:
    for game in games:
        totals = history.setdefault(game.player, np.zeros(8))
        totals[:4] += game.totals
        if not game.playoff:
            totals[4:] += game.totals


def tracking_window(games: Iterable[TrackingGame], cutoff: date) -> TrackingHistory:
    history: TrackingHistory = {}
    add_tracking(history, (game for game in games if game.day < cutoff))
    return history


def dated_tracking(
    previous: Iterable[TrackingGame], current: Iterable[TrackingGame], days: Sequence[date]
) -> Iterator[tuple[date, TrackingHistory]]:
    """Yield the mutable running view of games before each day; consume it before advancing."""
    if list(days) != sorted(set(days)):
        raise ValueError("evaluation dates must be unique and increasing")
    grouped: dict[date, list[TrackingGame]] = defaultdict(list)
    for game in (*previous, *current):
        grouped[game.day].append(game)
    dates = iter(sorted(grouped))
    next_date = next(dates, None)
    history: TrackingHistory = {}
    for day in days:
        while next_date is not None and next_date < day:
            add_tracking(history, grouped[next_date])
            next_date = next(dates, None)
        yield day, history


def rates(totals: FloatArray) -> FloatArray:
    """Rows of (possessions, turnovers, FGA, FGM) -> per-100 turnovers, per-100 FGA, FG%."""
    pp, tov, fga, fgm = totals.T
    out = np.full((len(totals), 3), np.nan)
    exposed = pp > 0
    out[exposed, 0] = 100 * tov[exposed] / pp[exposed]
    out[exposed, 1] = 100 * fga[exposed] / pp[exposed]
    shots = fga > 0
    out[shots, 2] = fgm[shots] / fga[shots]
    return out


def tracking_matrix(history: Mapping[int, FloatArray], players: Sequence[int]) -> FloatArray:
    totals = np.zeros((len(players), 8))
    for i, player in enumerate(players):
        if player in history:
            totals[i] = history[player]
    return np.hstack((rates(totals[:, :4]), rates(totals[:, 4:])))


def predict_all(models: Mapping[str, PriorPair], values: FloatArray) -> dict[str, FloatArray]:
    """Tracking candidates fall back to Full defense when all their tracking inputs are null."""
    out = {name: predict_pair(pair, values) for name, pair in models.items()}
    for name, columns in TRACKED.items():
        if name in out:
            none = ~np.isfinite(values[:, columns]).any(axis=1)
            out[name][none, 1] = out["full"][none, 1]
    return out


def fit_fold(
    labels: Labels,
    seasons: Sequence[int],
    logs: Mapping[int, list[Appearance]],
    tracking: Mapping[int, list[TrackingGame]],
    cutoff: date,
    candidates: Mapping[str, Candidate],
) -> tuple[dict[str, PriorPair], dict[str, Any]]:
    values: list[FloatArray] = []
    targets: list[tuple[float, float]] = []
    exposure: list[tuple[float, float]] = []
    support: list[bool] = []
    coverage = {}
    for season in seasons:
        if any(row.game_date >= cutoff for row in logs[season]) or any(
            game.day >= cutoff for game in tracking[season]
        ):
            raise ValueError("a calibration window is incomplete at the fit cutoff")
        history = completed_history(logs[season], cutoff)
        track = tracking_window(tracking[season], cutoff)
        by_player = {player: label for (s, player), label in labels.items() if s == season}
        eligible = sorted(p for p, label in by_player.items() if label.enough() and p in history)
        box, _ = feature_matrix(history, eligible)
        joined = np.hstack((box, tracking_matrix(track, eligible)))
        values.append(joined)
        targets.extend(by_player[p].values for p in eligible)
        exposure.extend(by_player[p].exposure for p in eligible)
        support.extend(by_player[p].forward for p in eligible)
        coverage[str(season)] = {
            "training_rows": len(eligible),
            "all_null_tracking": int((~np.isfinite(joined[:, TRACK]).any(axis=1)).sum()),
            "null_tracking_values": dict(
                zip(
                    TRACKING_CODES,
                    np.isnan(joined[:, len(CODES) :]).sum(axis=0).tolist(),
                    strict=True,
                )
            ),
        }
    x = np.concatenate(values)
    y = np.asarray(targets, dtype=np.float64)
    n = np.asarray(exposure, dtype=np.float64)
    forward = np.asarray(support, dtype=np.bool_)
    return {name: fit_candidate(x, y, n, forward, c) for name, c in candidates.items()}, coverage


def model_record(models: Mapping[str, PriorPair], origin: str, coverage: Any) -> dict[str, Any]:
    return {
        "artifact_label": ARTIFACT_LABEL,
        "evidence_tier": EVIDENCE,
        "origin": origin,
        "coverage": coverage,
        "candidates": {
            name: {
                side: model.record(ALL_CODES)
                for side, model in zip(("offense", "defense"), pair, strict=True)
            }
            for name, pair in models.items()
        },
    }


def check_reference(models: Mapping[str, PriorPair], stored: Mapping[str, Any]) -> None:
    """The refitted box-only Full must equal the stored #30 fit."""
    for side, model in zip(("offense", "defense"), models["full"], strict=True):
        record = stored["candidates"]["full"][side]
        if record["features"] != [CODES[i] for i in model.features]:
            raise ValueError("the #30 Full feature set changed")
        for key in ("coefficients", "mean", "scale"):
            if not np.allclose(getattr(model, key), record[key], rtol=0, atol=1e-10):
                raise ValueError(f"refitted Full differs from #30 ({side} {key})")
        if abs(model.intercept - record["intercept"]) > 1e-10:
            raise ValueError(f"refitted Full differs from #30 ({side} intercept)")


def opening_snapshot(
    season: int,
    day: date,
    previous: Sequence[Appearance],
    previous_tracking: Sequence[TrackingGame],
    models: Mapping[str, PriorPair],
) -> tuple[Opening, FloatArray]:
    history = completed_history(previous, day)
    keys = np.asarray(sorted(history), dtype=np.int64)
    box, minutes = feature_matrix(history, keys.tolist())
    values = np.hstack(
        (box, tracking_matrix(tracking_window(previous_tracking, day), keys.tolist()))
    )
    snapshot = Opening(
        season,
        day,
        keys,
        minutes,
        values[:, VOLUME],
        predict_all(models, values),
        {name: np.array([model.intercept for model in pair]) for name, pair in models.items()},
        {name: pair_fallback(pair, values) for name, pair in models.items()},
    )
    return snapshot, values


@dataclass(frozen=True)
class Court:
    values: FloatArray
    defenders_tracked: IntArray
    missing_box: IntArray
    dated: dict[str, FloatArray]


def predict_court(
    rows: Rows,
    context: FloatArray,
    logs: tuple[Sequence[Appearance], Sequence[Appearance]],
    tracking: tuple[Sequence[TrackingGame], Sequence[TrackingGame]],
    models: Mapping[str, PriorPair],
) -> Court:
    days = [date.fromordinal(int(day)) for day in np.unique(rows.day)]
    values = np.empty((len(rows), len(COURT_NAMES)))
    values[:, 0] = context
    tracked = np.empty(len(rows), dtype=np.int64)
    missing = np.empty(len(rows), dtype=np.int64)
    dated: dict[str, list[Any]] = defaultdict(list)
    box_views = dated_histories(logs[0], logs[1], days)
    track_views = dated_tracking(tracking[0], tracking[1], days)
    for (day, history), (same_day, track) in zip(box_views, track_views, strict=True):
        if day != same_day:
            raise ValueError("box and tracking snapshots are out of step")
        subset = rows.day == day.toordinal()
        ids = np.unique(
            np.concatenate((rows.offense[subset].ravel(), rows.defense[subset].ravel()))
        )
        offense = np.searchsorted(ids, rows.offense[subset])
        defense = np.searchsorted(ids, rows.defense[subset])
        box, minutes = feature_matrix(history, ids.tolist())
        joined = np.hstack((box, tracking_matrix(track, ids.tolist())))
        priors = predict_all(models, joined)
        base = context[subset]
        for k, name in enumerate(COURT_MODELS):
            attack, stop = signed_lineup_sum(priors[name], offense, defense)
            values[subset, 1 + k] = base + attack + stop
            values[subset, 1 + len(COURT_MODELS) + k] = base + stop
        has_tracking = np.isfinite(joined[:, TRACK]).any(axis=1)
        tracked[subset] = has_tracking[defense].sum(axis=1)
        missing[subset] = np.isnan(minutes[offense]).sum(axis=1) + np.isnan(minutes[defense]).sum(
            axis=1
        )
        dated["day"].append(np.full(len(ids), day.toordinal()))
        dated["player_id"].append(ids)
        dated["has_tracking"].append(has_tracking)
        dated["priors"].append(np.stack([priors[name] for name in COURT_MODELS], axis=1))
    return Court(values, tracked, missing, {k: np.concatenate(v) for k, v in dated.items()})


def weekly(rows: Rows, values: FloatArray, mask: BoolArray) -> FloatArray:
    squared = ((values[mask] - rows.y[mask, None]) / 100) ** 2
    _, week = np.unique((rows.day[mask] - 1) // 7, return_inverse=True)  # ordinal 1 was Monday
    size = int(np.max(week)) + 1 if len(week) else 0
    return sum_by(week, np.column_stack((np.ones(int(mask.sum())), squared)), size)


def court_pool(blocks: Sequence[FloatArray]) -> dict[str, Any]:
    blocks = [block for block in blocks if len(block)]
    total = np.concatenate(blocks).sum(axis=0)
    mse = total[1:] / total[0]
    index = {name: i for i, name in enumerate(COURT_NAMES)}
    return {
        "possessions": int(total[0]),
        "mse": dict(zip(COURT_NAMES, mse.tolist(), strict=True)),
        "deltas": {
            f"{first}_minus_{second}": {
                "delta": float(mse[index[first]] - mse[index[second]]),
                "interval": clustered_interval(blocks, index[first], index[second], rmse=False),
            }
            for first, second in CONTRASTS
        },
    }


def k0_contrasts(errors: Mapping[str, FloatArray], players: IntArray) -> dict[str, Any]:
    """RMSE of each candidate minus Full by side, with player-cluster intervals."""
    if not len(players):
        return {"player_seasons": 0}
    ids, inverse = np.unique(players, return_inverse=True)
    out: dict[str, Any] = {
        "player_seasons": len(players),
        "distinct_players": len(ids),
        "side_order": ["offense", "defense", "total"],
        "rmse": {
            name: np.sqrt(np.mean(value**2, axis=0)).tolist() for name, value in errors.items()
        },
        "minus_full": {},
    }
    for name in errors:
        if name == "full":
            continue
        contrasts = []
        for side in range(3):
            stacked = np.column_stack(
                (np.ones(len(players)), errors[name][:, side] ** 2, errors["full"][:, side] ** 2)
            )
            delta = np.sqrt(stacked[:, 1].mean()) - np.sqrt(stacked[:, 2].mean())
            cluster = sum_by(inverse, stacked, len(ids))
            contrasts.append(
                {"delta": float(delta), "interval": clustered_interval([cluster], 0, 1, rmse=True)}
            )
        out["minus_full"][name] = contrasts
    return out


def k0_slices(
    snapshot: Opening, values: FloatArray, labels: Labels, births: Mapping[int, date]
) -> tuple[dict[str, Any], IntArray, dict[str, FloatArray], dict[str, BoolArray]]:
    summary, players, errors = label_scores(snapshot, labels, births)
    indices = lookup(snapshot.players, players)
    known = indices < len(snapshot.players)
    padded = np.vstack((values, np.full(values.shape[1], np.nan)))[indices]
    full_defense = np.append(snapshot.predictions["full"][:, 1], snapshot.fallback["full"][1])[
        indices
    ]
    exposure = np.asarray(
        [min(labels[snapshot.season, int(player)].exposure) for player in players]
    )
    masks = {
        "paired_tracking": np.isfinite(padded[:, TRACK]).any(axis=1),
        "all": np.ones(len(players), dtype=bool),
        "no_opening_history": ~known,
        "defensive_specialists": full_defense >= np.quantile(full_defense, 0.8),
        "label_exposure_250_to_999": exposure < 1000,
        "label_exposure_1000_plus": exposure >= 1000,
    }
    for band, mask in minutes_bands(np.append(snapshot.minutes, np.nan)[indices]).items():
        masks[f"minutes_{band}"] = mask
    return summary, players, errors, masks


def spm_reference(processed: Path) -> tuple[Path, dict[str, Any]]:
    directory = processed / "spm" / SPM_VERSION
    manifest = read_json(checked_file(directory / "manifest.json", SPM_MANIFEST))
    for season in EVALUATED:
        name = f"{REFERENCE}-{season}/fit.json"
        checked_file(directory / name, manifest["outputs"][name])
    checked_file(directory / "results.json", manifest["outputs"]["results.json"])
    return directory, manifest


def run(raw: Path, processed: Path, output: Path, protocol_sha256: str) -> None:
    started = time.monotonic()
    protocol = verify_protocol(PROTOCOL, protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    target_dir, registration, frozen, calendar, digests = target_inputs(processed)
    training = load_labels(target_dir / "targets.csv", evaluation=False)
    spm_dir, _ = spm_reference(processed)
    logs, log_inputs, tracking, tracking_inputs = {}, {}, {}, {}
    for season in SEASONS:
        logs[season], log_inputs[str(season)] = checked_logs(raw, season)
        tracking[season], tracking_inputs[str(season)] = checked_tracking(raw, season, logs[season])
    births, age_inputs = checked_ages(raw)
    rules = registration[REFERENCE]
    report: dict[str, Any] = {
        "artifact_label": ARTIFACT_LABEL,
        "evidence_tier": EVIDENCE,
        "version": VERSION,
        "strict": {"status": "unavailable", "eligible": 0, "reason": "capture-bound revisions"},
        "window": {
            "documented": "2017-18 through 2022-23",
            "used_seasons": list(SEASONS),
            "unused": {"2017": "no #28 target or #30 box pin in the contiguous reference"},
            "playoffs": "pooled in the primary; regular-only sensitivity",
        },
        "tracking_coverage": tracking_inputs,
        "folds": {},
    }
    k0_errors: list[tuple[IntArray, dict[str, FloatArray], dict[str, BoolArray]]] = []
    court_blocks: dict[str, list[FloatArray]] = defaultdict(list)
    row_inputs: dict[str, Any] = {}
    with TemporaryDirectory(prefix=".tracking-spm-", dir=output.parent) as sandbox:
        stage = Path(sandbox) / "results"
        stage.mkdir()
        cache: dict[int, Rows] = {}

        def canonical(season: int) -> Rows:
            if season not in cache:
                load = load_season(
                    processed, season, AUTHORIZED_SEASONS, Path(sandbox), TARGET_PINS
                )
                row_inputs[str(season)] = {
                    "row_manifest_sha256": load.pin.row_manifest_sha256,
                    "pilot_manifest_sha256": load.pin.pilot_manifest_sha256,
                }
                cache[season] = assemble([load])
                verify_row_dates(cache[season], season, calendar)
            return cache[season]

        frozen_folds = {}
        for fold in rules["folds"]:
            season = fold["evaluation_season"]
            origin = fold["training_target_set"]
            record = frozen[origin]
            cutoff = date.fromisoformat(record["cutoff"])
            first_day = calendar[season][0]
            earlier = record["closes_season"]
            if (
                cutoff > first_day
                or earlier != season - 1
                or fold["training_seasons"] != record["seasons"]
            ):
                raise ValueError("a fit origin overlaps the evaluation season")
            models, coverage = fit_fold(
                training[origin], record["seasons"], logs, tracking, cutoff, MODELS
            )
            check_reference(models, read_json(spm_dir / f"{REFERENCE}-{season}" / "fit.json"))
            snapshot, values = opening_snapshot(
                season, first_day, logs[earlier], tracking[earlier], models
            )
            previous_rows = canonical(earlier)
            if np.any(previous_rows.day >= first_day.toordinal()):
                raise ValueError("a context row is not strictly earlier than the evaluation season")
            intercept, gamma = fit_context(
                previous_rows.context, previous_rows.y, np.ones(len(previous_rows))
            )
            rows = canonical(season)
            court = predict_court(
                rows,
                intercept + rows.context @ gamma,
                (logs[earlier], logs[season]),
                (tracking[earlier], tracking[season]),
                models,
            )
            directory = stage / f"{REFERENCE}-{season}"
            directory.mkdir()
            np.savez_compressed(
                directory / "opening.npz",
                player_id=snapshot.players,
                values=values,
                candidates=tuple(snapshot.predictions),
                priors=np.stack(list(snapshot.predictions.values()), axis=1),
            )
            np.savez_compressed(
                directory / "dated_priors.npz",
                candidates=COURT_MODELS,
                day=court.dated["day"],
                player_id=court.dated["player_id"],
                has_tracking=court.dated["has_tracking"],
                priors=court.dated["priors"],
            )
            np.savez_compressed(
                directory / "court_predictions.npz",
                game_ids=rows.game_ids,
                game=rows.game,
                possession_seq=rows.possession_seq,
                names=COURT_NAMES,
                points_per_100=court.values,
                defenders_tracked=court.defenders_tracked,
            )
            fit = model_record(models, origin, coverage)
            write_json(directory / "fit.json", fit)
            frozen_folds[season] = (snapshot, values, rows, court, fit, coverage, origin, cutoff)

        # Every prediction above is written before any label or outcome is scored.
        for season, (_, _, rows, court, _, _, _, _) in frozen_folds.items():
            court_blocks["all"].append(weekly(rows, court.values, np.ones(len(rows), dtype=bool)))
        reproduced = court_pool(court_blocks["all"])["mse"]["context_full"]
        stored = read_json(spm_dir / "results.json")["court_common_modern_pool"][REFERENCE]["mse"]
        if not np.isclose(reproduced, stored["context_full"], rtol=1e-9, atol=0):
            raise ValueError(f"context + Full does not reproduce #30: {reproduced}")
        report["reference_reproduction"] = {"context_full_mse": reproduced, "matches_30": True}

        evaluation = load_labels(target_dir / "evaluation_labels.csv", evaluation=True)
        truth = evaluation[rules["outer_seasons_use"]]
        for season, (
            snapshot,
            values,
            rows,
            court,
            fit,
            coverage,
            origin,
            cutoff,
        ) in frozen_folds.items():
            summary, players, errors, masks = k0_slices(snapshot, values, truth, births[season])
            k0_errors.append((players, errors, masks))
            slices = {
                "all": np.ones(len(rows), dtype=bool),
                "regular": ~rows.playoff,
                "playoffs": rows.playoff,
                "all_defenders_tracked": court.defenders_tracked == 5,
                "some_defender_untracked": court.defenders_tracked < 5,
                "some_player_without_box_history": court.missing_box > 0,
            }
            season_court = {}
            for name, mask in slices.items():
                block = weekly(rows, court.values, mask)
                if name != "all":
                    court_blocks[name].append(block)
                season_court[name] = court_pool([block]) if mask.any() else {"possessions": 0}
            fallback = {
                name: int((~np.isfinite(values[:, cols]).any(axis=1)).sum())
                for name, cols in TRACKED.items()
            }
            report["folds"][str(season)] = {
                "origin": origin,
                "fit_cutoff": cutoff.isoformat(),
                "training": coverage,
                "opening_players": len(snapshot.players),
                "opening_tracking_fallback": fallback,
                "k0": {
                    key: k0_contrasts({n: e[m] for n, e in errors.items()}, players[m])
                    for key, m in masks.items()
                },
                "k0_label_scores": summary,
                "court": season_court,
            }
        pooled_players = np.concatenate([p for p, _, _ in k0_errors])
        report["k0_pool"] = {
            key: k0_contrasts(
                {
                    name: np.concatenate([e[name][m[key]] for _, e, m in k0_errors])
                    for name in MODELS
                },
                np.concatenate([p[m[key]] for p, _, m in k0_errors]),
            )
            for key in k0_errors[0][2]
        }
        report["k0_pool"]["player_seasons_all"] = len(pooled_players)
        report["court_pool"] = {name: court_pool(blocks) for name, blocks in court_blocks.items()}

        final_origin = rules["outer_seasons_use"]
        final_record = frozen[final_origin]
        final, final_coverage = fit_fold(
            training[final_origin],
            final_record["seasons"],
            logs,
            tracking,
            date.fromisoformat(final_record["cutoff"]),
            {name: MODELS[name] for name in ("full", "full_tracking")},
        )
        write_json(
            stage / "final_contiguous_fit.json", model_record(final, final_origin, final_coverage)
        )
        write_json(stage / "results.json", report)
        outputs = {
            str(path.relative_to(stage)): sha256_file(path)
            for path in sorted(stage.rglob("*"))
            if path.is_file()
        }
        write_json(
            stage / "manifest.json",
            {
                "schema_version": 1,
                "version": VERSION,
                "generated_at": utc_now(),
                "artifact_label": ARTIFACT_LABEL,
                "evidence_tier": EVIDENCE,
                "data_attribution": ATTRIBUTION,
                "protocol": protocol,
                "outputs": outputs,
                "inputs": {
                    "target_outputs": digests,
                    "spm_reference_manifest_sha256": SPM_MANIFEST,
                    "box_logs": log_inputs,
                    "tracking": tracking_inputs,
                    "canonical_rows": row_inputs,
                    "age": age_inputs,
                },
                "versions": {
                    "python": platform.python_version(),
                    "numpy": np.__version__,
                    "duckdb": duckdb.__version__,
                    "bil": version("basketball-intelligence-lab"),
                },
                "runtime_seconds": time.monotonic() - started,
                "peak_rss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            },
        )
        stage.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    run(args.raw.resolve(), args.processed.resolve(), args.output.resolve(), args.protocol_sha256)


if __name__ == "__main__":
    main()
