"""Request and response shapes for web research.

The response is the honest-reporting surface of this feature, and most of what looks
like verbosity here is doing that job. Three fields exist purely so a consumer cannot
mistake one kind of nothing for another:

``searched`` separates "the web holds nothing about this" from "no search happened".
``providers`` says what became of each engine, so a thin dossier can be explained.
``stories`` sits beside ``domains`` so that eight mastheads carrying one wire report
are not read as eight independent confirmations.

Evidence carries ``start``, ``end`` and ``provider`` for the same reason. Together
they let a client re-derive the quote from the snippet the provider returned, which
turns "this passage is verbatim" from a promise in a docstring into something the
consumer can check.

``fact_checks`` is the fourth, and the one with the sharpest failure mode. Every field
in it is either the fact-checker's own words or this service's arithmetic, labelled as
such, and there is no aggregate verdict anywhere in the response. A published fact
check is evidence — strong evidence, from people who did the same job this service is
doing — and it is not the answer to whether the submitted claim is true. Two things
enforce that here: ``fact_checks[].claim.text`` is always the *database's* wording, so
a review of a neighbouring claim cannot be read as a ruling on this one, and
``fact_checked`` distinguishes "nobody has reviewed this" from "the lookup did not
happen".
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain import (
    Axis,
    Band,
    ClaimResearch,
    Credibility,
    DateBasis,
    Direction,
    Dossier,
    Evidence,
    FactCheck,
    Observation,
    ProviderOutcome,
    ProviderStatus,
    Reading,
    Retrieval,
    Review,
    ReviewedClaim,
    Role,
    SkippedClaim,
    Source,
    Stance,
)


class ResearchRequest(BaseModel):
    """Body of ``POST /research``. Exactly one of ``text`` or ``claims``.

    Two inputs because they need different things installed. ``text`` runs claim
    extraction first, which needs spaCy and the model, and produces much better
    queries: the entities and keywords it finds are what the second and third query
    formulations are built from. ``claims`` skips extraction entirely, works in a
    deployment that has search keys but no language model, and is honest about the
    cost — with no entities or keywords to work from, each claim is searched as
    written and nothing else, which is visible in the ``queries`` that come back.
    """

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Prose to extract claims from and then research — the same input "
            "`/extract-claim` takes. Requires the NLP extras."
        ),
    )
    claims: list[str] | None = Field(
        default=None,
        min_length=1,
        description=(
            "Claims to research as given, one per entry, skipping extraction. Each is "
            "searched as written, so phrase them as standalone assertions."
        ),
    )

    @model_validator(mode="after")
    def exactly_one_input(self) -> Self:
        """Reject both and neither.

        Both would be ambiguous about which claims to research and in what order, and
        silently preferring one would make the other input look accepted.
        """
        if (self.text is None) == (self.claims is None):
            raise ValueError("provide exactly one of 'text' or 'claims'")
        if self.claims is not None and any(not c.strip() for c in self.claims):
            raise ValueError("'claims' entries must not be blank")
        return self


class RetrievalOut(BaseModel):
    """One provider's answer about one page: the audit trail.

    Every field is what an engine said, not what this service concluded. Where two
    engines disagree — a different title, a different date — both entries appear and
    neither is corrected, because the disagreement is the interesting part.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(description="`tavily`, `brave` or `serper`.")
    query: str = Field(description="The query this answer came back for.")
    rank: int = Field(
        description="1-based position in this provider's answer to this query."
    )
    url: str = Field(description="Exactly the URL the provider returned.")
    title: str = Field(description="This provider's title for the page.")
    snippet: str = Field(
        description="This provider's extract. Evidence offsets index this string."
    )
    score: float | None = Field(
        default=None,
        description=(
            "The provider's own relevance score, where it gives one. Not comparable "
            "between providers, and deliberately not rescaled into something that "
            "would look comparable."
        ),
    )
    published_at: datetime | None = None
    date_basis: DateBasis | None = Field(
        default=None, description="In what sense this provider meant its date."
    )
    date_text: str | None = Field(
        default=None, description="The provider's date string, verbatim."
    )

    @classmethod
    def from_domain(cls, retrieval: Retrieval) -> Self:
        return cls(
            provider=retrieval.provider,
            query=retrieval.query,
            rank=retrieval.rank,
            url=retrieval.url,
            title=retrieval.title,
            snippet=retrieval.snippet,
            score=retrieval.score,
            published_at=retrieval.published_at,
            date_basis=retrieval.date_basis,
            date_text=retrieval.date_text,
        )


