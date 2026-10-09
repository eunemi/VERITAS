"""The seam: what the service promises that no layer beneath it can.

Every module beside this one tests a part in isolation — query construction, evidence
selection, deduplication, assembly, fan-out. This one tests the four things that only
exist once those parts are wired together, and each of them is a way the service could
overstate what was found.

**An empty answer and no answer are different findings.** A deployment with no keys
returns a dossier, not an exception, because "the web was searched and holds nothing
about this" and "no search happened" are opposite conclusions that a 500 would flatten
into the same non-answer. :attr:`~app.domain.research.Dossier.searched` is the only
field that separates them, so several tests below build the two bodies side by side and
assert they differ in exactly that bit.

**A claim that was not researched is named.** Two exclusions apply — the extractor
marked it unfit, and the ``SEARCH_MAX_CLAIMS`` ceiling — and the response has to
describe the whole submission, so both land on
:attr:`~app.domain.research.Dossier.skipped` with a reason instead of being absent.
The ``claims`` path is exempt from the first and subject to the second.

**One clock.** ``retrieved_at`` is read once and handed to every provider and to the
dating. :class:`tests.search_bench.Fake` records the instant it was given precisely so
that can be proved rather than assumed.

**Nothing is fabricated.** The last section is the direct form: every URL, domain and
quote in the dossier is traced back to something a fake actually returned.

**Fact checks are evidence, not a verdict.** The final section covers the second fan-out.
It runs beside the search rather than after it, it has its own key and its own outcome —
so a deployment can have complete web research and no fact-check coverage at all — and
what it finds is attached beside the web sources rather than folded into them or summed
into a rating. The tests there mirror the ``searched`` pair above against
:attr:`~app.domain.research.Dossier.fact_checked`, which is the sharper of the two flags:
an empty ``fact_checks`` reads as "nobody has ruled on this claim", and a reader's next
step from that is to treat the claim as unexamined.

Runs with nothing installed. The extractor is a stub, so :mod:`app.nlp` is imported
but never used — which is the discipline :mod:`app.nlp` keeps its heavy imports inside
function bodies to preserve.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import pytest

from app.core.config import SearchProvider, Settings
from app.core.errors import FactCheckError, PayloadTooLargeError, SearchError
from app.domain import (
    Dossier,
    ExtractedClaim,
    Extraction,
    ProviderStatus,
    Stance,
    Unfit,
)
from app.search.base import SearchResult
from app.services.claims import ClaimExtractionService
from app.services.research import WebResearchService
from tests import factcheck_bench
from tests.research_bench import (
    WIRE,
    WIRE_TITLE,
    WIRE_TITLE_REGIONAL,
    WIRE_TITLE_REWRITTEN,
    WIRE_TRUNCATED,
    WIRE_WITH_LEAD,
)
from tests.search_bench import Fake, bench, found
from tests.stubs import SAMPLE_TEXT, StubClaimExtractor, extractor_bench

CLAIM = "The Bank of England held its benchmark rate at 4.75% in March 2026."

#: The first claim :func:`tests.stubs.sample_extraction` makes, and the second, which
#: it marks unfit. Spelled out because several tests below assert on one or the other.
FIT = "The bridge opened in March 2026."
UNFIT = "It is a beautiful bridge."

#: Long enough for :func:`app.providers.http.redact` to act on it.
FACT_CHECK_KEY = "fc-secret-key-value"


def service(**overrides: object) -> WebResearchService:
    """A service with one provider configured unless a test says otherwise."""
    overrides.setdefault("SEARCH_PROVIDERS", [SearchProvider.TAVILY])
    settings = Settings(_env_file=None, **overrides)
    return WebResearchService(
        settings=settings, extractor=ClaimExtractionService(settings=settings)
    )


def checking(**overrides: object) -> WebResearchService:
    """A service with a fact-check key, so the lookup runs instead of being skipped.

    Separate from :func:`service` because most of this file is about the search, and a
    key set everywhere would mean every test above silently depended on a fake database
    being registered.
    """
    overrides.setdefault("GOOGLE_FACT_CHECK_API_KEY", FACT_CHECK_KEY)
    return service(**overrides)


def wire(url: str, *, title: str = WIRE_TITLE, snippet: str = WIRE) -> SearchResult:
    """A result that carries evidence for :data:`CLAIM`."""
    return found(url, title=title, snippet=snippet)


def claims_of(fit: Sequence[str] = (), unfit: Sequence[str] = ()) -> Extraction:
    """An extraction naming each of ``fit`` as checkable and each of ``unfit`` as not.

    ``entities`` and ``keywords`` are left empty: this file never asserts on them, and
    an extraction with none is the honest shape for a stub that did no analysis.
    """
    made = [
        ExtractedClaim(ref=index, text=text, quote=text, start=0, end=len(text))
        for index, text in enumerate(fit, start=1)
    ]
    rejected = [
        ExtractedClaim(
            ref=index,
            text=text,
            quote=text,
            start=0,
            end=len(text),
            checkable=False,
            reason=Unfit.OPINION,
        )
        for index, text in enumerate(unfit, start=len(made) + 1)
    ]
    return Extraction(
        claims=tuple(made + rejected),
        entities=(),
        keywords=(),
        sentences=len(made) + len(rejected),
    )


# ======================================================= searched, or not searched ====


async def test_no_configured_key_is_a_dossier_and_not_an_exception() -> None:
    """No fakes: the real factories run and every one raises for want of a key.

    Raising here would be the service reporting a deployment problem as a fact about
    the claim. The claim is still present, its queries are still recorded, and
    ``searched`` says the whole thing is uninformative.
    """
    result = await service().from_claims([CLAIM])

    assert isinstance(result, Dossier)
    assert result.searched is False
    assert result.claims[0].sources == ()
    # The queries were built and are reported, so a reader can see what *would* have
    # been asked. Reporting them as empty would misdescribe the request.
    assert result.claims[0].queries == (CLAIM,)
    assert [outcome.status for outcome in result.providers] == [ProviderStatus.SKIPPED]
    assert all(outcome.detail for outcome in result.providers)


async def test_an_empty_index_is_not_the_same_answer_as_an_unsearched_one() -> None:
    """The load-bearing distinction of the whole feature.

    Both dossiers below have no sources. One means the web was searched and holds
    nothing about this claim; the other means no search happened. A consumer that read
    the empty tuple without ``searched`` would report an expired API key as an absence
    of evidence — the single most damaging thing this service could cause.
    """
    with bench({SearchProvider.TAVILY: Fake("tavily", results=[])}):
        answered = await service().from_claims([CLAIM])
    unsearched = await service().from_claims([CLAIM])

    assert answered.claims[0].sources == unsearched.claims[0].sources == ()
    assert answered.searched is True
    assert unsearched.searched is False


async def test_every_provider_failing_is_still_a_dossier() -> None:
    """A total outage is reported on the body, in full, and does not raise."""
    dead = SearchError("tavily is down", provider="tavily")

    with bench({SearchProvider.TAVILY: Fake("tavily", error=dead)}):
        result = await service().from_claims([CLAIM])

    assert result.searched is False
    assert result.complete is False
    assert [outcome.status for outcome in result.providers] == [ProviderStatus.FAILED]
    assert len(result.failures) == 1
    assert "tavily is down" in result.providers[0].detail


async def test_one_dead_provider_costs_only_its_own_results() -> None:
    """Through the service, where the surviving results have to reach the dossier."""
    dead = Fake("tavily", error=SearchError("tavily is down", provider="tavily"))
    alive = Fake("brave", results=[wire("https://bbc.co.uk/news/1")])

    with bench({SearchProvider.TAVILY: dead, SearchProvider.BRAVE: alive}):
        result = await service(
            SEARCH_PROVIDERS=[SearchProvider.TAVILY, SearchProvider.BRAVE]
        ).from_claims([CLAIM])

    assert result.searched is True
    assert result.complete is False
    assert [source.domain for source in result.claims[0].sources] == ["bbc.co.uk"]
    outcomes = {outcome.provider: outcome.status for outcome in result.providers}
    assert outcomes == {
        "tavily": ProviderStatus.FAILED,
        "brave": ProviderStatus.SEARCHED,
    }


async def test_a_provider_key_never_reaches_a_reportable_detail() -> None:
    """The key comes from the settings this service was built with.

    Provider error messages quote the request, and this detail is returned to a
    client. The redaction is the fan-out's, but the secrets come from here, so a
    settings field the redactor is not told about would fail at this level and nowhere
    else.
    """
    key = "tvly-service-level-secret"
    leaky = Fake(
        "tavily", error=SearchError(f"rejected token {key}", provider="tavily")
    )

    with bench({SearchProvider.TAVILY: leaky}):
        result = await service(TAVILY_API_KEY=key).from_claims([CLAIM])

    assert key not in result.providers[0].detail
    assert "***" in result.providers[0].detail


# ============================================================= what was not searched ====


async def test_an_unfit_claim_is_skipped_with_the_extractors_reason() -> None:
    """Not dropped. A dossier listing one claim for prose that made two misdescribes
    the prose, even though the claim it lists is real."""
    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        extractor_bench(StubClaimExtractor()),
    ):
        result = await service().from_text(SAMPLE_TEXT)

    assert [claim.claim for claim in result.claims] == [FIT]
    assert [(s.claim, s.reason) for s in result.skipped] == [(UNFIT, "opinion")]


async def test_an_unfit_claim_costs_no_search() -> None:
    """The reason the exclusion exists: three queries against three providers spent on
    "the policy was a disgrace" buys nothing."""
    fake = Fake("tavily", results=[])

    with bench({SearchProvider.TAVILY: fake}), extractor_bench(StubClaimExtractor()):
        await service().from_text(SAMPLE_TEXT)

    assert UNFIT not in fake.queries
    assert FIT in fake.queries


async def test_the_claims_path_does_not_judge_what_it_was_given() -> None:
    """The same string the extractor called unfit, searched because a caller asked.

    A caller asserting that this is a claim is better evidence than a regex, and the
    ``claims`` path exists so a caller that disagrees with the extractor has somewhere
    to go. Refusing here would leave that disagreement unresolvable.
    """
    fake = Fake("tavily", results=[])

    with bench({SearchProvider.TAVILY: fake}):
        result = await service().from_claims([UNFIT])

    assert [claim.claim for claim in result.claims] == [UNFIT]
    assert result.skipped == ()
    assert fake.queries == [UNFIT]


async def test_the_claims_path_never_touches_the_extractor() -> None:
    """The whole point of the second entry point: no spaCy, no model, no download.

    The stub raises on any call, so this fails loudly rather than by being slow.
    """
    stub = StubClaimExtractor(raises=AssertionError("the claims path extracted"))

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        extractor_bench(stub),
    ):
        result = await service().from_claims([CLAIM])

    assert stub.seen == []
    assert [claim.claim for claim in result.claims] == [CLAIM]


async def test_the_ceiling_names_every_claim_it_cut() -> None:
    """Truncation is visible or it is a lie about the submission."""
    sent = [f"Claim number {index} was made in March 2026." for index in range(1, 5)]
    fake = Fake("tavily", results=[])

    with bench({SearchProvider.TAVILY: fake}):
        result = await service(SEARCH_MAX_CLAIMS=2).from_claims(sent)

    assert [claim.claim for claim in result.claims] == sent[:2]
    assert [skipped.claim for skipped in result.skipped] == sent[2:]
    for skipped in result.skipped:
        assert "SEARCH_MAX_CLAIMS=2" in skipped.reason
        assert "only the first 2 claims of 4" in skipped.reason
    # Nothing past the ceiling was searched for, so the cut saved the work it claims.
    assert sorted(fake.queries) == sorted(sent[:2])


async def test_the_ceiling_keeps_the_claims_the_submission_led_with() -> None:
    """First *n*, not a sample. Any other rule needs a notion of which claims matter
    that this service does not have, and inventing one would hide the ordering the
    caller chose."""
    sent = [f"Claim number {index} was made in March 2026." for index in range(1, 6)]

    with bench({SearchProvider.TAVILY: Fake("tavily", results=[])}):
        result = await service(SEARCH_MAX_CLAIMS=3).from_claims(sent)

    assert [claim.claim for claim in result.claims] == sent[:3]


async def test_the_ceiling_applies_to_the_text_path_too() -> None:
    """Both exclusions can fire on one request, and both are reported.

    The unfit claim sits *between* the two checkable ones on purpose: the ceiling is
    applied after the unfit have been removed, so a ceiling of one has to keep the
    first checkable claim rather than the first claim.
    """
    extraction = claims_of(
        fit=["The bridge opened in March 2026.", "The bridge cost 40 million pounds."],
        unfit=["It was lovely."],
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        extractor_bench(StubClaimExtractor(extraction=extraction)),
    ):
        result = await service(SEARCH_MAX_CLAIMS=1).from_text("whatever")

    assert [claim.claim for claim in result.claims] == [
        "The bridge opened in March 2026."
    ]
    # Unfit first, then what the ceiling dropped: the order the exclusions were applied
    # in, which is what a reader reconstructing the request needs.
    assert [skipped.claim for skipped in result.skipped] == [
        "It was lovely.",
        "The bridge cost 40 million pounds.",
    ]
    assert result.skipped[0].reason == "opinion"
    assert "SEARCH_MAX_CLAIMS=1" in result.skipped[1].reason


async def test_prose_that_makes_no_checkable_claim_is_not_an_error() -> None:
    """A submission of pure opinion comes back with everything on ``skipped``."""
    fake = Fake("tavily", results=[])

    with (
        bench({SearchProvider.TAVILY: fake}),
        extractor_bench(StubClaimExtractor(extraction=claims_of(unfit=[UNFIT]))),
    ):
        result = await service().from_text(UNFIT)

    assert result.claims == ()
    assert [skipped.claim for skipped in result.skipped] == [UNFIT]
    assert fake.queries == []
    # No task was sent, and the provider is still accounted for.
    assert [outcome.status for outcome in result.providers] == [ProviderStatus.SEARCHED]


async def test_an_oversized_claims_batch_is_refused_before_any_search() -> None:
    """The limit is on the submission, so it is the joined length that counts.

    Ten claims of a thousand characters is the same load as one of ten thousand, and a
    per-claim bound would let the batch through.
    """
    fake = Fake("tavily", results=[])

    with (
        bench({SearchProvider.TAVILY: fake}),
        pytest.raises(PayloadTooLargeError) as raised,
    ):
        await service(MAX_TEXT_CHARS=20).from_claims(["x" * 12, "y" * 12])

    assert raised.value.details == {"field": "claims", "characters": 25, "limit": 20}
    assert fake.queries == []


# ==================================================================== one clock ====


async def test_every_provider_is_given_the_instant_on_the_dossier() -> None:
    """Brave reports relative ages, so this is what keeps two providers' answers about
    one page from resolving to two dates.

    Two claims and two providers, so four searches, all against one reading of the
    clock — and that reading is the one the dossier publishes.
    """
    left = Fake("tavily", results=[wire("https://bbc.co.uk/news/1")])
    right = Fake("brave", results=[wire("https://sky.com/news/2")])

    with bench({SearchProvider.TAVILY: left, SearchProvider.BRAVE: right}):
        result = await service(
            SEARCH_PROVIDERS=[SearchProvider.TAVILY, SearchProvider.BRAVE]
        ).from_claims([CLAIM, "Inflation was 2.8% in March 2026."])

    stamps = set(left.nows) | set(right.nows)
    assert len(left.nows) == len(right.nows) == 2
    assert stamps == {result.retrieved_at}


async def test_the_url_date_is_read_against_that_same_instant() -> None:
    """A path date must not be judged against a second clock reading.

    A request straddling midnight would otherwise date half its sources to yesterday.
    The date below is in the past for any plausible ``now``, so what this pins is that
    the URL basis is reached at all through the service and anchored, not that a
    particular day was chosen.
    """
    dated = "https://bbc.co.uk/news/2026/03/04/rates-held"

    with bench({SearchProvider.TAVILY: Fake("tavily", results=[wire(dated)])}):
        result = await service().from_claims([CLAIM])
    source = result.claims[0].sources[0]

    assert source.published_at == datetime(
        2026, 3, 4, tzinfo=source.published_at.tzinfo
    )
    assert source.date_basis == "url_path"
    assert source.date_text is None
    assert result.retrieved_at >= source.published_at


# ================================================================== the queries ====


async def test_the_claims_path_searches_the_claim_as_written_and_nothing_else() -> None:
    """One rung, because there are no entities or keywords to build another from.

    A narrower search than the ``text`` path performs, and it is visible on the
    response rather than hidden. Adding a word here — "fact check", "true or false" —
    would search for something the caller did not ask about.
    """
    fake = Fake("tavily", results=[])

    with bench({SearchProvider.TAVILY: fake}):
        result = await service().from_claims([CLAIM])

    assert fake.queries == [CLAIM]
    assert result.claims[0].queries == (CLAIM,)


async def test_the_text_path_searches_what_the_extractor_found() -> None:
    """More than one formulation, and the first is the claim as it was read out."""
    fake = Fake("tavily", results=[])

    with bench({SearchProvider.TAVILY: fake}), extractor_bench(StubClaimExtractor()):
        result = await service().from_text(SAMPLE_TEXT)
    reported = result.claims[0].queries

    assert reported[0] == FIT
    assert len(reported) > 1
    # Sorted, because the queries go out concurrently: the order they reach one
    # provider is not something the fan-out promises.
    assert sorted(fake.queries) == sorted(reported)


async def test_the_query_budget_is_honoured() -> None:
    """``SEARCH_QUERIES_PER_CLAIM`` bounds the ladder, and the record shows the bound."""
    fake = Fake("tavily", results=[])

    with (
        bench({SearchProvider.TAVILY: fake}),
        extractor_bench(StubClaimExtractor()),
    ):
        result = await service(SEARCH_QUERIES_PER_CLAIM=1).from_text(SAMPLE_TEXT)

    assert result.claims[0].queries == (FIT,)
    assert fake.queries == [FIT]


async def test_the_queries_on_the_dossier_are_the_ones_that_were_sent() -> None:
    """Two claims, so a per-claim mix-up would show. Rebuilding the list at this layer
    would give something plausible that stops being true the first time query
    construction changes."""
    second = "Inflation was 2.8% in March 2026."
    fake = Fake("tavily", results=[])

    with bench({SearchProvider.TAVILY: fake}):
        result = await service().from_claims([CLAIM, second])

    assert [claim.queries for claim in result.claims] == [(CLAIM,), (second,)]
    assert sorted(fake.queries) == sorted([CLAIM, second])


# ================================================= results stay with their claim ====


async def test_each_claim_keeps_its_own_results() -> None:
    """Aligned by index, not keyed by claim text."""

    class ByQuery(Fake):
        async def search(
            self, query: str, *, max_results: int = 10, now: datetime
        ) -> list[SearchResult]:
            self.queries.append(query)
            self.nows.append(now)
            slug = "rate" if "rate" in query else "inflation"
            return [wire(f"https://bbc.co.uk/news/{slug}")]

    with bench({SearchProvider.TAVILY: ByQuery("tavily")}):
        result = await service().from_claims(
            [CLAIM, "Inflation was 2.8% in March 2026."]
        )

    assert [s.url for s in result.claims[0].sources] == ["https://bbc.co.uk/news/rate"]
    assert [s.url for s in result.claims[1].sources] == [
        "https://bbc.co.uk/news/inflation"
    ]


async def test_two_identical_claims_are_researched_twice_and_reported_twice() -> None:
    """Keying by claim text would silently drop one of these.

    Two sentences in one submission can be identical after rewriting, and a caller
    that sent the same claim twice is owed two answers rather than one and a gap.
    """
    fake = Fake("tavily", results=[wire("https://bbc.co.uk/news/1")])

    with bench({SearchProvider.TAVILY: fake}):
        result = await service().from_claims([CLAIM, CLAIM])

    assert len(result.claims) == 2
    assert result.claims[0] == result.claims[1]
    assert fake.queries == [CLAIM, CLAIM]


# ================================================================= the dedup ====


async def test_one_page_from_three_engines_is_one_source() -> None:
    """Page identity is a merge, and the corroboration between engines is recorded.

    Three rows for one document would read as three sources, which is the count a
    reader uses to judge whether a claim is corroborated.
    """
    spellings = {
        SearchProvider.TAVILY: Fake(
            "tavily", results=[wire("https://bbc.co.uk/news/1?utm_source=x")]
        ),
        SearchProvider.BRAVE: Fake(
            "brave", results=[wire("http://www.bbc.co.uk/news/1/")]
        ),
        SearchProvider.SERPER: Fake(
            "serper", results=[wire("https://bbc.co.uk/news/1#top")]
        ),
    }

    with bench(dict(spellings)):
        result = await service(
            SEARCH_PROVIDERS=[
                SearchProvider.TAVILY,
                SearchProvider.BRAVE,
                SearchProvider.SERPER,
            ]
        ).from_claims([CLAIM])
    researched = result.claims[0]

    assert len(researched.sources) == 1
    source = researched.sources[0]
    assert sorted(source.providers) == ["brave", "serper", "tavily"]
    assert len(source.urls) == 3
    assert source.url == "https://bbc.co.uk/news/1"
    assert researched.domains == ("bbc.co.uk",)
    assert researched.stories == 1


async def test_syndication_is_marked_and_never_merged() -> None:
    """Three publishers running one wire report. Story identity is the weaker claim.

    Merging them would delete two sources a provider returned; counting them as three
    independent confirmations would overstate corroboration. The honest answer is
    three sources, three domains, one story.
    """
    fake = Fake(
        "tavily",
        results=[
            wire("https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE),
            wire(
                "https://apnews.com/b",
                title=WIRE_TITLE_REWRITTEN,
                snippet=WIRE_TRUNCATED,
            ),
            wire(
                "https://heraldscotland.com/c",
                title=WIRE_TITLE_REGIONAL,
                snippet=WIRE_WITH_LEAD,
            ),
        ],
    )

    with bench({SearchProvider.TAVILY: fake}):
        result = await service().from_claims([CLAIM])
    researched = result.claims[0]

    assert len(researched.sources) == 3
    assert len(researched.domains) == 3
    assert researched.stories == 1
    assert {source.cluster for source in researched.sources} == {1}


async def test_a_url_that_is_not_a_web_page_never_becomes_a_source() -> None:
    """A source a reader cannot open cannot be checked, and inventing a host for it
    would put a publisher's name against a page that has none."""
    fake = Fake(
        "tavily",
        results=[
            found("mailto:tips@example.com", snippet=WIRE),
            wire("https://bbc.co.uk/1"),
        ],
    )

    with bench({SearchProvider.TAVILY: fake}):
        result = await service().from_claims([CLAIM])

    assert [source.url for source in result.claims[0].sources] == [
        "https://bbc.co.uk/1"
    ]


