"""R1 v2: box-only confirmatory run of Expected impact v1 on the 2025–26 holdout (#42).

Protocol: ``docs/research/r1-confirmatory-protocol.md`` (v2). The runner reuses the frozen #36
EI and #39 team-outcome functions unchanged and adds only the plumbing the protocol names: the
season, cutoffs and row seasons as parameters; blocks built from fixed dates and the team log;
the fixed cold rating; the strict two-interval verdict; and the holdout guard.

The guard lifts only when the protocol file matches ``R1_PROTOCOL_SHA256``, is committed
unchanged and the working tree is clean. ``R1_PROTOCOL_SHA256`` is set only by the stage-B
freeze commit; until then every holdout read refuses. Pilot, row and V3-event loaders never
accept 2025–26 under R1 v2.

Subcommands:
    reproduce RAW PROCESSED OUT       #36 and #39 2024–25 outputs from the parametrized code
    predict   RAW PROCESSED OUT --season {2024,2025}
    score     RAW OUT [--seal]
    capture   RAW                     2025–26 player and team logs (guarded)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import duckdb
import numpy as np

from bil.data.pilot_sources import (
    ATTRIBUTION,
    BOX_BASE,
    NBA_TERMS,
    RIGHTS_REF,
    sha256_file,
    utc_now,
    write_json,
)
from bil.features.box import Appearance
from bil.features.box_build import PLAYER_LOG, TEAM_LOG, load_appearances
from bil.models.expected_impact import (
    SPM_MANIFEST,
    SPM_RUN,
    Ratings,
    fit_informed,
    prepare,
    ratings,
    spm_fit,
    write_ratings,
)
from bil.models.expected_impact_outer import ADDENDUM, outer_logs, parse_config
from bil.models.rapm.baseline import _peak_memory_mib
from bil.models.rapm.multiseason import (
    FROZEN_BLOCK,
    HOLDOUT_START_YEAR,
    REPO_ROOT,
    SEASON_PINS,
    TEMPORAL_BY_NAME,
    AddendumError,
    Analysis,
    Scenario,
    _git_head,
    _prepare,
    _run_git,
    _versions,
    _write_json,
    season_blocks,
    verify_addendum,
)
from bil.models.spm_build import LOG_PINS, checked_file, checked_logs, read_json
from bil.models.team_outcomes import (
    LOG_SEASONS,
    BoxIndex,
    Game,
    Inputs,
    Snapshot,
    build_inputs,
    load_ratings,
    predict_all,
    score,
    team_games,
)

PROTOCOL = REPO_ROOT / "docs/research/r1-confirmatory-protocol.md"
PINS = REPO_ROOT / "docs/research/r1-holdout-pins.json"
ACCESS_LOG = REPO_ROOT / "docs/research/r1-holdout-access-log.md"
R1_PROTOCOL_SHA256: str | None = None  # set only by the stage-B freeze commit
VERSION = "r1-v2"
HOLDOUT_SEASON = HOLDOUT_START_YEAR
# The locked SPM fit's no-history prior with zero deviation: the cold rating of every
# issue-36-v1 snapshot (protocol §3.1). Ratings files carry six decimals.
COLD_RATING = -0.375704
COLD_TOLERANCE = 1e-6
ROW_SEASONS = {2024: (2022, 2023), 2025: (2023, 2024)}  # dry run, holdout
REFERENCE_EI = ("issue-36-v1", "f74fc2a5e76b7a22964ca8b96736344bc49f3611dd0acf37fbdaeb9ae130a131")
REFERENCE_TEAM = (
    "issue-39-v1",
    "8486bf8c42a30c708b12717c4955617d43aef044c4cf0cbc5b6da5fa8b1b1cee",
    "ef0dd71e5b9723534eec4d8ee292f4110ce88b905f1fbb4671913ba2b980cee9",
)
REPRODUCTION_TOLERANCE = 1e-9
MODELS = ("hca", "team_rating", "ei", "ei_oracle", "ei_preseason")
TOP_LEVEL_LOGS = (PLAYER_LOG, TEAM_LOG)


class HoldoutLocked(RuntimeError):
    """A 2025–26 read was attempted without a frozen, committed protocol."""


# Files the frozen block's "protocols" digests name (protocol §0 and frozen block).
PROTOCOL_FILES = {
    "validation_strategy": "docs/validation-strategy.md",
    "expected_impact_protocol": "docs/research/expected-impact-protocol.md",
    "outer_addendum": "docs/research/expected-impact-outer-addendum.md",
    "team_outcomes_protocol": "docs/research/team-outcomes-protocol.md",
    "epm_agreement_protocol": "docs/research/epm-agreement-protocol.md",
    "season_quality": "docs/research/season-quality-2017-2025.md",
}
LOG_LABEL = "pre-score manifest sha256: "


def frozen_block() -> dict[str, Any]:
    match = FROZEN_BLOCK.search(PROTOCOL.read_text(encoding="utf-8"))
    if match is None:
        raise HoldoutLocked("the R1 protocol has no frozen-config block")
    block: dict[str, Any] = json.loads(match.group(1))
    return block


def guard() -> dict[str, Any]:
    """Lift the holdout guard, or refuse. A digest from the command line cannot lift it.

    The protocol must match ``R1_PROTOCOL_SHA256``, be committed unchanged on a clean tree,
    be frozen, and every protocol its frozen block names must still match its digest.
    """
    if R1_PROTOCOL_SHA256 is None:
        raise HoldoutLocked("R1 is not frozen: R1_PROTOCOL_SHA256 is unset")
    try:
        freeze = verify_addendum(PROTOCOL, R1_PROTOCOL_SHA256, REPO_ROOT)
    except AddendumError as exc:
        raise HoldoutLocked(str(exc)) from exc
    block = frozen_block()
    if block.get("status") != "frozen":
        raise HoldoutLocked("the R1 protocol's frozen block is not marked frozen")
    for key, relative in PROTOCOL_FILES.items():
        if sha256_file(REPO_ROOT / relative) != block["protocols"][key]:
            raise HoldoutLocked(f"{relative} differs from the digest the R1 protocol registers")
    return freeze


def _snapshot_dir(raw: Path, season: int, snapshot: str) -> Path:
    """A pinned snapshot directory; names are plain and seasons map to their own label."""
    if not snapshot or any(c in snapshot for c in "/\\") or snapshot.startswith("."):
        raise ValueError(f"invalid snapshot name {snapshot!r}")
    if season == HOLDOUT_SEASON:
        guard()
        return raw / season_label(season) / snapshot
    if season > HOLDOUT_SEASON:
        raise ValueError(f"R1 reads no season after {HOLDOUT_SEASON}")
    return raw / SEASON_PINS[season].label / snapshot


def season_label(season: int) -> str:
    return f"{season}-{(season + 1) % 100:02d}"


# --- box logs ---------------------------------------------------------------------------


def _fetch(url: str, path: Path, attempts: int = 3) -> str:
    """Download once; retry only on a network error before anything is parsed (§4.1)."""
    request = Request(url, headers={"User-Agent": "bil-research-capture"})
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=60) as response, path.open("wb") as target:
                for block in iter(lambda: response.read(65536), b""):
                    target.write(block)
            return utc_now()
        except (URLError, TimeoutError):
            path.unlink(missing_ok=True)
            if attempt == attempts - 1:
                raise
    raise AssertionError("unreachable")


def capture_holdout_logs(raw: Path, snapshot: str = "r1-v1") -> dict[str, Any]:
    """Capture and pin the 2025–26 NBA.com player and team logs. Nothing is parsed here."""
    directory = _snapshot_dir(raw, HOLDOUT_SEASON, snapshot)
    directory.mkdir(mode=0o700, parents=True)
    try:
        return _capture(directory, snapshot)
    except BaseException:
        shutil.rmtree(directory)  # a retry starts from an empty directory (§4.1)
        raise


def _capture(directory: Path, snapshot: str) -> dict[str, Any]:
    end = HOLDOUT_SEASON + 1
    record: dict[str, Any] = {
        "schema_version": 1,
        "season_start_year": HOLDOUT_SEASON,
        "attribution": ATTRIBUTION,
        "terms": NBA_TERMS,
        "artifacts": [],
    }
    for kind, name in (("team", TEAM_LOG), ("player", PLAYER_LOG)):
        url = f"{BOX_BASE}/{kind}_game_logs/season={end}/data.parquet"
        retrieved = _fetch(url, directory / name)
        digest = sha256_file(directory / name)
        record["artifacts"].append(
            {
                "artifact_id": f"{name}@{digest}",
                "name": name,
                "uri": url,
                "source_id": "billmill",
                "upstream_namespace": "nba",
                "sha256": digest,
                "size_bytes": (directory / name).stat().st_size,
                "retrieved_at": retrieved,
                "rights_ref": RIGHTS_REF,
            }
        )
    write_json(directory / "snapshot.json", record)
    return {"snapshot": snapshot, "sha256": sha256_file(directory / "snapshot.json")}


def box_logs(
    raw: Path, season: int, pin: Mapping[str, str]
) -> tuple[list[Appearance], dict[str, Any], Path]:
    """One season's verified player log, its profile and directory. 2025–26 needs the guard."""
    if season < HOLDOUT_SEASON:
        rows, profile = outer_logs(raw, season, pin)
        return rows, profile, raw / SEASON_PINS[season].label / pin["snapshot"]
    if season != HOLDOUT_SEASON:
        raise ValueError(f"R1 reads no season after {HOLDOUT_SEASON}")
    directory = _snapshot_dir(raw, season, pin["snapshot"])
    record = read_json(checked_file(directory / "snapshot.json", pin["sha256"]))
    if record["season_start_year"] != season or record["attribution"] != ATTRIBUTION:
        raise ValueError("box log snapshot season or attribution mismatch")
    assets = {asset["name"]: asset for asset in record["artifacts"]}
    for name in TOP_LEVEL_LOGS:
        path = checked_file(directory / name, assets[name]["sha256"])
        if path.stat().st_size != assets[name]["size_bytes"]:
            raise ValueError("box log snapshot size mismatch")
    with duckdb.connect() as connection:
        rows, profile = load_appearances(connection, directory, season_start_year=season)
    if not rows or any(row.game_date >= date(season + 1, 7, 1) for row in rows):
        raise ValueError("box log rows fall outside the cohort window")
    return (
        rows,
        {"snapshot": pin["snapshot"], "snapshot_sha256": pin["sha256"], **profile},
        directory,
    )