class EvidenceOut(BaseModel):
    """A passage of a source that bears on the claim, quoted exactly.

    ``quote`` is a slice of one provider's snippet and never a summary. The invariant
    a client can verify::

        retrieval = next(r for r in source.retrievals if r.provider == ev.provider)
        assert retrieval.snippet[ev.start:ev.end] == ev.quote

    ``score`` measures how much of the claim's wording this passage repeats. It is
    **not** agreement: a passage flatly contradicting the claim repeats its entities
    and figures and therefore scores high, which is intended. A source that disagrees
    is the most valuable one here, and reading this number as support would invert
    that.
    """

    model_config = ConfigDict(extra="forbid")

    quote: str = Field(description="Verbatim slice of `provider`'s snippet.")
    provider: str = Field(description="Whose snippet `start` and `end` index.")
    start: int
    end: int = Field(description="Exclusive, so `snippet[start:end] == quote`.")
    score: float = Field(
        description=(
            "0-1 lexical overlap with the claim. Relevance, not agreement — a "
            "contradiction scores high."
        )
    )
    matched_entities: list[str] = Field(
        default_factory=list, description="Claim entities this passage names."
    )
    matched_terms: list[str] = Field(
        default_factory=list, description="Claim keywords this passage uses."
    )
    matched_numbers: list[str] = Field(
        default_factory=list,
        description="Claim figures this passage repeats, canonicalised.",
    )

    @classmethod
    def from_domain(cls, evidence: Evidence) -> Self:
        return cls(
            quote=evidence.quote,
            provider=evidence.provider,
            start=evidence.start,
            end=evidence.end,
            score=evidence.score,
            matched_entities=list(evidence.matched_entities),
            matched_terms=list(evidence.matched_terms),
            matched_numbers=list(evidence.matched_numbers),
        )


