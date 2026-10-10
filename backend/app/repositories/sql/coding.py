"""Domain objects to JSON columns and back.

Written out rather than generated. The obvious alternative — a pydantic
``TypeAdapter`` per shape — would be shorter, but it puts pydantic underneath the
repository (the domain is deliberately framework-free, see :mod:`app.domain`) and
it resolves unions by trying members in order, which turns
a shape the encoder got slightly wrong into a silently mis-typed object instead of
an error.

Encoding is generic: :func:`plain` walks any frozen dataclass. Decoding is not,
and cannot be — ``{"ref": 1, ...}`` does not say what it is, so each decoder names
the class it builds. That asymmetry is the cost of storing documents in columns,
and it is paid here, once, rather than at every call site.

Two conventions hold throughout:

* Sequences come back as ``tuple``, because every domain container is a tuple and a
  list would compare unequal to a freshly built record of the same content.
* A missing key decodes to the dataclass default. A column written before a field
  existed still reads, which is what makes adding a field to a report a code change
  rather than a data migration.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from app.domain import (
    Annotation,
    Axis,
    Credibility,
    DateBasis,
    Determination,
    Direction,
    Exhibit,
    FactCheck,
    ImageDetail,
    LedgerEntry,
    Observation,
    PlateRegion,
    Reading,
    Relevance,
    Reliability,
    Retrieval,
    Review,
    ReviewedClaim,
    Role,
    Signal,
    Stance,
    Verdict,
)

# ------------------------------------------------------------------ encode ---


def plain(value: Any) -> Any:
    """Render ``value`` as something :mod:`json` can serialise.

    Enums become their *value*, not their name, matching the columns built by
    :func:`app.models.types.enum_column` and the strings the API publishes.
    Datetimes become ISO-8601 with an offset — a JSON column has no timestamp type,
    so the offset is the only thing carrying the timezone across.
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    return value


def plain_all(values: Any) -> list[Any]:
    return [plain(item) for item in values]


# ------------------------------------------------------------------ decode ---


def _moment(value: Any) -> datetime | None:
    """Parse a stored ISO-8601 string, forcing the result to be aware.

    A value written before :class:`app.models.types.UTCDateTime` existed, or by
    anything that dropped the offset, would otherwise decode naive and compare
    unequal to every aware datetime beside it.
    """
    if not value:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _strs(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in value or ())


def _floats(value: Any) -> tuple[float, ...]:
    return tuple(float(item) for item in value or ())


def load_verdict(data: dict[str, Any]) -> Verdict:
    return Verdict(
        determination=Determination(data["determination"]),
        headline=data["headline"],
        rationale=data["rationale"],
        confidence=float(data["confidence"]),
    )


def load_ledger(rows: Any) -> tuple[LedgerEntry, ...]:
    return tuple(LedgerEntry(key=row["key"], value=row["value"]) for row in rows or ())


def load_annotations(rows: Any) -> tuple[Annotation, ...]:
    return tuple(
        Annotation(
            ref=int(row["ref"]),
            quote=row["quote"],
            note=row["note"],
            determination=Determination(row["determination"]),
        )
        for row in rows or ()
    )


def load_signals(rows: Any) -> tuple[Signal, ...]:
    return tuple(
        Signal(
            label=row["label"],
            reading=row["reading"],
            weight=float(row["weight"]),
        )
        for row in rows or ()
    )


def load_exhibits(rows: Any) -> tuple[Exhibit, ...]:
    return tuple(
        Exhibit(
            ref=int(row["ref"]),
            source=row["source"],
            published=row["published"],
            relevance=Relevance(row["relevance"]),
            reliability=Reliability(row["reliability"]),
            determination=Determination(row["determination"]),
            extract=row["extract"],
            url=row.get("url", ""),
            claim_ref=row.get("claim_ref"),
        )
        for row in rows or ()
    )


