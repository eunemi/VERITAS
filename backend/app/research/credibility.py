"""Reading each source on the six axes of :mod:`app.domain.credibility`.

The domain module defines what a reading *is* and refuses, structurally, to let it
become a truth value. This module is the thing that produces one, and it is where the
refusal has to be kept honestly rather than only typed: a scorer with access to a
publisher registry is one careless conditional away from grading mastheads.

What it reads, and what it cannot
---------------------------------
Only two things: what the registry in :mod:`app.research.registries` says a domain
*is*, and what the search providers returned about the page — its date, whose snippets
carried a passage bearing on the claim, whether another source in the same dossier is
the same story or the same company. There is no network call, no page fetch and no
model, which is why every finding below is a fact a reader can check from the response
they were sent.

That also fixes the ceiling. Most of what anyone would want to know about a page's
transparency — is there a byline, are there citations, is there a corrections
policy — is on the page, and this service does not fetch pages. So
:attr:`~app.domain.credibility.Reading.score` is ``None`` on that axis for most sources,
and that is the design working rather than a gap in it.

One closed table, and nothing decided outside it
------------------------------------------------
Every judgement this module can make is an entry in :data:`VOCABULARY`: its axis, which
way it bears, the level it asserts, and how much of the axis it accounts for. The
functions below only *detect* — they find the fact and write the prose, and they cannot
invent a level, because :func:`_observe` will not mint an observation whose slug is not
in the table. A scoring rule spread across thirty conditionals is a scoring rule nobody
can review; this one is a table somebody can disagree with line by line.

The arithmetic, in full
-----------------------
An axis is the weighted mean of the levels of the observations on it::

    score = sum(weight * level) / sum(weight)

Nothing else happens to it. No axis is weighted against another — the domain's
:attr:`~app.domain.credibility.Credibility.standing` is a plain mean over the axes that
could be assessed, because which axis matters depends on the claim in hand and this
service does not have it.

``weight`` is published on every :class:`~app.domain.credibility.Observation` and
``level`` is in the table above, so a reader can recompute any number in a response
rather than accept it. The weights are the table's own and are therefore comparable
between sources — a ``0.9`` means the same thing everywhere — which is worth more than
normalising them to sum to one within each reading.

Three braces against "this domain is true"
------------------------------------------
**A registry hit reaches three axes and never a fourth.** Recognising a domain says
something about who is accountable (:attr:`~app.domain.credibility.Axis.RELIABILITY`),
whether it holds the record (:attr:`~app.domain.credibility.Axis.OFFICIAL`) and who it
answers to (:attr:`~app.domain.credibility.Axis.INDEPENDENCE`), and nothing whatever
about the page that was actually retrieved. :data:`REGISTRY_AXES` and
:data:`REGISTRY_FINDINGS` say so and ``test_research_credibility`` enforces it, because
:data:`~app.domain.credibility.MIN_AXES` is four: a recognised masthead therefore cannot
reach :attr:`~app.domain.credibility.Band.STRONG` on being recognised, no matter how
high its three axes score. Getting there needs something observed about the page — a
date, or a passage that bears on the claim. That is the entire point of the floor, and
it is why there is deliberately no transparency finding for "the registry names this
publisher" even though it would be true.

**A registry miss lowers nothing.** The table is a few hundred domains and the web is
hundreds of millions, so a miss is the ordinary case. It produces no observation at all
and leaves the axis unassessed, rather than a middling default that would make "nobody
here has heard of this publisher" arithmetically identical to "we looked and it was
bad". This is how a first-hand account from an outlet nobody has heard of stays readable
as evidence.

**Age is reported, never charged.** An old page is not a weak page: the 2016 debunk is
the reason a rumour is known to be false, and the statute a claim turns on may be from
1974. So the only ``lowers`` finding on :attr:`~app.domain.credibility.Axis.DATE` is
:data:`dated_after_retrieval <VOCABULARY>` — a publication date later than the moment
the page was retrieved, which is not old but impossible. Everything else about age is
``neutral``: observed, reported, and moving nothing.

What is deliberately not read
-----------------------------
**How many engines found the page.** Three providers returning one URL is one page that
is easy to find, not three witnesses, and
:attr:`~app.domain.research.Source.providers` documents that distinction. Feeding it
into :attr:`~app.domain.credibility.Axis.INDEPENDENCE` would turn search-engine
agreement into corroboration between publishers.

**The provider's own relevance score.** Tavily's ``0.81`` and Brave's silence say
nothing about each other, so there is no comparable quantity to score.

**Rank.** Where an engine placed a result is a statement about the engine's index, and
this module would be laundering it into a statement about the publisher.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.credibility import (
    ORDER,
    Axis,
    Credibility,
    Direction,
    Observation,
    Reading,
    Role,
)
from app.domain.research import DateBasis, Source
from app.research import registries

__all__ = [
    "FUTURE_TOLERANCE",
    "MAX_QUOTE_CHARS",
    "NEUTRAL",
    "REGISTRY_AXES",
    "REGISTRY_FINDINGS",
    "ROLE_FINDINGS",
    "VOCABULARY",
    "Finding",
    "rate",
]

#: The level at which an observation moves its axis neither way.
#:
#: Named rather than written as ``0.5`` in nine places, because it is the value
#: :attr:`~app.domain.credibility.Direction.NEUTRAL` is defined by: an entry in
#: :data:`VOCABULARY` is consistent exactly when its level sits above this for
#: ``raises``, below it for ``lowers``, and on it for ``neutral``.
NEUTRAL = 0.5

#: How far past the moment of retrieval a stated date may sit before it is impossible.
#:
#: A day, and the slack is not politeness. A publisher stamping a page with its own
#: local midnight can legitimately read as tomorrow in UTC, and half the world is
#: already tomorrow, so a few hours ahead is a timezone artefact rather than a false
#: date. More than a day ahead of the retrieval that found the page is neither.
FUTURE_TOLERANCE = timedelta(days=1)

#: Longest quoted fragment in an observation's ``detail``.
#:
#: The quote in a detail is there so a reader can see *what* was matched without
#: leaving the line; the whole passage is already published verbatim on
#: :attr:`~app.domain.research.Source.evidence`, with the offsets that prove it is a
#: slice. Truncation keeps the prefix exactly as it arrived and marks the cut, so the
#: fragment stays a quotation rather than becoming a paraphrase.
MAX_QUOTE_CHARS = 120


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing this module knows how to notice, and what noticing it is worth.

    The row type of :data:`VOCABULARY`. It carries the ``level`` that an
    :class:`~app.domain.credibility.Observation` does not, and the separation is on
    purpose: the level is a property of the *kind* of finding and belongs in one
    reviewable table, while an observation is one sighting of it and carries the prose
    and the axis it landed on. Publishing a per-observation level would invite a caller
    to read it as a measurement of that page rather than as this module's tariff for
    that finding.
    """

    axis: Axis
    direction: Direction
    #: What this finding asserts for its axis, in ``[0, 1]``. Must agree with
    #: ``direction`` about :data:`NEUTRAL`; ``test_research_credibility`` checks that
    #: every row does.
    level: float
    #: How much of the axis one sighting accounts for, in ``[0, 1]``. Relative to the
    #: other observations on the same reading — see the module docstring's arithmetic.
    weight: float