class SourceOut(BaseModel):
    """One web page, however many engines returned it and under however many URLs."""

    model_config = ConfigDict(extra="forbid")

    ref: int = Field(description="1-based, in the order returned. Cite this.")
    url: str = Field(description="Normalised: the identity this page is deduped on.")
    urls: list[str] = Field(
        description=(
            "Every spelling a provider returned, since normalisation is lossy and a "
            "client following the link should be able to use what was given."
        )
    )
    title: str
    domain: str = Field(
        description="Registrable domain — `bbc.co.uk`, not `www.bbc.co.uk`. The unit "
        "publisher independence is counted over."
    )
    host: str = Field(description="Full host, kept because the subdomain is often the "
        "section.")
    evidence: list[EvidenceOut] = Field(
        description=(
            "Passages bearing on the claim, strongest first. **Empty is a real "
            "answer**: the page was found and nothing in any snippet matched the "
            "claim. An arbitrary first sentence presented here would fabricate "
            "relevance out of genuine text."
        )
    )
    retrievals: list[RetrievalOut] = Field(
        description="Who found it, on what query, at what rank. Never empty."
    )
    published_at: datetime | None = Field(
        default=None, description="Read `date_basis` before trusting this."
    )
    date_basis: DateBasis | None = Field(
        default=None,
        description=(
            "Where the date came from, strongest first: `provider` (an engine called "
            "it the publication date), `provider_modified` (an engine gave a date but "
            "would not say which), `provider_relative` (an age resolved against "
            "`retrieved_at`), `url_path` (this service read it out of the URL). Only "
            "`provider` is quotable as 'published on'. Null exactly when "
            "`published_at` is."
        ),
    )
    date_text: str | None = Field(
        default=None,
        description=(
            "The provider's own date string, so the parse can be checked. Unset when "
            "`date_basis` is `url_path`, because no provider said it."
        ),
    )
    cluster: int | None = Field(
        default=None,
        description=(
            "Syndication group, or null when this page stands alone. Sources sharing "
            "one are telling the same story — a wire report under several mastheads — "
            "and count once toward `stories`. They are marked, never merged: every "
            "publisher stays in this list and stays counted in `domains`."
        ),
    )
    providers: list[str] = Field(
        description="Which engines returned this page. Corroboration between indexes, "
        "which is not corroboration between publishers."
    )

    @classmethod
    def from_domain(cls, source: Source) -> Self:
        return cls(
            ref=source.ref,
            url=source.url,
            urls=list(source.urls),
            title=source.title,
            domain=source.domain,
            host=source.host,
            evidence=[EvidenceOut.from_domain(e) for e in source.evidence],
            retrievals=[RetrievalOut.from_domain(r) for r in source.retrievals],
            published_at=source.published_at,
            date_basis=source.date_basis,
            date_text=source.date_text,
            cluster=source.cluster,
            providers=list(source.providers),
        )


class ReviewOut(BaseModel):
    """One publisher's published review of one claim.

    Read ``rating`` and ignore ``stance`` if the two ever seem to disagree. ``rating``
    is the publisher's own string and is the authoritative field; ``stance`` is this
    service's reading of it, and ``stance_from`` names the phrase that produced the
    reading so the mapping can be checked from the response itself.
    """

    model_config = ConfigDict(extra="forbid")

    publisher: str = Field(
        description="The organisation that published the review, as it names itself."
    )
    site: str = Field(
        description=(
            "The review's host without scheme or `www`, as the database derived it. "
            "Never substituted for `publisher`: an empty `publisher` means the database "
            "did not say who reviewed it."
        )
    )
    url: str = Field(description="The review itself. Follow this before citing it.")
    rating: str = Field(
        description=(
            "The publisher's verdict, **exactly as worded** — `False`, `Four "
            "Pinocchios`, `Mixture`, `Missing context`. Free text with no shared scale "
            "across publishers, and deliberately not normalised over the top of."
        )
    )
    title: str = Field(default="", description="The review's headline, where given.")
    language: str = Field(default="", description="BCP-47, as reported.")
    reviewed_at: datetime | None = Field(
        default=None, description="When the review was published, parsed from `date_text`."
    )
    date_text: str | None = Field(
        default=None,
        description="The database's date string, verbatim, kept even if it would not parse.",
    )
    stance: Stance = Field(
        description=(
            "**This service's reading of `rating`, not the publisher's word.** One of "
            "`false`, `mostly_false`, `mixed`, `mostly_true`, `true`, `unsupported` "
            "(nobody could establish it either way), `outdated` (true once, not now), "
            "`unrecognised`. `unrecognised` is not an error and is common: many real "
            "ratings — `Missing context`, `Labeled Satire`, `Altered photo` — are not "
            "points on a true/false axis, and non-English ratings are not read at all. "
            "`rating` is intact beside it in every case."
        )
    )
    stance_from: str = Field(
        default="",
        description=(
            "The vocabulary phrase `stance` was read from, for auditing. Empty when "
            "nothing matched; two phrases joined by ` / ` when the rating matched "
            "conflicting entries and was left `unrecognised`."
        ),
    )

    @classmethod
    def from_domain(cls, review: Review) -> Self:
        return cls(
            publisher=review.publisher,
            site=review.site,
            url=review.url,
            rating=review.rating,
            title=review.title,
            language=review.language,
            reviewed_at=review.reviewed_at,
            date_text=review.date_text,
            stance=review.stance,
            stance_from=review.stance_from,
        )


