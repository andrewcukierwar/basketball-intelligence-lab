"""EI refresh cadence against the daily team rating (#129).

Registered protocol: ``docs/research/refresh-cadence-protocol.md``. Everything except the refresh
cadence is the frozen #36 EI and #39 team-outcome path:

- the W2 window, context offset, 8,000/8,000 penalties and final SPM fit;
- the #39 pregame minutes, pace and team-rating configuration;
- the #39 frozen calibration as the matched calibration.

Cadences in each 2023–24 and 2024–25 season:

- ``block``: the #36 cutoffs (1 Oct, 1 Dec, 1 Feb, 1 Apr, first playoff day);
- ``weekly``: 1 Oct and every Monday through the season's last game;
- ``daily``: 1 Oct and every game day;
- ``daily_box``: the SPM prior refreshed daily from box logs, with the on-court deviation,
  context coefficients and intercept held at the latest block fit.

The block cadence must reproduce the published #36 possession predictions and the #39 game
margins, or the run stops. A strict season-aware calibration (#136 post-freeze construction, fit
on 2023–24, scored on 2024–25) is reported as a separate comparison.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bil.data.pilot_sources import sha256_file
from bil.features.box import Appearance
from bil.models.calibration_lineage import (
    PARENTS,
    TEAM_MANIFEST,
    TEAM_RUN,
    Example,
    Parent,
    fit_post_freeze,
    load_calibration,
    write_examples,
)
from bil.models.expected_impact import (
    SPM_MANIFEST,
    SPM_RUN,
    WINDOW,
    Prepared,
    as_of_ratings,
    cold_prior,
    fit_informed,
    predict_informed,
    prepare,
    spm_fit,
)
from bil.models.expected_impact_outer import ADDENDUM, OUTER_SEASONS, ROW_SEASONS, outer_logs
from bil.models.expected_impact_outer import parse_config as parse_addendum
from bil.models.rapm.baseline import _peak_memory_mib
from bil.models.rapm.multiseason import (
    REPO_ROOT,
    SEASON_PINS,
    Analysis,
    PlayerFit,
    Rows,
    Scenario,
    _git_head,
    _prepare,
    _versions,
    _write_json,
    paired_delta,
    predict,
    season_blocks,
    week_clusters,
)
from bil.models.rapm.targets import verify_protocol
from bil.models.spm_build import LOG_PINS, checked_file, checked_logs, read_json
from bil.models.team_outcomes import LOG_SEASONS as TEAM_LOG_SEASONS
from bil.models.team_outcomes import (
    BoxIndex,
    Game,
    Snapshot,
    metrics,
    normal_cdf,
    paired,
    project_minutes,
    ridge_team_ratings,
    team_games,
    team_net,
    verdict,
)

FloatArray = NDArray[np.float64]

VERSION = "issue-129-v1"
PROTOCOL = REPO_ROOT / "docs/research/refresh-cadence-protocol.md"
CADENCES = ("block", "weekly", "daily", "daily_box")
EI_RUN = "issue-36-v1"
REPRODUCTION_TOLERANCE = {"possession": 1e-6, "margin": 1e-4}
STRICT_FIT = (date(2023, 10, 1), date(2024, 7, 1))  # post-freeze calibration season, cutoff


# --- cutoffs ---------------------------------------------------------------------------


def cutoffs(
    cadence: str, season: int, block_cutoffs: Sequence[date], days: Sequence[date]
) -> list[date]:
    """Refresh dates for one season. ``days`` are the season's game days."""
    start = date(season, 10, 1)
    last = max(days)
    if cadence == "block":
        return sorted(block_cutoffs)
    if cadence == "weekly":
        monday = start + timedelta(days=(7 - start.weekday()) % 7 or 7)
        weeks = []
        while monday <= last:
            weeks.append(monday)
            monday += timedelta(days=7)
        return [start, *weeks]
    if cadence in ("daily", "daily_box"):
        return sorted({start, *(d for d in days if d >= start)})
    raise ValueError(f"unknown cadence {cadence}")