#: Every judgement this module can make. **Nothing decides a score outside this table.**
#:
#: Read it as a tariff a reader is invited to disagree with, not as a set of
#: measurements. Each section states what the axis is asking and each row states the
#: fact that answers it, so an entry can be argued with on its merits — "a wire service
#: is not more accountable than a national newspaper" is a sentence somebody can
#: usefully say about a line of this table, and cannot usefully say about a number in a
#: response.
#:
#: Two rows that look like mistakes and are not:
#:
#: * ``state_masthead`` sits at the same level as ``masthead``. A state broadcaster has
#:   an editorial chain and somebody who answers for the copy, which is the whole of
#:   what :attr:`~app.domain.credibility.Axis.RELIABILITY` asks. Who it answers *to* is
#:   a different question, and it is charged once, on
#:   :attr:`~app.domain.credibility.Axis.INDEPENDENCE`, where it belongs.
#: * ``fact_checking_organisation`` sits at the same level as ``masthead`` rather than
#:   above it. A fact-checker is a source like any other; privileging one here would let
#:   this service treat somebody else's verdict as evidence for a verdict.
VOCABULARY: dict[str, Finding] = {
    # ================================================================ reliability ====
    #
    # Asks: is anyone *accountable* for what this page says — an editorial chain, a
    # named institution, a body that issues corrections? Explicitly not a track record
    # of being right. This service cannot measure that, and a number claiming to would
    # be invented.
    #
    # Every row here is registry-driven, and there is no row for a registry miss: see
    # the module docstring's second brace.
    "government_registry": Finding(
        Axis.RELIABILITY, Direction.RAISES, level=0.90, weight=0.90
    ),
    "academic_registry": Finding(
        Axis.RELIABILITY, Direction.RAISES, level=0.80, weight=0.80
    ),
    "record_holder": Finding(
        Axis.RELIABILITY, Direction.RAISES, level=0.90, weight=0.90
    ),
    "document_archive": Finding(
        Axis.RELIABILITY, Direction.RAISES, level=0.75, weight=0.80
    ),
    "wire_service": Finding(
        Axis.RELIABILITY, Direction.RAISES, level=0.90, weight=0.90
    ),
    "masthead": Finding(Axis.RELIABILITY, Direction.RAISES, level=0.80, weight=0.90),
    "fact_checking_organisation": Finding(
        Axis.RELIABILITY, Direction.RAISES, level=0.80, weight=0.90
    ),
    "state_masthead": Finding(
        Axis.RELIABILITY, Direction.RAISES, level=0.80, weight=0.90
    ),
    # A republisher is accountable for the reprint and not for the reporting, which is
    # neither a point for nor against it on this axis. Recorded anyway, because a
    # response that showed nothing here could not be told apart from one where the
    # publisher was never looked up.
    "republisher": Finding(
        Axis.RELIABILITY, Direction.NEUTRAL, level=NEUTRAL, weight=0.50
    ),
    "host_does_not_vouch": Finding(
        Axis.RELIABILITY, Direction.LOWERS, level=0.20, weight=0.90
    ),
    "platform_tenant": Finding(
        Axis.RELIABILITY, Direction.LOWERS, level=0.25, weight=0.80
    ),
    # =================================================================== official ====
    #
    # Asks: does this publisher hold the record the claim is about? A statute on the
    # legislature's own site, a filing on the regulator's, a figure on the agency that
    # computed it. Authority over the record, and not over its interpretation.
    #
    # Only ever raised. A newspaper does not hold the record and nothing observable says
    # it is *bad* at holding one, so the axis stays unassessed for most sources rather
    # than scored low — the distinction the domain's ``None`` exists to keep.
    "official_suffix": Finding(
        Axis.OFFICIAL, Direction.RAISES, level=0.95, weight=1.00
    ),
    "official_publisher": Finding(
        Axis.OFFICIAL, Direction.RAISES, level=0.90, weight=0.90
    ),
    # Weaker than a government registry, and deliberately so: a university holds the
    # record of its own research and its own announcements. It does not hold the
    # government's, and a claim about what a statute says is not settled by a faculty
    # page.
    "academic_suffix": Finding(
        Axis.OFFICIAL, Direction.RAISES, level=0.65, weight=0.70
    ),
    "primary_document_host": Finding(
        Axis.OFFICIAL, Direction.RAISES, level=0.70, weight=0.80
    ),
    # A ministry's own broadcaster is the authority on what the ministry announced. Held
    # at a low weight because whether *this* claim is about that government is not
    # something this service knows, and the detail says so on every sighting.
    "government_answerable_record": Finding(
        Axis.OFFICIAL, Direction.RAISES, level=0.60, weight=0.40
    ),
    # =============================================================== transparency ====
    #
    # Asks: does the page say who published it and when, in a form that can be checked?
    #
    # The thinnest axis here, and honestly so. A byline, a corrections policy and a
    # citation list are all on the page, and this service reads only what the providers
    # returned — so what is left of the axis is the date disclosure, plus the one case
    # where the providers contradict each other about it. There is no row for "the
    # registry names this publisher", which would be true and would push a registry hit
    # onto a fourth axis; see the module docstring's first brace.
    "publication_date_stated": Finding(
        Axis.TRANSPARENCY, Direction.RAISES, level=0.85, weight=0.80
    ),
    # The provider read an absolute date off the page but would not say whether it was
    # the publication or the last-modification date. The page disclosed *a* date, which
    # is not the same as saying when it was published.
    "date_sense_unstated": Finding(
        Axis.TRANSPARENCY, Direction.NEUTRAL, level=NEUTRAL, weight=0.40
    ),
    # A relative age — "2 days ago" — is the provider's arithmetic, not a date the page
    # was seen to carry. Worth recording and worth nothing either way.
    "age_not_a_date": Finding(
        Axis.TRANSPARENCY, Direction.NEUTRAL, level=NEUTRAL, weight=0.30
    ),
    # Two engines both calling their date the publication date, and disagreeing about
    # which day it was. Whatever the page says about when it was published, it cannot be
    # checked off it cleanly — which is exactly what this axis asks.
    "providers_disagree_on_date": Finding(
        Axis.TRANSPARENCY, Direction.LOWERS, level=0.35, weight=0.60
    ),
    # =================================================================== evidence ====
    #
    # Asks: does the retrieved text substantiate anything about the claim? A reading of
    # the passages :mod:`app.research.evidence` selected, so it is a statement about
    # what the providers returned and not about the whole document — every detail below
    # says as much.
    #
    # Note what a high score here does *not* mean. A passage that flatly contradicts the
    # claim scores at the top of this axis, and must: the axis measures whether the text
    # engages the claim checkably, and a source that disagrees is the most important
    # source in a dossier.
    "passage_carries_figures": Finding(
        Axis.EVIDENCE, Direction.RAISES, level=0.95, weight=1.00
    ),
    "passage_names_subject": Finding(
        Axis.EVIDENCE, Direction.RAISES, level=0.75, weight=0.80
    ),
    "passage_shares_topic": Finding(
        Axis.EVIDENCE, Direction.RAISES, level=0.55, weight=0.60
    ),
    # The claim offered no figures, entities or keywords to anchor on — what a
    # deployment without the NLP extras produces — so the passage qualified on word
    # overlap alone. That is a fact about the claim as extracted, not about the page.
    "passage_word_overlap_only": Finding(
        Axis.EVIDENCE, Direction.NEUTRAL, level=NEUTRAL, weight=0.50
    ),
    "second_passage": Finding(
        Axis.EVIDENCE, Direction.RAISES, level=0.70, weight=0.40
    ),
    "no_qualifying_passage": Finding(
        Axis.EVIDENCE, Direction.LOWERS, level=0.15, weight=0.90
    ),
    # ======================================================================= date ====
    #
    # Asks: is the publication date known, on what basis, and how does it sit against
    # the moment of retrieval? The basis rows carry the axis; the window rows are
    # remarks at a low weight, and every one of them is ``neutral``. See the module
    # docstring's third brace on why age is never charged.
    "provider_stated_date": Finding(
        Axis.DATE, Direction.RAISES, level=0.90, weight=0.90
    ),
    "provider_undifferentiated_date": Finding(
        Axis.DATE, Direction.RAISES, level=0.70, weight=0.70
    ),
    "provider_relative_age": Finding(
        Axis.DATE, Direction.RAISES, level=0.60, weight=0.60
    ),
    # Read out of a dated path in the URL. A fact about the URL a provider returned
    # rather than a claim by the publisher, which is why it is the weakest basis and
    # still a positive one: a date that can be pointed at beats no date at all.
    "date_read_from_url": Finding(
        Axis.DATE, Direction.RAISES, level=0.55, weight=0.50
    ),
    "within_current_window": Finding(
        Axis.DATE, Direction.RAISES, level=0.75, weight=0.50
    ),
    "beyond_current_window": Finding(
        Axis.DATE, Direction.NEUTRAL, level=NEUTRAL, weight=0.40
    ),
    "long_predates_retrieval": Finding(
        Axis.DATE, Direction.NEUTRAL, level=NEUTRAL, weight=0.40
    ),
    # Not old — impossible. A page cannot have been published after the search that
    # found it, so whatever this date is, it is not the publication date.
    "dated_after_retrieval": Finding(
        Axis.DATE, Direction.LOWERS, level=0.15, weight=0.90
    ),
    # =============================================================== independence ====
    #
    # Asks: is this a distinct voice, or another copy of one already counted? The only
    # axis that is a statement about a source's *relation* to the rest of the dossier,
    # which is why it is the only one that cannot be scored from a source alone.
    "distinct_publisher": Finding(
        Axis.INDEPENDENCE, Direction.RAISES, level=0.75, weight=0.60
    ),
    "syndicated_copy": Finding(
        Axis.INDEPENDENCE, Direction.LOWERS, level=0.30, weight=0.90
    ),
    "same_publisher_twice": Finding(
        Axis.INDEPENDENCE, Direction.LOWERS, level=0.40, weight=0.70
    ),
    "shared_corporate_owner": Finding(
        Axis.INDEPENDENCE, Direction.LOWERS, level=0.35, weight=0.80
    ),
    "government_answerable_voice": Finding(
        Axis.INDEPENDENCE, Direction.LOWERS, level=0.25, weight=0.90
    ),
    "reprints_others": Finding(
        Axis.INDEPENDENCE, Direction.LOWERS, level=0.30, weight=0.90
    ),
}