class ReviewedClaimOut(BaseModel):
    """A claim as the fact-check database holds it, with the reviews published on it.

    ``text`` is the field to read first and the reason this object is not flattened
    away. It is how the *database* words the claim, which is not how the submission
    worded it, and comparing the two is the only way to tell a ruling on this claim
    from a ruling on a neighbouring one.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        description=(
            "The claim **as the database words it** — not the submitted claim and not a "
            "paraphrase of it. Compare it against the `claim` field on this entry "
            "before reading any `rating` as a verdict on the submission."
        )
    )
    reviews: list[ReviewOut] = Field(
        description=(
            "Every review the database holds for this claim, in the order returned. "
            "Never empty: a record with no review carries no verdict and is dropped."
        )
    )
    claimant: str = Field(
        default="", description="Who the database says made the claim, where it says."
    )
    claimed_at: datetime | None = Field(
        default=None,
        description=(
            "When the claim was made. Worth reading beside `reviews[].reviewed_at`: an "
            "old claim resurfacing is the commonest thing a lookup finds."
        ),
    )
    date_text: str | None = Field(
        default=None, description="The database's claim-date string, verbatim."
    )

    @classmethod
    def from_domain(cls, reviewed: ReviewedClaim) -> Self:
        return cls(
            text=reviewed.text,
            reviews=[ReviewOut.from_domain(r) for r in reviewed.reviews],
            claimant=reviewed.claimant,
            claimed_at=reviewed.claimed_at,
            date_text=reviewed.date_text,
        )


class FactCheckOut(BaseModel):
    """A published fact check that bears on the claim. **Evidence, not the answer.**

    Somebody already did this job for a claim resembling the submitted one, and that is
    worth a great deal — which is exactly why it must not be mistaken for the verdict.
    Two things in this object keep the distinction visible: everything the database said
    is nested inside ``claim``, everything this service worked out is beside it, and
    there is no aggregate rating field anywhere.

    ``agreement`` is as close as the response comes to one, and it is null the moment
    two reviewers differ or one rating could not be read. It is agreement *among the
    reviewers*, on this service's reading of their vocabulary, about the claim as
    ``claim.text`` words it — not a ruling on the submission.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Which database this came from, e.g. `google`.")
    claim: ReviewedClaimOut = Field(
        description="The database's record, verbatim, reviews included."
    )
    match: float = Field(
        description=(
            "0-1 lexical overlap between `claim.text` and the claim under check, on the "
            "same scale as `sources[].evidence[].score`. This service's arithmetic, not "
            "the publisher's. A high number is **not** licence to read `rating` as the "
            "verdict on the submitted claim: two claims sharing a year and a topic "
            "score well while being different assertions. Read `claim.text`."
        )
    )
    matched_entities: list[str] = Field(
        default_factory=list, description="Claim entities the database's wording names."
    )
    matched_terms: list[str] = Field(
        default_factory=list, description="Claim keywords the database's wording uses."
    )
    matched_numbers: list[str] = Field(
        default_factory=list,
        description="Claim figures the database's wording repeats, canonicalised.",
    )
    publishers: list[str] = Field(
        default_factory=list,
        description=(
            "Distinct publisher names, in order. Two names can be one newsroom, so this "
            "is a list of reviewers and not a count of independent ones."
        ),
    )
    agreement: Stance | None = Field(
        default=None,
        description=(
            "The one stance every review here shares, or null. Null covers three "
            "different situations — the reviewers disagreed, a rating could not be "
            "read, or the ratings were empty — and all three mean the same thing: "
            "there is nothing here to lean on. No majority is taken."
        ),
    )

    @classmethod
    def from_domain(cls, check: FactCheck) -> Self:
        return cls(
            source=check.source,
            claim=ReviewedClaimOut.from_domain(check.claim),
            match=check.match,
            matched_entities=list(check.matched_entities),
            matched_terms=list(check.matched_terms),
            matched_numbers=list(check.matched_numbers),
            publishers=list(check.publishers),
            agreement=check.agreement,
        )


