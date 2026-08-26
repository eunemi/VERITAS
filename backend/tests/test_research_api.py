"""The ``POST /research`` endpoint, over HTTP, with no network.

Three contracts are asserted here and nowhere else, because they are properties of the
*response* rather than of any module underneath it.

**The status code is about the request, never about the web.** Every provider dead,
no keys configured, an index that returned nothing — all of them are ``200`` with the
outcome on the body. The tests below drive each of those states and check the code,
because the tempting alternatives are all worse in the same way: a ``502`` for "Tavily
timed out" discards the results Brave returned in the same request, and a ``500`` for
"no keys are configured" is indistinguishable, to a client, from "nothing has been
written about this claim".

**``searched`` is what separates the two kinds of nothing.** An expired key and a
claim nobody has ever written about produce the same empty ``sources``, and the only
thing standing between those two readings is that flag. There is a test here that
drives both and asserts they differ in exactly that field — it is the single most
load-bearing assertion in the file. ``fact_checked`` gets the same treatment in the
last section, where the wrong reading is the more inviting of the two: an empty
``fact_checks`` list reads as "nobody has ruled on this claim" and licenses treating it
as unexamined.

**A fact check is evidence in the body, never the answer.** The final section asserts
that as a property of the serialised JSON rather than of any object underneath it:
everything a publisher said nests under ``fact_checks[].claim``, everything this
service derived sits beside it, ``claim.text`` is always the *database's* wording so a
ruling on a neighbouring claim cannot read as a ruling on the submitted one, and no
field at any level of the response is a verdict on what the client sent.

Everything else is plumbing that has been proved elsewhere and is checked once here
end to end: that the two-level dedup survives serialisation, that an evidence quote
can be re-derived from the JSON alone, and that nothing is appended to a query on the
way out.

**Not runnable offline.** Unlike the rest of the research tests, this file needs
FastAPI, pydantic and httpx installed. The search providers are faked through
:mod:`tests.search_bench` and the extractor through :mod:`tests.stubs`, so nothing
reaches the network — but the ASGI stack itself is real and cannot be stubbed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from pydantic import SecretStr

from app.core.config import SearchProvider, Settings, get_settings
from app.core.errors import ConfigurationError, FactCheckError, SearchError
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

V1 = "/api/v1"

#: The claim the fixtures search for. Sent through the ``claims`` input in most tests,
#: which means one query per claim and therefore counts that are easy to read.
CLAIM = "The Bank of England held its benchmark rate at 4.75% in March 2026."

#: A snippet about something else entirely, for the cases where a page is found and
#: says nothing about the claim.
UNRELATED = (
    "Ferry services between Portsmouth and Fishbourne were cancelled on Sunday "
    "after high winds closed the Solent to smaller vessels for several hours."
)

#: Long enough for :func:`app.providers.http.redact` to act on it.
FACT_CHECK_KEY = "fc-secret-key-value"


@pytest.fixture
def configure(app: FastAPI, settings: Settings) -> Callable[..., Settings]:
    """Override the settings the route sees, one field at a time.

    ``model_copy`` rather than a fresh :class:`Settings`, so a test names only what it
    is varying and inherits the deterministic rest — including ``_env_file=None``,
    without which these tests would read the developer's ``.env`` and pass or fail
    depending on what is in it.
    """

    def apply(**overrides: object) -> Settings:
        tuned = settings.model_copy(update=overrides)
        app.dependency_overrides[get_settings] = lambda: tuned
        return tuned

    return apply


@pytest.fixture
def one_provider(configure: Callable[..., Settings]) -> Settings:
    """A roster of exactly one provider, so result counts are unambiguous."""
    return configure(SEARCH_PROVIDERS=[SearchProvider.TAVILY])


@pytest.fixture
def checking(configure: Callable[..., Settings]) -> Settings:
    """One provider *and* a fact-check key, so the lookup runs instead of being skipped.

    Separate from :func:`one_provider` because most of this file is about the search, and
    a key set everywhere would mean every test above silently depended on a fake database
    being registered.
    """
    return configure(
        SEARCH_PROVIDERS=[SearchProvider.TAVILY],
        GOOGLE_FACT_CHECK_API_KEY=SecretStr(FACT_CHECK_KEY),
    )


async def research(client: AsyncClient, **payload: object) -> Response:
    """POST a body and return the response. Named for what the reader cares about."""
    return await client.post(f"{V1}/research", json=payload)


# ============================================================== which input ====


async def test_both_inputs_is_a_422_and_nothing_is_searched(
    client: AsyncClient, one_provider: Settings
) -> None:
    """Ambiguous about which claims to research, and in what order.

    Silently preferring one would make the other input look accepted, so this is
    refused before a single query is sent — which the fake proves rather than assumes.
    """
    fake = Fake("tavily", results=[found("https://bbc.co.uk/news/1", snippet=WIRE)])

    with bench({SearchProvider.TAVILY: fake}):
        response = await research(client, text=SAMPLE_TEXT, claims=[CLAIM])

    assert response.status_code == 422
    assert fake.queries == []


async def test_neither_input_is_a_422(client: AsyncClient) -> None:
    response = await research(client)

    assert response.status_code == 422


async def test_the_refusal_says_which_rule_was_broken(client: AsyncClient) -> None:
    """A 422 that does not name the rule leaves a client guessing at two fields."""
    response = await research(client)

    messages = [e["message"] for e in response.json()["error"]["details"]["errors"]]
    assert any("exactly one of" in message for message in messages)


@pytest.mark.parametrize("claims", [[""], ["   "], [CLAIM, ""], ["\n\t"]])
async def test_a_blank_claim_entry_is_refused(
    client: AsyncClient, claims: list[str]
) -> None:
    """A blank claim would be searched as a blank query, and match everything.

    Dropping it silently is the other option, and it would produce a response
    describing fewer claims than were submitted with nothing to say why.
    """
    response = await research(client, claims=claims)

    assert response.status_code == 422


async def test_an_empty_claims_list_is_refused(client: AsyncClient) -> None:
    response = await research(client, claims=[])

    assert response.status_code == 422


async def test_an_empty_text_is_refused(client: AsyncClient) -> None:
    response = await research(client, text="")

    assert response.status_code == 422


async def test_an_unexpected_field_is_refused(client: AsyncClient) -> None:
    """``extra="forbid"``, and this is the field that makes it matter.

    A caller trying to steer the search by naming providers in the body needs to
    learn that the field does nothing, rather than have it ignored and read the
    response as having honoured it.
    """
    response = await research(client, claims=[CLAIM], providers=["tavily"])

    assert response.status_code == 422


async def test_errors_use_the_error_envelope(client: AsyncClient) -> None:
    response = await research(client)

    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


# ============================================================= the size limit ====


async def test_oversized_text_is_413_before_the_extractor(
    client: AsyncClient, configure: Callable[..., Settings]
) -> None:
    """The guard runs first, so an oversized body does not load a 12 MB model."""
    configure(MAX_TEXT_CHARS=20)
    stub = StubClaimExtractor()

    with extractor_bench(stub):
        response = await research(client, text="x" * 50)

    assert response.status_code == 413
    assert response.json()["error"]["details"] == {
        "field": "text",
        "characters": 50,
        "limit": 20,
    }
    assert stub.seen == []


async def test_oversized_claims_are_413_naming_the_claims_field(
    client: AsyncClient, configure: Callable[..., Settings]
) -> None:
    """The ceiling applies to both inputs, and ``details`` says which one to shorten.

    Measured over the claims joined by newlines — the whole submission — because a
    caller can otherwise get past a per-claim limit by splitting one long string.
    """
    configure(MAX_TEXT_CHARS=20, SEARCH_PROVIDERS=[SearchProvider.TAVILY])
    fake = Fake("tavily", results=[found("https://bbc.co.uk/news/1", snippet=WIRE)])

    with bench({SearchProvider.TAVILY: fake}):
        response = await research(client, claims=["x" * 12, "y" * 12])

    assert response.status_code == 413
    assert response.json()["error"]["details"] == {
        "field": "claims",
        "characters": 25,  # 12 + 1 newline + 12
        "limit": 20,
    }
    assert fake.queries == []


# ============================================================== always a 200 ====


async def test_no_configured_provider_is_a_200_that_says_nothing_was_searched(
    client: AsyncClient,
) -> None:
    """The commonest way to deploy this half-configured, and it must be legible.

    No fakes: the real factories run and every one raises for want of a key. A 500
    here would be indistinguishable, to a client, from a claim nobody has written
    about — so the failure is on the body and the status code is a 200.
    """
    response = await research(client, claims=[CLAIM])

    assert response.status_code == 200
    body = response.json()
    assert body["searched"] is False
    assert {p["status"] for p in body["providers"]} == {"skipped"}
    assert body["claims"][0]["sources"] == []
    # The queries were built and are reported, so a reader can see what *would* have
    # been asked. Reporting them as empty would misdescribe the request.
    assert body["claims"][0]["queries"] == [CLAIM]
    assert all(p["detail"] for p in body["providers"])


async def test_an_empty_index_is_not_the_same_answer_as_an_unsearched_one(
    client: AsyncClient, one_provider: Settings
) -> None:
    """The load-bearing distinction of the whole feature.

    Both responses below have ``sources: []``. One means the web was searched and
    holds nothing about this claim; the other means no search happened. ``searched``
    is the only field that separates them, and a consumer that reads the empty list
    without it would report an expired API key as an absence of evidence.
    """
    with bench({SearchProvider.TAVILY: Fake("tavily", results=[])}):
        answered = await research(client, claims=[CLAIM])
    unsearched = await research(client, claims=[CLAIM])  # no key, no fake

    assert answered.json()["claims"][0]["sources"] == []
    assert unsearched.json()["claims"][0]["sources"] == []
    assert answered.json()["searched"] is True
    assert unsearched.json()["searched"] is False


async def test_a_dead_provider_costs_only_its_own_results(
    client: AsyncClient, configure: Callable[..., Settings]
) -> None:
    """One engine down, the other's results intact, and the loss stated on the body."""
    configure(SEARCH_PROVIDERS=[SearchProvider.TAVILY, SearchProvider.BRAVE])
    dead = Fake("tavily", error=SearchError("tavily is down", provider="tavily"))
    alive = Fake("brave", results=[found("https://bbc.co.uk/news/1", snippet=WIRE)])

    with bench({SearchProvider.TAVILY: dead, SearchProvider.BRAVE: alive}):
        response = await research(client, claims=[CLAIM])

    assert response.status_code == 200
    body = response.json()
    outcomes = {p["provider"]: p for p in body["providers"]}
    assert outcomes["tavily"]["status"] == "failed"
    assert outcomes["tavily"]["code"] == "search_error"
    assert outcomes["brave"]["status"] == "searched"
    assert body["searched"] is True
    assert [s["domain"] for s in body["claims"][0]["sources"]] == ["bbc.co.uk"]