#: The only axes a publisher registry lookup is allowed to move.
#:
#: The first brace in the module docstring, as data. Together with
#: :data:`~app.domain.credibility.MIN_AXES` — four of six — this is what makes "no domain
#: is automatically anything" structural rather than a matter of care: three axes is one
#: short of the floor for :attr:`~app.domain.credibility.Band.STRONG`, so a recognised
#: domain with nothing observable about the page it was found at cannot reach the top
#: band however high those three score.
REGISTRY_AXES: frozenset[Axis] = frozenset(
    {Axis.RELIABILITY, Axis.OFFICIAL, Axis.INDEPENDENCE}
)

#: The findings :mod:`app.research.registries` alone can produce.
#:
#: Enumerated rather than inferred so that adding a registry-driven finding on a fourth
#: axis is a test failure and not a quiet loss of the guarantee above. Note what is
#: absent: ``syndicated_copy``, ``same_publisher_twice``, ``shared_corporate_owner`` and
#: ``distinct_publisher`` are all on :attr:`~app.domain.credibility.Axis.INDEPENDENCE`
#: and none of them is here, because each is a fact about *this dossier* rather than
#: about the domain.
REGISTRY_FINDINGS: frozenset[str] = frozenset(
    {
        "government_registry",
        "academic_registry",
        "record_holder",
        "document_archive",
        "wire_service",
        "masthead",
        "fact_checking_organisation",
        "state_masthead",
        "republisher",
        "host_does_not_vouch",
        "platform_tenant",
        "official_suffix",
        "official_publisher",
        "academic_suffix",
        "primary_document_host",
        "government_answerable_record",
        "government_answerable_voice",
        "reprints_others",
    }
)

