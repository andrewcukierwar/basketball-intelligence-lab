"""Pinned input snapshots for the private 2022–23 NBA data pilot."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import file_digest
from pathlib import Path
from typing import TypedDict, cast
from urllib.request import urlopen

ARCHIVE_REVISION = "46488f0f8e1cab58fc1256511ea808166a443a15"
ARCHIVE_BASE = f"https://raw.githubusercontent.com/shufinskiy/nba_data/{ARCHIVE_REVISION}/datasets"
BOX_BASE = "https://basketball-data.billmill.org/nba/stats"
RIGHTS_REF = "nba-stats-private-noncommercial-pilot"
ATTRIBUTION = "NBA.com (NBA game statistics)"
NBA_TERMS = "https://www.nba.com/termsofuse"


@dataclass(frozen=True)
class Source:
    name: str
    uri: str
    sha256: str
    size_bytes: int
    publisher: str
    revision: str | None = None


def _archive(name: str, sha256: str, size_bytes: int) -> Source:
    return Source(
        name,
        f"{ARCHIVE_BASE}/{name}",
        sha256,
        size_bytes,
        "shufinskiy",
        ARCHIVE_REVISION,
    )


SOURCES = (
    _archive(
        "nbastats_2022.tar.xz",
        "46fead1357db9d1e56ed8158c820fe8e65e12c444151448c4e225889296629d0",
        8_551_312,
    ),
    _archive(
        "nbastats_po_2022.tar.xz",
        "512c600cb21b8fce1b123cf709c07e10902d7893eb3185a6f5ebe93db0447c87",
        559_312,
    ),
    _archive(
        "nbastatsv3_2022.tar.xz",
        "42c24abf0abbc0ccef00addaba4b8c76df230a0ff3c0e5b301353307941fd04c",
        8_640_724,
    ),
    _archive(
        "nbastatsv3_po_2022.tar.xz",
        "de43f41ac4ce2d7a579b5cd933f980e5413313ec8b5da734cc9c36d1bbb2bb3f",
        573_940,
    ),
    _archive(
        "shotdetail_2022.tar.xz",
        "62533f4e444ef0fc3354cdf6bbc04e249eb14ba9f444e6cd247c3e95d235e46d",
        2_792_344,
    ),
    _archive(
        "shotdetail_po_2022.tar.xz",
        "9e3137fd28b590d8c7a446c286500fc01d786e483b51fcc85f461d5a89cdbe37",
        193_132,
    ),
    Source(
        "team_game_logs.parquet",
        f"{BOX_BASE}/team_game_logs/season=2023/data.parquet",
        "bd3b4a9f745249c970970beffd27813ce2ed7e235a9df20228fde042535a6c43",
        157_942,
        "billmill",
    ),
    Source(
        "player_game_logs.parquet",
        f"{BOX_BASE}/player_game_logs/season=2023/data.parquet",
        "5f378f06b35f36bf2aa928d2fb77c4d14ed87a4f43161f43b4e4de30c601638e",
        1_608_541,
        "billmill",
    ),
)


class Artifact(TypedDict):
    artifact_id: str
    name: str
    uri: str
    source_id: str
    upstream_namespace: str
    source_revision: str | None
    sha256: str
    size_bytes: int
    retrieved_at: str
    rights_ref: str


class Snapshot(TypedDict):
    schema_version: int
    season_start_year: int
    attribution: str
    terms: str
    artifacts: list[Artifact]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    with path.open("rb") as data:
        return file_digest(data, "sha256").hexdigest()


def verify_artifact(path: Path, source: Source) -> None:
    if path.stat().st_size != source.size_bytes or sha256_file(path) != source.sha256:
        raise ValueError(f"Source bytes differ from the audited snapshot for {source.name}")


def capture_snapshot(directory: Path) -> Snapshot:
    """Store one complete acquisition in a new, private directory."""
    directory.mkdir(mode=0o700, parents=True)
    snapshot: Snapshot = {
        "schema_version": 1,
        "season_start_year": 2022,
        "attribution": ATTRIBUTION,
        "terms": NBA_TERMS,
        "artifacts": [],
    }
    try:
        for source in SOURCES:
            path = directory / source.name
            with urlopen(source.uri, timeout=45) as response:
                with path.open("xb") as target:
                    for block in iter(lambda: response.read(65536), b""):
                        if target.tell() + len(block) > source.size_bytes:
                            raise ValueError(f"Source exceeds audited size for {source.name}")
                        target.write(block)
            retrieved_at = utc_now()
            verify_artifact(path, source)
            snapshot["artifacts"].append(
                Artifact(
                    artifact_id=f"{source.name}@{source.sha256}",
                    name=source.name,
                    uri=source.uri,
                    source_id=source.publisher,
                    upstream_namespace="nba",
                    source_revision=source.revision,
                    sha256=source.sha256,
                    size_bytes=source.size_bytes,
                    retrieved_at=retrieved_at,
                    rights_ref=RIGHTS_REF,
                )
            )
        write_json(directory / "snapshot.json", snapshot)
    except BaseException:
        shutil.rmtree(directory)
        raise
    return snapshot


def load_snapshot(directory: Path) -> Snapshot:
    snapshot = cast(Snapshot, json.loads((directory / "snapshot.json").read_text(encoding="utf-8")))
    if (
        snapshot["schema_version"] != 1
        or snapshot["season_start_year"] != 2022
        or snapshot["attribution"] != ATTRIBUTION
        or snapshot["terms"] != NBA_TERMS
    ):
        raise ValueError("Invalid 2022–23 source snapshot")
    records = {row["name"]: row for row in snapshot["artifacts"]}
    if len(records) != len(snapshot["artifacts"]) or records.keys() != {s.name for s in SOURCES}:
        raise ValueError("Snapshot must contain each pinned artifact exactly once")
    for source in SOURCES:
        record = records[source.name]
        if (
            record["uri"] != source.uri
            or record["sha256"] != source.sha256
            or record["size_bytes"] != source.size_bytes
            or record["artifact_id"] != f"{source.name}@{source.sha256}"
            or record["source_id"] != source.publisher
            or record["upstream_namespace"] != "nba"
            or record["source_revision"] != source.revision
            or record["rights_ref"] != RIGHTS_REF
        ):
            raise ValueError(f"Source manifest differs from the pinned record for {source.name}")
        captured = datetime.fromisoformat(record["retrieved_at"])
        if captured.tzinfo is None or captured.utcoffset() != timezone.utc.utcoffset(captured):
            raise ValueError(f"Source capture timestamp must be UTC for {source.name}")
        verify_artifact(directory / source.name, source)
    return snapshot
