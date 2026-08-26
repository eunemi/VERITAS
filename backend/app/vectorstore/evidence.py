"""Evidence as indexable documents: identity, metadata, and the two dedupes.

Sits between a :class:`~app.domain.research.ClaimResearch` and whichever
:class:`~app.vectorstore.base.VectorStore` is configured, and knows nothing about
either database. Four decisions live here.

**One collection per claim.** :mod:`app.vectorstore.base` declines to invent a
metadata filter language, and rightly: the first store implemented would have
fixed its shape. The protocol already carries a ``collection`` argument, so
per-claim isolation is a naming decision rather than a query one — and it is
structural, which a filter is not. A query cannot return another claim's passages
because it never reaches them.

**A passage's identity is its text.** The id is a digest of the quote, folded, so
the same sentence found by two engines under two URLs is one document and
indexing the same dossier twice writes the same rows. ``blake2b`` rather than
:func:`hash`, which is salted per process — the reason is
:mod:`app.research.dedupe`'s: two workers must agree about what is a duplicate.

**Duplicates are removed at both ends, and neither end deletes a publisher.**
:func:`documents` merges quotes that are *identical* once folded, which is a fact
about the strings, and records every source that carried each one. :func:`collapse`
drops quotes *contained* in a better-scoring one, which is a judgement about
truncation — providers return the same paragraph cut at different lengths — and it
happens at query time, so nothing is discarded from the index and the carriers of
a collapsed copy are still named on the copy that survives.

**Nothing here reads a passage as supporting or refuting anything.** Same rule as
:mod:`app.research.evidence`: relevance is a measurement, and a flat
contradiction of the claim is the most relevant passage in the dossier.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.research import ClaimResearch, Evidence, Source
from app.research import dedupe, terms
from app.vectorstore.base import Document, Match

__all__ = [
    "KEYS",
    "Relevant",
    "collapse",
    "collection_for",
    "decode",
    "documents",
    "identity",
]

#: Prefix on every collection this module names, so a store shared with something
#: else is still legible in its own console.
COLLECTION_PREFIX = "evidence-"

#: Digest width for ids and collection names. Sixteen bytes is 32 hex characters,
#: which keeps a collection name at 41 — inside Chroma's 63-character limit, with
#: room for a longer prefix — and makes a collision between two distinct passages
#: not worth reasoning about.
DIGEST_BYTES = 16

#: The stand-in for an absent cluster. Chroma stores no ``None``, and a passage
#: that belongs to no syndication cluster has to be distinguishable from one whose
#: cluster is 0.
NO_CLUSTER = -1

#: Every metadata key written, so the encoder, the decoder and the tests read one
#: list. ``ref``, ``url``, ``domain``, ``title`` and the dates describe the
#: strongest source that carried the passage; ``refs`` and ``domains`` name all of
#: them, which is what makes the index-time merge lossless.
KEYS = (
    "claim",
    "lexical",
    "provider",
    "ref",
    "url",
    "domain",
    "title",
    "published_at",
    "date_basis",
    "cluster",
    "refs",
    "domains",
)


@dataclass(frozen=True, slots=True)
class Relevant:
    """One retrieved passage, with the source metadata stored beside it.

    ``similarity`` is the vector store's, ``lexical`` is
    :attr:`~app.domain.research.Evidence.score` as the dossier recorded it. Both
    are kept because they measure different things and disagree usefully: a
    passage that restates the claim in other words scores high on the first and
    low on the second.
    """

    quote: str
    similarity: float
    claim: str
    ref: int
    url: str
    domain: str
    title: str
    provider: str
    lexical: float
    #: Every source in the dossier that carried this exact passage, ``ref`` first.
    refs: tuple[int, ...]
    #: Their domains, in the same order. Length of this is the honest count of
    #: publishers behind the passage.
    domains: tuple[str, ...]
    published_at: datetime | None = None
    date_basis: str | None = None
    cluster: int | None = None


def collection_for(claim: str) -> str:
    """The collection holding ``claim``'s passages.

    Derived from the claim text rather than assigned, so a caller that indexed a
    dossier and a caller that later retrieves for the same claim arrive at the
    same name without storing a mapping between them.
    """
    return f"{COLLECTION_PREFIX}{_digest(claim)}"


def identity(quote: str) -> str:
    """The document id for ``quote``."""
    return _digest(quote)


def documents(research: ClaimResearch) -> tuple[Document, ...]:
    """``research``'s passages as documents, one per distinct quote.

    Sources are read in dossier order, which is strength order, so the first
    carrier of a quote is the strongest and is the one whose url, title and date
    the metadata reports.
    """
    primary: dict[str, tuple[Source, Evidence]] = {}
    carriers: dict[str, list[Source]] = {}
    for source in research.sources:
        for passage in source.evidence:
            key = identity(passage.quote)
            if key not in primary:
                primary[key] = (source, passage)
                carriers[key] = [source]
                continue
            # One page found by several engines is already one Source, so a repeat
            # key is a second publisher carrying the same sentence. All of a
            # source's passages are consecutive here, so the last carrier is the
            # only one worth comparing against.
            if carriers[key][-1].ref != source.ref:
                carriers[key].append(source)

    return tuple(
        Document(
            id=key,
            text=passage.quote,
            metadata=_encode(research.claim, source, passage, carriers[key]),
        )
        for key, (source, passage) in primary.items()
    )


def decode(match: Match) -> Relevant:
    """A store's :class:`~app.vectorstore.base.Match` back into a :class:`Relevant`."""
    metadata = match.metadata
    cluster = int(metadata.get("cluster", NO_CLUSTER))
    published = str(metadata.get("published_at") or "")
    basis = str(metadata.get("date_basis") or "")
    return Relevant(
        quote=match.text,
        similarity=match.score,
        claim=str(metadata.get("claim", "")),
        ref=int(metadata.get("ref", 0)),
        url=str(metadata.get("url", "")),
        domain=str(metadata.get("domain", "")),
        title=str(metadata.get("title", "")),
        provider=str(metadata.get("provider", "")),
        lexical=float(metadata.get("lexical", 0.0)),
        refs=tuple(int(ref) for ref in _split(metadata.get("refs"))),
        domains=tuple(_split(metadata.get("domains"))),
        published_at=datetime.fromisoformat(published) if published else None,
        date_basis=basis or None,
        cluster=None if cluster == NO_CLUSTER else cluster,
    )