def latest(values: Sequence[date], day: date) -> date:
    eligible = [v for v in values if v <= day]
    if not eligible:
        raise ValueError(f"no refresh on or before {day}")
    return max(eligible)


# --- EI refreshes ----------------------------------------------------------------------


@dataclass
class Refresh:
    prepared: Prepared
    fit: PlayerFit
    snapshot: Snapshot
    seconds: float


def _snapshot(prepared: Prepared, fit: PlayerFit, analysis: Analysis, label: str) -> Snapshot:
    rated = as_of_ratings(
        prepared, fit, analysis.design, {"cutoff": prepared.cutoff, "label": label}
    )
    assert rated.cold is not None
    total = {int(p): float(r.sum()) for p, r in zip(rated.player_ids, rated.rating, strict=True)}
    return Snapshot(prepared.cutoff, total, float(rated.cold.sum()), rated.snapshot_id)


def _box_only(prepared: Prepared, base: Refresh, analysis: Analysis) -> tuple[Snapshot, PlayerFit]:
    """Daily prior with the deviation, context and intercept of the latest block fit."""
    fit = base.fit
    # Ratings are prior + deviation; the deviation is indexed by design player.
    m = analysis.design.size
    deviation = np.zeros((prepared.player_ids.size, 2))
    deviation[:m, 0], deviation[:m, 1] = fit.effects[:m], fit.effects[m:]
    keep = prepared.box_history.copy()
    keep[:m] |= fit.exposure > 0
    cold = float(cold_prior(prepared.spm).sum())
    total = {
        int(p): float(prepared.priors[i].sum() + deviation[i].sum())
        for i, p in enumerate(prepared.player_ids)
        if keep[i]
    }
    digest = hashlib.sha256(
        f"{prepared.cutoff}|{base.snapshot.snapshot_id}".encode()
        + np.ascontiguousarray(prepared.priors).tobytes()
    ).hexdigest()
    return Snapshot(prepared.cutoff, total, cold, digest), fit


def refreshes(
    analysis: Analysis,
    spm: Any,
    logs: Mapping[int, Sequence[Appearance]],
    plan: Mapping[str, Mapping[int, list[date]]],
    penalties: tuple[float, float],
) -> tuple[dict[str, dict[date, Refresh]], dict[str, FloatArray]]:
    """Fit every refresh; return refreshes and possession predictions per cadence."""
    rows = analysis.rows
    out: dict[str, dict[date, Refresh]] = {c: {} for c in CADENCES}
    predictions = {c: np.full(len(rows), np.nan) for c in CADENCES}
    cache: dict[date, tuple[Prepared, float]] = {}
    for season in OUTER_SEASONS:
        in_season = rows.season == season
        for cadence in ("block", "weekly", "daily", "daily_box"):
            dates = plan[cadence][season]
            bounds = [*dates[1:], None]
            for cutoff, end in zip(dates, bounds, strict=True):
                started = time.perf_counter()
                if cutoff not in cache:
                    t0 = time.perf_counter()
                    p = prepare(analysis, cutoff, spm, logs[season - 1], logs[season])
                    cache[cutoff] = (p, time.perf_counter() - t0)
                p, prep_seconds = cache[cutoff]
                scored_mask = in_season & (rows.day >= cutoff.toordinal())
                if end is not None:
                    scored_mask &= rows.day < end.toordinal()
                scored = np.flatnonzero(scored_mask).astype(np.int64)
                if cadence == "daily_box":
                    block_day = latest(plan["block"][season], cutoff)
                    base = out["block"][block_day]
                    snapshot, fit = _box_only(p, base, analysis)
                    if scored.size:
                        b = base.prepared
                        predictions[cadence][scored] = (
                            predict(fit, analysis.design, scored)
                            + rows.context[scored] @ b.gamma
                            + p.offset[scored]
                        )
                    out[cadence][cutoff] = Refresh(
                        p, fit, snapshot, time.perf_counter() - started + prep_seconds
                    )
                    continue
                fit = fit_informed(analysis, p, *penalties, f"{cadence}:{cutoff}")
                if scored.size:
                    overlap = np.intersect1d(rows.game[p.index], rows.game[scored])
                    if overlap.size:
                        raise ValueError(f"{cadence} {cutoff} scores a game inside its window")
                    predictions[cadence][scored] = predict_informed(analysis, p, fit, scored)["ei"]
                snapshot = _snapshot(p, fit, analysis, cadence)
                out[cadence][cutoff] = Refresh(
                    p, fit, snapshot, time.perf_counter() - started + prep_seconds
                )
    return out, predictions