class ObservationOut(BaseModel):
    """One thing observed about a source, and how much it moved one axis.

    The itemisation behind every number in ``credibility``. A score a client cannot
    take apart is a score it has to trust, so each axis publishes what was seen, which
    way it bore, and how much of the axis it accounted for.
    """

    model_config = ConfigDict(extra="forbid")

    axis: Axis = Field(description="Which of the six axes this observation bears on.")
    finding: str = Field(
        description=(
            "Stable snake-case slug — `official_suffix`, `syndicated_copy`. Branch on "
            "this rather than on `detail`, which is prose and may be reworded."
        )
    )
    direction: Direction = Field(
        description=(
            "`raises`, `lowers`, or `neutral` — seen, bearing on the axis, and moving "
            "it neither way. `neutral` is how a response shows something was checked "
            "and found unremarkable, which is not the same as not having checked."
        )
    )
    detail: str = Field(
        description="Readable prose, verbatim wherever it quotes the source."
    )
    weight: float = Field(
        description=(
            "0-1: how much of the axis this observation accounts for, so the "
            "arithmetic behind `score` can be reconstructed instead of accepted."
        )
    )

    @classmethod
    def from_domain(cls, observation: Observation) -> Self:
        return cls(
            axis=observation.axis,
            finding=observation.finding,
            direction=observation.direction,
            detail=observation.detail,
            weight=observation.weight,
        )


class ReadingOut(BaseModel):
    """One axis of one source, scored or explicitly not.

    ``assessed`` sits beside ``score`` so that "we could not assess this" and "we
    assessed it and it came out at zero" are two answers a client can tell apart rather
    than one it has to infer from a null. Much of what a reader would want to know —
    is there a byline, a corrections policy — needs the page fetched, which this
    service does not do, so ``assessed: false`` is common and is the design working
    rather than a gap in it.
    """

    model_config = ConfigDict(extra="forbid")

    axis: Axis = Field(
        description=(
            "`reliability` (is anyone accountable for the page — an editorial chain, a "
            "named institution, a corrections process; **not** a track record of being "
            "right), `official` (does this publisher hold the record the claim is "
            "about), `transparency` (does the page say who published it and when), "
            "`evidence` (does the retrieved text substantiate anything about the "
            "claim), `date` (what is known about when it was published, and on what "
            "basis), `independence` (is this a distinct voice or another copy of one "
            "already counted). All six are reported for every source."
        )
    )
    score: float | None = Field(
        default=None,
        description=(
            "0-1, or null when nothing available bore on this axis. **Read `assessed` "
            "before this**: null is not a low score, the same way a source with no "
            "stated date is not a source with a bad date."
        ),
    )
    assessed: bool = Field(
        description=(
            "Whether anything bore on this axis at all. False means `score` is null "
            "because there was nothing to measure — never that something was measured "
            "and came out badly."
        )
    )
    observations: list[ObservationOut] = Field(
        default_factory=list,
        description=(
            "What was observed, strongest first. Never empty while `assessed` is true: "
            "a score with nothing itemised behind it would be exactly the "
            "unaccountable number this section exists to avoid."
        ),
    )

    @classmethod
    def from_domain(cls, reading: Reading) -> Self:
        return cls(
            axis=reading.axis,
            score=reading.score,
            assessed=reading.assessed,
            observations=[ObservationOut.from_domain(o) for o in reading.observations],
        )


