"""What a web search found, and where every part of it came from.

This is the shape that passes from :mod:`app.research` to the fact-check desk, and
its design is driven by one requirement: **nothing in a dossier may be anything
other than what a provider returned.** Everything here is therefore either a
verbatim copy of provider output, a slice of one, or an arithmetic fact about the
set — and where a value is *derived*, the derivation is named in a sibling field
rather than presented as though a provider had said it.

Three consequences worth stating outright, because each one is a field that would
be absent from a less careful design:

:class:`Retrieval`
    A :class:`Source` does not merely record *that* it was found; it records who
    found it, on which query, at what rank, and with what title and snippet *that
    provider* returned. Two engines returning one URL is one source and two
    retrievals. Without this the dossier asserts a page exists on nobody's
    authority, and a merge that took the title from one result and the URL from
    another would be undetectable.

:class:`DateBasis`
    A date is either something a provider stated or something this application
    worked out, and the two are not interchangeable. ``published_at`` is never
    populated without a ``date_basis`` saying where it came from, and
    ``date_text`` keeps the provider's own string so a parse can be audited
    against it. No provider date means ``None`` — not the retrieval time, not
    today, not a guess.

:class:`ProviderOutcome`
    "We searched and found nothing" and "we could not search" are different
    answers, and a bare empty list tells them apart only by accident. Every
    provider that was asked appears here with what it did, so
    :attr:`Dossier.searched` can distinguish an absence of evidence from an
    absence of searching.

What is deliberately *not* on a :class:`Source`:
:class:`~app.domain.enums.Reliability`, or any other reckoning of what a
publisher's word is worth. How much it is worth is a policy judgement about the
world, not a fact about a search response, and putting one on a source would be
exactly the kind of unearned authority the rest of this module is built to
prevent. That rule is unchanged by anything below it: every field of a
:class:`Source` is still something a provider returned.

:attr:`ClaimResearch.credibility` is where this service's own reading of the
sources goes, and it sits *beside* :attr:`ClaimResearch.sources` rather than
inside them, exactly as :attr:`ClaimResearch.fact_checks` does. The two are
matched by :attr:`Source.ref`, so a reader can tell this service's judgement
from a provider's report without knowing how the application works. A
:class:`~app.domain.credibility.Credibility` is **not** a
:class:`~app.domain.enums.Reliability` and not a verdict: it grades the
source — who is accountable for the page, whether it holds the record it
describes, whether it is a reprint of the page beside it — and says nothing
about the claim. ``Reliability`` is still assigned elsewhere, by the fact-check
desk, when it turns these into :class:`~app.domain.verification.Exhibit`
records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.credibility import Credibility
from app.domain.factcheck import FactCheck


class DateBasis(StrEnum):
    """Where a source's publication date came from.

    Ordered from most to least authoritative, and the ordering is the point: a
    reader weighing two conflicting dates needs to know which one a publisher
    stated and which one this service worked out from a URL.

    The members are as fine-grained as they are because the three search APIs are
    each vague in a different way, and flattening that vagueness into one "date"
    field would assert precision none of them offers. Brave, for instance,
    documents ``page_age`` as "the page's date, based on its published or last
    modified date" and provides nothing to tell those two apart — so a story
    published in 2017 and corrected in 2024 may arrive stamped 2024, and calling
    that a publication date would be this service's invention rather than
    Brave's. Hence :attr:`PROVIDER_MODIFIED`.

    What is deliberately absent is a member for a **crawl timestamp**. Brave
    returns two (``page_fetched``, ``fetched_content_timestamp``) and they are
    always available, which makes them the most tempting field on the response and
    the most dishonest one to use: when a search engine last fetched a page says
    nothing about when its publisher wrote it. A five-year-old article crawled
    this morning would be dated this morning. No code path in
    :mod:`app.search` reads them, and the absence of a member here is what makes
    that structural rather than a matter of remembering.
    """

    #: The provider stated an absolute date and described it as the publication
    #: date. The strongest case. Tavily's ``published_date``, Serper's ``date``,
    #: Brave's ``article.date``.
    PROVIDER = "provider"
    #: The provider stated an absolute date but not *which* date — publication or
    #: last modification. Brave's ``page_age``. Usable for ordering and for "no
    #: later than"; not quotable as a publication date.
    PROVIDER_MODIFIED = "provider_modified"
    #: The provider returned a relative age — Brave's ``age``, documented as
    #: ``"2 days ago"`` — which only becomes a date when read against the moment
    #: of retrieval. Precise to the granularity the provider used and no further,
    #: so an age in days resolves to a day and an age in months to a month.
    PROVIDER_RELATIVE = "provider_relative"
    #: Read out of a dated path in the URL itself, ``/2017/08/30/``. Weakest, and
    #: included because news URLs carry it far more often than search APIs report
    #: a date. It is a fact about the URL rather than a claim by the publisher.
    URL_PATH = "url_path"


class ProviderStatus(StrEnum):
    """What happened when one provider was asked."""

    #: It answered every query it was given. ``results`` is what it returned,
    #: zero included.
    SEARCHED = "searched"
    #: It answered some queries and not others — a rate limit part-way through a
    #: batch, most often. Its results are real and usable; the dossier is
    #: thinner than it should be and does not pretend otherwise. Reporting this as
    #: ``SEARCHED`` would hide the gap, and as ``FAILED`` would discard evidence
    #: that was actually retrieved.
    PARTIAL = "partial"
    #: It was never asked — no API key is configured for it.
    SKIPPED = "skipped"
    #: It was asked and did not answer at all. ``code`` and ``detail`` say why.
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Retrieval:
    """One provider's report of finding one URL.

    The audit record behind every source. ``title`` and ``snippet`` are held per
    retrieval rather than only on the :class:`Source` because providers disagree
    about both — they truncate a page's text at different points and sometimes
    render a different title — and a dossier that kept only the winner could not
    show that they disagreed.

    ``snippet`` is the provider's text exactly as it arrived, unmodified. It has
    to be: :attr:`Evidence.start` and :attr:`Evidence.end` index into it, so any
    cleaning would move the offsets and quietly break the guarantee that a quote
    is a slice of what the provider actually sent.
    """

    #: The provider's registered name, e.g. ``"tavily"``.
    provider: str
    #: The query string that surfaced this result, verbatim.
    query: str
    #: 1-based position in that provider's result list for that query. A provider
    #: that ranked a page first is making a stronger statement than one that
    #: ranked it ninth, and the rank is the only form that statement takes.
    rank: int
    #: The URL exactly as the provider returned it, before normalisation.
    url: str
    #: The title exactly as the provider returned it.
    title: str
    #: The snippet exactly as the provider returned it. Evidence offsets index
    #: this string.
    snippet: str
    #: The provider's own relevance number, when it reports one. Not comparable
    #: across providers and never treated as one: Tavily's 0.81 and Brave's
    #: absence of a score say nothing about each other.
    score: float | None = None
    #: When *this* provider said the page was published, if it said anything.
    #: Held per retrieval for the same reason ``title`` is: providers disagree.
    #: One may report a 2017 publication date and another a 2024 modification
    #: date for the same URL, and a :class:`Source` that kept only the winner
    #: could not show that they disagreed — nor could a reader tell whether the
    #: date on a source was corroborated or was one engine's guess.
    published_at: datetime | None = None
    #: What kind of date :attr:`published_at` is, for this provider. ``None``
    #: exactly when ``published_at`` is ``None``.
    date_basis: DateBasis | None = None
    #: This provider's date string verbatim, kept even when it could not be
    #: parsed, so a failed parse is visible rather than silently absent.
    date_text: str | None = None


@dataclass(frozen=True, slots=True)
class Evidence:
    """A passage of a source that bears on the claim, quoted verbatim.

    Selected, never written. The quote is a slice of one retrieval's snippet, and
    the invariant is exact::

        retrieval.snippet[evidence.start : evidence.end] == evidence.quote

    for the retrieval whose ``provider`` matches this evidence's. That is the same
    guarantee :class:`~app.domain.claims.ExtractedClaim` makes about the prose it
    came from, and it is here for the same reason: a reader must be able to check
    that nothing was paraphrased into existence.

    ``provider`` names whose snippet was quoted because engines surface different
    parts of the same page, and selecting from only one of them would throw away
    the passage that happened to contain the claim's figure. Quoting from each and
    saying which is quoted costs one field and keeps the invariant exact; the
    alternative — stitching several providers' snippets into one string and
    quoting that — would produce a "verbatim" quote that no provider ever sent.

    The three ``matched_*`` tuples are why this passage was chosen. They make the
    score legible: a reader can see that a passage scored well because it repeats
    the claim's figure rather than because it shares its topic words.
    """

    #: The passage, exactly as it appears in the snippet.
    quote: str
    #: Which retrieval's snippet ``quote`` is a slice of.
    provider: str
    #: Character offset of ``quote`` in that retrieval's snippet.
    start: int
    #: Exclusive end offset, so ``snippet[start:end] == quote``.
    end: int
    #: Lexical overlap with the claim, in ``(0, 1]``. A measurement, not a
    #: judgement: it says this passage shares the claim's entities, terms and
    #: figures, and says nothing whatever about whether it supports the claim.
    #: A flat contradiction of the claim scores *high* here, and must — a source
    #: that disagrees is the most important source in the dossier.
    score: float
    #: The claim's named entities this passage repeats.
    matched_entities: tuple[str, ...] = ()
    #: The claim's keyword terms this passage repeats.
    matched_terms: tuple[str, ...] = ()
    #: The claim's figures this passage repeats. Weighted hardest of the three:
    #: a passage carrying the claim's own number is checkable against it, while
    #: one merely sharing its subject is background.
    matched_numbers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Source:
    """One web page found while researching a claim.

    Deduplicated: one ``Source`` is one page, however many providers returned it
    and however many URL spellings they used. ``retrievals`` is the evidence that
    it was found at all, and it is never empty — a source with no retrieval would
    be a page this service asserted the existence of on its own authority, which
    is the thing that must not happen.
    """

    #: 1-based, assigned after ordering, so a reader and a desk cite the same
    #: number for the same page.
    ref: int
    #: The normalised URL: the one identity this page is deduplicated on.
    url: str
    #: Every distinct spelling a provider returned for it, in provider order.
    #: Kept because normalisation is lossy — a stripped tracking parameter cannot
    #: be recovered — and because a caller following the link should be able to
    #: use exactly what the provider gave.
    urls: tuple[str, ...]
    #: The chosen title. Providers disagree; ``retrievals`` holds each one's.
    title: str
    #: Registrable domain — the unit of publisher identity, so ``bbc.co.uk``
    #: rather than ``www.bbc.co.uk`` and ``foo.substack.com`` rather than
    #: ``substack.com``. This is what independence is counted over.
    domain: str
    #: Full lower-cased host, kept alongside ``domain`` because the subdomain is
    #: often the section — ``news.``, ``blogs.`` — and a reader wants it.
    host: str
    #: Passages of this page that bear on the claim, strongest first. Empty when
    #: nothing in any snippet did, which is reported rather than papered over: an
    #: arbitrary first sentence presented as "evidence" would be a fabrication of
    #: relevance even though every character of it was real.
    evidence: tuple[Evidence, ...]
    #: Who found it, on what query, at what rank. Never empty.
    retrievals: tuple[Retrieval, ...]
    #: When it was published, if that is known at all. Chosen from the
    #: retrievals by the strength of their basis — a stated publication date
    #: beats an ambiguous one, which beats a relative age, which beats a date
    #: read out of the URL — and ties broken by retrieval order. Every
    #: provider's own answer stays on its :class:`Retrieval`, so a disagreement
    #: is recorded rather than resolved away.
    published_at: datetime | None = None
    #: Where :attr:`published_at` came from. ``None`` exactly when
    #: ``published_at`` is ``None``.
    date_basis: DateBasis | None = None
    #: The provider's own date string, verbatim, when there was one — so a parse
    #: can be checked against what arrived rather than trusted. Belongs to
    #: whichever retrieval supplied :attr:`published_at`; it is not set when the
    #: date was derived from the URL, since no provider said it.
    date_text: str | None = None
    #: Which syndication cluster this belongs to, or ``None`` when it stands
    #: alone. Sources sharing a cluster are telling the same story — one wire
    #: report under several mastheads — and count once toward corroboration.
    #: They are *marked*, never merged: a false merge would delete a real
    #: publisher, while a false cluster label only miscounts and stays visible.
    cluster: int | None = None

    @property
    def providers(self) -> tuple[str, ...]:
        """Which providers returned this page, in retrieval order, deduplicated.

        Corroboration between search engines, which is worth knowing and is not
        the same thing as corroboration between publishers: three engines
        returning one page is one source that is easy to find, not three sources.
        """
        seen: list[str] = []
        for retrieval in self.retrievals:
            if retrieval.provider not in seen:
                seen.append(retrieval.provider)
        return tuple(seen)

    @property
    def best_rank(self) -> int:
        """The strongest position any provider gave it."""
        return min(retrieval.rank for retrieval in self.retrievals)

    def snippet_for(self, provider: str) -> str | None:
        """The snippet ``provider`` returned, for checking an evidence quote.

        The first, when a provider returned the page for more than one query.
        Evidence records which provider it was quoted from, and this is how a
        caller — or a test — gets back the string those offsets index.
        """
        for retrieval in self.retrievals:
            if retrieval.provider == provider:
                return retrieval.snippet
        return None


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    """What one provider did when it was asked.

    Present for every provider in the roster, including the ones that were never
    called, because the alternative is a dossier whose emptiness cannot be
    explained. A caller seeing no sources needs to know whether three engines
    agreed there is nothing to find or three engines were misconfigured, and
    those two produce an identical ``sources`` list.
    """

    provider: str
    status: ProviderStatus
    #: The queries it was given. Empty when ``SKIPPED``.
    queries: tuple[str, ...] = ()
    #: Raw results returned across all its queries, before deduplication. Larger
    #: than this provider's contribution to ``sources`` whenever it returned the
    #: same page twice or a page another provider also returned.
    results: int = 0
    #: The error ``code`` from :mod:`app.core.errors` when ``FAILED``, so a client
    #: can branch on a partial dossier the way it branches on a failed request.
    code: str = ""
    #: Human-readable explanation: why it was skipped, or how it failed. Never
    #: contains a credential — see :func:`app.providers.http.redact`.
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SkippedClaim:
    """A claim that was submitted or extracted but never searched for, and why.

    Exists so a dossier describes the whole submission rather than the part of it that
    happened to be researched. Prose making twelve claims of which three were searched
    produces a dossier that, without this, reads as prose making three — every claim in
    it real, and the overall picture wrong. Two things cause it: the extractor judged a
    clause unfit to check, or the per-request claim ceiling cut it off.
    """

    #: The claim text, so a caller that disagrees can resubmit it on its own.
    claim: str
    #: Plain prose. The extractor's own reason, or the ceiling that applied.
    reason: str


@dataclass(frozen=True, slots=True)
class ClaimResearch:
    """The sources found for one claim.

    ``queries`` is every formulation that was actually sent, not a
    reconstruction: a reader who wants to know why an obvious source is missing
    should be able to see what was asked, and repeat it.
    """

    #: The claim as it was researched — the self-contained rewrite, since that is
    #: what the queries were built from.
    claim: str
    #: Every query sent for this claim, in the order they were built.
    queries: tuple[str, ...]
    #: Deduplicated pages, strongest first.
    sources: tuple[Source, ...]
    #: Fact checks already published on this claim, closest wording first.
    #:
    #: Kept beside :attr:`sources` rather than folded into them, and that separation is
    #: the point: a fact check is a source, but it is a source whose author was doing
    #: this service's job, and mixing the two would let a published verdict be read as
    #: corroborating evidence for one. It also means a reader can see the ratio — six
    #: pages and no fact check is a different situation from six pages and three.
    #:
    #: Empty means one of three things, and :attr:`Dossier.fact_checked` is what tells
    #: them apart: no database was configured, the lookup failed, or nobody has
    #: reviewed this claim. Only the third is a statement about the world.
    fact_checks: tuple[FactCheck, ...] = ()
    #: How well each source stands up *as a source*, one entry per entry in
    #: :attr:`sources`.
    #:
    #: A **parallel tuple**, matched to :attr:`sources` by
    #: :attr:`~app.domain.credibility.Credibility.ref` rather than a field on a
    #: :class:`Source`, and the separation is the same one :attr:`fact_checks` draws:
    #: a source carries only what a provider returned, and every number here is this
    #: service's own reading. Kept beside the sources, a reader can see which is which
    #: without knowing how this application works.
    #:
    #: It grades the publisher and the page, never the claim —
    #: :mod:`app.domain.credibility` imports no verdict type and has no field that
    #: could carry one. Empty when the scoring is switched off, which is an absence of
    #: assessment rather than a finding about any source in the list.
    credibility: tuple[Credibility, ...] = ()

    @property
    def domains(self) -> tuple[str, ...]:
        """Distinct publishers, in the order they first appear."""
        seen: list[str] = []
        for source in self.sources:
            if source.domain not in seen:
                seen.append(source.domain)
        return tuple(seen)

    @property
    def stories(self) -> int:
        """How many distinct stories the sources amount to.

        Sources in one syndication cluster count once; unclustered sources count
        individually. This is the number to read as corroboration, and it is
        reported alongside ``len(domains)`` rather than instead of it: eight
        mastheads carrying one wire report are eight domains and one story, and a
        reader who is shown only the eight has been misled by arithmetic.
        """
        clusters = {s.cluster for s in self.sources if s.cluster is not None}
        alone = sum(1 for s in self.sources if s.cluster is None)
        return len(clusters) + alone


@dataclass(frozen=True, slots=True)
class Dossier:
    """Everything one research request found.

    :attr:`searched` is the field that keeps this honest. An empty dossier means
    one of two opposite things — nothing is out there, or nothing was asked — and
    a consumer that cannot tell them apart will report "no evidence found" for an
    expired API key. So the outcomes are part of the result rather than a log
    line, and "we do not know" is a state this type can express.
    """

    #: One entry per claim researched, in the order they were submitted.
    claims: tuple[ClaimResearch, ...]
    #: One entry per provider in the roster, whatever became of it.
    providers: tuple[ProviderOutcome, ...]
    #: When the search ran. The anchor for any ``PROVIDER_RELATIVE`` date, which
    #: is why it is recorded rather than left to the reader's clock.
    retrieved_at: datetime
    #: Claims that were not researched, and why. Empty when everything submitted was
    #: searched for, which is the common case.
    skipped: tuple[SkippedClaim, ...] = ()
    #: What became of the fact-check database, on the same terms as :attr:`providers`.
    #:
    #: A separate field rather than another entry in :attr:`providers` because the two
    #: answer different questions and :attr:`searched` reads the first. A deployment
    #: with search keys and no fact-check key has searched the web perfectly well, and
    #: folding a ``SKIPPED`` fact-check outcome in with the search providers would make
    #: :attr:`complete` false for a dossier that is complete in every way the operator
    #: configured.
    fact_checkers: tuple[ProviderOutcome, ...] = ()

    @property
    def searched(self) -> bool:
        """True when at least one provider actually answered.

        False makes every empty ``sources`` list in this dossier meaningless
        rather than negative, and a caller must treat it that way.

        A partial answer counts: results that were retrieved are real, whatever
        else went wrong alongside them.
        """
        return any(
            o.status in (ProviderStatus.SEARCHED, ProviderStatus.PARTIAL)
            for o in self.providers
        )

    @property
    def complete(self) -> bool:
        """True when every provider in the roster answered every query.

        A dossier can be useful without being complete; the distinction belongs
        to the caller, which is why both are reported and neither is an error.
        Partial and skipped providers both make this false — the first because
        some queries went unanswered, the second because a configured roster with
        a missing key is a narrower search than the operator asked for.
        """
        return bool(self.providers) and all(
            o.status is ProviderStatus.SEARCHED for o in self.providers
        )

    @property
    def failures(self) -> tuple[ProviderOutcome, ...]:
        """The providers that were asked and returned nothing usable.

        Partial providers are excluded: they did return usable results, and
        :attr:`complete` is what reveals them.
        """
        return tuple(o for o in self.providers if o.status is ProviderStatus.FAILED)

    @property
    def sources(self) -> int:
        """Total pages found across every claim, counting a shared page once per
        claim it was found for."""
        return sum(len(claim.sources) for claim in self.claims)

    @property
    def fact_checked(self) -> bool:
        """True when a fact-check database actually answered.

        This is :attr:`searched`'s counterpart and it exists for a sharper reason. An
        empty :attr:`ClaimResearch.fact_checks` reads naturally as "no fact-checker has
        ruled on this claim" — a statement about the world, and an inviting one, since
        the next step a reader takes from it is to treat the claim as unexamined. False
        here makes every empty list in this dossier mean nothing at all instead, and a
        caller must not render one as an absence of fact checks.

        A partial answer counts: the records that came back are real, whatever happened
        to the claims alongside them. Which claims those were is in
        :attr:`ProviderOutcome.queries`.
        """
        return any(
            o.status in (ProviderStatus.SEARCHED, ProviderStatus.PARTIAL)
            for o in self.fact_checkers
        )

    @property
    def fact_checks(self) -> int:
        """Total fact-check records found across every claim."""
        return sum(len(claim.fact_checks) for claim in self.claims)
