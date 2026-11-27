"""Replayable origin refresh with cutoff enforcement and atomic publication (#142).

One origin `D` produces one Expected Impact snapshot under the #36 configuration, as a #135
as-of rating artifact. The refresh is replay-only on pinned 2023–25 inputs: no live capture and no
2025–26 date.

- **Cutoff.** The snapshot reads only possessions and box lines dated strictly before `D`, which
  `expected_impact.prepare` enforces.
- **Identity.** The artifact ID is a content hash of the origin, the input digests, the parent
  fit and selection IDs, and the configuration. The code commit is recorded but is not part of
  the identity.
- **Idempotence.** If `ROOT/D/<id>` exists and its manifest names the same ID, the refresh is a
  no-op and nothing is fitted or rewritten. Changed inputs give a new ID in a new directory.
- **Atomicity.** The artifact is written into a staging directory inside `ROOT` and renamed into
  place. A run interrupted by an exception removes its staging directory. A killed process or
  power loss can leave a dot-prefixed staging directory, which is never read as an artifact.
  Files are fsynced before the rename.
- **Code changes.** The identity covers ``VERSION``, not the model code. A code change that
  changes outputs must bump ``VERSION``.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import math
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import numpy as np

from bil.data.pilot_sources import sha256_file
from bil.features.box import Appearance, snapshot_instant
from bil.features.box_build import PLAYER_LOG, TEAM_LOG
from bil.models.calibration_lineage import load_calibration
from bil.models.expected_impact import (
    SPM_MANIFEST,
    SPM_RUN,
    Prepared,
    SpmFit,
    as_of_ratings,
    fit_informed,
    prepare,
    spm_fit,
    write_ratings,
)
from bil.models.expected_impact_outer import (
    ADDENDUM,
    FINAL_CUTOFF,
    OUTER_SEASONS,
    ROW_SEASONS,
    outer_logs,
    parse_config,
)
from bil.models.rapm.multiseason import (
    SEASON_PINS,
    TEMPORAL_BY_NAME,
    Analysis,
    PlayerFit,
    Scenario,
    SeasonPin,
    _git_head,
    _prepare,
    season_blocks,
)
from bil.models.spm_build import checked_file, read_json
from bil.refresh_sources import (
    Capture,
    Mode,
    Resolution,
    box_capture,
    possession_captures,
    resolve,
)

VERSION = "origin-refresh-issue-145-v4"
MANIFEST = "manifest.json"
RATINGS = "ratings.csv"
SOURCES = "sources.json"
REVISIONS = "revisions.jsonl"
CHECKPOINTS = "_checkpoints"
OUTCOMES = "_outcomes.jsonl"
RETIRED = "_retired"
CHECKPOINT_RETENTION = 14  # origins whose fitted state is kept
FROZEN_TOLERANCE = 1e-6


class RefreshError(ValueError):
    """An origin cannot be refreshed or an existing artifact is inconsistent."""


@dataclass(frozen=True)
class Inputs:
    """Everything one origin refresh reads, already verified against its pins."""

    analysis: Analysis
    spm: SpmFit
    logs: Mapping[int, Sequence[Appearance]]
    config: Mapping[str, Any]  # window and penalties
    input_ids: Mapping[str, Any]  # digests of row sets, box logs, SPM fit, configuration source
    parents: Mapping[str, str]  # parent fit and selection IDs
    seasons: tuple[int, ...] = OUTER_SEASONS  # replay scope
    captures: tuple[Capture, ...] = ()  # per-game source captures; derived from the inputs if empty
    mode: Mode = "retrospective"  # pinned replay snapshots carry only post-season capture times
    calibration: Path | None = None  # a #136 post-freeze calibration directory, checked per origin


@dataclass(frozen=True)
class Published:
    path: Path
    artifact_id: str
    created: bool
    checkpoint: str = "none"  # "computed", "reused" or "none"


class RevisionConflict(RefreshError):
    """An origin already holds a different artifact; the change was recorded, not published."""


def season_of(origin: date) -> int:
    return origin.year if origin.month >= 8 else origin.year - 1


def artifact_id(
    origin: date,
    input_ids: Mapping[str, Any],
    parents: Mapping[str, str],
    config: Mapping[str, Any],
) -> str:
    body = {
        "version": VERSION,
        "origin": origin.isoformat(),
        "inputs": input_ids,
        "parents": parents,
        "config": config,
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def check_origin(origin: date, seasons: Sequence[int] = OUTER_SEASONS) -> int:
    """Replay scope: an origin inside a pinned replay season and before the holdout."""
    season = season_of(origin)
    if origin >= FINAL_CUTOFF or season not in seasons:
        raise RefreshError(f"origin {origin} is outside the replay seasons {list(seasons)}")
    return season


def existing(root: Path, origin: date, aid: str) -> Path | None:
    target = root / origin.isoformat() / aid
    if not target.exists():
        return None
    manifest = target / MANIFEST
    if not manifest.is_file():
        raise RefreshError(f"{target} exists without a manifest")
    try:
        record = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RefreshError(f"{target} has an unreadable manifest") from error
    if not isinstance(record, dict) or not isinstance(record.get("outputs"), dict):
        raise RefreshError(f"{target} has a malformed manifest")
    if record.get("artifact_id") != aid or record.get("origin") != origin.isoformat():
        raise RefreshError(f"{target} holds a different artifact")
    ratings = target / RATINGS
    if not ratings.is_file() or sha256_file(ratings) != record["outputs"].get(RATINGS):
        raise RefreshError(f"{target} ratings do not match their manifest")
    return target


def publish(
    root: Path, origin: date, aid: str, write: Callable[[Path], Mapping[str, Any]]
) -> Published:
    """Run ``write`` into a staging directory and rename it into place, unless already there."""
    found = existing(root, origin, aid)
    if found is not None:
        return Published(found, aid, False)
    parent = root / origin.isoformat()
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(mkdtemp(prefix=f".{aid[:12]}.staging-", dir=parent))
    try:
        extra = dict(write(stage))
        outputs = {p.name: sha256_file(p) for p in sorted(stage.iterdir()) if p.is_file()}
        manifest = {
            "schema_version": 1,
            "version": VERSION,
            "artifact_id": aid,
            "origin": origin.isoformat(),
            **extra,
            "outputs": outputs,
        }
        (stage / MANIFEST).write_text(
            json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        _fsync(stage)
        target = parent / aid
        try:
            os.rename(stage, target)
        except OSError:
            # Another run published the same ID first. Accept it only if it is consistent.
            if existing(root, origin, aid) is None:
                raise
            return Published(target, aid, False)
        _fsync_dir(parent)
        return Published(target, aid, True)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _fsync(directory: Path) -> None:
    for path in directory.iterdir():
        if path.is_file():
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
    _fsync_dir(directory)


def _fsync_dir(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


# --- checkpoints ------------------------------------------------------------------------


def _checkpoint_paths(store: Path, origin: date, aid: str) -> tuple[Path, Path]:
    stem = f"{origin.isoformat()}-{aid}"
    return store / f"{stem}.npz", store / f"{stem}.json"


def _identity(origin: date, input_ids: Mapping[str, Any], inputs: Inputs) -> dict[str, Any]:
    return {
        "version": VERSION,
        "origin": origin.isoformat(),
        "inputs": input_ids,
        "parents": inputs.parents,
        "config": inputs.config,
    }


def save_checkpoint(
    store: Path,
    origin: date,
    aid: str,
    identity: Mapping[str, Any],
    prepared: Prepared,
    fit: PlayerFit,
    retention: int = CHECKPOINT_RETENTION,
) -> None:
    """Write the fitted state of one origin. The JSON sidecar is written last and commits it.

    Only window rows and their weights are kept per cutoff. The per-loaded-row prior offset is
    recomputed from the priors on load, so storage is bounded by the window, not the row set.
    """
    store.mkdir(parents=True, exist_ok=True)
    npz, meta = _checkpoint_paths(store, origin, aid)
    stage = Path(mkdtemp(prefix=".checkpoint-", dir=store))
    try:
        np.savez_compressed(
            stage / "state.npz",
            index=prepared.index,
            weights=prepared.weights,
            gamma=prepared.gamma,
            player_ids=prepared.player_ids,
            priors=prepared.priors,
            box_history=prepared.box_history,
            effects=fit.effects,
            used=fit.used,
            exposure=fit.exposure,
        )
        record = {
            "artifact_id": aid,
            "identity": identity,
            "npz_sha256": sha256_file(stage / "state.npz"),
            "context_intercept": prepared.context_intercept,
            "intercept": fit.intercept,
            "info": fit.info,
            "audit": prepared.audit,
        }
        (stage / "meta.json").write_text(
            json.dumps(record, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        _fsync(stage)
        os.replace(stage / "state.npz", npz)
        os.replace(stage / "meta.json", meta)
        _fsync_dir(store)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    # A superseded identity of the same origin is never reused again.
    for old in store.glob(f"{origin.isoformat()}-*"):
        if old.stem != npz.stem:
            old.unlink(missing_ok=True)
    prune_checkpoints(store, retention, protect=origin)


def load_checkpoint(
    store: Path, origin: date, aid: str, identity: Mapping[str, Any], inputs: Inputs
) -> tuple[Prepared, PlayerFit] | None:
    """The fitted state of ``origin``, only if every identity component matches exactly."""
    npz, meta = _checkpoint_paths(store, origin, aid)
    if not meta.is_file() or not npz.is_file():
        return None
    try:
        record = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    same = json.dumps(record.get("identity"), sort_keys=True, default=str) == json.dumps(
        dict(identity), sort_keys=True, default=str
    )
    if record.get("artifact_id") != aid or not same or sha256_file(npz) != record["npz_sha256"]:
        return None
    with np.load(npz, allow_pickle=False) as state:
        data = {name: state[name] for name in state.files}
    design = inputs.analysis.design
    m, priors = design.size, data["priors"]
    offset = np.asarray(design.players @ np.concatenate([priors[:m, 0], priors[:m, 1]]))
    prepared = Prepared(
        origin,
        data["index"],
        data["weights"],
        float(record["context_intercept"]),
        data["gamma"],
        data["player_ids"],
        priors,
        data["box_history"],
        offset,
        inputs.spm,
        record["audit"],
    )
    fit = PlayerFit(
        float(record["intercept"]),
        data["effects"],
        data["used"],
        data["exposure"],
        record["info"],
    )
    return prepared, fit


def prune_checkpoints(
    store: Path, keep: int = CHECKPOINT_RETENTION, protect: date | None = None
) -> list[str]:
    """Remove checkpoints of all but the ``keep`` latest origins, never ``protect`` (the origin
    just written, so a backfill keeps its own state); returns the removed stems.

    A state file without its committing sidecar is an orphan and is always removed.
    """
    for orphan in store.glob("*.npz"):
        if not orphan.name.startswith(".") and not orphan.with_suffix(".json").exists():
            orphan.unlink(missing_ok=True)
    stems = sorted({p.stem for p in store.glob("*.json") if not p.name.startswith(".")})
    origins = sorted({stem[:10] for stem in stems})
    old = set(origins[:-keep]) if keep > 0 else set(origins)
    old.discard(protect.isoformat() if protect else "")
    removed = []
    for stem in stems:
        if stem[:10] in old:
            for suffix in (".json", ".npz"):
                (store / f"{stem}{suffix}").unlink(missing_ok=True)
            removed.append(stem)
    return removed


# --- late revisions ---------------------------------------------------------------------


def _others(root: Path, origin: date, aid: str) -> list[str]:
    parent = root / origin.isoformat()
    if not parent.is_dir():
        return []
    return sorted(
        d.name
        for d in parent.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name != aid
    )


def revision_record(
    root: Path,
    origin: date,
    previous: str,
    aid: str,
    input_ids: Mapping[str, Any],
    inputs: Inputs,
    sources: Mapping[str, Any],
) -> dict[str, Any]:
    """What differs between a published artifact and the one a refresh would now publish."""
    old = root / origin.isoformat() / previous
    manifest = json.loads((old / MANIFEST).read_text(encoding="utf-8"))
    path = old / SOURCES
    before = json.loads(path.read_text(encoding="utf-8"))["games"] if path.is_file() else {}
    after = sources["games"]
    both = set(before) & set(after)
    changed = sorted(k for k in both if before[k][:2] != after[k][:2])  # revision or content
    recaptured = sorted(k for k in both if before[k][:2] == after[k][:2] and before[k] != after[k])
    added, removed = sorted(set(after) - set(before)), sorted(set(before) - set(after))
    inputs_before = manifest.get("inputs", {})
    return {
        "detected_at": datetime.now(UTC).isoformat(),
        "origin": origin.isoformat(),
        "previous_artifact_id": previous,
        "new_artifact_id": aid,
        "changed_inputs": sorted(
            k
            for k in set(inputs_before) | set(input_ids)
            if inputs_before.get(k) != input_ids.get(k)
        ),
        "changed_config": sorted(
            k
            for k in set(manifest.get("config", {})) | set(inputs.config)
            if manifest.get("config", {}).get(k) != inputs.config.get(k)
        ),
        "changed_parents": sorted(
            k
            for k in set(manifest.get("parents", {})) | set(inputs.parents)
            if manifest.get("parents", {}).get(k) != inputs.parents.get(k)
        ),
        "version_changed": manifest.get("version") != VERSION,
        "games_changed": len(changed),
        "games_recaptured_unchanged": len(recaptured),
        "games_added": len(added),
        "games_removed": len(removed),
        "examples": {"changed": changed[:50], "added": added[:50], "removed": removed[:50]},
    }


def _append(path: Path, record: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def replay_captures(
    inputs: Inputs, retrieved: Mapping[str, Any] | None = None
) -> tuple[Capture, ...]:
    """One capture per pinned box-log snapshot and per pinned possession row-set season."""
    retrieved = retrieved or {}
    boxes = [
        box_capture(
            f"box_logs/{season}",
            inputs.input_ids["box_logs"].get(str(season), "unpinned"),
            retrieved.get(str(season)),
            logs,
        )
        for season, logs in sorted(inputs.logs.items())
    ]
    rows = possession_captures(inputs.analysis.rows, inputs.input_ids["rows"])
    return (*boxes, *rows)


def resolution_for(origin: date, inputs: Inputs) -> Resolution:
    """The per-game source revisions this origin reads (#143)."""
    if inputs.mode != "retrospective":
        raise RefreshError(
            "the replay refresh reads one pinned capture per source; strict resolution needs the "
            "live captures that the rest of #43 adds"
        )
    return resolve(inputs.captures or replay_captures(inputs), origin, inputs.mode)


def stage_of(error: BaseException) -> str:
    """The refresh phase in which ``error`` was raised (``unknown`` outside a refresh)."""
    return str(getattr(error, "refresh_stage", "unknown"))


def check_parents(origin: date, inputs: Inputs) -> None:
    """Every fitted parent must be dated strictly before the origin."""
    if inputs.spm.origin_cutoff >= origin:
        raise RefreshError(
            f"late parent: SPM fit {inputs.spm.fit_id} has origin {inputs.spm.origin_cutoff}, "
            f"not strictly before {origin}"
        )


def calibration_for(origin: date, inputs: Inputs) -> dict[str, Any] | None:
    """Re-check the calibration's lineage at ``origin`` (#136) and identify it."""
    if inputs.calibration is None:
        return None
    artifact = load_calibration(inputs.calibration, origin)
    return {
        "calibration_id": sha256_file(inputs.calibration / "calibration.json"),
        "fit_cutoff": artifact["fit_cutoff"],
        "construction": artifact.get("construction"),
    }


def refresh_origin(
    root: Path,
    origin: date,
    inputs: Inputs,
    *,
    checkpoints: Path | None = None,
    reuse: bool = True,
    accept_revision: bool = False,
    retention: int = CHECKPOINT_RETENTION,
) -> Published:
    """Build and publish the snapshot for ``origin``; a no-op when it already exists.

    Any failure carries the phase it happened in (:func:`stage_of`): ``origin``, ``parent``,
    ``calibration``, ``sources``, ``revision`` or ``publish``. See ``_refresh_origin``.
    """
    stage = ["origin"]
    try:
        return _refresh_origin(
            root, origin, inputs, stage, checkpoints, reuse, accept_revision, retention
        )
    except Exception as error:
        if not hasattr(error, "refresh_stage"):
            with contextlib.suppress(AttributeError):
                error.refresh_stage = stage[0]  # type: ignore[attr-defined]
        raise


def _refresh_origin(
    root: Path,
    origin: date,
    inputs: Inputs,
    stage: list[str],
    checkpoints: Path | None,
    reuse: bool,
    accept_revision: bool,
    retention: int,
) -> Published:
    """Build and publish the snapshot for ``origin``; a no-op when it already exists.

    - **Checkpoints.** With a ``checkpoints`` store, the fitted state of the origin is reused
      when its full identity matches (``reuse``), and saved otherwise.
    - **Late revisions.** If the origin already holds a different artifact, what changed is
      appended to ``ROOT/<origin>/revisions.jsonl`` and :class:`RevisionConflict` is raised,
      unless ``accept_revision`` publishes the new artifact beside the old one (also recorded).
    """
    season = check_origin(origin, inputs.seasons)
    stage[0] = "parent"
    check_parents(origin, inputs)
    stage[0] = "calibration"
    calibration = calibration_for(origin, inputs)
    if calibration is not None:
        inputs = replace(
            inputs, parents={**inputs.parents, "calibration": calibration["calibration_id"]}
        )
    stage[0] = "sources"
    resolution = resolution_for(origin, inputs)
    input_ids = {**inputs.input_ids, "source_resolution": resolution.digest()}
    aid = artifact_id(origin, input_ids, inputs.parents, inputs.config)
    if existing(root, origin, aid) is not None:
        return Published(root / origin.isoformat() / aid, aid, False)
    stage[0] = "revision"
    others, broken = [], []
    for name in _others(root, origin, aid):
        try:
            existing(root, origin, name)
            others.append(name)
        except RefreshError as error:
            broken.append({"artifact_id": name, "reason": str(error)})
    log = root / origin.isoformat() / REVISIONS
    if broken:
        _append(
            log,
            {
                "detected_at": datetime.now(UTC).isoformat(),
                "origin": origin.isoformat(),
                "new_artifact_id": aid,
                "inconsistent": broken,
                "action": "refused",
            },
        )
        raise RevisionConflict(
            f"{origin} holds inconsistent artifacts {[b['artifact_id'] for b in broken]}; "
            f"recorded in {REVISIONS} and not published"
        )
    revision = None
    if others:
        revision = revision_record(
            root, origin, others[-1], aid, input_ids, inputs, resolution.record()
        )
        if not accept_revision:
            _append(log, {**revision, "action": "refused"})
            raise RevisionConflict(
                f"{origin} already holds {others}; the revision to {aid[:12]} was recorded in "
                f"{REVISIONS} and not published"
            )
    identity = _identity(origin, input_ids, inputs)
    state = {"checkpoint": "none"}

    def write(stage: Path) -> Mapping[str, Any]:
        analysis = inputs.analysis
        loaded = (
            load_checkpoint(checkpoints, origin, aid, identity, inputs)
            if checkpoints is not None and reuse
            else None
        )
        if loaded is not None:
            prepared, fit = loaded
            state["checkpoint"] = "reused"
        else:
            prepared = prepare(
                analysis, origin, inputs.spm, inputs.logs[season - 1], inputs.logs[season]
            )
            offense, defense = inputs.config["offense_ridge"], inputs.config["defense_ridge"]
            fit = fit_informed(analysis, prepared, offense, defense, f"refresh:{origin}")
            if checkpoints is not None:
                save_checkpoint(checkpoints, origin, aid, identity, prepared, fit, retention)
                state["checkpoint"] = "computed"
        snap = as_of_ratings(
            prepared,
            fit,
            analysis.design,
            {**inputs.config, "cutoff": origin, "spm": inputs.spm.fit_id},
        )
        write_ratings(stage / RATINGS, [snap])
        (stage / SOURCES).write_text(
            json.dumps(resolution.record(), sort_keys=True) + "\n", encoding="utf-8"
        )
        head, clean = _git_head()
        return {
            "inputs": input_ids,
            "source_resolution": resolution.summary(),
            "calibration": calibration,
            "checkpoint": state["checkpoint"],
            "parents": inputs.parents,
            "config": inputs.config,
            "snapshot_id": snap.snapshot_id,
            "coverage": snap.coverage,
            "eligibility": prepared.audit,
            "code_commit": head,
            "working_tree_clean": clean,
        }

    stage[0] = "publish"
    done = publish(root, origin, aid, write)
    if revision is not None:  # recorded only once the accepted revision is actually published
        _append(log, {**revision, "action": "published"})
    return replace(done, checkpoint=state["checkpoint"])


# --- outcomes, current artifact and rollback (#145) ----------------------------------------


def record_outcome(root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """Append one auditable outcome to ``ROOT/_outcomes.jsonl`` and return it."""
    root.mkdir(parents=True, exist_ok=True)
    full = {"at": datetime.now(UTC).isoformat(), **record}
    _append(root / OUTCOMES, full)
    return full


def _failure(origin: date | None, stage: str, error: BaseException, ids: Any) -> dict[str, Any]:
    return {
        "origin": origin.isoformat() if origin else None,
        "outcome": "refused",
        "stage": stage,
        "error": type(error).__name__,
        "reason": str(error),
        "inputs": ids,
    }


def requested_inputs(
    raw: Path,
    processed: Path,
    addendum: Path = ADDENDUM,
    pins: Mapping[int, SeasonPin] = SEASON_PINS,
    calibration: Path | None = None,
) -> dict[str, Any]:
    """What a load was asked to read, recorded when the load itself is refused."""
    return {
        "raw": str(raw),
        "processed": str(processed),
        "addendum": str(addendum),
        "addendum_sha256": sha256_file(addendum) if addendum.is_file() else None,
        "row_pins": {pins[s].label: pins[s].row_manifest_sha256 for s in ROW_SEASONS if s in pins},
        "calibration": str(calibration) if calibration else None,
    }


def build(
    root: Path,
    origins: Sequence[date],
    load: Callable[[], Inputs],
    requested: Mapping[str, Any] | None = None,
    **options: Any,
) -> tuple[list[dict[str, Any]], int]:
    """Load once and refresh each origin, recording one outcome per origin; returns
    (outcomes, failures). A failure at one origin never stops the others. ``requested``
    describes the inputs for the record of a refused load."""
    try:
        inputs = load()
    except Exception as error:
        records = [record_outcome(root, _failure(o, "load", error, requested)) for o in origins]
        return records, len(records)
    outcomes, failures = [], 0
    for origin in origins:
        try:
            done = refresh_origin(root, origin, inputs, **options)
        except Exception as error:
            failures += 1
            failed = _failure(origin, stage_of(error), error, inputs.input_ids)
            outcomes.append(record_outcome(root, failed))
            continue
        outcomes.append(
            record_outcome(
                root,
                {
                    "origin": origin.isoformat(),
                    "outcome": "published" if done.created else "unchanged",
                    "artifact_id": done.artifact_id,
                    "checkpoint": done.checkpoint,
                    "path": str(done.path),
                },
            )
        )
    return outcomes, failures


def current(root: Path, origin: date) -> Path | None:
    """The artifact consumers should read for ``origin``.

    It is the single valid artifact. If an accepted revision left several, it is the latest
    one ``revisions.jsonl`` records as published. Retired artifacts are not candidates.
    """
    valid = []
    for name in _others(root, origin, ""):
        with contextlib.suppress(RefreshError):
            valid.append(existing(root, origin, name))
    found = [p for p in valid if p is not None]
    if len(found) <= 1:
        return found[0] if found else None
    log = root / origin.isoformat() / REVISIONS
    names = {p.name: p for p in found}
    if log.is_file():
        for line in reversed(log.read_text(encoding="utf-8").splitlines()):
            entry = json.loads(line)
            if entry.get("action") == "published" and entry.get("new_artifact_id") in names:
                return names[entry["new_artifact_id"]]
    raise RefreshError(f"{origin} holds {sorted(names)} and no record says which is current")


def retire(root: Path, origin: date, aid: str, reason: str) -> Path:
    """Roll back by moving an artifact to ``ROOT/_retired/<origin>/``; recorded, never deleted."""
    source = root / origin.isoformat() / aid
    if existing(root, origin, aid) is None:
        raise RefreshError(f"{source} is not a published artifact")
    target = root / RETIRED / origin.isoformat() / aid
    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(source, target)
    _fsync_dir(source.parent)
    entry = {"origin": origin.isoformat(), "artifact_id": aid, "reason": reason}
    _append(
        root / origin.isoformat() / REVISIONS,
        {"detected_at": datetime.now(UTC).isoformat(), **entry, "action": "retired"},
    )
    record_outcome(root, {**entry, "outcome": "retired", "path": str(target)})
    return target


# --- pinned replay inputs --------------------------------------------------------------


def load_inputs(
    raw: Path,
    processed: Path,
    scratch: Path,
    *,
    addendum: Path = ADDENDUM,
    pins: Mapping[int, SeasonPin] = SEASON_PINS,
    calibration: Path | None = None,
) -> Inputs:
    """The #36 configuration, locked SPM fit, outer row sets and pinned box logs.

    ``addendum`` and ``pins`` default to the registered ones; the #145 drills pass altered
    copies to show that a wrong digest refuses before anything is fitted.
    """
    config = parse_config(addendum.read_text(encoding="utf-8"))
    ei = config["models"]["ei"]
    if ei["window"] != "W2" or TEMPORAL_BY_NAME[ei["window"]].name != "W2":
        raise RefreshError("the #36 EI window is not W2")
    spm_dir = processed / "spm" / SPM_RUN
    checked_file(spm_dir / "manifest.json", SPM_MANIFEST)
    spm = spm_fit(read_json(checked_file(spm_dir / config["spm_fit"], config["spm_fit_sha256"])))
    logs, log_ids, retrieved = {}, {}, {}
    for key, pin in config["box_logs"].items():
        logs[int(key)], _ = outer_logs(raw, int(key), pin)
        log_ids[key] = pin["sha256"]
        snapshot = raw / SEASON_PINS[int(key)].label / pin["snapshot"] / "snapshot.json"
        assets = read_json(checked_file(snapshot, pin["sha256"]))["artifacts"]
        retrieved[key] = max(
            snapshot_instant(a["retrieved_at"])
            for a in assets
            if a["name"] in (PLAYER_LOG, TEAM_LOG)
        )
    _, rows, design, row_inputs = _prepare(processed, ROW_SEASONS, ROW_SEASONS, scratch, pins)
    analysis = Analysis(rows, design, Scenario("primary", np.ones(len(rows), dtype=bool)), [], [])
    row_ids = {
        label: entry["row_manifest_sha256"]
        for label, entry in row_inputs.items()
        if not label.startswith("_")
    }
    inputs = Inputs(
        analysis,
        spm,
        logs,
        {
            "window": ei["window"],
            "offense_ridge": ei["offense_ridge"],
            "defense_ridge": ei["defense_ridge"],
        },
        {
            "rows": row_ids,
            "box_logs": log_ids,
            "spm_fit_sha256": config["spm_fit_sha256"],
            "addendum_sha256": sha256_file(addendum),
        },
        {"spm": spm.fit_id, "penalty_selection": "issue-35-v1 W2 8000/8000"},
    )
    return replace(inputs, captures=replay_captures(inputs, retrieved), calibration=calibration)


Pair = tuple[float, float]


def compare_ratings(
    ours: Mapping[int, Pair], theirs: Mapping[int, Pair], cold: Pair | None
) -> dict[str, Any]:
    """Compare a refreshed v2 roster with a published legacy (#36) export of the same cutoff.

    The legacy export lists every globally indexed player. The v2 roster keeps only players
    eligible at the cutoff, and every other indexed player scores at the explicit ``cold`` prior
    (#135). So each refreshed player must match its published value, no refreshed player may be
    missing from the export, and each published player off the roster must equal the cold prior.
    """
    common = sorted(set(ours) & set(theirs))
    dropped = sorted(set(theirs) - set(ours))
    gaps = [abs(a - b) for p in common for a, b in zip(ours[p], theirs[p], strict=True)]
    cold_gaps = [
        abs(a - b)
        for p in dropped
        for a, b in zip(theirs[p], cold or (float("inf"),) * 2, strict=True)
    ]
    report: dict[str, Any] = {
        "players": len(ours),
        "missing_from_published": len(set(ours) - set(theirs)),
        "off_roster_at_cold_prior": len(dropped),
        "max_abs_rating_gap": max(gaps, default=float("inf")),
        "max_abs_cold_gap": max(cold_gaps, default=0.0),
        "non_finite": sum(not math.isfinite(g) for g in gaps + cold_gaps),
    }
    # Python's max skips a NaN that is not first, so every gap is checked, not only the max.
    report["reproduced"] = (
        bool(common)
        and report["missing_from_published"] == 0
        and all(g <= FROZEN_TOLERANCE for g in gaps + cold_gaps)
    )
    return report


def verify_frozen(root: Path, processed: Path, inputs: Inputs) -> dict[str, Any]:
    """Refresh at the #36 block cutoffs and compare with the published `issue-36-v1` ratings."""
    directory = processed / "expected_impact" / "issue-36-v1"
    manifest = read_json(directory / "manifest.json")
    path = checked_file(directory / RATINGS, manifest["outputs"][RATINGS])
    published: dict[str, dict[int, tuple[float, float]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            published.setdefault(row["as_of"], {})[int(row["player_id"])] = (
                float(row["rating_offense"]),
                float(row["rating_defense"]),
            )
    report: dict[str, Any] = {}
    rows = inputs.analysis.rows
    for season in OUTER_SEASONS:
        for block in season_blocks(rows, season):
            done = refresh_origin(root, block.cutoff, inputs)
            with (done.path / RATINGS).open(newline="", encoding="utf-8") as handle:
                records = list(csv.DictReader(handle))
            ours = {
                int(r["player_id"]): (float(r["rating_offense"]), float(r["rating_defense"]))
                for r in records
            }
            colds = {(float(r["cold_offense"]), float(r["cold_defense"])) for r in records}
            if len(colds) != 1:
                raise RefreshError(f"{done.path} does not carry one cold prior")
            theirs = published.get(block.cutoff.isoformat(), {})
            report[block.cutoff.isoformat()] = {
                "artifact_id": done.artifact_id,
                **compare_ratings(ours, theirs, colds.pop()),
            }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    retiring = sub.add_parser("retire", help="roll back one artifact of one origin")
    retiring.add_argument("root", type=Path)
    retiring.add_argument("--origin", type=date.fromisoformat, required=True)
    retiring.add_argument("--artifact", required=True)
    retiring.add_argument("--reason", required=True)
    for name in ("build", "verify-frozen"):
        p = sub.add_parser(name)
        p.add_argument("raw", type=Path)
        p.add_argument("processed", type=Path)
        p.add_argument("root", type=Path)
        if name == "build":
            p.add_argument("--origin", type=date.fromisoformat, required=True, action="append")
            p.add_argument("--no-checkpoints", action="store_true", help="neither read nor save")
            p.add_argument("--accept-revision", action="store_true")
            p.add_argument("--calibration", type=Path, help="a #136 calibration directory")
    args = parser.parse_args()
    if args.command == "retire":
        print(retire(args.root, args.origin, args.artifact, args.reason))
        return
    args.root.mkdir(parents=True, exist_ok=True)

    def load() -> Inputs:
        scratch = Path(mkdtemp(prefix=".inputs-", dir=args.root))
        try:
            return load_inputs(
                args.raw, args.processed, scratch, calibration=getattr(args, "calibration", None)
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    if args.command == "build":
        outcomes, failures = build(
            args.root,
            args.origin,
            load,
            requested_inputs(args.raw, args.processed, calibration=args.calibration),
            checkpoints=None if args.no_checkpoints else args.root / CHECKPOINTS,
            accept_revision=args.accept_revision,
        )
        for outcome in outcomes:
            print(json.dumps(outcome, default=str))
        if failures:
            raise SystemExit(f"{failures} origin(s) refused; see {args.root / OUTCOMES}")
    else:
        inputs = load()
        report = verify_frozen(args.root, args.processed, inputs)
        print(json.dumps(report, indent=2))
        failed = sorted(cutoff for cutoff, entry in report.items() if not entry["reproduced"])
        if failed or not report:
            raise SystemExit(f"frozen rebuild did not reproduce issue-36-v1 at {failed}")


if __name__ == "__main__":
    main()