async def test_every_provider_failing_is_still_a_200(
    client: AsyncClient, one_provider: Settings
) -> None:
    """Nothing partial to salvage, and still not an error status.

    ``searched: false`` carries the finding, which is what lets a client tell this
    apart from a successful search that found nothing.
    """
    with bench(
        {SearchProvider.TAVILY: Fake("tavily", error=SearchError("502", provider="tavily"))}
    ):
        response = await research(client, claims=[CLAIM])

    assert response.status_code == 200
    assert response.json()["searched"] is False
    assert response.json()["providers"][0]["status"] == "failed"


async def test_an_api_key_never_reaches_the_response_body(
    client: AsyncClient, configure: Callable[..., Settings]
) -> None:
    """Provider error text is returned to the client, and providers echo requests.

    The key is only ever unwrapped into a request header, so in principle nothing
    here has one to find. This is the last line of defence, and it is checked against
    the whole serialised body rather than the one field that is expected to carry the
    message.
    """
    key = "sk-tavily-0123456789"
    configure(
        SEARCH_PROVIDERS=[SearchProvider.TAVILY], TAVILY_API_KEY=SecretStr(key)
    )
    leaky = Fake(
        "tavily",
        error=SearchError(f"401 unauthorized for key {key}", provider="tavily"),
    )

    with bench({SearchProvider.TAVILY: leaky}):
        response = await research(client, claims=[CLAIM])

    assert response.status_code == 200
    assert key not in response.text
    assert "***" in response.json()["providers"][0]["detail"]