def season_pins(season: int) -> dict[int, dict[str, str]]:
    """Box-log pins for the previous and scored seasons."""
    addendum = parse_config(ADDENDUM.read_text(encoding="utf-8"))["box_logs"]
    pins = {s: addendum[str(s)] for s in (season - 1, season) if str(s) in addendum}
    if season == HOLDOUT_SEASON:
        pins[season] = read_json(PINS)["box_logs"][str(season)]
    return pins


# --- blocks and EI snapshots ------------------------------------------------------------


@dataclass(frozen=True)
class Cut:
    label: str
    role: str
    cutoff: date


def cuts(season: int, games: Sequence[Game]) -> list[Cut]:
    """R1–R4 at fixed dates and P at the first playoff date of the season's team log."""
    y = season
    out = [
        Cut(f"{y}-R1", "regular", date(y, 10, 1)),
        Cut(f"{y}-R2", "regular", date(y, 12, 1)),
        Cut(f"{y}-R3", "regular", date(y + 1, 2, 1)),
        Cut(f"{y}-R4", "regular", date(y + 1, 4, 1)),
    ]
    playoff = [g.day for g in games if g.season == season and g.playoff]
    if playoff:
        out.append(Cut(f"{y}-P", "playoffs", min(playoff)))
    return out


def ei_snapshots(
    analysis: Analysis,
    spm: Any,
    ei: Mapping[str, Any],
    previous: Sequence[Appearance],
    current: Sequence[Appearance],
    blocks: Sequence[Cut],
    final_cutoff: date,
) -> list[Ratings]:
    """The frozen EI fit at each cutoff, exactly as in the #36 runner, without scoring."""
    if TEMPORAL_BY_NAME[ei["window"]].name != "W2":
        raise AddendumError("v1 prepare() uses the W2 window")
    out = []
    for label, cutoff in [(b.label, b.cutoff) for b in blocks] + [("final", final_cutoff)]:
        p = prepare(analysis, cutoff, spm, previous, current)
        fit = fit_informed(analysis, p, ei["offense_ridge"], ei["defense_ridge"], label)
        out.append(ratings(p, fit, analysis.design, {**ei, "cutoff": cutoff, "spm": spm.fit_id}))
    return out