#: What each :class:`~app.domain.credibility.Role` establishes, and on which axes.
#:
#: The registry says what a publisher *is*; this says what that is worth. Kept as a
#: table rather than a chain of ``if`` statements so that the mapping from the eight
#: roles to the findings they fire is readable in one place — and so that adding a role
#: to :class:`~app.domain.credibility.Role` without deciding what it establishes is a
#: ``KeyError`` in a test rather than a role that silently scores nothing.
#:
#: :attr:`~app.domain.credibility.Role.STATE_CONTROLLED` is the row worth reading twice.
#: It fires on three axes and pulls in two directions: an accountable masthead, a
#: government's own record, and a voice that is not independent of the government whose
#: record it is. Collapsing those into one number is precisely what six axes exist to
#: avoid.
ROLE_FINDINGS: dict[Role, tuple[str, ...]] = {
    Role.OFFICIAL: ("record_holder", "official_publisher"),
    Role.REFERENCE: ("document_archive", "primary_document_host"),
    Role.NEWS_AGENCY: ("wire_service",),
    Role.ESTABLISHED_MEDIA: ("masthead",),
    Role.FACT_CHECKER: ("fact_checking_organisation",),
    Role.STATE_CONTROLLED: (
        "state_masthead",
        "government_answerable_record",
        "government_answerable_voice",
    ),
    Role.AGGREGATOR: ("republisher", "reprints_others"),
    Role.USER_GENERATED: ("host_does_not_vouch",),
}


# =================================================================== the entry point ====


def rate(
    sources: Sequence[Source],
    *,
    now: datetime,
    fresh_days: int,
    stale_days: int,
) -> tuple[Credibility, ...]:
    """One :class:`~app.domain.credibility.Credibility` per source, in source order.

    Parallel to ``sources`` and matched to it by
    :attr:`~app.domain.credibility.Credibility.ref`, never by position — the ref is on
    the record so a caller does not have to trust an alignment it cannot see.

    ``sources`` is one claim's sources and must be exactly that.
    :attr:`~app.domain.credibility.Axis.INDEPENDENCE` is a statement about a source's
    relation to the others in the dossier: passing a second claim's sources in would
    have a page counted as a sibling of coverage it was never weighed against, and
    passing a single source in isolation would silently drop the axis.

    ``now`` is the dossier's :attr:`~app.domain.research.Dossier.retrieved_at` rather
    than a fresh clock reading, so a page's age is measured from the same instant its
    date was resolved against. Two clocks would let one source be fresh for the dating
    and stale for the grading.

    ``fresh_days`` and ``stale_days`` are required rather than defaulted, and that is
    the point of them being parameters at all: they are configuration, they live on
    :class:`~app.core.config.Settings`, and no module in :mod:`app.research` may read
    settings. A default here would be a second copy of an operator's number, free to
    drift from the one that is actually in force.

    Nothing is dropped, reordered or rescored. Every source in gets a record out,
    including one that could not be assessed on any axis at all — which reads as
    :attr:`~app.domain.credibility.Band.UNKNOWN`, and is an absence of assessment rather
    than a finding against a publisher.
    """
    context = _Context.of(sources)
    return tuple(
        _rate_one(
            source,
            context=context,
            now=now,
            fresh=timedelta(days=fresh_days),
            stale=timedelta(days=stale_days),
        )
        for source in sources
    )