async def test_one_outcome_per_configured_provider(client: AsyncClient) -> None:
    """Whatever became of it. A provider absent from this list was never accounted for."""
    response = await research(client, claims=[CLAIM])

    reported = [p["provider"] for p in response.json()["providers"]]
    assert reported == ["brave", "serper", "tavily"]


async def test_the_response_carries_exactly_the_documented_fields(
    client: AsyncClient,
) -> None:
    response = await research(client, claims=[CLAIM])
    body = response.json()

    assert set(body) == {
        "claims",
        "skipped",
        "providers",
        "fact_checkers",
        "retrieved_at",
        "searched",
        "fact_checked",
    }
    assert set(body["claims"][0]) == {
        "claim",
        "queries",
        "sources",
        "fact_checks",
        "domains",
        "stories",
    }


# ========================================================== what was searched ====


async def test_the_queries_reported_are_the_queries_sent(
    client: AsyncClient, one_provider: Settings
) -> None:
    """``queries`` is a record, not a reconstruction.

    Rebuilding it for the response would give a list that stays plausible while
    quietly ceasing to be true — the first time query construction changed under a
    cached result. The fake is the witness: what it saw must equal what was reported.
    """
    fake = Fake("tavily", results=[found("https://bbc.co.uk/news/1", snippet=WIRE)])

    with bench({SearchProvider.TAVILY: fake}):
        response = await research(client, claims=[CLAIM, "Inflation fell to 2.8%."])

    reported = [q for claim in response.json()["claims"] for q in claim["queries"]]
    assert sorted(fake.queries) == sorted(reported)
    assert len(fake.queries) == 2


async def test_no_steering_words_are_added_to_a_query(
    client: AsyncClient, one_provider: Settings
) -> None:
    """A query this service steered would return evidence it had chosen the shape of.

    No "fact check", no "debunked", no "is it true" — on the ``claims`` path the claim
    is searched exactly as written, which is also why that path reports one query.
    """
    fake = Fake("tavily", results=[])

    with bench({SearchProvider.TAVILY: fake}):
        await research(client, claims=[CLAIM])

    assert fake.queries == [CLAIM]


async def test_the_claims_path_never_touches_the_extractor(
    client: AsyncClient, one_provider: Settings
) -> None:
    """Which is what makes it work in a deployment with search keys and no model."""
    stub = StubClaimExtractor(raises=AssertionError("the extractor was called"))

    with extractor_bench(stub), bench({SearchProvider.TAVILY: Fake("tavily")}):
        response = await research(client, claims=[CLAIM])

    assert response.status_code == 200
    assert stub.seen == []