class CredibilityOut(BaseModel):
    """How well one source stands up **as a source**. Never a reading of the claim.

    Attached to a ``sources`` entry by ``ref`` rather than nested inside it, because
    every field of a source is what a provider returned and every number here is this
    service's own judgement — keeping them apart is what lets a client tell the two
    apart without knowing how this service works.

    Nothing in this object is a truth value and none of them can be combined into one.
    A source that flatly contradicts the claim can score at the top of every axis here,
    and must: this grades the publisher and the page, and what the page *says* is the
    separate question a desk answers.

    ``standing`` and ``coverage`` are one fact in two fields. Read them together or
    neither: a standing of 1.0 over one assessed axis of six is a single observation
    agreeing with itself, and shown alone it publishes a strong claim about a publisher
    on the strength of nothing.
    """

    model_config = ConfigDict(extra="forbid")

    ref: int = Field(
        description=(
            "The `sources[].ref` this grades. Match on it rather than on position — "
            "the two lists are parallel, and a client that zips them is relying on an "
            "alignment this field exists to make explicit."
        )
    )
    domain: str = Field(
        description=(
            "The source's registrable domain, repeated here so one record is legible "
            "on its own — in a log line, or beside a rendered citation."
        )
    )
    role: Role | None = Field(
        default=None,
        description=(
            "What the publisher registry says this domain **is**: `official`, "
            "`reference`, `news_agency`, `established_media`, `fact_checker`, "
            "`state_controlled`, `aggregator`, `user_generated`. Each is a checkable "
            "fact about an institution — who owns it, what records it holds, whether "
            "it writes what it publishes — and none is a grade of truthfulness; there "
            "is deliberately no `reliable` value. **Null is the common case and means "
            "the registry holds no entry**, not that the domain is disreputable: the "
            "registry is a few hundred domains and the web is not, and an unrecognised "
            "publisher is assessed on what can be seen about the page, which is how a "
            "first-hand account from an outlet nobody has heard of stays readable as "
            "evidence."
        ),
    )
    standing: float | None = Field(
        default=None,
        description=(
            "0-1 mean of the axes that could be assessed, or null when none could. "
            "**Do not show or compare it without `coverage`** — a 1.0 drawn from one "
            "axis of six is not a strong source, and the two fields exist to be read "
            "together. Unweighted on purpose: which axes matter depends on the claim "
            "in hand, which this service does not know, so the per-axis `readings` are "
            "published for a client that does. It describes the source and not the "
            "claim: no value of it makes anything the page says more or less true."
        ),
    )
    band: Band = Field(
        description=(
            "`standing` as a coarse label — `strong`, `moderate`, `weak`, `unknown` — "
            "and the field to order a list on, because the number's precision is not "
            "real: 0.61 against 0.64 is noise from which axes happened to be "
            "assessable. `strong` also requires four of the six axes assessed, so a "
            "recognised masthead cannot reach the top band on being recognised. "
            "**`unknown` is not the bottom of the scale**: it means no axis could be "
            "assessed at all, and rendering it as `weak` turns an absence of "
            "information into a negative finding about a publisher."
        )
    )
    coverage: float = Field(
        description=(
            "0-1: the share of the six axes that could be assessed. Always present, "
            "and the field `standing` has to be read against — a high standing at a "
            "coverage of 0.17 is one axis of six agreeing with itself."
        )
    )
    assessed: list[Axis] = Field(
        default_factory=list,
        description="The axes something bore on, in reporting order.",
    )
    unassessed: list[Axis] = Field(
        default_factory=list,
        description=(
            "The axes nothing available bore on. Routinely non-empty: `transparency` "
            "and often `date` need the page itself, and this service reads only what "
            "the search providers returned."
        ),
    )
    readings: list[ReadingOut] = Field(
        description=(
            "All six axes in reporting order, assessed or not, each with what was "
            "observed. Complete rather than sparse: a missing entry and an "
            "unassessable axis would otherwise be indistinguishable, and the second is "
            "much more common."
        )
    )

    @classmethod
    def from_domain(cls, credibility: Credibility) -> Self:
        return cls(
            ref=credibility.ref,
            domain=credibility.domain,
            role=credibility.role,
            standing=credibility.standing,
            band=credibility.band,
            coverage=credibility.coverage,
            assessed=list(credibility.assessed),
            unassessed=list(credibility.unassessed),
            readings=[ReadingOut.from_domain(r) for r in credibility.readings],
        )