@dataclass(frozen=True, slots=True)
class _Context:
    """What the rest of the dossier says about one source's independence.

    Counted once for the whole list rather than recomputed per source, which is the only
    reason this is a type: the alternative walks every other source for each source, and
    a dossier is not always small.

    All three counters are over *distinct* things, and each distinction is load-bearing.
    ``owners`` counts domains and not sources, so one publisher returned twice is not a
    corporate group; ``domains`` counts sources, because the same publisher appearing
    twice is exactly what that finding is about.
    """

    #: How many sources share each syndication cluster id.
    clusters: Counter[int]
    #: Which distinct domains sit under each corporate owner slug, sorted.
    owners: dict[str, tuple[str, ...]]
    #: How many sources sit on each registrable domain.
    domains: Counter[str]
    #: How many sources are in the dossier at all.
    total: int

    @classmethod
    def of(cls, sources: Sequence[Source]) -> _Context:
        owners: dict[str, set[str]] = {}
        for source in sources:
            slug = registries.owner(source.domain)
            if slug is not None:
                owners.setdefault(slug, set()).add(source.domain)
        return cls(
            clusters=Counter(s.cluster for s in sources if s.cluster is not None),
            owners={slug: tuple(sorted(seen)) for slug, seen in owners.items()},
            domains=Counter(s.domain for s in sources),
            total=len(sources),
        )


def _rate_one(
    source: Source,
    *,
    context: _Context,
    now: datetime,
    fresh: timedelta,
    stale: timedelta,
) -> Credibility:
    """Read one source on all six axes.

    ``role`` is looked up once and passed down, so the six detectors cannot disagree
    about what the registry said.
    """
    role = registries.look_up(source.domain)
    observations = (
        *_reliability(source, role=role),
        *_official(source, role=role),
        *_transparency(source),
        *_evidence(source),
        *_date(source, now=now, fresh=fresh, stale=stale),
        *_independence(source, role=role, context=context),
    )
    return Credibility(
        ref=source.ref,
        domain=source.domain,
        readings=tuple(_reading(axis, observations) for axis in ORDER),
        role=role,
    )


# ======================================================================== the axes ====


def _reliability(source: Source, *, role: Role | None) -> list[Observation]:
    """Is anyone accountable for what this page says?

    Registry-driven throughout, and silent when the registry has nothing — see the
    module docstring's second brace. The suffix rules are checked as well as the
    publisher table because most government bodies are caught by a registry's
    eligibility rules rather than listed by name.
    """
    found: list[Observation] = []

    suffix = registries.official_suffix(source.host)
    if suffix is not None:
        found.append(
            _observe(
                "government_registry",
                f"{source.host} sits under the {suffix} registry, whose names are "
                f"issued only to government or treaty bodies, so a named public body "
                f"answers for this page",
            )
        )

    academic = registries.academic_suffix(source.host)
    if academic is not None:
        found.append(
            _observe(
                "academic_registry",
                f"{source.host} sits under the {academic} registry, reserved for "
                f"degree-granting institutions and research councils",
            )
        )

    tenant = registries.self_published(source.domain)
    if tenant is not None:
        found.append(
            _observe(
                "platform_tenant",
                f"{source.domain} is a tenant of {tenant}, which did not write this "
                f"and does not vouch for it — a finding about who is accountable, not "
                f"about the writing",
            )
        )

    found.extend(_from_role(role, Axis.RELIABILITY, source))
    return found


def _official(source: Source, *, role: Role | None) -> list[Observation]:
    """Does this publisher hold the record the claim is about?

    The caveat on ``official_suffix`` is written into the detail on every sighting
    rather than left to the reader, because :data:`app.research.registries.OFFICIAL_SUFFIXES`
    promises this module attaches it: a ministry's press release is authoritative on
    what the ministry announced and is not an independent assessment of whether it
    worked.
    """
    found: list[Observation] = []

    suffix = registries.official_suffix(source.host)
    if suffix is not None:
        found.append(
            _observe(
                "official_suffix",
                f"{source.host} is under the {suffix} registry, so it holds the "
                f"official record it publishes — authoritative on what this body "
                f"announced, and not an independent assessment of whether it was "
                f"right or whether it worked",
            )
        )

    academic = registries.academic_suffix(source.host)
    if academic is not None:
        found.append(
            _observe(
                "academic_suffix",
                f"{source.host} is under the {academic} registry, so it holds the "
                f"record of its own research and announcements — not the "
                f"government's, and not the last word on a claim about a statute",
            )
        )

    found.extend(_from_role(role, Axis.OFFICIAL, source))
    return found


def _transparency(source: Source) -> list[Observation]:
    """Does the page say who published it and when, in a form that can be checked?

    Almost always the thinnest reading of the six, and the module docstring says why:
    the byline, the citations and the corrections policy are on the page, and this
    service reads only what the providers returned. What survives is the date
    disclosure — and it is read off the *basis*, not the date, because the two ask
    different questions. A stated publication date is the page disclosing when it was
    published; a relative age is the provider's arithmetic about it.

    Nothing is lowered for a page whose date no provider reported. Serper reports none
    by design and Tavily none unless the request was for news, so charging for it would
    be charging a publisher for an engine's choice.
    """
    found: list[Observation] = []
    basis = source.date_basis

    if basis is DateBasis.PROVIDER:
        found.append(
            _observe(
                "publication_date_stated",
                f"a provider read an absolute publication date off this page"
                f"{_as_stated(source)}",
            )
        )
    elif basis is DateBasis.PROVIDER_MODIFIED:
        found.append(
            _observe(
                "date_sense_unstated",
                f"a provider read an absolute date off this page but would not say "
                f"whether it was the publication or the last-modification date"
                f"{_as_stated(source)}",
            )
        )
    elif basis is DateBasis.PROVIDER_RELATIVE:
        found.append(
            _observe(
                "age_not_a_date",
                f"a provider reported this page's age rather than a date it was seen "
                f"to carry{_as_stated(source)}",
            )
        )

    disputed = _disputed_dates(source)
    if disputed is not None:
        found.append(
            _observe(
                "providers_disagree_on_date",
                f"providers disagree about the publication date: "
                f"{', '.join(disputed)} — whichever the page states, it cannot be "
                f"read off cleanly",
            )
        )

    return found


