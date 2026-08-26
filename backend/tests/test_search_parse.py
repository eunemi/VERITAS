"""Provider response parsing, against recorded response shapes.

Every client's ``parse`` is public so that it can be exercised here without a
network. That matters more than usual for this package: the three clients were
written against vendor documentation, and for :mod:`app.search.serper` against
third-party examples of it, so these fixtures *are* the specification this code was
built to. If a vendor changes shape, the assertion that fails should be the one
naming the field that moved.

The bodies below are trimmed to the fields the parsers read, plus the ones they
must be seen to ignore — Brave's crawl timestamps, Serper's ``peopleAlsoAsk``. The
ignored fields are the point of several of these tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.core.errors import SearchError
from app.domain import DateBasis
from app.search.brave import BraveClient, clamp_query
from app.search.serper import SerperClient
from app.search.tavily import CHUNK_SEPARATOR, TavilyClient

#: Fixed reference instant. Every relative age in these tests resolves against it,
#: which is the whole reason `now` is a parameter rather than a clock read.
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


@pytest.fixture
def settings() -> Settings:
    """Settings with every search key set, so any client can be constructed."""
    return Settings(
        _env_file=None,
        TAVILY_API_KEY="tvly-secret-key-value",
        BRAVE_API_KEY="brave-secret-key-value",
        SERPER_API_KEY="serper-secret-key-value",
    )


# ------------------------------------------------------------------- tavily ----

TAVILY_BODY = {
    "query": "messi world cup",
    "results": [
        {
            "title": "Lionel Messi - Wikipedia",
            "url": "https://en.wikipedia.org/wiki/Lionel_Messi",
            # Two reranked chunks, joined the way Tavily documents.
            "content": (
                "Messi was born on 24 June 1987 in Rosario."
                f"{CHUNK_SEPARATOR}"
                "He captained Argentina to the 2022 World Cup title."
            ),
            "score": 0.81025,
            "raw_content": None,
        },
        {
            "title": "Argentina win the World Cup",
            "url": "https://www.bbc.co.uk/sport/football/63997150",
            "content": "Argentina beat France on penalties in Qatar.",
            "score": 0.7,
        },
    ],
    "response_time": 1.09,
}


def test_tavily_parses_documented_body(settings: Settings) -> None:
    results = TavilyClient(settings).parse(TAVILY_BODY, now=NOW)

    assert [r.url for r in results] == [
        "https://en.wikipedia.org/wiki/Lionel_Messi",
        "https://www.bbc.co.uk/sport/football/63997150",
    ]
    assert results[0].title == "Lionel Messi - Wikipedia"
    assert results[0].score == pytest.approx(0.81025)


def test_tavily_keeps_the_chunk_separator_verbatim(settings: Settings) -> None:
    """The elision must survive parsing, because evidence selection needs to see it.

    If a client stripped or normalised it, :mod:`app.research.evidence` could not
    tell where one chunk ends and the next begins, and a quote spanning the join
    would read as continuous prose the publisher never wrote.
    """
    results = TavilyClient(settings).parse(TAVILY_BODY, now=NOW)

    assert CHUNK_SEPARATOR in results[0].snippet
    assert results[0].snippet == TAVILY_BODY["results"][0]["content"]  # type: ignore[index]


def test_tavily_general_topic_results_have_no_date(settings: Settings) -> None:
    """`published_date` is news-only, and its absence must not become a guess."""
    results = TavilyClient(settings).parse(TAVILY_BODY, now=NOW)

    assert all(r.published_at is None for r in results)
    assert all(r.date_basis is None for r in results)
    assert all(r.date_text is None for r in results)


def test_tavily_reads_a_news_published_date(settings: Settings) -> None:
    body = {
        "results": [
            {
                "title": "Rates held",
                "url": "https://example.com/news",
                "content": "The committee voted to hold.",
                "published_date": "Tue, 11 Mar 2025 17:00:00 GMT",
            }
        ]
    }

    (result,) = TavilyClient(settings).parse(body, now=NOW)

    assert result.published_at == datetime(2025, 3, 11, 17, 0, tzinfo=UTC)
    assert result.date_basis is DateBasis.PROVIDER
    assert result.date_text == "Tue, 11 Mar 2025 17:00:00 GMT"


def test_tavily_keeps_an_unparseable_date_as_text(settings: Settings) -> None:
    """No date, but the string is kept: a parser gap has to stay diagnosable."""
    body = {
        "results": [
            {
                "title": "Odd",
                "url": "https://example.com/odd",
                "content": "text",
                "published_date": "last Michaelmas",
            }
        ]
    }

    (result,) = TavilyClient(settings).parse(body, now=NOW)

    assert result.published_at is None
    assert result.date_basis is None
    assert result.date_text == "last Michaelmas"


def test_tavily_ignores_a_boolean_score(settings: Settings) -> None:
    """`True` is an `int` in Python; it must not become a relevance of 1.0."""
    body = {
        "results": [
            {
                "title": "T",
                "url": "https://example.com/",
                "content": "c",
                "score": True,
            }
        ]
    }

    (result,) = TavilyClient(settings).parse(body, now=NOW)

    assert result.score is None


def test_tavily_skips_an_item_with_no_url_but_keeps_the_rest(
    settings: Settings,
) -> None:
    body = {
        "results": [
            {"title": "No URL", "content": "c"},
            {"title": "Fine", "url": "https://example.com/fine", "content": "c"},
        ]
    }

    results = TavilyClient(settings).parse(body, now=NOW)

    assert [r.url for r in results] == ["https://example.com/fine"]


def test_tavily_empty_results_is_an_answer_not_an_error(settings: Settings) -> None:
    assert TavilyClient(settings).parse({"results": []}, now=NOW) == []


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param([], id="array-instead-of-object"),
        pytest.param({"data": {"results": []}}, id="results-nested-deeper"),
        pytest.param({"results": {"0": {}}}, id="results-not-an-array"),
    ],
)
def test_tavily_rejects_a_changed_envelope(settings: Settings, payload: object) -> None:
    """A schema change must raise, never read as "found nothing"."""
    with pytest.raises(SearchError):
        TavilyClient(settings).parse(payload, now=NOW)


def test_tavily_rejects_items_it_could_not_parse_at_all(settings: Settings) -> None:
    """Items in, none out: a renamed URL field is a broken parser, not an empty index."""
    body = {"results": [{"title": "a", "link": "https://example.com/a"}] * 3}

    with pytest.raises(SearchError, match="none could be parsed"):
        TavilyClient(settings).parse(body, now=NOW)


# -------------------------------------------------------------------- brave ----

BRAVE_BODY = {
    "type": "search",
    "query": {"original": "budget deficit 2019"},
    "web": {
        "type": "search",
        "results": [
            {
                "title": "Deficit rose in 2019",
                "url": "https://www.reuters.com/article/deficit",
                "description": "The deficit rose to 4.6% of GDP.",
                "article": {"date": "2019-03-04T00:00:00"},
                # Both of these are present and both must be ignored: they say
                # when Brave crawled the page, not when anyone published it.
                "page_age": "2024-11-02T08:15:00",
                "page_fetched": "2026-08-22T23:00:00",
                "fetched_content_timestamp": 1755000000,
                "meta_url": {"hostname": "www.reuters.com"},
            }
        ],
    },
}


def test_brave_prefers_the_article_date_over_page_age(settings: Settings) -> None:
    """`article.date` is the only field Brave documents as a publication date."""
    (result,) = BraveClient(settings).parse(BRAVE_BODY, now=NOW)

    assert result.published_at == datetime(2019, 3, 4, tzinfo=UTC)
    assert result.date_basis is DateBasis.PROVIDER
    assert result.date_text == "2019-03-04T00:00:00"


def test_brave_reads_the_hostname_the_provider_sent(settings: Settings) -> None:
    (result,) = BraveClient(settings).parse(BRAVE_BODY, now=NOW)

    assert result.source == "www.reuters.com"


def test_brave_page_age_alone_is_a_modification_date(settings: Settings) -> None:
    body = {
        "web": {
            "results": [
                {
                    "url": "https://example.com/a",
                    "title": "A",
                    "description": "d",
                    "page_age": "2024-11-02T08:15:00",
                    "page_fetched": "2026-08-22T23:00:00",
                }
            ]
        }
    }

    (result,) = BraveClient(settings).parse(body, now=NOW)

    assert result.published_at == datetime(2024, 11, 2, 8, 15, tzinfo=UTC)
    assert result.date_basis is DateBasis.PROVIDER_MODIFIED


def test_brave_resolves_a_relative_age_against_now(settings: Settings) -> None:
    body = {
        "web": {
            "results": [
                {
                    "url": "https://example.com/a",
                    "title": "A",
                    "description": "d",
                    "age": "2 days ago",
                }
            ]
        }
    }

    (result,) = BraveClient(settings).parse(body, now=NOW)

    assert result.published_at == datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    assert result.date_basis is DateBasis.PROVIDER_RELATIVE
    assert result.date_text == "2 days ago"


def test_brave_never_dates_a_result_from_a_crawl_timestamp(
    settings: Settings,
) -> None:
    """The most-often-present fields are the ones that must never be read.

    A result whose only timestamps are crawl times is undated. Reading one would
    date every stale page in the index to whenever Brave last visited it.
    """
    body = {
        "web": {
            "results": [
                {
                    "url": "https://example.com/old",
                    "title": "Old",
                    "description": "d",
                    "page_fetched": "2026-08-22T23:00:00",
                    "fetched_content_timestamp": 1755000000,
                }
            ]
        }
    }

    (result,) = BraveClient(settings).parse(body, now=NOW)

    assert result.published_at is None
    assert result.date_basis is None
    assert result.date_text is None


def test_brave_does_not_fall_back_from_an_unparseable_stronger_field(
    settings: Settings,
) -> None:
    """A failed read of `article.date` must not silently become `age`.

    Falling through would label a relative crawl-adjacent age as though Brave had
    reported it as the publication date of the article.
    """
    body = {
        "web": {
            "results": [
                {
                    "url": "https://example.com/a",
                    "title": "A",
                    "description": "d",
                    "article": {"date": "sometime in spring"},
                    "age": "2 days ago",
                }
            ]
        }
    }

    (result,) = BraveClient(settings).parse(body, now=NOW)

    assert result.published_at is None
    assert result.date_text == "sometime in spring"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"type": "search"}, id="web-absent"),
        pytest.param({"web": None}, id="web-null"),
        pytest.param({"web": {"results": None}}, id="results-null"),
        pytest.param({"web": {"results": []}}, id="results-empty"),
    ],
)
def test_brave_no_web_results_is_an_empty_answer(
    settings: Settings, payload: object
) -> None:
    """Documented and legal: Brave searched, and had nothing to say."""
    assert BraveClient(settings).parse(payload, now=NOW) == []


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("nope", id="not-an-object"),
        pytest.param({"web": []}, id="web-not-an-object"),
        pytest.param({"web": {"results": {}}}, id="results-not-an-array"),
    ],
)
def test_brave_rejects_a_changed_envelope(settings: Settings, payload: object) -> None:
    with pytest.raises(SearchError):
        BraveClient(settings).parse(payload, now=NOW)


def test_brave_does_not_keep_extra_snippets(settings: Settings) -> None:
    """Joining them would invent adjacencies that do not exist on the page."""
    body = {
        "web": {
            "results": [
                {
                    "url": "https://example.com/a",
                    "title": "A",
                    "description": "The first passage.",
                    "extra_snippets": ["A later passage.", "Another one."],
                }
            ]
        }
    }

    (result,) = BraveClient(settings).parse(body, now=NOW)

    assert result.snippet == "The first passage."


def test_clamp_query_cuts_on_a_word_boundary() -> None:
    """Half a name is a different search term."""
    assert clamp_query("Kamala Harris deficit claim", chars=13) == "Kamala Harris"


def test_clamp_query_enforces_the_word_limit() -> None:
    clamped = clamp_query(" ".join(["word"] * 80))

    assert len(clamped.split()) == 50


def test_clamp_query_leaves_a_short_query_alone() -> None:
    assert clamp_query("did the deficit rise in 2019") == (
        "did the deficit rise in 2019"
    )


# ------------------------------------------------------------------- serper ----

SERPER_BODY = {
    "searchParameters": {"q": "apple inc revenue", "type": "search"},
    # Neither of these is a source, and neither may be quoted as one.
    "knowledgeGraph": {
        "title": "Apple",
        "description": "Apple Inc. is an American multinational.",
    },
    "organic": [
        {
            "title": "Apple Inc. - Wikipedia",
            "link": "https://en.wikipedia.org/wiki/Apple_Inc.",
            "snippet": "Apple reported revenue of $394.3 billion in 2022.",
            "position": 1,
        },
        {
            "title": "Apple posts record results",
            "link": "https://www.apple.com/newsroom/2022/10/results/",
            "snippet": "The company announced record quarterly revenue.",
            "date": "Mar 10, 2022",
            "position": 2,
        },
    ],
    "peopleAlsoAsk": [
        {
            "question": "How much does Apple make?",
            "snippet": "Apple made a lot.",
            "link": "https://example.com/paa",
        }
    ],
    "relatedSearches": [{"query": "apple revenue 2023"}],
}


def test_serper_parses_organic_results(settings: Settings) -> None:
    results = SerperClient(settings).parse(SERPER_BODY, now=NOW)

    assert [r.url for r in results] == [
        "https://en.wikipedia.org/wiki/Apple_Inc.",
        "https://www.apple.com/newsroom/2022/10/results/",
    ]
    assert results[0].snippet == "Apple reported revenue of $394.3 billion in 2022."


def test_serper_ignores_everything_that_is_not_a_source(settings: Settings) -> None:
    """`knowledgeGraph` and `peopleAlsoAsk` are Google's prose, not a publisher's."""
    results = SerperClient(settings).parse(SERPER_BODY, now=NOW)

    assert len(results) == 2
    assert all("paa" not in r.url for r in results)


def test_serper_reads_its_display_date(settings: Settings) -> None:
    results = SerperClient(settings).parse(SERPER_BODY, now=NOW)

    assert results[1].published_at == datetime(2022, 3, 10, tzinfo=UTC)
    assert results[1].date_basis is DateBasis.PROVIDER
    assert results[1].date_text == "Mar 10, 2022"
    assert results[0].published_at is None


def test_serper_assigns_no_score(settings: Settings) -> None:
    """`position` is a rank: as a score, a low number would read as a weak result."""
    results = SerperClient(settings).parse(SERPER_BODY, now=NOW)

    assert all(r.score is None for r in results)


def test_serper_no_organic_block_is_an_empty_answer(settings: Settings) -> None:
    assert SerperClient(settings).parse({"searchParameters": {}}, now=NOW) == []


def test_serper_rejects_a_renamed_url_field(settings: Settings) -> None:
    """The failure mode this provider is most likely to have, given its docs.

    Serper's contract could not be verified against first-party documentation, so
    this is the assertion that makes shipping it defensible: if ``link`` is not what
    the field is called, the client fails loudly instead of reporting that Google
    found nothing.
    """
    body = {"organic": [{"title": "a", "url": "https://example.com/a"}] * 5}

    with pytest.raises(SearchError, match="none could be parsed"):
        SerperClient(settings).parse(body, now=NOW)