class ClaimResearchOut(BaseModel):
    """What was found for one claim."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(description="The claim as researched — the standalone rewrite.")
    queries: list[str] = Field(
        description=(
            "Every query actually sent, in order. Not a reconstruction: a reader who "
            "wants to know why an obvious source is missing can repeat these."
        )
    )
    sources: list[SourceOut] = Field(
        description="Deduplicated pages, strongest evidence first."
    )
    fact_checks: list[FactCheckOut] = Field(
        default_factory=list,
        description=(
            "Fact checks already published on this claim, closest wording first. Kept "
            "beside `sources` rather than among them because a fact check is a source "
            "whose author was doing this service's job, and burying it in a ranked page "
            "list would hide that. **Empty means one of three things** and this field "
            "cannot tell them apart: nobody has reviewed the claim, the database has not "
            "indexed the review, or the lookup did not happen. Read `fact_checked` on "
            "the response before reporting the first."
        ),
    )
    credibility: list[CredibilityOut] = Field(
        default_factory=list,
        description=(
            "How well each of `sources` stands up as a source, matched to it by `ref` "
            "and **not** by position. Beside `sources` rather than inside them because "
            "every field of a source is what a provider returned, while every number "
            "here is this service's own reading of it. It grades the publisher and the "
            "page — accountability, officiality, independence, what is known about the "
            "date — and says nothing about whether the claim is true: there is no "
            "verdict in it, and a source that contradicts the claim scoring at the top "
            "of every axis is the normal case rather than a contradiction. Empty when "
            "the scoring is switched off, which is an absence of assessment and not a "
            "finding about any source here."
        ),
    )
    domains: list[str] = Field(description="Distinct publishers, in order of appearance.")
    stories: int = Field(
        description=(
            "Distinct stories: clustered sources count once, unclustered count "
            "individually. **This is the corroboration number, not "
            "`len(domains)`.** Eight mastheads carrying one wire report are eight "
            "domains and one story."
        )
    )

    @classmethod
    def from_domain(cls, research: ClaimResearch) -> Self:
        return cls(
            claim=research.claim,
            queries=list(research.queries),
            sources=[SourceOut.from_domain(s) for s in research.sources],
            fact_checks=[FactCheckOut.from_domain(f) for f in research.fact_checks],
            credibility=[CredibilityOut.from_domain(c) for c in research.credibility],
            domains=list(research.domains),
            stories=research.stories,
        )


class ProviderOutcomeOut(BaseModel):
    """What became of one provider — a search engine, or the fact-check database.

    One shape for both, because the question is the same one in both places: did it
    answer, and if not, why not. ``queries`` is what was sent, which for a fact-check
    lookup is one claim per entry rather than one query formulation per entry.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str
    status: ProviderStatus = Field(
        description=(
            "`searched` (answered everything, possibly with zero results), `partial` "
            "(answered some queries — the dossier is thinner than it should be), "
            "`skipped` (no API key configured), `failed` (asked, did not answer)."
        )
    )
    queries: list[str] = Field(default_factory=list)
    results: int = Field(default=0, description="Raw results returned, before dedup.")
    code: str = Field(default="", description="Error code when `status` is `failed`.")
    detail: str = Field(
        default="",
        description="Why, in prose. API keys are redacted before they reach this.",
    )

    @classmethod
    def from_domain(cls, outcome: ProviderOutcome) -> Self:
        return cls(
            provider=outcome.provider,
            status=outcome.status,
            queries=list(outcome.queries),
            results=outcome.results,
            code=outcome.code,
            detail=outcome.detail,
        )