def _evidence(source: Source) -> list[Observation]:
    """Does the retrieved text substantiate anything about the claim?

    The one axis that is normally assessed for every source, because an absent passage
    is a real measurement: :mod:`app.research.evidence` looked at text this service
    holds and found nothing in it bearing on the claim.

    With one exception, and it matters. If no provider returned any text at all there
    was nothing to select from, and reporting that as "no passage bore on the claim"
    would charge the page for an empty response. The axis goes unassessed instead.

    The channel of the strongest passage decides the finding, hardest channel first:
    a passage repeating the claim's own figures is checkable against it, one naming its
    subject is close, and one sharing only its topic words is background reading.
    """
    if not any(retrieval.snippet.strip() for retrieval in source.retrievals):
        return []

    if not source.evidence:
        return [
            _observe(
                "no_qualifying_passage",
                "no passage in the text the providers returned bore on the claim; "
                "this reads the retrieved snippets and not the whole page",
            )
        ]

    best = source.evidence[0]
    found: list[Observation] = []

    if best.matched_numbers:
        found.append(
            _observe(
                "passage_carries_figures",
                f"the retrieved text repeats the claim's figures "
                f"({', '.join(best.matched_numbers)}): {_quote(best.quote)}",
            )
        )
    elif best.matched_entities:
        found.append(
            _observe(
                "passage_names_subject",
                f"the retrieved text names the claim's subject "
                f"({', '.join(best.matched_entities)}) but carries none of its "
                f"figures: {_quote(best.quote)}",
            )
        )
    elif best.matched_terms:
        found.append(
            _observe(
                "passage_shares_topic",
                f"the retrieved text shares the claim's topic "
                f"({', '.join(best.matched_terms)}) and none of its figures or named "
                f"subjects: {_quote(best.quote)}",
            )
        )
    else:
        found.append(
            _observe(
                "passage_word_overlap_only",
                f"the claim offered no figures, subjects or keywords to match on, so "
                f"this passage qualified on word overlap alone: {_quote(best.quote)}",
            )
        )

    if len(source.evidence) > 1:
        found.append(
            _observe(
                "second_passage",
                f"{len(source.evidence)} passages of the retrieved text bear on the "
                f"claim rather than one",
            )
        )

    return found


def _date(
    source: Source, *, now: datetime, fresh: timedelta, stale: timedelta
) -> list[Observation]:
    """What is known about when this page was published, and on what basis?

    Two kinds of row, and the split is the third brace in the module docstring. The
    *basis* carries the axis: a date a publisher stated is worth more than one this
    service read out of a URL path, because only the first is quotable as "published
    on". The *window* is a remark at a low weight and is always ``neutral`` — an old
    page is not a weak page, and a scorer that charged for age would quietly downgrade
    the primary documents that settle most claims.

    An absent date produces nothing at all, leaving the axis unassessed. That is the
    exact case :attr:`~app.domain.credibility.Reading.score` is documented by: a source
    with no stated date is not a source with a bad date, and a middling default would
    make the two indistinguishable while looking like a measurement.
    """
    published = source.published_at
    if published is None:
        return []

    found: list[Observation] = []
    basis = source.date_basis
    if basis is not None:
        found.append(_observe(_BASIS_FINDINGS[basis], _basis_detail(source, basis)))

    when = _aware(published)
    moment = _aware(now)
    if when > moment + FUTURE_TOLERANCE:
        # No window reading follows: the age of an impossible date is not a fact about
        # the page, and reporting it as "current" would be the worst reading available.
        found.append(
            _observe(
                "dated_after_retrieval",
                f"dated {when.date().isoformat()}, later than the "
                f"{moment.date().isoformat()} search that found it — whatever this "
                f"date is, it is not the publication date",
            )
        )
        return found

    age = moment - when
    if age <= fresh:
        found.append(
            _observe(
                "within_current_window",
                f"published {_days(age)} before retrieval, inside the "
                f"{fresh.days}-day window that reads as current",
            )
        )
    elif age <= stale:
        found.append(
            _observe(
                "beyond_current_window",
                f"published {_days(age)} before retrieval, outside the "
                f"{fresh.days}-day window that reads as current — reported, and not "
                f"held against it",
            )
        )
    else:
        found.append(
            _observe(
                "long_predates_retrieval",
                f"published {_days(age)} before retrieval, more than {stale.days} "
                f"days back — old is not weak: a debunk or a statute is often the "
                f"oldest thing in a dossier and the thing that settles it",
            )
        )
    return found