def with_cold(snapshots: Sequence[Snapshot], path: Path) -> list[Snapshot]:
    """Fix every snapshot's cold rating at COLD_RATING; any cold row present must agree."""
    present: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["box_history"] == "False" and float(row["window_possessions"]) == 0:
                present[row["as_of"]] = float(row["rating_total"])
    for day, value in present.items():
        if abs(value - COLD_RATING) > COLD_TOLERANCE:
            raise ValueError(f"cold row {value} on {day} differs from the fixed cold rating")
    return [replace(s, cold=COLD_RATING) for s in snapshots]


def _spm(processed: Path, config: Mapping[str, Any]) -> Any:
    spm_dir = processed / "spm" / SPM_RUN
    checked_file(spm_dir / "manifest.json", SPM_MANIFEST)
    return spm_fit(read_json(checked_file(spm_dir / config["spm_fit"], config["spm_fit_sha256"])))


def _analysis(processed: Path, seasons: Sequence[int], stage: Path) -> tuple[Analysis, Any]:
    _, rows, design, inputs = _prepare(processed, seasons, seasons, stage)
    analysis = Analysis(rows, design, Scenario("primary", np.ones(len(rows), dtype=bool)), [], [])
    return analysis, inputs


def frozen_team(processed: Path) -> tuple[float, tuple[float, float], dict[str, Any]]:
    """Pace, team-rating configuration and calibrations from the frozen #39 run."""
    name, manifest_sha, results_sha = REFERENCE_TEAM
    directory = processed / "team_outcomes" / name
    checked_file(directory / "manifest.json", manifest_sha)
    results = read_json(checked_file(directory / "results.json", results_sha))
    config = results["selected_team_config"]
    return results["pace"], (config["half_life"], config["ridge"]), results["calibration"]


