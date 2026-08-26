"""What the model is shown, and the only things it may cite.

The brief is a closed table. Every source, passage, published review and recorded
conflict gets an id, and :mod:`app.reasoning.answer` accepts an answer only if
everything cited in it is one of those ids — so "cite your evidence" becomes a lookup
in a table this service built, rather than a request the model may satisfy with prose.

Nothing here is generated. :func:`render` lays out material already in the dossier,
verbatim, and the ids in the string a model reads are the ids its answer is checked
against, because both come from the same :class:`Brief`. A separate pass that
re-derived them could drift; there is no separate pass.

The grounding sets — :attr:`Brief.domains`, :attr:`Brief.figures`,
:attr:`Brief.passages` — are collected here rather than in the validator because they
describe the brief, and computing them next to the text they summarise is what keeps
them honest when the layout changes.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.credibility import Credibility
from app.domain.factcheck import FactCheck
from app.domain.research import Source
from app.graph.verdict import Bearing, Indication
from app.research.terms import fold, numbers, squeeze
from app.research.urls import registrable_domain

__all__ = [
    "CONFLICT",
    "EXHIBIT",
    "MAX_EXHIBITS",
    "REVIEW",
    "SOURCE",
    "Brief",
    "Exhibit",
    "assemble",
    "render",
]

#: Id prefixes. One letter each, because the model has to reproduce them exactly and
#: every extra character is a chance to get it wrong and have the answer rejected.
SOURCE = "S"
EXHIBIT = "E"
REVIEW = "R"
CONFLICT = "C"

#: Default ceiling on passages shown. Mirrors ``REASONING_MAX_EXHIBITS`` so this
#: module is usable — and testable — without a settings object.
MAX_EXHIBITS = 12

#: Longest quoted run reproduced from a review's rating text. Ratings are short
#: phrases ("Mostly False", "Pants on Fire"), and a publisher that wrote an essay
#: into the field should not get to write it into the prompt.
MAX_RATING_CHARS = 120

_DATE = "%Y-%m-%d"


@dataclass(frozen=True, slots=True)
class Exhibit:
    """One quotable passage, with the source it came from."""

    id: str
    ref: int
    domain: str
    url: str
    title: str
    quote: str
    provider: str
    published_at: datetime | None = None
    standing: float | None = None


@dataclass(frozen=True, slots=True)
class Brief:
    """Everything the model may see, plus what an answer is checked against."""

    claim: str
    exhibits: tuple[Exhibit, ...]
    #: Rendered lines, already carrying their ids. Not citable in ``evidence`` —
    #: that list is passages — but referable by id in the prose.
    reviews: tuple[str, ...]
    conflicts: tuple[str, ...]
    #: Every id in the brief, which is exactly the set an answer may name.
    ids: frozenset[str]
    #: Registrable domains that appear, so naming an outlet can be checked.
    domains: frozenset[str]
    #: Canonical figures that appear, so stating a number can be checked.
    figures: frozenset[str]
    #: Folded text of the claim and every quote, for checking quoted spans.
    passages: tuple[str, ...]

    @property
    def empty(self) -> bool:
        """Whether there is anything to reason about at all."""
        return not self.exhibits and not self.reviews

    def exhibit(self, cited: str) -> Exhibit | None:
        for exhibit in self.exhibits:
            if exhibit.id == cited:
                return exhibit
        return None


def assemble(
    claim: str,
    sources: Sequence[Source],
    *,
    fact_checks: Sequence[FactCheck] = (),
    conflicts: Sequence[Indication] = (),
    credibility: Sequence[Credibility] = (),
    max_exhibits: int = MAX_EXHIBITS,
) -> Brief:
    """Build the closed table for one claim."""
    standing = {grade.ref: grade.standing for grade in credibility}
    exhibits = _exhibits(sources, standing, max_exhibits)
    reviews = tuple(
        _review(index, check) for index, check in enumerate(fact_checks, start=1)
    )
    recorded = tuple(
        f"[{CONFLICT}{index}] {_conflict(indication)}"
        for index, indication in enumerate(conflicts, start=1)
    )

    # Only sources that contributed a passage. A source held back by the exhibit
    # ceiling is not in the rendered brief, and admitting its id or its domain would
    # let a model name an outlet it was never shown and have that pass as grounded.
    shown = tuple(
        source
        for source in sources
        if any(exhibit.ref == source.ref for exhibit in exhibits)
    )

    ids = {f"{SOURCE}{source.ref}" for source in shown}
    ids |= {exhibit.id for exhibit in exhibits}
    ids |= {f"{REVIEW}{index}" for index in range(1, len(reviews) + 1)}
    ids |= {f"{CONFLICT}{index}" for index in range(1, len(recorded) + 1)}

    quotes = tuple(exhibit.quote for exhibit in exhibits)
    return Brief(
        claim=claim,
        exhibits=exhibits,
        reviews=reviews,
        conflicts=recorded,
        ids=frozenset(ids),
        domains=_domains(shown, fact_checks),
        figures=_figures((claim, *quotes, *reviews, *recorded)),
        passages=tuple(fold(squeeze(text)) for text in (claim, *quotes)),
    )


def render(brief: Brief) -> str:
    """The brief as the model reads it."""
    lines = [f"CLAIM: {brief.claim}", ""]

    seen: dict[int, Exhibit] = {}
    for exhibit in brief.exhibits:
        seen.setdefault(exhibit.ref, exhibit)
    if seen:
        lines.append("SOURCES")
        lines += [_source(exhibit) for exhibit in seen.values()]
        lines.append("")

    if brief.exhibits:
        lines.append("EVIDENCE — the only passages you may cite")
        lines += [
            f'[{exhibit.id}] (from {SOURCE}{exhibit.ref}) "{squeeze(exhibit.quote)}"'
            for exhibit in brief.exhibits
        ]
        lines.append("")

    if brief.reviews:
        lines.append("PUBLISHED FACT CHECKS")
        lines += list(brief.reviews)
        lines.append("")

    if brief.conflicts:
        lines.append("RECORDED CONFLICTS")
        lines += list(brief.conflicts)
        lines.append("")

    return "\n".join(lines).strip()


def _exhibits(
    sources: Sequence[Source],
    standing: dict[int, float | None],
    limit: int,
) -> tuple[Exhibit, ...]:
    """Passages to show, one per source before any source gets a second.

    Breadth first, deliberately. Taking each source's passages in turn would let one
    page with six quotable sentences fill the table and leave the corroborating
    sources unrepresented — and corroboration across sources is the thing the model
    is being asked to weigh.
    """
    picked: list[Exhibit] = []
    deepest = max((len(source.evidence) for source in sources), default=0)
    for depth in range(deepest):
        for source in sources:
            if len(picked) >= limit:
                return tuple(picked)
            if depth >= len(source.evidence):
                continue
            evidence = source.evidence[depth]
            picked.append(
                Exhibit(
                    id=f"{EXHIBIT}{len(picked) + 1}",
                    ref=source.ref,
                    domain=source.domain,
                    url=source.url,
                    title=source.title,
                    quote=evidence.quote,
                    provider=evidence.provider,
                    published_at=source.published_at,
                    standing=standing.get(source.ref),
                )
            )
    return tuple(picked)


def _source(exhibit: Exhibit) -> str:
    parts = [f"[{SOURCE}{exhibit.ref}]", exhibit.domain]
    if exhibit.title:
        parts.append(f'"{squeeze(exhibit.title)}"')
    parts.append(
        f"published {exhibit.published_at.strftime(_DATE)}"
        if exhibit.published_at
        else "no publication date"
    )
    if exhibit.standing is not None:
        parts.append(f"standing {exhibit.standing:.2f}")
    return " — ".join(parts)


def _review(index: int, check: FactCheck) -> str:
    """One published fact check, with what this service made of it.

    The reading is stated as well as the rating because they can differ: a rating
    this service could not interpret is :attr:`~app.domain.factcheck.Stance.
    UNRECOGNISED`, and a model shown "rated False" with no further comment would
    reasonably treat an uncounted review as a counted one.
    """
    publishers = ", ".join(check.publishers) or "an unnamed publisher"
    ratings = ", ".join(
        squeeze(review.rating)[:MAX_RATING_CHARS]
        for review in check.reviews
        if review.rating.strip()
    )
    agreed = check.agreement
    reading = (
        f"read as {agreed.value}"
        if agreed is not None
        else "no single agreed reading, so not counted"
    )
    return (
        f"[{REVIEW}{index}] {publishers} reviewed "
        f'"{squeeze(check.claim.text)}"'
        f" — rated {ratings or 'without a stated rating'}"
        f" — {reading} — wording match {check.match:.2f}"
    )


def _conflict(indication: Indication) -> str:
    bearing = "against the claim" if indication.bearing is Bearing.REFUTES else "for it"
    return (
        f"{indication.detail or indication.agent} — counts {bearing}"
        f" at weight {indication.weight:.2f}"
    )


def _domains(
    sources: Sequence[Source], fact_checks: Sequence[FactCheck]
) -> frozenset[str]:
    """Every domain a grounded answer may name.

    Review sites are included even though a review is not citable as evidence: they
    are named in the brief, so a model repeating one has repeated something it was
    shown rather than produced an outlet from nowhere.
    """
    found = {source.domain for source in sources if source.domain}
    found |= {registrable_domain(source.host) for source in sources if source.host}
    for check in fact_checks:
        for review in check.reviews:
            if review.site:
                found.add(registrable_domain(review.site))
    return frozenset(domain for domain in found if domain)


def _figures(texts: Iterable[str]) -> frozenset[str]:
    return frozenset(figure for text in texts for figure in numbers(text))