# --- team inputs -----------------------------------------------------------------------


def game_inputs(
    games: Sequence[Game],
    history: Sequence[Game],
    index: BoxIndex,
    ei: Mapping[str, Mapping[date, Refresh]],
    team_plan: Mapping[str, Mapping[int, list[date]]],
    pace: float,
    teams: Sequence[str],
    team_config: tuple[float, float],
) -> tuple[dict[str, FloatArray], list[dict[str, Any]]]:
    """Raw home-minus-away inputs per game for every EI and team cadence."""
    raw: dict[str, list[float]] = {f"ei_{c}": [] for c in CADENCES}
    raw.update({f"team_{c}": [] for c in ("block", "weekly", "daily")})
    detail: list[dict[str, Any]] = []
    fits: dict[date, dict[str, float]] = {}
    for g in games:
        assert g.home is not None and g.away is not None
        home = project_minutes(index, g.season, g.home, g.day)
        away = project_minutes(index, g.season, g.away, g.day)
        row: dict[str, Any] = {"game_id": g.game_id}
        for cadence in CADENCES:
            day = latest(list(ei[cadence]), g.day)
            snap = ei[cadence][day].snapshot
            (h, h_cold), (a, a_cold) = (team_net(p.minutes, snap) for p in (home, away))
            raw[f"ei_{cadence}"].append((h - a) * pace / 100)
            row[f"ei_{cadence}_as_of"] = day.isoformat()
            row[f"ei_{cadence}_snapshot"] = snap.snapshot_id
            row[f"ei_{cadence}_cold_share"] = (h_cold + a_cold) / 2
        for cadence in ("block", "weekly", "daily"):
            day = g.day if cadence == "daily" else latest(team_plan[cadence][g.season], g.day)
            if day not in fits:
                fits[day] = ridge_team_ratings(history, day, teams, *team_config)[1]
            raw[f"team_{cadence}"].append(fits[day][g.home] - fits[day][g.away])
            row[f"team_{cadence}_as_of"] = day.isoformat()
        detail.append(row)
    return {k: np.asarray(v) for k, v in raw.items()}, detail


def calibrated(
    raw: Mapping[str, FloatArray], calib: Mapping[str, Mapping[str, float]]
) -> dict[str, tuple[FloatArray, FloatArray]]:
    out = {}
    for name, values in raw.items():
        c = calib["ei" if name.startswith("ei_") else "team_rating"]
        margin = c["a"] + c["b"] * values
        out[name] = (margin, normal_cdf(margin / c["sigma"]))
    return out


# --- scoring ---------------------------------------------------------------------------

