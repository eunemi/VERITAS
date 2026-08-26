"""Domain vocabulary.

The closed sets of values the application reasons about. They live here rather
than in :mod:`app.schemas` because services, the desk seam and the repository all
need them, and none of those layers should have to import a wire format to name a
determination.

Every member's *value* is the string that goes over the wire. Where that string
looks unusual — ``Determination`` is upper case and contains spaces, ``Desk`` uses
a hyphen in ``fact-check`` — it is because the frontend already publishes these
exact strings (``Determination`` in ``src/lib/types/agents.ts``, the desk ids in
``src/lib/desks.ts``) and prints them directly. Matching them means the API needs
no translation table and the vocabulary stays a single decision. The cost is that
these values are display strings; if the product is ever localised, this enum is
where the indirection gets added.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum

from app.core.errors import ValidationError


class Desk(StrEnum):
    """The examination desks.

    Values match the route segments and the keys of ``DESKS`` in
    ``src/lib/desks.ts``, so a desk named here is the desk the frontend links to.
    Declaration order is the running order and the order reports are published in.

    ``DECISION`` is not a peer of the other five. ``desks.ts`` states that it
    "Reads: The five desk records" and "Does not: Re-examine the artifact itself",
    so it adjudicates what the others found rather than examining the artifact.
    That is why it is absent from :data:`DEFAULT_DESKS`, cannot be requested, and
    is appended by the orchestrator rather than chosen by a caller.
    """

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FACT_CHECK = "fact-check"
    DECISION = "decision"


#: The desk that weighs the others' findings and signs the record. Named so the
#: orchestrator and the seam can refer to the role rather than to the member.
ADJUDICATOR = Desk.DECISION


class ArtifactKind(StrEnum):
    """What was submitted for examination.

    ``CLAIM`` is deliberately distinct from ``TEXT``: a claim is one checkable
    assertion bound for the fact-check desk, while text is prose that has to have
    its claims extracted first. Conflating them would mean the fact-check desk
    guessing which of the two it received.
    """

    TEXT = "text"
    CLAIM = "claim"
    URL = "url"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class Determination(StrEnum):
    """How a desk came down on an annotation, an exhibit, or a whole record.

    One vocabulary across all six desks, which is what lets the decision desk
    weigh their findings against each other without a per-desk translation.
    """

    SUPPORTED = "SUPPORTED"
    CONSISTENT = "CONSISTENT"
    CLEAR = "CLEAR"
    REQUIRES_VERIFICATION = "REQUIRES VERIFICATION"
    INSUFFICIENT = "INSUFFICIENT"
    CONTESTED = "CONTESTED"
    CONTRADICTED = "CONTRADICTED"
    ANOMALOUS = "ANOMALOUS"
    SYNTHETIC = "SYNTHETIC"


class Status(StrEnum):
    """Where a verification, or one desk within it, is in its lifecycle.

    One enum for both scopes because the four states are the same and a desk that
    reports a fifth would be a desk the top-level record cannot summarise.

    ``COMPLETED`` and ``FAILED`` are terminal; a client that sees either can stop
    polling. :attr:`is_terminal` is the one place that distinction is encoded, so
    a client-facing flag and any internal guard cannot drift apart.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """True when no further transition will happen without a new request."""
        return self in {Status.COMPLETED, Status.FAILED}