async def test_the_text_path_searches_what_the_extractor_found(
    client: AsyncClient, one_provider: Settings
) -> None:
    """Three formulations for the one checkable claim, the first of which is the claim.

    The later rungs exist because the extractor found an entity and a keyword; the
    ``claims`` path has neither and gets one query. The difference is visible in
    ``queries`` rather than hidden.
    """
    fake = Fake("tavily", results=[])

    with extractor_bench(StubClaimExtractor()), bench({SearchProvider.TAVILY: fake}):
        response = await research(client, text=SAMPLE_TEXT)

    queries = response.json()["claims"][0]["queries"]
    assert queries[0] == "The bridge opened in March 2026."
    assert len(queries) > 1
    # Sorted, because the queries go out concurrently: the order they arrive at one
    # provider is not something the fan-out promises, and asserting it would be
    # asserting an accident of scheduling.
    assert sorted(fake.queries) == sorted(queries)


async def test_a_missing_model_is_a_500_naming_the_fix(client: AsyncClient) -> None:
    """Only reachable through ``text``; ``claims`` needs no model at all."""
    stub = StubClaimExtractor(
        raises=ConfigurationError(
            "The spaCy model 'en_core_web_sm' is not installed.",
            details={"install": "python -m spacy download en_core_web_sm"},
        )
    )

    with extractor_bench(stub):
        response = await research(client, text=SAMPLE_TEXT)

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "configuration_error"
    assert error["details"]["install"] == "python -m spacy download en_core_web_sm"


# ================================================================== the dedup ====


async def test_one_page_from_three_engines_is_one_source(
    client: AsyncClient, configure: Callable[..., Settings]
) -> None:
    """Three URL spellings of one document, merged, with every spelling kept.

    Merging is safe here and only here: the same server sends the same bytes for all
    three. The corroboration between indexes is recorded on ``providers``, which is
    not corroboration between publishers.
    """
    configure(
        SEARCH_PROVIDERS=[
            SearchProvider.TAVILY,
            SearchProvider.BRAVE,
            SearchProvider.SERPER,
        ]
    )
    fakes: dict[SearchProvider, Fake | Exception] = {
        SearchProvider.TAVILY: Fake(
            "tavily", results=[found("https://bbc.co.uk/news/1?utm_source=x", snippet=WIRE)]
        ),
        SearchProvider.BRAVE: Fake(
            "brave", results=[found("http://www.bbc.co.uk/news/1/", snippet=WIRE)]
        ),
        SearchProvider.SERPER: Fake(
            "serper", results=[found("https://bbc.co.uk/news/1#top", snippet=WIRE)]
        ),
    }

    with bench(fakes):
        response = await research(client, claims=[CLAIM])

    claim = response.json()["claims"][0]
    assert len(claim["sources"]) == 1
    source = claim["sources"][0]
    assert sorted(source["providers"]) == ["brave", "serper", "tavily"]
    assert len(source["urls"]) == 3
    assert source["url"] == "https://bbc.co.uk/news/1"
    assert claim["domains"] == ["bbc.co.uk"]
    assert claim["stories"] == 1