CONTRASTS = {
    # name: (model, comparator)
    "weekly_vs_block": ("ei_weekly", "ei_block"),
    "daily_vs_block": ("ei_daily", "ei_block"),
    "box_refresh": ("ei_daily_box", "ei_block"),
    "on_court_refresh": ("ei_daily", "ei_daily_box"),
    "block_vs_team_daily": ("ei_block", "team_daily"),
    "weekly_vs_team_daily": ("ei_weekly", "team_daily"),
    "daily_vs_team_daily": ("ei_daily", "team_daily"),
    "daily_box_vs_team_daily": ("ei_daily_box", "team_daily"),
    "block_vs_team_block": ("ei_block", "team_block"),
    "weekly_vs_team_weekly": ("ei_weekly", "team_weekly"),
    "team_block_vs_team_daily": ("team_block", "team_daily"),
}
PRIMARY = ("weekly_vs_block", "daily_vs_block", "weekly_vs_team_daily", "daily_vs_team_daily")


def score_games(
    games: Sequence[Game],
    predictions: Mapping[str, tuple[FloatArray, FloatArray]],
    seasons: Sequence[int],
) -> dict[str, Any]:
    margin = np.asarray([g.margin for g in games], dtype=np.float64)
    season = np.asarray([g.season for g in games])
    playoff = np.asarray([g.playoff for g in games])
    week = np.asarray([(g.day.toordinal() - 1) // 7 for g in games], dtype=np.int64)
    game = np.arange(len(games), dtype=np.int64)
    results: dict[str, Any] = {}
    for role, flag in (("regular", False), ("playoffs", True)):
        role_out: dict[str, Any] = {}
        groups = [("pooled", np.isin(season, seasons) & (playoff == flag))]
        groups += [(str(s), (season == s) & (playoff == flag)) for s in seasons]
        for label, keep in groups:
            if not keep.any():
                continue
            entry: dict[str, Any] = {
                name: {k: v for k, v in metrics(margin[keep], p[0][keep], p[1][keep]).items()}
                for name, p in predictions.items()
            }
            entry["contrasts"] = {
                name: paired(
                    margin[keep],
                    (predictions[a][0][keep], predictions[a][1][keep]),
                    (predictions[b][0][keep], predictions[b][1][keep]),
                    {"game": game[keep], "week": week[keep]},
                )
                for name, (a, b) in CONTRASTS.items()
            }
            role_out[label] = entry
        results[role] = role_out
    if len(seasons) > 1:
        regular = results["regular"]
        per_season = [regular[str(s)]["contrasts"] for s in seasons]
        results["verdicts"] = {
            name: {
                key: verdict(
                    regular["pooled"]["contrasts"][name], [p[name] for p in per_season], key
                )
                for key in ("rmse", "log_loss")
            }
            for name in CONTRASTS
        }
        results["week_interval_sensitivity"] = {
            name: {
                key: _week_verdict(regular["pooled"]["contrasts"][name], key)
                for key in ("rmse", "log_loss")
            }
            for name in CONTRASTS
        }
    return results


def _week_verdict(entry: Mapping[str, Any], key: str) -> str:
    low, high = entry[f"{key}_ci95_week"]
    return "below_zero" if high < 0 else "above_zero" if low > 0 else "includes_zero"


def closes_gap(verdicts: Mapping[str, Mapping[str, str]], cadence: str) -> bool:
    """Registered criterion: finer refresh beats block and is no longer worse than the team."""
    return (
        verdicts[f"{cadence}_vs_block"]["rmse"] == "ei_better"
        and verdicts[f"{cadence}_vs_team_daily"]["rmse"] != "ei_worse"
    )


def score_possessions(
    rows: Rows, keep: NDArray[np.bool_], predictions: Mapping[str, FloatArray]
) -> dict[str, Any]:
    index = np.flatnonzero(keep)
    y = rows.y[index]
    clusters = {"game": rows.game[index], "week": week_clusters(rows.day[index])}
    out: dict[str, Any] = {
        "possessions": int(index.size),
        "mse": {c: float(np.mean((p[index] - y) ** 2)) for c, p in predictions.items()},
    }
    out["delta_vs_block"] = {
        c: paired_delta(y, predictions[c][index], predictions["block"][index], clusters)
        for c in CADENCES
        if c != "block"
    }
    out["on_court_refresh"] = paired_delta(
        y, predictions["daily"][index], predictions["daily_box"][index], clusters
    )
    return out


# --- strict season-aware calibration ---------------------------------------------------


def strict_calibrations(
    games: Sequence[Game],
    raw: Mapping[str, FloatArray],
    detail: Sequence[Mapping[str, Any]],
    stage: Path,
    ei_manifest: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Parent]]:
    """#136 post-freeze calibration per cadence: 2023–24 regular-season examples, cutoff 1 July."""
    start, cutoff = STRICT_FIT
    registry = dict(PARENTS)
    out: dict[str, dict[str, Any]] = {}
    for cadence in CADENCES:
        team_key = "team_daily" if cadence == "daily_box" else f"team_{cadence}"
        ei_parent = Parent(
            f"ei:{VERSION}-{cadence}", EI_RUN, ei_manifest, "#35 W2 8000/8000", date(2023, 6, 30)
        )
        team_parent = Parent(
            f"team_rating:{VERSION}-{cadence}",
            TEAM_RUN,
            TEAM_MANIFEST,
            "#39 half-life 60, ridge 4",
            date(2023, 6, 30),
        )
        registry[ei_parent.parent_id] = ei_parent
        registry[team_parent.parent_id] = team_parent
        examples = []
        for i, g in enumerate(games):
            if g.playoff or not start <= g.day < cutoff or g.margin is None:
                continue
            for source, parent, key in (
                ("ei", ei_parent, f"ei_{cadence}"),
                ("team_rating", team_parent, team_key),
            ):
                as_of = date.fromisoformat(detail[i][f"{key}_as_of"])
                examples.append(
                    Example(
                        source,
                        g.game_id,
                        g.day,
                        float(raw[key][i]),
                        g.margin,
                        parent.parent_id,
                        as_of,
                        str(detail[i].get(f"{key}_snapshot", f"team@{as_of}")),
                        VERSION,
                    )
                )
        directory = stage / f"calibration_{cadence}"
        directory.mkdir()
        kept = [e for e in examples if e.game_day < cutoff]
        write_examples(directory / "examples.csv", kept)
        _write_json(directory / "calibration.json", fit_post_freeze(kept, registry, cutoff))
        out[cadence] = load_calibration(directory, date(2024, 10, 1), registry)
    return out, registry


# --- runner ----------------------------------------------------------------------------


def _published_possessions(processed: Path) -> dict[str, NDArray[Any]]:
    directory = processed / "expected_impact" / EI_RUN
    manifest = read_json(directory / "manifest.json")
    path = checked_file(directory / "predictions.npz", manifest["outputs"]["predictions.npz"])
    with np.load(path) as data:
        return {k: data[k] for k in ("block", "game_id", "possession_seq", "ei")}


def _published_games(processed: Path) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    directory = processed / "team_outcomes" / TEAM_RUN
    manifest = read_json(checked_file(directory / "manifest.json", TEAM_MANIFEST))
    results = read_json(
        checked_file(directory / "results.json", manifest["outputs"]["results.json"])
    )
    path = checked_file(directory / "predictions.csv", manifest["outputs"]["predictions.csv"])
    with path.open(newline="", encoding="utf-8") as handle:
        rows = {r["game_id"]: r for r in csv.DictReader(handle)}
    margins = {
        gid: {"ei": float(r["ei_margin"]), "team": float(r["team_rating_margin"])}
        for gid, r in rows.items()
    }
    return results, margins


def run(raw: Path, processed: Path, output: Path, protocol_sha256: str) -> dict[str, Any]:
    started = time.perf_counter()
    protocol = verify_protocol(PROTOCOL, protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    addendum = parse_addendum(ADDENDUM.read_text(encoding="utf-8"))
    ei_config = addendum["models"]["ei"]
    penalties = (float(ei_config["offense_ridge"]), float(ei_config["defense_ridge"]))
    if ei_config["window"] != WINDOW.name:
        raise ValueError("the #36 EI window is not W2")
    team_results, team_margins = _published_games(processed)
    calib = team_results["calibration"]
    pace = float(team_results["pace"])
    team_config = (
        float(team_results["selected_team_config"]["half_life"]),
        float(team_results["selected_team_config"]["ridge"]),
    )
    spm_dir = processed / "spm" / SPM_RUN
    checked_file(spm_dir / "manifest.json", SPM_MANIFEST)
    spm = spm_fit(
        read_json(checked_file(spm_dir / addendum["spm_fit"], addendum["spm_fit_sha256"]))
    )
    logs: dict[int, list[Appearance]] = {}
    games: list[Game] = []
    for season in TEAM_LOG_SEASONS:
        if season in LOG_PINS:
            logs[season], _ = checked_logs(raw, season)
            directory = raw / SEASON_PINS[season].label / LOG_PINS[season][0]
        else:
            pin = addendum["box_logs"][str(season)]
            logs[season], _ = outer_logs(raw, season, pin)
            directory = raw / SEASON_PINS[season].label / pin["snapshot"]
        games.extend(team_games(directory, season)[0])
    index = BoxIndex.build(logs)
    teams = sorted({t for g in games for t in g.teams})
    scored_games = [
        g for g in games if g.season in OUTER_SEASONS and g.home is not None and g.away is not None
    ]
    ei_manifest = sha256_file(processed / "expected_impact" / EI_RUN / "manifest.json")
    with TemporaryDirectory(prefix=".cadence-", dir=output.parent) as sandbox:
        stage = Path(sandbox) / "results"
        stage.mkdir()
        _, rows, design, row_inputs = _prepare(processed, ROW_SEASONS, ROW_SEASONS, stage)
        log: list[dict[str, Any]] = []
        analysis = Analysis(
            rows, design, Scenario("primary", np.ones(len(rows), dtype=bool)), [], log
        )
        plan: dict[str, dict[int, list[date]]] = {c: {} for c in CADENCES}
        for season in OUTER_SEASONS:
            blocks = [b.cutoff for b in season_blocks(rows, season)]
            days = sorted({g.day for g in games if g.season == season})
            for cadence in CADENCES:
                plan[cadence][season] = cutoffs(cadence, season, blocks, days)
        fitted, possession = refreshes(analysis, spm, logs, plan, penalties)
        raw_inputs, detail = game_inputs(
            scored_games, games, index, fitted, plan, pace, teams, team_config
        )
        frozen = calibrated(raw_inputs, calib)
        strict, registry = strict_calibrations(scored_games, raw_inputs, detail, stage, ei_manifest)
        strict_predictions = {}
        for name, values in raw_inputs.items():
            cadence = name.split("_", 1)[1]
            source = "ei" if name.startswith("ei_") else "team_rating"
            c = strict[cadence]["sources"][source]
            margin = c["a"] + c["b"] * values
            strict_predictions[name] = (margin, normal_cdf(margin / c["sigma"]))
        with (stage / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            names = list(frozen)
            writer.writerow(
                ["game_id", "season", "date", "playoff", "home", "away"]
                + [f"{n}_raw" for n in names]
                + [f"{n}_margin" for n in names]
            )
            for i, g in enumerate(scored_games):
                writer.writerow(
                    [g.game_id, g.season, g.day.isoformat(), g.playoff, g.home, g.away]
                    + [f"{raw_inputs[n][i]:.6f}" for n in names]
                    + [f"{frozen[n][0][i]:.6f}" for n in names]
                )
        np.savez_compressed(stage / "possession_predictions.npz", allow_pickle=False, **possession)
        # Every prediction is fixed above. Reproduction gates, then scoring.
        published = _published_possessions(processed)
        order = np.concatenate(
            [np.flatnonzero(b.scored) for s in OUTER_SEASONS for b in season_blocks(rows, s)]
        )
        possession_gap = float(np.max(np.abs(possession["block"][order] - published["ei"])))
        ei_gap = max(
            abs(frozen["ei_block"][0][i] - team_margins[g.game_id]["ei"])
            for i, g in enumerate(scored_games)
        )
        team_gap = max(
            abs(frozen["team_daily"][0][i] - team_margins[g.game_id]["team"])
            for i, g in enumerate(scored_games)
        )
        gaps = {
            "possession_ei": possession_gap,
            "game_ei_margin": ei_gap,
            "game_team_margin": team_gap,
        }
        if (
            possession_gap > REPRODUCTION_TOLERANCE["possession"]
            or max(ei_gap, team_gap) > (REPRODUCTION_TOLERANCE["margin"])
        ):
            raise ValueError(f"block cadence does not reproduce the published runs: {gaps}")
        evaluation = score_games(scored_games, frozen, OUTER_SEASONS)
        verdicts = evaluation["verdicts"]
        keep = np.isin(rows.season, OUTER_SEASONS)
        results: dict[str, Any] = {
            "version": VERSION,
            "cadences": {c: {str(s): len(plan[c][s]) for s in OUTER_SEASONS} for c in CADENCES},
            "reproduction": gaps,
            "matched_calibration": calib,
            "evaluation_frozen_calibration": evaluation,
            "closes_gap": {c: closes_gap(verdicts, c) for c in ("weekly", "daily")},
            "primary": list(PRIMARY),
            "strict_calibration": {c: v["sources"] for c, v in strict.items()},
            "strict_parents": {k: str(v) for k, v in registry.items() if VERSION in k},
            "evaluation_strict_2024_25": score_games(scored_games, strict_predictions, (2024,)),
            "evaluation_frozen_2024_25": score_games(scored_games, frozen, (2024,)),
            "possession": {
                "pooled": score_possessions(rows, keep, possession),
                **{
                    f"{s}_{role}": score_possessions(
                        rows,
                        keep & (rows.season == s) & (rows.playoff == (role == "playoffs")),
                        possession,
                    )
                    for s in OUTER_SEASONS
                    for role in ("regular", "playoffs")
                },
            },
            "runtime_per_refresh_seconds": {
                c: {
                    "refreshes": len(fitted[c]),
                    "mean": float(np.mean([r.seconds for r in fitted[c].values()])),
                    "max": float(np.max([r.seconds for r in fitted[c].values()])),
                    "total": float(np.sum([r.seconds for r in fitted[c].values()])),
                }
                for c in CADENCES
            },
            "cold_minute_share": {
                c: float(np.mean([d[f"ei_{c}_cold_share"] for d in detail])) for c in CADENCES
            },
            "games": len(scored_games),
        }
        _write_json(stage / "results.json", results)
        _write_json(stage / "fit_log.json", log)
        head, clean = _git_head()
        manifest = {
            "schema_version": 1,
            "version": VERSION,
            "protocol": protocol,
            "code_commit": head,
            "working_tree_clean_at_end": clean,
            "inputs": {
                "rows": row_inputs,
                "ei_run_manifest_sha256": ei_manifest,
                "team_run_manifest_sha256": TEAM_MANIFEST,
                "spm": addendum["spm_fit"],
            },
            "versions": _versions(),
            "runtime_seconds": time.perf_counter() - started,
            "peak_memory_mib": _peak_memory_mib(),
            "outputs": {
                path.name: sha256_file(path) for path in sorted(stage.iterdir()) if path.is_file()
            },
            "private_outputs": ["predictions.csv", "possession_predictions.npz"],
        }
        _write_json(stage / "manifest.json", manifest)
        stage.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    print(run(args.raw, args.processed, args.output, args.protocol_sha256)["outputs"])


if __name__ == "__main__":
    main()