class SkippedClaimOut(BaseModel):
    """A claim that was extracted but never searched for, and why.

    Present so the response describes the whole submission. A body listing three
    researched claims for prose that made twelve would read as prose that made three,
    which is a misdescription even though every claim shown is real.
    """

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(description="The claim text, resubmittable via `claims`.")
    reason: str = Field(
        description=(
            "Either the extractor's reason for marking it unfit to check, or the "
            "`SEARCH_MAX_CLAIMS` ceiling that cut it off."
        )
    )

    @classmethod
    def from_domain(cls, skipped: SkippedClaim) -> Self:
        return cls(claim=skipped.claim, reason=skipped.reason)


class ResearchResponse(BaseModel):
    """Body of ``200 POST /research``.

    Read ``searched`` first. When it is ``false`` every empty ``sources`` list in this
    response means "not looked for", not "not found", and no conclusion about any
    claim follows from one. ``fact_checked`` is the same warning for every empty
    ``fact_checks`` list, and it is the more dangerous of the two to skip: an absence of
    fact checks reads as "nobody has examined this claim", which invites exactly the
    conclusion a spent quota does not support.

    Nothing in this body is a verdict on any claim. The response reports what was found
    — pages, passages, and other people's published reviews — and adjudication is a
    separate step that takes this as its input.
    """

    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimResearchOut] = Field(
        description="One entry per claim researched, in the order it appeared."
    )
    skipped: list[SkippedClaimOut] = Field(
        default_factory=list,
        description=(
            "Claims that were submitted or extracted but not searched for — unfit to "
            "check, or past the `SEARCH_MAX_CLAIMS` ceiling. The `claims` input is "
            "never judged unfit, but the ceiling applies to it too: what it cuts is "
            "listed here rather than silently absent."
        ),
    )
    providers: list[ProviderOutcomeOut] = Field(
        description="One entry per configured provider, whatever became of it."
    )
    fact_checkers: list[ProviderOutcomeOut] = Field(
        default_factory=list,
        description=(
            "What became of the fact-check database, on the same terms as `providers`. "
            "Separate from it because a missing fact-check key is not a failure of the "
            "web search, and folding the two together would make every deployment "
            "without one look like a broken one. `queries` here lists the claims that "
            "were looked up, one per entry."
        ),
    )
    retrieved_at: datetime = Field(
        description=(
            "When the search ran, and the anchor any relative provider age was "
            "resolved against."
        )
    )
    searched: bool = Field(
        description=(
            "True when at least one provider actually answered. **False makes every "
            "empty `sources` list here meaningless rather than negative** — check it "
            "before reporting an absence of evidence, since an expired API key looks "
            "exactly like a claim nobody has written about."
        )
    )
    fact_checked: bool = Field(
        description=(
            "True when the fact-check database actually answered. **False makes every "
            "empty `fact_checks` list here meaningless rather than negative** — and "
            "unlike `searched`, the wrong reading of it is an inviting one, because "
            "\"no fact-checker has ruled on this\" is the natural way to read an empty "
            "list and it licenses treating the claim as unexamined. A partial answer "
            "counts as true; which claims it covered is in `fact_checkers[].queries`."
        )
    )

    @classmethod
    def from_domain(cls, dossier: Dossier) -> Self:
        return cls(
            claims=[ClaimResearchOut.from_domain(c) for c in dossier.claims],
            skipped=[SkippedClaimOut.from_domain(s) for s in dossier.skipped],
            providers=[ProviderOutcomeOut.from_domain(p) for p in dossier.providers],
            fact_checkers=[
                ProviderOutcomeOut.from_domain(p) for p in dossier.fact_checkers
            ],
            retrieved_at=dossier.retrieved_at,
            searched=dossier.searched,
            fact_checked=dossier.fact_checked,
        )
