"""Resolve canonical revisions at a research cutoff."""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from hashlib import sha256
from typing import Any, Literal
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
Mode = Literal["strict_rolling", "retrospective"]
Role = Literal["features", "fit", "outcomes"]


class ValidationError(ValueError):
    """A run or its supporting evidence violates the evaluation contract."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def instant(value: object) -> datetime:
    if isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            if "T" in value and timestamp.utcoffset() == UTC.utcoffset(None):
                return timestamp
    raise ValidationError(f"expected a UTC instant, got {value!r}")


def played_before(played_date: date, rating_date: date) -> bool:
    """Whether a game's Eastern calendar date is strictly before the rating date."""
    return played_date < rating_date


def eastern_origin(day: date) -> datetime:
    """Translate midnight on an NBA rating date to UTC."""
    return datetime.combine(day, time(), EASTERN).astimezone(UTC)


@dataclass(frozen=True)
class Revision:
    """The immutable timing, source and content identity of one canonical revision."""

    key: str
    revision: int
    source_artifact_id: str
    content_sha256: str
    kind: Literal["schedule", "observation", "outcome", "external_epm"]
    availability_basis: Literal["published", "capture_bound", "unknown"]
    available_at: datetime | None
    evidence_ref: str | None
    change: Literal["upsert", "retract"] = "upsert"
    observed_date: date | None = None
    observed_at: datetime | None = None
    finalized_at: datetime | None = None

    @property
    def identity(self) -> tuple[str, int]:
        return self.key, self.revision

    @classmethod
    def from_json(cls, row: Mapping[str, Any]) -> "Revision":
        return cls(
            key=row["key"],
            revision=row["revision"],
            source_artifact_id=row["source_artifact_id"],
            content_sha256=row["content_sha256"],
            kind=row["kind"],
            availability_basis=row["availability_basis"],
            available_at=_optional_instant(row.get("available_at")),
            evidence_ref=row.get("evidence_ref"),
            change=row.get("change", "upsert"),
            observed_date=date.fromisoformat(row["observed_date"])
            if row.get("observed_date") is not None
            else None,
            observed_at=_optional_instant(row.get("observed_at")),
            finalized_at=_optional_instant(row.get("finalized_at")),
        )

    def validate(self) -> None:
        require(
            isinstance(self.key, str)
            and self.key
            and type(self.revision) is int
            and self.revision > 0,
            "canonical revision requires a nonempty key and positive integer revision",
        )
        require(
            isinstance(self.source_artifact_id, str) and self.source_artifact_id,
            f"{self.identity}: missing source artifact",
        )
        require(is_digest(self.content_sha256), f"{self.identity}: invalid content SHA-256")
        require(
            self.kind in {"schedule", "observation", "outcome", "external_epm"},
            f"{self.identity}: invalid row kind",
        )
        require(self.change in {"upsert", "retract"}, f"{self.identity}: invalid change")
        if self.availability_basis == "unknown":
            require(
                self.available_at is None, f"{self.identity}: unknown availability requires null"
            )
        else:
            require(
                self.availability_basis in {"published", "capture_bound"},
                f"{self.identity}: invalid availability basis",
            )
            require(
                self.available_at is not None
                and isinstance(self.evidence_ref, str)
                and self.evidence_ref,
                f"{self.identity}: missing availability evidence",
            )


def is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _optional_instant(value: object) -> datetime | None:
    return None if value is None else instant(value)


@dataclass(frozen=True)
class Selection:
    """Selected revisions and an auditable count of exclusions."""

    rows: tuple[Revision, ...]
    exclusions: tuple[tuple[str, int], ...]


def resolve_revisions(
    rows: Iterable[Revision],
    *,
    cutoff: datetime,
    mode: Mode,
    role: Role,
    rating_date: date | None = None,
) -> Selection:
    """Choose visible versions before applying retractions and use eligibility.

    Retrospective inputs come from an explicitly pinned snapshot and can carry
    late or unknown availability. Observation and maturity still obey the cutoff.
    """
    require(cutoff.utcoffset() == UTC.utcoffset(None), "selection cutoff must be UTC")
    require(mode in {"retrospective", "strict_rolling"}, "invalid selection mode")
    require(role in {"features", "fit", "outcomes"}, "invalid selection role")
    latest: dict[str, Revision] = {}
    seen = set()
    excluded: Counter[str] = Counter()
    for row in rows:
        row.validate()
        require(row.identity not in seen, f"duplicate canonical revision {row.identity}")
        seen.add(row.identity)
        if mode == "strict_rolling":
            if row.available_at is None:
                excluded["availability_unknown"] += 1
                continue
            if row.available_at > cutoff:
                excluded["available_after_cutoff"] += 1
                continue
        previous = latest.get(row.key)
        if previous is None or row.revision > previous.revision:
            latest[row.key] = row

    selected = []
    for row in sorted(latest.values(), key=lambda row: row.key):
        reason = _ineligible_reason(row, cutoff, role, rating_date)
        if reason:
            excluded[reason] += 1
        else:
            selected.append(row)
    return Selection(tuple(selected), tuple(sorted(excluded.items())))


def _ineligible_reason(
    row: Revision, cutoff: datetime, role: Role, rating_date: date | None
) -> str | None:
    if row.change == "retract":
        return "retracted"
    if row.kind == "external_epm" or (role == "outcomes" and row.kind != "outcome"):
        return "ineligible_source_role"
    if row.kind == "schedule":
        return None
    if rating_date is not None and row.observed_date is None:
        return "played_date_unknown"
    if (
        rating_date is not None
        and row.observed_date is not None
        and not played_before(row.observed_date, rating_date)
    ):
        return "same_or_later_played_date"
    observed_at = row.finalized_at if row.kind == "outcome" else row.observed_at
    if observed_at is None and row.kind == "observation":
        observed_at = row.finalized_at
        if row.observed_date is None or row.observed_date >= cutoff.astimezone(EASTERN).date():
            return "observation_time_unknown"
    if observed_at is None:
        return "observation_time_unknown"
    if observed_at >= cutoff:
        return "observed_at_or_after_cutoff"
    return None


def digest(content: bytes) -> str:
    return sha256(content).hexdigest()
