"""Pinned input snapshots for the private NBA possession builds, one season at a time."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import file_digest
from pathlib import Path
from typing import NotRequired, TypedDict, cast
from urllib.request import urlopen

ARCHIVE_REVISION = "46488f0f8e1cab58fc1256511ea808166a443a15"
ARCHIVE_BASE = f"https://raw.githubusercontent.com/shufinskiy/nba_data/{ARCHIVE_REVISION}/datasets"
BOX_BASE = "https://basketball-data.billmill.org/nba/stats"
BENTES_BASE = "https://github.com/ramirobentes/nba_data/releases/download"
RIGHTS_REF = "nba-stats-private-noncommercial-pilot"
ATTRIBUTION = "NBA.com (NBA game statistics)"
NBA_TERMS = "https://www.nba.com/termsofuse"

# Seasons are keyed by starting year, so 2023 means 2023–24. Shufinskiy names files by starting
# year, while Bill Mill and Bentes use the ending year. 2025–26 is the confirmatory holdout
# governed by issue #42. It has no pins here, so it cannot be captured, loaded or built.
HOLDOUT_START_YEAR = 2025


@dataclass(frozen=True)
class Source:
    name: str
    uri: str
    sha256: str
    size_bytes: int
    publisher: str
    revision: str | None = None
    # Basename in a local audit capture, when it differs from the snapshot name.
    local_name: str | None = None


# Shufinskiy archive digests and sizes, as recorded in the issue #51 coverage register.
_ARCHIVE_PINS: dict[int, dict[str, tuple[str, int]]] = {
    2022: {
        "nbastats": ("46fead1357db9d1e56ed8158c820fe8e65e12c444151448c4e225889296629d0", 8_551_312),
        "nbastats_po": (
            "512c600cb21b8fce1b123cf709c07e10902d7893eb3185a6f5ebe93db0447c87",
            559_312,
        ),
        "nbastatsv3": (
            "42c24abf0abbc0ccef00addaba4b8c76df230a0ff3c0e5b301353307941fd04c",
            8_640_724,
        ),
        "nbastatsv3_po": (
            "de43f41ac4ce2d7a579b5cd933f980e5413313ec8b5da734cc9c36d1bbb2bb3f",
            573_940,
        ),
        "shotdetail": (
            "62533f4e444ef0fc3354cdf6bbc04e249eb14ba9f444e6cd247c3e95d235e46d",
            2_792_344,
        ),
        "shotdetail_po": (
            "9e3137fd28b590d8c7a446c286500fc01d786e483b51fcc85f461d5a89cdbe37",
            193_132,
        ),
        "cdnnba": ("de895e3474365fc14b028f514eb0f8c9c1503b95d3f1a5aef5a408305ddfb41f", 18_705_272),
        "cdnnba_po": (
            "2f20055f6d7d54fdc74fb910ef8db0901166fca3a701a2a4f50448af3a32298c",
            1_218_416,
        ),
        "datanba": ("8be05e5ae4b598b115ecfed8d4c9cef5cd324a21d6383bd8dd185401f2ebbf69", 11_310_412),
        "datanba_po": ("b112928125780366f9b4dc40c06d480b64e738d8b3c797a37de91eb87a1540ba", 743_948),
        "pbpstats": (
            "a4847be1f5adeda20453b14cfcd7e67aaffb85398b00bdacd15ae00b3f91d710",
            15_206_248,
        ),
        "pbpstats_po": (
            "5f7cf15db7978cd553871e884253a6c69d981ad840e9b2261d828c0e514802c3",
            1_033_288,
        ),
    },
    2023: {
        "nbastats": ("ec0029c0d45a90b769d173010f60b73c6c8866acf1d4d914a72476373ce3a913", 8_480_776),
        "nbastats_po": (
            "8fce0780f0a3aaec00b84b93457edd8562cc34ccaa64a01db2f193f0048de8bb",
            536_072,
        ),
        "nbastatsv3": (
            "3a6976219b87fb50cecf8b2c54cb2af110f2f013ed8368d694035806802c8b04",
            8_622_472,
        ),
        "nbastatsv3_po": (
            "7ea0923674e736051a97c6d4e6726913564a225d800947b25b8d27f0e3eb672b",
            549_760,
        ),
        "shotdetail": (
            "303e71f967c199568b345cd73a75e595f1f99532cca3e6ce59afb286b63f840d",
            2_812_692,
        ),
        "shotdetail_po": (
            "36d6a1794c2003ae7ca4a27978956fd0385aa2619d4e35f2b32637554191fdb4",
            183_112,
        ),
        "cdnnba": ("33d49fefc809f73d5d6cbad6d1d6690e0df6c89fe2b5a4d814ecc9ea4df6101b", 18_598_380),
        "cdnnba_po": (
            "5c347769636d136504a3ccb028417333edc7a67ead0aba7e61ba5bf6cc304685",
            1_160_972,
        ),
        "datanba": ("c82be81e532b3cc023a5646ca427e2ca35812f96f1e685ee0b743aba1839bc1e", 11_196_452),
        "datanba_po": ("1198adbf2c849aa3868e7e17804840cbc9f8b91f37916ef108f44c2f2219c128", 710_044),
        "pbpstats": (
            "c4eff1692da05ec83094a056aa8d773fe7965f3d0aa7c01d1b3dd5f50a0e3fe8",
            15_029_304,
        ),
        "pbpstats_po": (
            "e561465e5fc0c0513c2bf2692d351b27662ee9342c0fd9bf5da7beda38444b73",
            976_520,
        ),
    },
    2024: {
        "nbastats": ("8f370da00ad0a6d4157921bd161d56ea32647a165d906516f2b36384a6a4989a", 8_583_784),
        "nbastats_po": (
            "19c243bfb63305f8a7e5922f37acb781d587c2768493850e5fe852c901b8ce72",
            581_156,
        ),
        "nbastatsv3": (
            "38fb8bfb43be8db3d47576600f32f25d89cc3cc05ebac77a51f4db42faf0b841",
            8_781_060,
        ),
        "nbastatsv3_po": (
            "9995c1d4b14eae69a75294d9e20559cf515d54ff8c2d3167aedda4b4de5d2cb0",
            599_168,
        ),
        "shotdetail": (
            "950100f9c84fe750ae2ac8eaeb82d24cdfb9f60a9ed04ceaa66f64789d7c216e",
            2_832_144,
        ),
        "shotdetail_po": (
            "2a972625db433504486d837c38c917146da269939e6d984b8024f148d3d79507",
            191_548,
        ),
        "cdnnba": ("35a82e6b29821adb22b8474dea8c51e08847d8e00690d1d5ffde7d000e0087d1", 18_886_652),
        "cdnnba_po": (
            "065798b27908f9e16d8f9b6f19f429d0a798d98ce67aad116c9c9b7786f801f7",
            1_255_524,
        ),
        "datanba": ("79f698e66439e3e43bdb6299eb4da7897b5e007985193350da280c8a4ec76e60", 11_344_636),
        "datanba_po": ("62068c9b16aa789e90d395ecc7891ad853f1566968ebc280f9d5f3d39f22b855", 760_372),
        "pbpstats": (
            "3e124793cc7fbc279627926e207b634fd593e5b56a69b8d0324f21460913c5c6",
            13_739_644,
        ),
        "pbpstats_po": (
            "c41f2ae7e577d117694b47da67ad0b963a554eb0640e9fa7690c16781c4b20a2",
            433_808,
        ),
    },
}

# Bill Mill team and player box logs as (sha256, bytes), from the issue #51 register.
_BOX_PINS: dict[int, tuple[tuple[str, int], tuple[str, int]]] = {
    2022: (
        ("bd3b4a9f745249c970970beffd27813ce2ed7e235a9df20228fde042535a6c43", 157_942),
        ("5f378f06b35f36bf2aa928d2fb77c4d14ed87a4f43161f43b4e4de30c601638e", 1_608_541),
    ),
    2023: (
        ("25abfb7b0d94034193c7d848515ff8b70346e7fe07cf26694ca4936bc4b332c6", 160_365),
        ("73ad4a13099b63e3ba4d3bc3d8b2da0b400aea556b265af5004fc1a17452e851", 1_637_665),
    ),
    2024: (
        ("eb3d357ecf0914211c3d62bfd56a020fd61c4853efa925949a4ad9cf0b570397", 161_071),
        ("e974d0e94025b1bbb00af90441f943938230122304c9677c850dc134cff1d3bb", 1_651_318),
    ),
}

# Bentes regular-season and playoff lineup stints as (sha256, bytes, release asset ID).
_BENTES_PINS: dict[int, tuple[tuple[str, int, int], tuple[str, int, int]]] = {
    2022: (
        ("e99075847d7748db1ea414b888fc00cfb9ee7bb9727e58794ef2e7fccbe2efb7", 1_469_829, 582067188),
        ("441759669ae9f7afbf39f4e40dc82dc4fe2378148d3e7036ad3f10b89d390260", 88_694, 582066033),
    ),
    2023: (
        ("325b2d18cdf09a0ba73bf51d32b62797bdb996bf82637c768b644d91d59c6420", 1_409_831, 582067239),
        ("60223eff0c8e587efcdd7b8951f641c86965360627254feaccf04d745210a5ec", 89_353, 582066062),
    ),
    2024: (
        ("3d4d1eaa57bb4585b7a9aaba2e77e0ad665d13d9e0b4b97d0859864f2d2b19b5", 1_497_184, 582067329),
        ("6e090b868c8bd049e52631b08facd1fc46dcefb98a8dc2c779c68926d7dfcb60", 94_824, 582066103),
    ),
}

SEASONS = tuple(sorted(_ARCHIVE_PINS))


def pinned_season(start_year: int) -> int:
    """Return a season with pinned sources, refusing the confirmatory holdout and later."""
    if start_year >= HOLDOUT_START_YEAR:
        raise ValueError(
            f"Season {start_year} is reserved for the confirmatory holdout (issue #42) "
            "and cannot be captured, loaded or built here"
        )
    if start_year not in _ARCHIVE_PINS:
        raise ValueError(f"No pinned sources for the season starting in {start_year}")
    return start_year


def _archive(name: str, sha256: str, size_bytes: int) -> Source:
    return Source(
        name,
        f"{ARCHIVE_BASE}/{name}",
        sha256,
        size_bytes,
        "shufinskiy",
        ARCHIVE_REVISION,
    )


def _archives(start_year: int, feeds: tuple[str, ...]) -> list[Source]:
    pins = _ARCHIVE_PINS[pinned_season(start_year)]
    return [
        _archive(f"{stem}_{start_year}.tar.xz", *pins[stem])
        for feed in feeds
        for stem in (feed, f"{feed}_po")
    ]


def lineup_stat_names(start_year: int) -> tuple[str, str]:
    """Bentes regular-season and playoff lineup files, which are named by ending year."""
    end = pinned_season(start_year) + 1
    return f"lineup_stats_regular_{end}.parquet", f"lineup_stats_playoffs_{end}.parquet"


def season_sources(start_year: int) -> tuple[Source, ...]:
    """Pinned build inputs for one season. Box logs keep season-neutral snapshot names."""
    team, player = _BOX_PINS[pinned_season(start_year)]
    end = start_year + 1
    return (
        *_archives(start_year, ("nbastats", "nbastatsv3", "shotdetail", "cdnnba", "datanba")),
        *(
            Source(
                f"{kind}_game_logs.parquet",
                f"{BOX_BASE}/{kind}_game_logs/season={end}/data.parquet",
                sha256,
                size_bytes,
                "billmill",
                local_name=f"{kind}_game_logs_{end}.parquet",
            )
            for kind, (sha256, size_bytes) in (("team", team), ("player", player))
        ),
    )


def season_evidence_sources(start_year: int) -> tuple[Source, ...]:
    """Pinned comparison feeds for one season. These files are never inputs to a build."""
    names = lineup_stat_names(start_year)
    return (
        *_archives(start_year, ("datanba", "cdnnba", "pbpstats")),
        *(
            Source(
                name,
                f"{BENTES_BASE}/lineup_stats/{name}",
                sha256,
                size_bytes,
                "bentes",
                f"github-release-asset-{asset}",
            )
            for name, (sha256, size_bytes, asset) in zip(
                names, _BENTES_PINS[start_year], strict=True
            )
        ),
    )


SOURCES = season_sources(2022)
# Independent comparison evidence. These files are never inputs to a pilot build.
EVIDENCE_SOURCES = season_evidence_sources(2022)


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
    # Set when the bytes were copied from a local audit capture instead of downloaded.
    # Each artifact's retrieved_at is then the modification time of the captured file.
    local_capture: NotRequired[str]


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


def _download(path: Path, source: Source) -> str:
    with urlopen(source.uri, timeout=45) as response:
        with path.open("xb") as target:
            for block in iter(lambda: response.read(65536), b""):
                if target.tell() + len(block) > source.size_bytes:
                    raise ValueError(f"Source exceeds audited size for {source.name}")
                target.write(block)
    return utc_now()


def _copy_local(path: Path, source: Source, local: Path) -> str:
    original = local / (source.local_name or source.name)
    if not original.is_file():
        raise FileNotFoundError(f"Local capture lacks {original.name}")
    verify_artifact(original, source)
    with original.open("rb") as data, path.open("xb") as target:
        shutil.copyfileobj(data, target)
    modified = datetime.fromtimestamp(original.stat().st_mtime, timezone.utc)
    return modified.isoformat()


def capture_snapshot(
    directory: Path,
    sources: tuple[Source, ...] | None = None,
    season_start_year: int = 2022,
    local: Path | None = None,
) -> Snapshot:
    """Store one complete acquisition in a new, private directory.

    With ``local``, copy already captured bytes from that directory instead of downloading.
    Every file must match its pinned size and SHA-256 either way.
    """
    pinned_season(season_start_year)
    sources = season_sources(season_start_year) if sources is None else sources
    directory.mkdir(mode=0o700, parents=True)
    snapshot: Snapshot = {
        "schema_version": 1,
        "season_start_year": season_start_year,
        "attribution": ATTRIBUTION,
        "terms": NBA_TERMS,
        "artifacts": [],
    }
    if local is not None:
        snapshot["local_capture"] = "/".join(local.resolve().parts[-2:])
    try:
        for source in sources:
            path = directory / source.name
            if local is None:
                retrieved_at = _download(path, source)
            else:
                retrieved_at = _copy_local(path, source, local)
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


def snapshot_season(directory: Path) -> int:
    """Read and validate the season recorded in a snapshot, before trusting its sources."""
    snapshot = json.loads((directory / "snapshot.json").read_text(encoding="utf-8"))
    year = snapshot.get("season_start_year") if isinstance(snapshot, dict) else None
    if type(year) is not int:
        raise ValueError("Snapshot does not record an integer season start year")
    return pinned_season(year)


def load_snapshot(
    directory: Path,
    sources: tuple[Source, ...] | None = None,
    season_start_year: int | None = None,
) -> Snapshot:
    snapshot = cast(Snapshot, json.loads((directory / "snapshot.json").read_text(encoding="utf-8")))
    year = snapshot["season_start_year"]
    if (
        snapshot["schema_version"] != 1
        or type(year) is not int
        or (season_start_year is not None and year != season_start_year)
        or snapshot["attribution"] != ATTRIBUTION
        or snapshot["terms"] != NBA_TERMS
    ):
        raise ValueError("Invalid source snapshot")
    pinned_season(year)
    sources = season_sources(year) if sources is None else sources
    records = {row["name"]: row for row in snapshot["artifacts"]}
    if len(records) != len(snapshot["artifacts"]) or records.keys() != {s.name for s in sources}:
        raise ValueError("Snapshot must contain each pinned artifact exactly once")
    for source in sources:
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
