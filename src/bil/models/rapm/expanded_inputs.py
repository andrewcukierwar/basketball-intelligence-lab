"""Verify and load the #161 experimental historical cohort without fitting a model."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator, Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb
import numpy as np
from numpy.typing import NDArray

from bil.data.pilot_sources import sha256_file
from bil.data.rapm_rows import DECISIVE_CONTROL
from bil.models.rapm.multiseason import SeasonLoad, SeasonPin, load_season

REGISTRATION_SHA256 = "dc94fd3ba01e5f78cd140acdc57663b7c51303534e45c86dd33c981e40de1367"
COHORTS = ("matched_5", "matched_10", "expanded_15", "conditional_16")
DATA_END = np.datetime64("2023-07-01", "D")

ControlKey = tuple[str, int, int]


def _verify_file(path: Path, expected: str) -> None:
    if sha256_file(path) != expected:
        raise ValueError(f"unexpected registered digest for {path}")


def _excluded_control_keys(pilot: Path, model: Path) -> list[ControlKey]:
    """Recompute the registered #138 exclusion, limited to modeled stable-lineup rows."""
    with duckdb.connect() as connection:
        for alias, path in (
            ("model", model),
            ("possession", pilot / "possession.parquet"),
            ("event", pilot / "event.parquet"),
        ):
            connection.read_parquet(str(path)).create_view(alias)
        return [
            (str(game), int(revision), int(sequence))
            for game, revision, sequence in connection.execute(
                f"""
                select distinct m.game_id, m.stream_revision, m.possession_seq
                from model m
                join possession p using (game_id, stream_revision, possession_seq)
                join event e on e.game_id = p.game_id
                    and e.stream_revision = p.stream_revision
                    and e.seq >= p.start_seq and e.seq < p.end_seq
                where p.status = 'accepted' and {DECISIVE_CONTROL}
                    and e.team_id is not null and e.team_id <> p.offense_team_id
                order by 1, 2, 3
                """
            ).fetchall()
        ]


def _exclude(
    data: Mapping[str, NDArray[Any]],
    keys: Sequence[ControlKey],
    expected_count: int,
    expected_digest: str,
) -> dict[str, NDArray[Any]]:
    serialized = "".join(f"{game},{revision},{seq}\n" for game, revision, seq in keys)
    if len(keys) != expected_count or sha256(serialized.encode()).hexdigest() != expected_digest:
        raise ValueError("control exclusion keys differ from the registration")

    if not keys:
        return dict(data)
    retained = np.ones(len(data["game_id"]), dtype=np.bool_)
    for game, revision, sequence in keys:
        hits = (
            (data["game_id"] == game)
            & (data["stream_revision"] == revision)
            & (data["possession_seq"] == sequence)
        )
        if np.count_nonzero(hits) != 1 or np.any(hits & ~retained):
            raise ValueError(
                f"control exclusion does not identify one loaded row: {game}/{revision}/{sequence}"
            )
        retained &= ~hits
    return {name: column[retained] for name, column in data.items()}


def _load_registered_season(data_root: Path, temp: Path, record: dict[str, Any]) -> SeasonLoad:
    season = record["year"]
    pin = SeasonPin(
        record["label"],
        record["row_manifest_sha256"],
        record["pilot_build"],
        record["pilot_manifest_sha256"],
        record["row_set"],
    )
    processed = data_root / "processed"
    rows = processed / pin.label / pin.row_set
    pilot = processed / pin.label / pin.pilot_build
    raw = data_root / "raw" / pin.label
    box = raw / record["box_snapshot"]
    _verify_file(raw / record["pilot_snapshot"] / "snapshot.json", record["pilot_snapshot_sha256"])
    _verify_file(box / "snapshot.json", record["box_snapshot_sha256"])
    for name, digest in record["box_artifact_sha256"].items():
        _verify_file(box / name, digest)
    for name, digest in record["row_artifact_sha256"].items():
        _verify_file(rows / name, digest)
    _verify_file(pilot / "manifest.json", pin.pilot_manifest_sha256)
    pilot_manifest = json.loads((pilot / "manifest.json").read_bytes())
    pilot_digests = {
        item["filename"]: item["sha256"] for item in pilot_manifest["output_artifacts"]
    }
    _verify_file(pilot / "possession.parquet", pilot_digests["possession.parquet"])

    loaded = load_season(
        processed, season, (season,), temp, {season: pin}, include_stream_revision=True
    )
    dates = loaded.data["game_date"].astype("datetime64[D]")
    if np.any(np.isnat(dates)) or np.any(dates >= DATA_END):
        raise ValueError(f"{pin.label} rows are outside the registered historical date boundary")
    if loaded.audit != record["timing_audit"]:
        raise ValueError(f"{pin.label} pre-possession timing audit differs from the registration")
    conflicts = _excluded_control_keys(pilot, rows / "model_row.parquet")
    loaded.data = _exclude(
        loaded.data,
        conflicts,
        record["control_conflicts_modeled"],
        record["excluded_control_keys_sha256"],
    )
    if len(loaded.data["game_id"]) != record["usable_rows"]:
        raise ValueError(f"{pin.label} eligible row count differs from the registration")
    for kind, expected in record["coverage"].items():
        eligible = int(np.count_nonzero(loaded.data["season_type"] == kind))
        coverage = loaded.coverage[kind]
        if (
            eligible != expected["usable_rows"]
            or coverage["games_accepted"] != expected["accepted_games"]
            or coverage["games_in_reconciliation"] != expected["expected_games"]
            or coverage["eligible_possessions"] != expected["rows"]
        ):
            raise ValueError(f"{pin.label} {kind} coverage differs from the registration")
        coverage["archived_eligible_possessions"] = coverage["eligible_possessions"]
        coverage["eligible_possessions"] = eligible
    return loaded


def load_inputs(
    data_root: Path, registration: Path, cohort: str, temp: Path
) -> Iterator[SeasonLoad]:
    """Yield the registered rows in season order after checking every input lineage pin."""
    if cohort not in COHORTS:
        raise ValueError(f"unregistered expanded input cohort: {cohort}")
    _verify_file(registration, REGISTRATION_SHA256)
    manifest = json.loads(registration.read_bytes())
    selection = manifest["nested_cohorts"][cohort]
    seasons = {record["year"]: record for record in manifest["seasons"]}
    total = 0
    for year in selection["seasons"]:
        loaded = _load_registered_season(data_root, temp, seasons[year])
        total += len(loaded.data["game_id"])
        yield loaded
    if total != selection["rows"]:
        raise ValueError(f"{cohort} total eligible row count differs from the registration")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("registration", type=Path)
    parser.add_argument("--cohort", choices=COHORTS, default="conditional_16")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="bil-expanded-inputs-") as temp:
        counts = {
            item.pin.label: len(item.data["game_id"])
            for item in load_inputs(args.data_root, args.registration, args.cohort, Path(temp))
        }
    print(json.dumps({"cohort": args.cohort, "rows": sum(counts.values()), "seasons": counts}))


if __name__ == "__main__":
    main()