# --- predictions ------------------------------------------------------------------------


def _prediction_rows(
    inputs: Inputs, predictions: Mapping[str, tuple[Any, Any]], names: Sequence[str]
) -> list[list[Any]]:
    header = ["game_id", "season", "date", "playoff", "home", "away", *inputs.detail[0].keys()]
    header += [f"{n}_{k}" for n in names for k in ("margin", "home_win_prob")]
    rows: list[list[Any]] = [header]
    for i, g in enumerate(inputs.games):
        rows.append(
            [g.game_id, g.season, g.day.isoformat(), g.playoff, g.home, g.away]
            + list(inputs.detail[i].values())
            + [f"{predictions[n][k][i]:.6f}" for n in names for k in (0, 1)]
        )
    return rows


def _write_rows(path: Path, rows: Sequence[Sequence[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def predict(raw: Path, processed: Path, output: Path, season: int) -> dict[str, Any]:
    """Fit every snapshot and write the pregame predictions, with no outcome scored."""
    started = time.perf_counter()
    if season not in ROW_SEASONS:
        raise ValueError("R1 v2 predicts the 2024–25 dry run or the 2025–26 holdout only")
    freeze = guard() if season == HOLDOUT_SEASON else {"dry_run": True}
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    config = parse_config(ADDENDUM.read_text(encoding="utf-8"))
    spm = _spm(processed, config)
    pins = season_pins(season)
    logs: dict[int, list[Appearance]] = {}
    log_inputs: dict[str, Any] = {}
    games: list[Game] = []
    game_counts: dict[str, Any] = {}
    for s in (season - 1, season):
        logs[s], log_inputs[str(s)], directory = box_logs(raw, s, pins[s])
        season_games, game_counts[str(s)] = team_games(directory, s)
        games.extend(season_games)
    blocks = cuts(season, games)
    pace, team_config, calib = frozen_team(processed)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".r1-", dir=output.parent) as sandbox:
        stage = Path(sandbox) / "run"
        stage.mkdir()
        analysis, row_inputs = _analysis(processed, ROW_SEASONS[season], stage)
        snaps = ei_snapshots(
            analysis,
            spm,
            config["models"]["ei"],
            logs[season - 1],
            logs[season],
            blocks,
            date(season + 1, 7, 1),
        )
        write_ratings(stage / "ratings.csv", snaps)
        loaded = with_cold(load_ratings(stage / "ratings.csv"), stage / "ratings.csv")
        in_season = [s for s in loaded if s.as_of.month != 7]
        preseason = [s for s in loaded if s.as_of == blocks[0].cutoff]
        index = BoxIndex.build(logs)
        teams = sorted({t for g in games for t in g.teams})
        # Scored games carry no outcome; the team rating sees only earlier days' margins.
        target = [replace(g, margin=None) for g in games if g.season == season]
        inputs = build_inputs(target, games, index, {season: in_season}, pace, teams, team_config)
        early = build_inputs(target, games, index, {season: preseason}, pace, teams, team_config)
        predictions = predict_all(inputs, calib)
        c = calib["ei"]
        margin = c["a"] + c["b"] * early.raw["ei"]
        predictions["ei_preseason"] = (margin, predict_all(early, calib)["ei"][1])
        _write_rows(stage / "predictions.csv", _prediction_rows(inputs, predictions, MODELS))
        head, clean = _git_head()
        manifest = {
            "schema_version": 1,
            "version": VERSION,
            "season": season,
            "role": "holdout" if season == HOLDOUT_SEASON else "dry_run",
            "protocol": freeze,
            "code_commit": head,
            "working_tree_clean_at_end": clean,
            "cutoffs": {b.label: b.cutoff.isoformat() for b in blocks},
            "cold_rating": COLD_RATING,
            "inputs": {"rows": row_inputs, "box_logs": log_inputs, "spm": config["spm_fit"]},
            "games": game_counts,
            "scored_games": len(inputs.games),
            "versions": _versions(),
            "runtime_seconds": time.perf_counter() - started,
            "peak_memory_mib": _peak_memory_mib(),
            "outputs": {p.name: sha256_file(p) for p in sorted(stage.iterdir()) if p.is_file()},
            "private_outputs": ["ratings.csv", "predictions.csv"],
        }
        _write_json(stage / "manifest.json", manifest)
        stage.rename(output)
    return manifest


# --- scoring ----------------------------------------------------------------------------


def strict_verdict(entry: Mapping[str, Any], key: str) -> dict[str, Any]:
    """Protocol §3: ei_better needs delta < 0 and both the game and week intervals below 0."""
    delta = entry[f"{key}_delta"]
    game, week = entry[f"{key}_ci95_game"], entry[f"{key}_ci95_week"]
    if delta < 0 and game[1] < 0 and week[1] < 0:
        verdict = "ei_better"
    elif delta > 0 and game[0] > 0 and week[0] > 0:
        verdict = "ei_worse"
    else:
        verdict = "inconclusive"
    including = [n for n, (lo, hi) in (("game", game), ("week", week)) if lo <= 0 <= hi]
    return {"verdict": verdict, "delta": delta, "interval_including_zero": including}


def _load_predictions(output: Path, raw: Path) -> tuple[Inputs, dict[str, Any], dict[str, Any]]:
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, digest in manifest["outputs"].items():
        if sha256_file(output / name) != digest:
            raise ValueError(f"{name} differs from the pre-score manifest")
    season = manifest["season"]
    pin = manifest["inputs"]["box_logs"][str(season)]
    directory = _snapshot_dir(raw, season, pin["snapshot"])
    outcomes = {g.game_id: g for g in team_games(directory, season)[0]}
    with (output / "predictions.csv").open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    games = [outcomes[r["game_id"]] for r in records]
    detail = [
        {"as_of": r["as_of"], "cold_minute_share": float(r["cold_minute_share"])} for r in records
    ]
    predictions = {
        n: (
            np.asarray([float(r[f"{n}_margin"]) for r in records]),
            np.asarray([float(r[f"{n}_home_win_prob"]) for r in records]),
        )
        for n in MODELS
    }
    return Inputs(games, {}, detail), predictions, manifest


def _subset(
    inputs: Inputs, predictions: Mapping[str, Any], keep: Sequence[bool]
) -> tuple[Inputs, dict[str, Any]]:
    mask = np.asarray(keep)
    games = [g for g, k in zip(inputs.games, mask, strict=True) if k]
    detail = [d for d, k in zip(inputs.detail, mask, strict=True) if k]
    return Inputs(games, {}, detail), {n: (m[mask], p[mask]) for n, (m, p) in predictions.items()}


def access_logged(log: str, digest: str) -> bool:
    """The log must carry a labelled line naming the pre-score manifest digest."""
    return any(line.strip().endswith(f"{LOG_LABEL}{digest}") for line in log.splitlines())


def score_run(raw: Path, output: Path, seal: bool) -> dict[str, Any]:
    """Score frozen predictions. The holdout needs its pre-score digest in the committed log."""
    manifest_digest = sha256_file(output / "manifest.json")
    if (output / "results.json").exists():
        raise FileExistsError("this run is already scored (single shot)")
    if (
        json.loads((output / "manifest.json").read_text(encoding="utf-8"))["season"]
        == HOLDOUT_SEASON
    ):
        guard()
        logged = _run_git(REPO_ROOT, "show", f"HEAD:{ACCESS_LOG.relative_to(REPO_ROOT)}")
        if logged.returncode != 0 or not access_logged(logged.stdout, manifest_digest):
            raise HoldoutLocked("the committed access log lacks the pre-score manifest digest")
    inputs, predictions, manifest = _load_predictions(output, raw)
    season = manifest["season"]
    scored = score(inputs, predictions, [season])
    regular = scored["regular"]["pooled"]["ei_minus"]["team_rating"]
    r3 = date.fromisoformat(manifest["cutoffs"][f"{season}-R3"])
    early_inputs, early_predictions = _subset(
        inputs, predictions, [not g.playoff and g.day < r3 for g in inputs.games]
    )
    early = score(early_inputs, early_predictions, [season])["regular"]["pooled"]["ei_minus"]
    labels = {v: k for k, v in manifest["cutoffs"].items()}
    cold: dict[str, list[float]] = defaultdict(list)
    for d in inputs.detail:
        cold[labels.get(d["as_of"], d["as_of"])].append(d["cold_minute_share"])
    results = {
        "pre_score_manifest_sha256": manifest_digest,
        "season": season,
        "verdicts": {
            "C1_margin_rmse_vs_team_rating": strict_verdict(regular, "rmse"),
            "C2_win_log_loss_vs_team_rating": strict_verdict(regular, "log_loss"),
        },
        "scores": scored,
        "early_season_slice_R1_R2": early,
        "cold_minute_share_by_block": {k: float(np.mean(v)) for k, v in sorted(cold.items())},
    }
    path = output / "results.json"
    _write_json(path, results)
    digest = sha256_file(path)
    if seal:
        os.chmod(path, 0)
        return {"results_sha256": digest, "sealed": True}
    return {"results_sha256": digest, **results["verdicts"]}


# --- reproduction proof -----------------------------------------------------------------


def _lines(path: Path, column: str, keep: set[str]) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        at = header.index(column)
        return [",".join(header)] + [",".join(r) for r in reader if r[at] in keep]


def _compare(mine: list[str], theirs: list[str]) -> dict[str, Any]:
    digest = [hashlib.sha256("\n".join(x).encode()).hexdigest() for x in (mine, theirs)]
    if digest[0] == digest[1]:
        return {"identical": True, "sha256": digest[0], "rows": len(mine) - 1}
    worst = 0.0
    if len(mine) != len(theirs):
        return {"identical": False, "rows": [len(mine), len(theirs)], "max_abs_diff": None}
    for a, b in zip(mine[1:], theirs[1:], strict=True):
        for x, y in zip(a.split(","), b.split(","), strict=True):
            if x != y:
                try:
                    worst = max(worst, abs(float(x) - float(y)))
                except ValueError:
                    return {"identical": False, "max_abs_diff": None, "first_difference": [x, y]}
    return {
        "identical": False,
        "max_abs_diff": worst,
        "within_tolerance": worst <= REPRODUCTION_TOLERANCE,
    }


def reproduce(raw: Path, processed: Path, output: Path) -> dict[str, Any]:
    """Recreate #36's 2024–25 ratings and #39's 2024–25 predictions from their own inputs."""
    season = 2024
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    config = parse_config(ADDENDUM.read_text(encoding="utf-8"))
    spm = _spm(processed, config)
    logs: dict[int, list[Appearance]] = {}
    games: list[Game] = []
    for s in LOG_SEASONS:
        if s in LOG_PINS:
            logs[s], _ = checked_logs(raw, s)
            directory = raw / SEASON_PINS[s].label / LOG_PINS[s][0]
        else:
            pin = config["box_logs"][str(s)]
            logs[s], _ = outer_logs(raw, s, pin)
            directory = raw / SEASON_PINS[s].label / pin["snapshot"]
        games.extend(team_games(directory, s)[0])
    output.mkdir(parents=True)
    report: dict[str, Any] = {}
    with TemporaryDirectory(prefix=".r1-repro-", dir=output) as sandbox:
        analysis, _ = _analysis(processed, (2021, 2022, 2023, 2024), Path(sandbox))
        blocks = cuts(season, games)
        reference = [b.cutoff for b in season_blocks(analysis.rows, season)]
        report["cutoffs_match_season_blocks"] = [b.cutoff for b in blocks] == reference
        snaps = ei_snapshots(
            analysis,
            spm,
            config["models"]["ei"],
            logs[2023],
            logs[2024],
            blocks,
            date(season + 1, 7, 1),
        )
    write_ratings(output / "ratings.csv", snaps)
    days = {s.cutoff.isoformat() for s in snaps}
    ei_dir = processed / "expected_impact" / REFERENCE_EI[0]
    manifest = read_json(checked_file(ei_dir / "manifest.json", REFERENCE_EI[1]))
    ei_ref = checked_file(ei_dir / "ratings.csv", manifest["outputs"]["ratings.csv"])
    report["ei_ratings"] = _compare(
        _lines(output / "ratings.csv", "as_of", days), _lines(ei_ref, "as_of", days)
    )
    # Team side: the unchanged #39 path with #36's own ratings file and cold rule.
    pace, team_config, calib = frozen_team(processed)
    snapshots = [
        s for s in load_ratings(ei_ref) if s.as_of.month != 7 and s.as_of.isoformat() in days
    ]
    teams = sorted({t for g in games for t in g.teams})
    target = [g for g in games if g.season == season]
    inputs = build_inputs(
        target, games, BoxIndex.build(logs), {season: snapshots}, pace, teams, team_config
    )
    predictions = predict_all(inputs, calib)
    names = list(predictions)
    _write_rows(output / "predictions.csv", _prediction_rows(inputs, predictions, names))
    team_ref = processed / "team_outcomes" / REFERENCE_TEAM[0] / "predictions.csv"
    report["team_predictions"] = _compare(
        _lines(output / "predictions.csv", "season", {str(season)}),
        _lines(team_ref, "season", {str(season)}),
    )
    report["pass"] = report["cutoffs_match_season_blocks"] and all(
        report[k]["identical"] or report[k].get("within_tolerance") is True
        for k in ("ei_ratings", "team_predictions")
    )
    _write_json(output / "reproduction.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for name in ("reproduce", "predict"):
        sub = commands.add_parser(name)
        sub.add_argument("raw", type=Path)
        sub.add_argument("processed", type=Path)
        sub.add_argument("output", type=Path)
        if name == "predict":
            sub.add_argument("--season", type=int, required=True)
    sub = commands.add_parser("score")
    sub.add_argument("raw", type=Path)
    sub.add_argument("output", type=Path)
    sub.add_argument("--seal", action="store_true", help="write results unreadable (dry run)")
    sub = commands.add_parser("capture")
    sub.add_argument("raw", type=Path)
    args = parser.parse_args()
    if args.action == "reproduce":
        result: Any = reproduce(args.raw.resolve(), args.processed.resolve(), args.output.resolve())
    elif args.action == "predict":
        manifest = predict(
            args.raw.resolve(), args.processed.resolve(), args.output.resolve(), args.season
        )
        result = {"outputs": manifest["outputs"], "scored_games": manifest["scored_games"]}
    elif args.action == "score":
        result = score_run(args.raw.resolve(), args.output.resolve(), args.seal)
    else:
        result = capture_holdout_logs(args.raw.resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