class Relevance(StrEnum):
    """How directly an exhibit bears on the claim."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Reliability(StrEnum):
    """How much weight the source of an exhibit carries.

    ``VERIFIED`` sits above ``HIGH`` because it means the record itself was
    reached — a primary document, not a report of one.
    """

    VERIFIED = "VERIFIED"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


#: Which desks examine which kind of artifact, and the roster used when a caller
#: names none. Taken from ``KINDS`` in ``src/app/investigate/CommissionBench.tsx``
#: rather than invented, so the roster the existing investigate page would send is
#: accepted rather than rejected. Two rows are load-bearing and easy to get wrong:
#: copy opens two desks (one reads how it is written, the other checks what it
#: asserts), and footage opens two because — in the page's own words — "footage is
#: two artifacts in one file". :data:`ADJUDICATOR` appears in no row; see
#: :class:`Desk`.
#:
#: Each roster is in :class:`Desk` declaration order, which is what a *requested*
#: roster is normalised to. Footage is the row where that matters rather than being
#: cosmetic: the orchestrator runs the desks in the order it is handed and stops at
#: the first that raises, ``Desk.VIDEO`` is not built yet, and the frontend's own
#: ``["video", "audio"]`` normalises to audio first. A default that ran video first
#: would fail a submitted video at 501 with no report on it, while the identical
#: request naming its desks explicitly came back with the track transcribed and
#: ruled on.
DEFAULT_DESKS: Mapping[ArtifactKind, tuple[Desk, ...]] = {
    ArtifactKind.TEXT: (Desk.TEXT, Desk.FACT_CHECK),
    ArtifactKind.CLAIM: (Desk.TEXT, Desk.FACT_CHECK),
    # A link is fetched and read as copy, so it goes to the same desks as text.
    ArtifactKind.URL: (Desk.TEXT, Desk.FACT_CHECK),
    ArtifactKind.IMAGE: (Desk.IMAGE,),
    ArtifactKind.AUDIO: (Desk.AUDIO,),
    ArtifactKind.VIDEO: (Desk.AUDIO, Desk.VIDEO),
}

#: Declaration order, for normalising a requested roster.
_RUNNING_ORDER: tuple[Desk, ...] = tuple(Desk)


def can_examine(desk: Desk, kind: ArtifactKind) -> bool:
    """True when ``desk`` is able to examine a ``kind`` artifact.

    False for :data:`ADJUDICATOR`, which examines nothing. Callers wanting "is
    this desk part of this verification" want :func:`desks_for` instead.
    """
    return desk in DEFAULT_DESKS.get(kind, ())


def desks_for(
    kind: ArtifactKind, requested: Iterable[Desk] | None = None
) -> tuple[Desk, ...]:
    """Resolve the examining desks for ``kind``, validating a requested roster.

    With ``requested`` omitted this returns the default roster. With one supplied
    it returns that roster, deduplicated and normalised to :class:`Desk`
    declaration order — so ``["fact-check", "text"]`` and ``["text",
    "fact-check"]`` produce the same record, and reports come back in a stable
    sequence regardless of how the request was written.

    :data:`ADJUDICATOR` is never included; the orchestrator appends it after the
    examining desks report.

    This lives in the domain rather than in the request schema so that a worker or
    a script gets identical defaults and identical rejection. Raises
    :class:`app.core.errors.ValidationError` — already a 422 — with the offending
    desk, the artifact kind and the permitted desks in ``details``.
    """
    allowed = DEFAULT_DESKS.get(kind, ())
    if requested is None:
        return allowed

    seen: list[Desk] = []
    for desk in requested:
        if desk is ADJUDICATOR:
            raise ValidationError(
                f"The {desk.value} desk cannot be requested. It reads the other "
                "desks' records and is added to every verification automatically.",
                details={
                    "desk": desk.value,
                    "artifact_kind": kind.value,
                    "allowed_desks": [d.value for d in allowed],
                },
            )
        if desk not in allowed:
            raise ValidationError(
                f"The {desk.value} desk cannot examine a {kind.value} artifact.",
                details={
                    "desk": desk.value,
                    "artifact_kind": kind.value,
                    "allowed_desks": [d.value for d in allowed],
                },
            )
        if desk not in seen:
            seen.append(desk)

    if not seen:
        raise ValidationError(
            "A verification needs at least one desk. Omit `desks` entirely to use "
            f"the default roster for a {kind.value} artifact.",
            details={
                "artifact_kind": kind.value,
                "allowed_desks": [d.value for d in allowed],
            },
        )
    return tuple(sorted(seen, key=_RUNNING_ORDER.index))