# =============================================================== no fabrication ====


async def test_every_source_in_the_dossier_came_from_a_provider() -> None:
    """The obligation stated directly, as a containment check.

    Two providers, overlapping results, a syndicated pair and a page that says nothing
    about the claim — so the assembly does real work — and afterwards every URL, host
    and provider name on the dossier traces back to a row a fake handed over.
    """
    returned = {
        "tavily": [
            wire("https://bbc.co.uk/news/1"),
            wire("https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE),
            found(
                "https://example.com/ferries",
                title="Ferries cancelled",
                snippet="High winds cancelled sailings from Portsmouth on Sunday.",
            ),
        ],
        "brave": [
            wire("https://www.bbc.co.uk/news/1/"),
            wire(
                "https://apnews.com/b",
                title=WIRE_TITLE_REWRITTEN,
                snippet=WIRE_TRUNCATED,
            ),
        ],
    }
    fakes = {
        SearchProvider.TAVILY: Fake("tavily", results=returned["tavily"]),
        SearchProvider.BRAVE: Fake("brave", results=returned["brave"]),
    }

    with bench(dict(fakes)):
        result = await service(
            SEARCH_PROVIDERS=[SearchProvider.TAVILY, SearchProvider.BRAVE]
        ).from_claims([CLAIM])

    offered = {r.url for results in returned.values() for r in results}
    for source in result.claims[0].sources:
        assert set(source.urls) <= offered
        assert source.url in {u for u in source.urls}
        assert source.host in source.url
        assert set(source.providers) <= {"tavily", "brave"}
        for retrieval in source.retrievals:
            assert retrieval.query == CLAIM
            assert retrieval.url in offered
    assert len(result.claims[0].sources) == 4


async def test_every_quote_is_a_substring_of_the_snippet_it_names() -> None:
    """The end-to-end form of the evidence guarantee.

    Two providers with differently truncated copies of one wire report, so a quote
    attributed to the wrong provider would not be found in that provider's snippet and
    this would fail.
    """
    fakes = {
        SearchProvider.TAVILY: Fake(
            "tavily", results=[wire("https://bbc.co.uk/news/1")]
        ),
        SearchProvider.BRAVE: Fake(
            "brave", results=[wire("https://bbc.co.uk/news/1", snippet=WIRE_TRUNCATED)]
        ),
    }

    with bench(dict(fakes)):
        result = await service(
            SEARCH_PROVIDERS=[SearchProvider.TAVILY, SearchProvider.BRAVE]
        ).from_claims([CLAIM])
    source = result.claims[0].sources[0]

    assert source.evidence
    for evidence in source.evidence:
        snippet = source.snippet_for(evidence.provider)
        assert snippet is not None
        assert snippet[evidence.start : evidence.end] == evidence.quote


async def test_a_page_that_says_nothing_keeps_its_place_with_no_evidence() -> None:
    """That a page three engines returned says nothing about the claim is information.

    Dropping it would replace that with silence, and the dossier would look like the
    search found only relevant things.
    """
    fake = Fake(
        "tavily",
        results=[
            found(
                "https://example.com/ferries",
                title="Ferries cancelled",
                snippet="High winds cancelled sailings from Portsmouth on Sunday.",
            )
        ],
    )

    with bench({SearchProvider.TAVILY: fake}):
        result = await service().from_claims([CLAIM])
    source = result.claims[0].sources[0]

    assert source.evidence == ()
    assert source.retrievals
    assert result.searched is True


# ================================================================= fact checks ====


async def test_a_fact_check_lands_on_the_claim_it_was_found_for() -> None:
    """Positional, and nothing downstream re-derives it.

    A shuffle here would attach a real published verdict to the wrong claim: genuine
    text, fabricated relevance, and nothing in the response to reveal it.
    """
    other = "Inflation was 2.8% in March 2026."
    database = factcheck_bench.Fake(
        found={
            CLAIM: [factcheck_bench.record(CLAIM)],
            other: [factcheck_bench.record(other)],
        }
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        result = await checking().from_claims([CLAIM, other])

    assert [c.claim.text for c in result.claims[0].fact_checks] == [CLAIM]
    assert [c.claim.text for c in result.claims[1].fact_checks] == [other]
    assert result.fact_checks == 2
    assert result.fact_checked is True


async def test_the_fact_check_lookup_reads_the_same_clock_as_the_search() -> None:
    """Both fan-outs run against one reading of it, and it is the one published.

    The two ask different services nothing about each other, so nothing but this test
    would notice a second ``utcnow()`` — and a review published between the two readings
    would then be "in the future" for one of them and not the other.
    """
    engine = Fake("tavily", results=[wire("https://bbc.co.uk/news/1")])
    database = factcheck_bench.Fake(results=[factcheck_bench.record(CLAIM)])

    with bench({SearchProvider.TAVILY: engine}), factcheck_bench.bench(database):
        result = await checking().from_claims([CLAIM])

    assert set(engine.nows) | set(database.nows) == {result.retrieved_at}


async def test_the_claim_is_looked_up_as_written_while_the_search_is_widened() -> None:
    """The two fan-outs want different things and are given different things.

    Search formulations strip and recombine keywords to surface *documents*; a
    fact-check index is keyed on claim wording, where a reworded variant matches a
    different record.
    So the lookup gets exactly one query per claim, unmodified — nothing appended, no
    "fact check", no "debunked".
    """
    engine = Fake("tavily", results=[])
    database = factcheck_bench.Fake()

    with bench({SearchProvider.TAVILY: engine}), factcheck_bench.bench(database):
        await checking().from_claims([CLAIM])

    assert database.queries == [CLAIM]
    assert engine.queries == [CLAIM]


async def test_a_claim_that_was_not_researched_is_not_looked_up_either() -> None:
    """The exclusions apply to both fan-outs, or the fact-check section would describe
    claims the sources section does not.
    """
    database = factcheck_bench.Fake()

    with (
        extractor_bench(
            StubClaimExtractor(extraction=claims_of(fit=[FIT], unfit=[UNFIT]))
        ),
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        result = await checking().from_text(SAMPLE_TEXT)

    assert database.queries == [FIT]
    assert [s.claim for s in result.skipped] == [UNFIT]


async def test_the_settings_reach_the_database() -> None:
    """Every one of these is invisible in the response: a page size that never left the
    config would look exactly like a database holding that many records.
    """
    database = factcheck_bench.Fake()

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        await checking(
            FACT_CHECK_MAX_RESULTS=5,
            FACT_CHECK_LANGUAGE="en",
            FACT_CHECK_MAX_AGE_DAYS=90,
        ).from_claims([CLAIM])

    assert database.limits == [5]
    assert database.languages == ["en"]
    assert database.ages == [90]


async def test_the_rating_is_read_on_the_way_through() -> None:
    """The clients may not interpret a rating and the schema will not either, so this is
    the one path on which it happens. Both values travel: the publisher's own string and
    this service's reading of it, labelled as derived.
    """
    database = factcheck_bench.Fake(
        results=[
            factcheck_bench.record(
                CLAIM,
                factcheck_bench.review(
                    publisher="PolitiFact",
                    url="https://politifact.com/factchecks/2026/mar/20/rate/",
                    rating="Mostly false",
                ),
            )
        ]
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        result = await checking().from_claims([CLAIM])

    found_check = result.claims[0].fact_checks[0]
    assert found_check.source == "google"
    assert found_check.reviews[0].rating == "Mostly false"
    assert found_check.reviews[0].stance is Stance.MOSTLY_FALSE
    assert found_check.reviews[0].stance_from == "mostly false"
    assert found_check.reviews[0].url == (
        "https://politifact.com/factchecks/2026/mar/20/rate/"
    )
    assert found_check.match == 1.0


async def test_a_review_of_a_different_claim_never_reaches_the_dossier() -> None:
    """And the flag still says the database answered.

    The most easily-confused pair of states in the whole response: zero fact checks
    *and* a working lookup. Google returns its best match for a query, so for a claim
    nobody has reviewed the best match is some other claim — which is dropped here, and
    must not be dropped in a way that reads as "the lookup never ran".
    """
    database = factcheck_bench.Fake(
        results=[factcheck_bench.record("Vaccines cause autism.")]
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        result = await checking().from_claims([CLAIM])

    assert result.claims[0].fact_checks == ()
    assert result.fact_checked is True


async def test_the_match_floor_is_configurable_and_applied_by_the_service() -> None:
    """A record that clears the default floor and not a raised one.

    The wording below shares the year and the subject with the claim and states
    something else about it — the shape of a neighbouring claim, which is what the
    floor is tuned against.
    """
    near = "The Bank of England held rates in March 2026."
    database = factcheck_bench.Fake(results=[factcheck_bench.record(near)])

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        kept = await checking().from_claims([CLAIM])
        dropped = await checking(FACT_CHECK_MIN_MATCH=0.9).from_claims([CLAIM])

    assert [c.claim.text for c in kept.claims[0].fact_checks] == [near]
    assert dropped.claims[0].fact_checks == ()


async def test_an_empty_database_answer_is_not_the_same_as_no_lookup() -> None:
    """The ``searched`` pair again, and the more dangerous of the two.

    Both dossiers below have no fact checks. One means the index was asked and holds no
    ruling on this claim; the other means no key is configured. A consumer reading the
    empty list alone would report a billing problem as "no fact-checker has examined
    this", which is a statement about the world.
    """
    with bench({SearchProvider.TAVILY: Fake("tavily", results=[])}):
        with factcheck_bench.bench(factcheck_bench.Fake(results=[])):
            answered = await checking().from_claims([CLAIM])
        unchecked = await service().from_claims([CLAIM])

    assert answered.claims[0].fact_checks == unchecked.claims[0].fact_checks == ()
    assert answered.fact_checked is True
    assert unchecked.fact_checked is False


async def test_a_missing_fact_check_key_does_not_make_the_search_look_broken() -> None:
    """The two rosters are reported separately, and this is why.

    The fact-check key is free but separate from the search keys, so a deployment
    with one and not the other is the common case rather than a fault. Folding the
    lookup into ``providers`` would make ``complete`` false and ``failures``
    non-empty for a service that searched everything it was configured to search.
    """
    page = wire("https://bbc.co.uk/news/1")

    with bench({SearchProvider.TAVILY: Fake("tavily", results=[page])}):
        result = await service().from_claims([CLAIM])

    assert result.searched is True
    assert result.complete is True
    assert result.failures == ()
    assert result.claims[0].sources
    assert result.fact_checked is False
    assert [o.status for o in result.fact_checkers] == [ProviderStatus.SKIPPED]
    assert "GOOGLE_FACT_CHECK_API_KEY" in result.fact_checkers[0].detail
    # And the fact-check outcome is not in the search roster, where a reader counting
    # providers would take it for a fourth engine.
    assert [o.provider for o in result.providers] == ["tavily"]


async def test_a_dead_database_costs_the_search_nothing() -> None:
    """One fan-out failing must not empty the other. Both directions are tested: the
    sources survive here, and ``test_one_dead_provider_costs_only_its_own_results``
    covers the search side.
    """
    database = factcheck_bench.Fake(
        error=FactCheckError("google is down", provider="google")
    )

    page = wire("https://bbc.co.uk/news/1")

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[page])}),
        factcheck_bench.bench(database),
    ):
        result = await checking().from_claims([CLAIM])

    assert result.claims[0].sources
    assert result.searched is True
    assert result.claims[0].fact_checks == ()
    assert result.fact_checked is False
    assert result.fact_checkers[0].status is ProviderStatus.FAILED
    assert result.fact_checkers[0].code == "fact_check_error"


async def test_the_fact_check_key_never_reaches_a_reportable_detail() -> None:
    """``detail`` is returned to the client, and provider messages echo requests."""
    database = factcheck_bench.Fake(
        error=FactCheckError(f"401 for key={FACT_CHECK_KEY}", provider="google")
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        result = await checking().from_claims([CLAIM])

    assert FACT_CHECK_KEY not in result.fact_checkers[0].detail
    assert "***" in result.fact_checkers[0].detail


async def test_a_fact_check_is_never_counted_among_the_sources() -> None:
    """Beside the web pages, not folded into them.

    A published fact check did not come from a search provider, must not be deduplicated
    against the pages and must not be ranked among them — so none of the claim's
    ``sources``, ``domains`` or ``stories`` may move when the lookup finds something. A
    dossier where they did would let one fact check read as corroboration by an extra
    outlet.
    """
    page = wire("https://bbc.co.uk/news/1")
    database = factcheck_bench.Fake(
        results=[
            factcheck_bench.record(
                CLAIM,
                factcheck_bench.review(
                    publisher="PolitiFact", url="https://bbc.co.uk/news/1"
                ),
            )
        ]
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[page])}),
        factcheck_bench.bench(database),
    ):
        checked = await checking().from_claims([CLAIM])
    with bench({SearchProvider.TAVILY: Fake("tavily", results=[page])}):
        plain = await service().from_claims([CLAIM])

    # Even sharing a URL with a source — the case a merge would trigger on.
    assert len(checked.claims[0].sources) == len(plain.claims[0].sources) == 1
    assert checked.sources == plain.sources == 1
    assert checked.claims[0].domains == plain.claims[0].domains == ("bbc.co.uk",)
    assert checked.claims[0].stories == plain.claims[0].stories == 1
    assert len(checked.claims[0].fact_checks) == 1