def collapse(found: Sequence[Relevant]) -> list[Relevant]:
    """``found`` with truncation duplicates removed, best-scoring copy kept.

    Containment rather than similarity, and against the copy already kept rather
    than pairwise: two engines' versions of one paragraph differ by where each cut
    it, so the shorter is a subset of the longer and scores 1.0 whichever way round
    it is measured.

    A quote too short to shingle is never collapsed. Containment is 1.0 for any
    subset however small — :data:`app.research.dedupe.MIN_SHINGLES` is the guard
    against that — and the alternative to keeping it is dropping a real passage
    for being brief.
    """
    kept: list[Relevant] = []
    prints: list[frozenset[tuple[str, ...]]] = []
    for candidate in found:
        fingerprint = dedupe.shingles(candidate.quote)
        if len(fingerprint) >= dedupe.MIN_SHINGLES and any(
            dedupe.containment(fingerprint, seen) >= dedupe.CONTAINMENT_THRESHOLD
            for seen in prints
        ):
            continue
        kept.append(candidate)
        prints.append(fingerprint)
    return kept


def _encode(
    claim: str, source: Source, passage: Evidence, carriers: Sequence[Source]
) -> dict[str, str | int | float]:
    """Source metadata in the scalars every store can hold.

    Lists are comma-joined and absences are spelled out — ``""`` for an unknown
    date, :data:`NO_CLUSTER` for no cluster — because a vector store stores
    scalars and dropping the key instead would make "not known" indistinguishable
    from "not written yet". Refs are integers and domains cannot contain a comma,
    so the join is reversible.
    """
    return {
        "claim": claim,
        "lexical": passage.score,
        "provider": passage.provider,
        "ref": source.ref,
        "url": source.url,
        "domain": source.domain,
        "title": source.title,
        "published_at": source.published_at.isoformat() if source.published_at else "",
        "date_basis": source.date_basis.value if source.date_basis else "",
        "cluster": source.cluster if source.cluster is not None else NO_CLUSTER,
        "refs": ",".join(str(carrier.ref) for carrier in carriers),
        "domains": ",".join(carrier.domain for carrier in carriers),
    }


def _split(value: object) -> tuple[str, ...]:
    text = str(value or "")
    return tuple(part for part in text.split(",") if part)


def _digest(text: str) -> str:
    """A stable digest of ``text``, insensitive to case, accents and spacing.

    The three normalisations are the ones two publishers differ by without
    differing in what they said, and they are the same ones
    :mod:`app.research.evidence` compares on.
    """
    folded = terms.fold(terms.squeeze(text))
    return hashlib.blake2b(folded.encode("utf-8"), digest_size=DIGEST_BYTES).hexdigest()