def _independence(
    source: Source, *, role: Role | None, context: _Context
) -> list[Observation]:
    """Is this a distinct voice, or another copy of one already counted?

    Three ways to be the same voice twice, and they catch different things. A shared
    :attr:`~app.domain.research.Source.cluster` is the same *copy* under two mastheads.
    A shared corporate owner is two mastheads on one newsroom budget covering a story
    separately. The same domain twice is one newsroom, twice. None of them is caught by
    the others, and all three overstate corroboration when missed.

    ``distinct_publisher`` needs at least two sources before it means anything:
    independence is a relation, and a lone source has nothing to be independent of. So a
    single-source dossier leaves this axis unassessed unless the registry has something
    to say. It is also only claimed when nothing else was found here — a state
    broadcaster or an aggregator has already been read on this axis, and adding "and it
    appears only once" would dilute the finding that actually matters with the weaker
    one that happens to also be true.

    How many search engines returned the page is deliberately not read here; see the
    module docstring.
    """
    found: list[Observation] = []
    related = False

    cluster = source.cluster
    if cluster is not None and context.clusters[cluster] > 1:
        related = True
        found.append(
            _observe(
                "syndicated_copy",
                f"one of {context.clusters[cluster]} sources in this dossier carrying "
                f"the same story, so it is not a second witness to it",
            )
        )

    if context.domains[source.domain] > 1:
        related = True
        found.append(
            _observe(
                "same_publisher_twice",
                f"{context.domains[source.domain]} sources in this dossier are pages "
                f"of {source.domain}, which is one publisher and not several",
            )
        )

    siblings = _siblings(source, context)
    if siblings:
        related = True
        found.append(
            _observe(
                "shared_corporate_owner",
                f"under the same corporate owner as {', '.join(siblings)} in this "
                f"dossier, so the mastheads differ and the newsroom budget may not",
            )
        )

    found.extend(_from_role(role, Axis.INDEPENDENCE, source))

    if not related and context.total > 1 and not found:
        found.append(
            _observe(
                "distinct_publisher",
                f"{source.domain} appears once in this dossier, shares no story with "
                f"another source in it, and is not a reprint of one",
            )
        )

    return found


# ========================================================================== helpers ====


def _from_role(role: Role | None, axis: Axis, source: Source) -> list[Observation]:
    """The registry role's findings for one axis, or nothing when it holds no entry.

    ``None`` returns an empty list and that is the whole of the second brace: a domain
    the registry has never heard of produces no observation, so the axis reads as
    unassessed rather than as assessed and poor.
    """
    if role is None:
        return []
    return [
        _observe(finding, _ROLE_DETAILS[finding](source))
        for finding in ROLE_FINDINGS[role]
        if VOCABULARY[finding].axis is axis
    ]


def _observe(finding: str, detail: str) -> Observation:
    """One sighting of ``finding``, with its axis, direction and weight from the table.

    The only way an :class:`~app.domain.credibility.Observation` is built in this
    module, and the reason the vocabulary is closed in practice and not only in
    principle: a slug that is not in :data:`VOCABULARY` raises here rather than
    producing an observation with an invented weight.
    """
    row = VOCABULARY[finding]
    return Observation(
        axis=row.axis,
        finding=finding,
        direction=row.direction,
        detail=detail,
        weight=row.weight,
    )


def _reading(axis: Axis, observations: Sequence[Observation]) -> Reading:
    """One axis's :class:`~app.domain.credibility.Reading` from every observation made.

    The weighted mean in the module docstring, over the observations that landed on this
    axis. No observations means ``None``, never a default: an axis nothing bore on is
    reported as unassessed, which is a different statement from a low score and is the
    commoner one.

    Observations come out strongest first — by weight, then by how far the finding
    moves the axis, then by slug so the order is total and the same dossier always
    serialises the same way.
    """
    on_axis = [o for o in observations if o.axis is axis]
    if not on_axis:
        return Reading(axis=axis, score=None)

    total = sum(o.weight for o in on_axis)
    on_axis.sort(
        key=lambda o: (
            -o.weight,
            -abs(VOCABULARY[o.finding].level - NEUTRAL),
            o.finding,
        )
    )
    if total == 0:
        # Only reachable if the table is edited to hold a zero-weight row. An
        # observation that accounts for none of its axis cannot set the axis, and
        # dividing by it would be worse than admitting there is no score. What was
        # observed is still published — the finding happened, whatever it is worth.
        return Reading(axis=axis, score=None, observations=tuple(on_axis))

    score = sum(o.weight * VOCABULARY[o.finding].level for o in on_axis) / total
    return Reading(axis=axis, score=round(score, 4), observations=tuple(on_axis))


def _siblings(source: Source, context: _Context) -> tuple[str, ...]:
    """The other domains in this dossier under the same corporate owner as ``source``.

    Returns the sibling *domains* and never the owner slug. Naming a corporate parent in
    a response would be an assertion about a company that
    :data:`app.research.registries.OWNERS` is explicit about not being careful enough to
    make; that two of these domains are one company is checkable by a reader, and it is
    the only part that bears on the axis.
    """
    slug = registries.owner(source.domain)
    if slug is None:
        return ()
    return tuple(d for d in context.owners.get(slug, ()) if d != source.domain)


def _disputed_dates(source: Source) -> tuple[str, ...] | None:
    """The days two providers both called the publication date, when they differ.

    Restricted to :attr:`~app.domain.research.DateBasis.PROVIDER` on both sides, which
    is what makes this a contradiction rather than two facts. A provider reporting a
    2024 modification date beside another's 2017 publication date is not disagreeing
    with it — that is exactly the case
    :attr:`~app.domain.research.DateBasis.PROVIDER_MODIFIED` exists to keep separate,
    and reading it as a dispute would punish a page for having been corrected.

    Compared by day, because a relative age resolves to no finer than that and two
    engines reporting the same day at different hours are agreeing.
    """
    days = {
        retrieval.published_at.date().isoformat()
        for retrieval in source.retrievals
        if retrieval.date_basis is DateBasis.PROVIDER
        and retrieval.published_at is not None
    }
    return tuple(sorted(days)) if len(days) > 1 else None


#: Which finding each date basis fires. Exhaustive over
#: :class:`~app.domain.research.DateBasis`, so a basis added there without a tariff here
#: is a ``KeyError`` in a test rather than a date that silently scores nothing.
_BASIS_FINDINGS: dict[DateBasis, str] = {
    DateBasis.PROVIDER: "provider_stated_date",
    DateBasis.PROVIDER_MODIFIED: "provider_undifferentiated_date",
    DateBasis.PROVIDER_RELATIVE: "provider_relative_age",
    DateBasis.URL_PATH: "date_read_from_url",
}