async def test_syndication_is_marked_and_never_merged(
    client: AsyncClient, one_provider: Settings
) -> None:
    """One wire report under three mastheads: three sources, three domains, one story.

    The asymmetry the whole feature turns on. Merging these would delete two real
    publishers from the record with nothing left to show it happened; leaving them
    unmarked would let three domains read as three independent confirmations.
    ``stories`` is the number a reader should believe.
    """
    fake = Fake(
        "tavily",
        results=[
            found("https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE),
            found(
                "https://apnews.com/b",
                title=WIRE_TITLE_REWRITTEN,
                snippet=WIRE_TRUNCATED,
            ),
            found(
                "https://heraldscotland.com/c",
                title=WIRE_TITLE_REGIONAL,
                snippet=WIRE_WITH_LEAD,
            ),
        ],
    )

    with bench({SearchProvider.TAVILY: fake}):
        response = await research(client, claims=[CLAIM])

    claim = response.json()["claims"][0]
    assert len(claim["sources"]) == 3
    assert sorted(claim["domains"]) == ["apnews.com", "heraldscotland.com", "reuters.com"]
    assert claim["stories"] == 1
    clusters = {source["cluster"] for source in claim["sources"]}
    assert clusters == {1}


async def test_a_url_that_is_not_a_web_page_never_becomes_a_source(
    client: AsyncClient, one_provider: Settings
) -> None:
    """A source a reader cannot open cannot be checked, so it is dropped, not renamed."""
    fake = Fake(
        "tavily",
        results=[
            found("mailto:tips@example.com", snippet=WIRE),
            found("https://bbc.co.uk/news/1", snippet=WIRE),
        ],
    )

    with bench({SearchProvider.TAVILY: fake}):
        response = await research(client, claims=[CLAIM])

    sources = response.json()["claims"][0]["sources"]
    assert [s["url"] for s in sources] == ["https://bbc.co.uk/news/1"]


# ================================================================ the evidence ====


async def test_an_evidence_quote_can_be_rederived_from_the_body_alone(
    client: AsyncClient, configure: Callable[..., Settings]
) -> None:
    """The verbatim guarantee, as something the consumer can check rather than trust.

    This is the exact procedure in :class:`~app.schemas.research.EvidenceOut`'s
    docstring, run against the serialised response: find the retrieval whose provider
    the evidence names, slice its snippet, compare. Two providers with differently
    truncated snippets, so offsets valid against one are wrong against the other and a
    mixed-up attribution cannot pass.
    """
    configure(SEARCH_PROVIDERS=[SearchProvider.TAVILY, SearchProvider.BRAVE])
    fakes: dict[SearchProvider, Fake | Exception] = {
        SearchProvider.TAVILY: Fake(
            "tavily", results=[found("https://bbc.co.uk/news/1", snippet=WIRE)]
        ),
        SearchProvider.BRAVE: Fake(
            "brave", results=[found("https://bbc.co.uk/news/1", snippet=WIRE_TRUNCATED)]
        ),
    }

    with bench(fakes):
        response = await research(client, claims=[CLAIM])

    source = response.json()["claims"][0]["sources"][0]
    assert source["evidence"]
    for evidence in source["evidence"]:
        snippet = next(
            r["snippet"]
            for r in source["retrievals"]
            if r["provider"] == evidence["provider"]
        )
        assert snippet[evidence["start"] : evidence["end"]] == evidence["quote"]


async def test_a_page_saying_nothing_about_the_claim_has_empty_evidence(
    client: AsyncClient, one_provider: Settings
) -> None:
    """Found and irrelevant is a finding, and it is reported as one.

    An arbitrary first sentence under the heading "evidence" would fabricate the
    *relevance* while every character stayed genuine — the one failure a reader has no
    way to detect. Dropping the source instead would make the search look as though it
    had found only relevant things.
    """
    fake = Fake("tavily", results=[found("https://sky.com/news/9", snippet=UNRELATED)])

    with bench({SearchProvider.TAVILY: fake}):
        response = await research(client, claims=[CLAIM])

    sources = response.json()["claims"][0]["sources"]
    assert len(sources) == 1
    assert sources[0]["evidence"] == []
    assert sources[0]["retrievals"][0]["snippet"] == UNRELATED


async def test_a_snippet_is_returned_exactly_as_the_provider_sent_it(
    client: AsyncClient, one_provider: Settings
) -> None:
    """Every evidence offset in the response indexes this string.

    Trimming it, collapsing its whitespace or stripping markup out of it would shift
    every offset computed from it and break the verbatim guarantee silently, so the
    round trip is asserted on a snippet with all three hazards in it.
    """
    ragged = f"  <b>Rates</b> held\n\n {WIRE}   "
    fake = Fake("tavily", results=[found("https://bbc.co.uk/news/1", snippet=ragged)])

    with bench({SearchProvider.TAVILY: fake}):
        response = await research(client, claims=[CLAIM])

    source = response.json()["claims"][0]["sources"][0]
    assert source["retrievals"][0]["snippet"] == ragged


# ================================================================== not searched ====


async def test_an_unfit_claim_is_reported_as_skipped_not_dropped(
    client: AsyncClient, one_provider: Settings
) -> None:
    """A response listing one claim for prose that made two misdescribes the prose.

    The extractor's own reason travels with it, so a caller that disagrees can see the
    judgement was made and resubmit through ``claims``, which does not second-guess.
    """
    with extractor_bench(StubClaimExtractor()), bench({SearchProvider.TAVILY: Fake("t")}):
        response = await research(client, text=SAMPLE_TEXT)

    body = response.json()
    assert [c["claim"] for c in body["claims"]] == ["The bridge opened in March 2026."]
    assert body["skipped"] == [
        {"claim": "It is a beautiful bridge.", "reason": "opinion"}
    ]


async def test_the_claims_path_does_not_second_guess_a_claim(
    client: AsyncClient, one_provider: Settings
) -> None:
    """The caller asserting that this string is a claim beats a regex saying it is not.

    The string below is what the extractor marks as opinion on the ``text`` path. Sent
    through ``claims`` it is searched, because refusing would be this service
    overruling an explicit request on a guess.
    """
    fake = Fake("tavily", results=[])

    with bench({SearchProvider.TAVILY: fake}):
        response = await research(client, claims=["It is a beautiful bridge."])

    body = response.json()
    assert body["skipped"] == []
    assert fake.queries == ["It is a beautiful bridge."]


async def test_the_claim_ceiling_names_every_claim_it_cut(
    client: AsyncClient, configure: Callable[..., Settings]
) -> None:
    """The ceiling applies to both inputs, and what it drops is listed, not absent.

    The first *n* are kept rather than a sample: they are the ones the submission led
    with, and any other rule would need a notion of which claims matter that this
    service does not have. The reason names the setting, so an operator reading a
    truncated response knows which number to raise.
    """
    configure(SEARCH_PROVIDERS=[SearchProvider.TAVILY], SEARCH_MAX_CLAIMS=2)
    fake = Fake("tavily", results=[])
    sent = [CLAIM, "Inflation fell to 2.8%.", "Unemployment rose.", "Growth stalled."]

    with bench({SearchProvider.TAVILY: fake}):
        response = await research(client, claims=sent)

    body = response.json()
    assert [c["claim"] for c in body["claims"]] == sent[:2]
    assert [s["claim"] for s in body["skipped"]] == sent[2:]
    assert "SEARCH_MAX_CLAIMS=2" in body["skipped"][0]["reason"]
    assert "only the first 2 claims of 4" in body["skipped"][0]["reason"]
    # Nothing past the ceiling was searched, rather than searched and discarded.
    assert sorted(fake.queries) == sorted(sent[:2])


async def test_each_claim_keeps_its_own_results(
    client: AsyncClient, one_provider: Settings
) -> None:
    """Two claims in one request are researched in one fan-out and stay separate.

    Results are aligned by index rather than keyed by claim text, because two claims
    in one request can be identical after rewriting and keying would silently drop
    one. Here the two are searched together and each reports the same page, which is
    what alignment looks like from outside.
    """
    fake = Fake("tavily", results=[found("https://bbc.co.uk/news/1", snippet=WIRE)])

    with bench({SearchProvider.TAVILY: fake}):
        response = await research(client, claims=[CLAIM, "Inflation fell to 2.8%."])

    claims = response.json()["claims"]
    assert len(claims) == 2
    assert [c["claim"] for c in claims] == [CLAIM, "Inflation fell to 2.8%."]
    for claim in claims:
        assert [s["url"] for s in claim["sources"]] == ["https://bbc.co.uk/news/1"]


# =============================================================== the fact checks ====


async def test_a_fact_check_is_serialised_with_every_documented_field(
    client: AsyncClient, checking: Settings
) -> None:
    """The whole object over the wire, asserted key by key at all three levels.

    ``extra="forbid"`` catches a field the response invents; only an exact key set
    catches one it silently stops sending. And the shape is the argument: everything the
    database said is nested under ``claim``, everything this service worked out sits
    beside it. A reader who cannot see that boundary in the JSON will read a publisher's
    rating as this service's verdict.
    """
    when = datetime(2026, 3, 20, 9, 0, tzinfo=UTC)
    database = factcheck_bench.Fake(
        results=[
            factcheck_bench.record(
                CLAIM,
                factcheck_bench.review(
                    publisher="PolitiFact",
                    site="politifact.com",
                    url="https://politifact.com/factchecks/2026/mar/20/rate/",
                    rating="Mostly false",
                    title="No, the Bank did not hold",
                    language="en",
                    reviewed_at=when,
                    date_text="2026-03-20T09:00:00Z",
                ),
                claimant="A Senator",
                claimed_at=when,
                date_text="2026-03-20T09:00:00Z",
            )
        ]
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        response = await research(client, claims=[CLAIM])

    assert response.status_code == 200
    check = response.json()["claims"][0]["fact_checks"][0]
    assert set(check) == {
        "source",
        "claim",
        "match",
        "matched_entities",
        "matched_terms",
        "matched_numbers",
        "publishers",
        "agreement",
    }
    assert set(check["claim"]) == {
        "text",
        "reviews",
        "claimant",
        "claimed_at",
        "date_text",
    }
    assert set(check["claim"]["reviews"][0]) == {
        "publisher",
        "site",
        "url",
        "rating",
        "title",
        "language",
        "reviewed_at",
        "date_text",
        "stance",
        "stance_from",
    }
    # The four fields the request asked for, and the ones a citation needs.
    review = check["claim"]["reviews"][0]
    assert review["rating"] == "Mostly false"
    assert review["publisher"] == "PolitiFact"
    assert review["url"] == "https://politifact.com/factchecks/2026/mar/20/rate/"
    # Parsed rather than string-compared: the date is the subject, its spelling is
    # pydantic's business. `date_text` beside it is the publisher's own string and *is*
    # asserted verbatim, because that one is a passthrough not to be reformatted.
    assert datetime.fromisoformat(review["reviewed_at"]) == when
    assert review["date_text"] == "2026-03-20T09:00:00Z"
    assert check["source"] == "google"


async def test_the_rating_is_returned_verbatim_with_the_reading_beside_it(
    client: AsyncClient, checking: Settings
) -> None:
    """Two fields, and neither may replace the other.

    ``rating`` is the publisher's own string and is what a client should quote;
    ``stance`` is this service's reading of it on a fixed axis, which is what a client
    can branch on. ``stance_from`` names the phrase that produced the reading, so the
    derivation is auditable from the body alone without the vocabulary table.
    """
    database = factcheck_bench.Fake(
        results=[
            factcheck_bench.record(
                CLAIM, factcheck_bench.review(rating="Pants on Fire!")
            )
        ]
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        response = await research(client, claims=[CLAIM])

    review = response.json()["claims"][0]["fact_checks"][0]["claim"]["reviews"][0]
    assert review["rating"] == "Pants on Fire!"
    assert review["stance"] == "false"
    assert review["stance_from"] == "pants on fire"


async def test_a_rating_this_service_cannot_read_still_reaches_the_client(
    client: AsyncClient, checking: Settings
) -> None:
    """``unrecognised`` and the publisher's string intact, which says exactly as much as
    the publisher did — strictly more than a confident wrong reading would.
    """
    database = factcheck_bench.Fake(
        results=[
            factcheck_bench.record(
                CLAIM, factcheck_bench.review(rating="Missing context")
            )
        ]
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        response = await research(client, claims=[CLAIM])

    review = response.json()["claims"][0]["fact_checks"][0]["claim"]["reviews"][0]
    assert review["rating"] == "Missing context"
    assert review["stance"] == "unrecognised"
    assert review["stance_from"] == ""


async def test_the_body_carries_no_verdict_on_the_submitted_claim(
    client: AsyncClient, checking: Settings
) -> None:
    """The request's own constraint, asserted as a property of the serialised body.

    Two reviewers, both reading ``false``, is the strongest input this endpoint can
    receive — and there is still no field anywhere in the response that rules on the
    claim the client submitted. ``agreement`` is the nearest thing and it is scoped to
    the reviewers' reading of the *database's* wording, which is why ``claim.text`` is
    checked here too.
    """
    database = factcheck_bench.Fake(
        results=[
            factcheck_bench.record(
                CLAIM,
                factcheck_bench.review(publisher="PolitiFact", rating="False"),
                factcheck_bench.review(publisher="FactCheck.org", rating="Untrue"),
            )
        ]
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        response = await research(client, claims=[CLAIM])

    body = response.json()
    check = body["claims"][0]["fact_checks"][0]
    assert check["agreement"] == "false"
    assert check["publishers"] == ["PolitiFact", "FactCheck.org"]
    # Scoped to the database's wording of the claim, not to what was submitted.
    assert check["claim"]["text"] == CLAIM
    # No summary verdict at any level. `rating` exists only inside a named publisher's
    # review, never hoisted to the fact check, the claim or the response.
    absent = {"verdict", "rating", "determination", "conclusion"}
    assert not absent & set(body)
    assert not absent & set(body["claims"][0])
    assert not absent & set(check)
    assert not absent & set(check["claim"])


async def test_reviewers_who_differ_report_no_agreement_over_the_wire(
    client: AsyncClient, checking: Settings
) -> None:
    """``null``, not a majority — two syndicated copies of one wire story must not
    outvote the newsroom that did the reporting. Both ratings are still in the body.
    """
    database = factcheck_bench.Fake(
        results=[
            factcheck_bench.record(
                CLAIM,
                factcheck_bench.review(publisher="PolitiFact", rating="False"),
                factcheck_bench.review(publisher="Snopes", rating="Mostly true"),
            )
        ]
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        response = await research(client, claims=[CLAIM])

    check = response.json()["claims"][0]["fact_checks"][0]
    assert check["agreement"] is None
    assert [r["rating"] for r in check["claim"]["reviews"]] == ["False", "Mostly true"]


async def test_a_review_of_a_neighbouring_claim_says_so_in_the_body(
    client: AsyncClient, checking: Settings
) -> None:
    """The most consequential thing this response has to get right.

    A fact-check index answers with its closest record, which for an unreviewed claim is
    a *different* claim. ``claim.text`` is the database's wording and ``match`` is this
    service's arithmetic on it, so a client that reads both can see it has been handed a
    verdict on something adjacent. A response that echoed the submitted claim here would
    turn a real published rating into a fabricated ruling.
    """
    near = "The Federal Reserve held rates at 4.75% in March 2026."
    database = factcheck_bench.Fake(
        results=[
            factcheck_bench.record(near, factcheck_bench.review(rating="False"))
        ]
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        response = await research(client, claims=[CLAIM])

    body = response.json()
    check = body["claims"][0]["fact_checks"][0]
    assert body["claims"][0]["claim"] == CLAIM
    assert check["claim"]["text"] == near
    assert 0.0 < check["match"] < 1.0
    # The itemisation is what lets a reader see *why* it is not a match: the entity that
    # makes it a different claim is the one missing here.
    assert "Bank of England" not in check["matched_entities"]


async def test_an_unreviewed_claim_is_not_the_same_answer_as_an_unchecked_one(
    client: AsyncClient, checking: Settings, configure: Callable[..., Settings]
) -> None:
    """The ``searched`` pair again, on the field where the wrong reading is inviting.

    Both bodies below have ``fact_checks: []``. One means the index was asked and
    holds no ruling; the other means no key is configured. Reading the empty list
    alone turns a billing problem into "no fact-checker has examined this claim",
    which is a statement about the world and an invitation to treat the claim as
    unexamined.
    """
    with bench({SearchProvider.TAVILY: Fake("tavily", results=[])}):
        with factcheck_bench.bench(factcheck_bench.Fake(results=[])):
            answered = await research(client, claims=[CLAIM])
        # The same roster, the same fake search, one field different.
        configure(
            SEARCH_PROVIDERS=[SearchProvider.TAVILY], GOOGLE_FACT_CHECK_API_KEY=None
        )
        unchecked = await research(client, claims=[CLAIM])

    assert answered.json()["claims"][0]["fact_checks"] == []
    assert unchecked.json()["claims"][0]["fact_checks"] == []
    assert answered.json()["fact_checked"] is True
    assert unchecked.json()["fact_checked"] is False


async def test_no_fact_check_key_is_a_200_that_does_not_look_like_a_broken_search(
    client: AsyncClient, one_provider: Settings
) -> None:
    """The commonest deployment there is: search keys, no fact-check key.

    No fake and no key, so the real factory runs and raises. It lands on
    ``fact_checkers`` rather than ``providers`` precisely so this case cannot make a
    fully-working search roster read as incomplete — and the reason names the setting an
    operator would need to set.
    """
    page = found("https://bbc.co.uk/news/1", snippet=WIRE)

    with bench({SearchProvider.TAVILY: Fake("tavily", results=[page])}):
        response = await research(client, claims=[CLAIM])

    assert response.status_code == 200
    body = response.json()
    assert body["searched"] is True
    assert body["claims"][0]["sources"]
    assert body["fact_checked"] is False
    assert [f["status"] for f in body["fact_checkers"]] == ["skipped"]
    assert "GOOGLE_FACT_CHECK_API_KEY" in body["fact_checkers"][0]["detail"]
    # And not counted among the search engines, where it would read as a fourth one.
    assert [p["provider"] for p in body["providers"]] == ["tavily"]


async def test_a_dead_database_is_a_200_with_the_search_results_intact(
    client: AsyncClient, checking: Settings
) -> None:
    """One fan-out failing must not empty the other, and ``failed`` must not read as
    ``skipped``: a deployment reading the latter would go looking for a key it has.
    """
    database = factcheck_bench.Fake(
        error=FactCheckError("google is down", provider="google")
    )

    page = found("https://bbc.co.uk/news/1", snippet=WIRE)

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[page])}),
        factcheck_bench.bench(database),
    ):
        response = await research(client, claims=[CLAIM])

    assert response.status_code == 200
    body = response.json()
    assert [s["domain"] for s in body["claims"][0]["sources"]] == ["bbc.co.uk"]
    assert body["searched"] is True
    assert body["claims"][0]["fact_checks"] == []
    assert body["fact_checked"] is False
    assert body["fact_checkers"][0]["status"] == "failed"
    assert body["fact_checkers"][0]["code"] == "fact_check_error"


async def test_the_fact_check_key_never_reaches_the_response_body(
    client: AsyncClient, configure: Callable[..., Settings]
) -> None:
    """Checked against the whole serialised body, not the field expected to carry it."""
    key = "AIzaSy-fact-check-0123456789"
    configure(
        SEARCH_PROVIDERS=[SearchProvider.TAVILY],
        GOOGLE_FACT_CHECK_API_KEY=SecretStr(key),
    )
    leaky = factcheck_bench.Fake(
        error=FactCheckError(f"403 unauthorized for key={key}", provider="google")
    )

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(leaky),
    ):
        response = await research(client, claims=[CLAIM])

    assert response.status_code == 200
    assert key not in response.text
    assert "***" in response.json()["fact_checkers"][0]["detail"]


async def test_each_claim_keeps_its_own_fact_checks(
    client: AsyncClient, checking: Settings
) -> None:
    """Aligned by position through two independent fan-outs and one serialisation.

    A shuffle anywhere along that path attaches a real published verdict to the wrong
    claim: genuine text, fabricated relevance, and nothing in the body to reveal it.
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
        response = await research(client, claims=[CLAIM, other])

    claims = response.json()["claims"]
    assert [c["fact_checks"][0]["claim"]["text"] for c in claims] == [CLAIM, other]


async def test_the_claims_looked_up_are_reported_on_the_outcome(
    client: AsyncClient, checking: Settings
) -> None:
    """``fact_checkers[].queries`` is the audit trail, and the only thing that says
    which claims a partial answer covered.
    """
    other = "Inflation was 2.8% in March 2026."

    with (
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(factcheck_bench.Fake(results=[])),
    ):
        response = await research(client, claims=[CLAIM, other])

    outcome = response.json()["fact_checkers"][0]
    assert outcome["provider"] == "google"
    assert outcome["queries"] == [CLAIM, other]
    assert outcome["status"] == "searched"
    assert outcome["results"] == 0


async def test_an_unfit_claim_is_never_looked_up_either(
    client: AsyncClient, checking: Settings
) -> None:
    """The exclusions cover both fan-outs, or the fact-check section of a response would
    describe claims the sources section does not.
    """
    database = factcheck_bench.Fake(results=[])

    with (
        extractor_bench(StubClaimExtractor()),
        bench({SearchProvider.TAVILY: Fake("tavily", results=[])}),
        factcheck_bench.bench(database),
    ):
        response = await research(client, text=SAMPLE_TEXT)

    body = response.json()
    researched = [c["claim"] for c in body["claims"]]
    assert database.queries == researched
    assert body["skipped"]
    assert all(s["claim"] not in database.queries for s in body["skipped"])