#: Written by :func:`dump_detail` so :func:`load_detail` can tell the two apart.
#: The union member cannot be inferred from the keys without guessing, and a guess
#: that lands on the wrong member produces a report whose exhibit belongs to a
#: different desk.
DETAIL_TYPE = "type"


def dump_detail(detail: ImageDetail | None) -> dict[str, Any] | None:
    if detail is None:
        return None
    kind = "image"
    return {DETAIL_TYPE: kind, **plain(detail)}


def load_detail(data: Any) -> ImageDetail | None:
    if not data:
        return None
    kind = data.get(DETAIL_TYPE)
    if kind == "image":
        return ImageDetail(
            width=int(data["width"]),
            height=int(data["height"]),
            text=data["text"],
            description=data.get("description", ""),
            observations=tuple(data.get("observations", ())),
            provenance=data.get("provenance", "Image origin has not been established."),
            web_status=data.get("web_status", "not_searched"),
            limitations=tuple(data.get("limitations", ())),
            metadata=load_ledger(data.get("metadata")),
            regions=tuple(
                PlateRegion(
                    ref=int(region["ref"]),
                    x=float(region["x"]),
                    y=float(region["y"]),
                    w=float(region["w"]),
                    h=float(region["h"]),
                    label=region["label"],
                )
                for region in data.get("regions") or ()
            ),
        )

    # An unknown discriminator is a desk this build does not have. Dropping the
    # exhibit keeps the rest of the report readable; raising would make one
    # unfamiliar row poison every read of the verification it belongs to.
    return None


def load_retrievals(rows: Any) -> tuple[Retrieval, ...]:
    return tuple(
        Retrieval(
            provider=row["provider"],
            query=row["query"],
            rank=int(row["rank"]),
            url=row["url"],
            title=row["title"],
            snippet=row["snippet"],
            score=None if row.get("score") is None else float(row["score"]),
            published_at=_moment(row.get("published_at")),
            date_basis=(
                DateBasis(row["date_basis"]) if row.get("date_basis") else None
            ),
            date_text=row.get("date_text"),
        )
        for row in rows or ()
    )


def load_credibility(data: Any) -> Credibility | None:
    if not data:
        return None
    return Credibility(
        ref=int(data["ref"]),
        domain=data["domain"],
        readings=tuple(
            Reading(
                axis=Axis(reading["axis"]),
                score=None if reading.get("score") is None else float(reading["score"]),
                observations=tuple(
                    Observation(
                        axis=Axis(observation["axis"]),
                        finding=observation["finding"],
                        direction=Direction(observation["direction"]),
                        detail=observation["detail"],
                        weight=float(observation["weight"]),
                    )
                    for observation in reading.get("observations") or ()
                ),
            )
            for reading in data.get("readings") or ()
        ),
        role=Role(data["role"]) if data.get("role") else None,
    )


def load_fact_checks(rows: Any) -> tuple[FactCheck, ...]:
    return tuple(
        FactCheck(
            source=row["source"],
            claim=ReviewedClaim(
                text=row["claim"]["text"],
                reviews=tuple(
                    Review(
                        publisher=review["publisher"],
                        site=review["site"],
                        url=review["url"],
                        rating=review["rating"],
                        title=review.get("title", ""),
                        language=review.get("language", ""),
                        reviewed_at=_moment(review.get("reviewed_at")),
                        date_text=review.get("date_text"),
                        stance=Stance(review.get("stance", Stance.UNRECOGNISED)),
                        stance_from=review.get("stance_from", ""),
                    )
                    for review in row["claim"].get("reviews") or ()
                ),
                claimant=row["claim"].get("claimant", ""),
                claimed_at=_moment(row["claim"].get("claimed_at")),
                date_text=row["claim"].get("date_text"),
            ),
            match=float(row["match"]),
            matched_entities=_strs(row.get("matched_entities")),
            matched_terms=_strs(row.get("matched_terms")),
            matched_numbers=_strs(row.get("matched_numbers")),
        )
        for row in rows or ()
    )