def _basis_detail(source: Source, basis: DateBasis) -> str:
    """Prose for one date basis, quoting the provider's own string where there is one.

    :attr:`~app.domain.research.Source.date_text` is the field a reader checks a parse
    against, and it is unset exactly when no provider stated a string — a URL-path date
    has none, because no provider said it. So that branch says where the date came from
    instead of quoting something no engine sent.
    """
    if basis is DateBasis.URL_PATH:
        return (
            "no provider reported a date, so this one was read out of the dated path "
            "in the URL — a fact about the URL rather than a claim by the publisher"
        )
    stated = _as_stated(source)
    return {
        DateBasis.PROVIDER: f"a provider stated this page's publication date{stated}",
        DateBasis.PROVIDER_MODIFIED: (
            f"a provider stated an absolute date without saying whether it was the "
            f"publication or the last-modification date{stated}"
        ),
        DateBasis.PROVIDER_RELATIVE: (
            f"a provider reported a relative age, resolved against the moment of "
            f"retrieval{stated}"
        ),
    }[basis]


def _as_stated(source: Source) -> str:
    """``: "2 days ago"`` — the provider's own date string, or nothing.

    Quoted verbatim rather than reformatted, because the point of the string is that a
    reader can check this service's parse against what actually arrived.
    """
    if not source.date_text:
        return ""
    return f': "{source.date_text}"'


def _quote(passage: str) -> str:
    """``passage`` in quotation marks, cut to :data:`MAX_QUOTE_CHARS`.

    The prefix is exact and the cut is marked, so the fragment is still a quotation. The
    whole passage is on :attr:`~app.domain.research.Source.evidence` with the offsets
    that prove it is a slice of a provider's snippet; this is the reading copy.
    """
    if len(passage) <= MAX_QUOTE_CHARS:
        return f'"{passage}"'
    return f'"{passage[:MAX_QUOTE_CHARS].rstrip()}…"'


def _days(age: timedelta) -> str:
    """``"412 days"``, singular where it should be. Zero reads as "the same day"."""
    if age.days == 0:
        return "less than a day"
    if age.days == 1:
        return "1 day"
    return f"{age.days} days"


def _aware(moment: datetime) -> datetime:
    """``moment`` as UTC, reading a naive value as UTC rather than as local time.

    Every date the application produces is aware — :mod:`app.utils.clock` exists so that
    ``datetime.utcnow`` is never reached for — so this is a guard against a caller
    building a :class:`~app.domain.research.Source` by hand, not a normal path. Reading
    naive input as UTC is the same documented assumption :mod:`app.providers.dates`
    makes; the alternative is a ``TypeError`` from comparing the two, which would fail a
    whole dossier over one hand-built timestamp.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


#: Detail prose for each role-driven finding, keyed by slug.
#:
#: A table of callables rather than a branch inside :func:`_from_role`, so that every
#: entry in :data:`ROLE_FINDINGS` demonstrably has prose behind it — a slug listed there
#: and missing here is a ``KeyError`` on the first source it fires for, and a test that
#: walks the eight roles finds it before a request does.
_ROLE_DETAILS: dict[str, Callable[[Source], str]] = {
    "record_holder": lambda s: (
        f"the registry records {s.domain} as a body that holds an official record — a "
        f"legislature, court, regulator, statistics agency, central bank or standards "
        f"body"
    ),
    "official_publisher": lambda s: (
        f"{s.domain} publishes the record it holds, so it is the authority on what "
        f"that record says — and not on how it should be read"
    ),
    "document_archive": lambda s: (
        f"{s.domain} is a repository of primary documents it did not itself author, so "
        f"the documents are first-hand and the hosting is not"
    ),
    "primary_document_host": lambda s: (
        f"{s.domain} holds primary documents directly rather than reporting on them"
    ),
    "wire_service": lambda s: (
        f"{s.domain} is a wire service: original reporting, with an editorial chain "
        f"answerable for the copy"
    ),
    "masthead": lambda s: (
        f"{s.domain} is a newsroom with a masthead, an editorial chain and a "
        f"corrections process — which is accountability, and not a record of being "
        f"right"
    ),
    "fact_checking_organisation": lambda s: (
        f"{s.domain} publishes fact-checking. Noted, and not privileged: a "
        f"fact-checker is a source like any other, which is why this reads the same as "
        f"any other masthead"
    ),
    "state_masthead": lambda s: (
        f"{s.domain} has a masthead and an editorial chain, which is the whole of what "
        f"this axis asks; who it answers to is reported on independence"
    ),
    "government_answerable_record": lambda s: (
        f"{s.domain} is editorially answerable to a government, so it is the authority "
        f"on what that government announced — whether this claim is about that "
        f"government is not something this service knows"
    ),
    "government_answerable_voice": lambda s: (
        f"{s.domain} is editorially answerable to a government, so it is not an "
        f"independent voice on that government's conduct. A statement about who it "
        f"answers to, and not about whether anything it published is true"
    ),
    "republisher": lambda s: (
        f"{s.domain} republishes other publishers' work, so accountability for the "
        f"reporting lies with whoever wrote it"
    ),
    "reprints_others": lambda s: (
        f"{s.domain} republishes other publishers' work, and a reprint is not a second "
        f"witness"
    ),
    "host_does_not_vouch": lambda s: (
        f"{s.domain} does not write what it hosts and does not vouch for it. Nobody is "
        f"accountable for the text — which is not a finding about the text, and an "
        f"eyewitness with no masthead is sometimes the best source in a dossier"
    ),
}
