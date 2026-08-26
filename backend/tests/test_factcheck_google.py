"""The Google Fact Check Tools client: what it sends, and what it makes of the answer.

``GoogleFactCheckClient.parse`` is public so it can be exercised without a network, and
the bodies below *are* the specification the client was written to: the v1alpha1
``claims:search`` reference, field by field. If Google changes shape, the assertion that
fails should be the one naming the field that moved.

Three properties of that contract drive most of what follows, and each has a test whose
only job is to hold the line on it:

* **Nothing is required.** Not ``text``, not ``claimReview``, not ``publisher``, not even
  ``url``. So the parser cannot index into a record; it has to decide whether enough
  arrived to be worth reporting, and say so by dropping the record rather than by filling
  the gap with something plausible.
* **``textualRating`` has no enum.** Its entire documentation is one sentence and an
  example. Anything treating it as a closed set would be wrong about the field, so the
  client stores the string and reads nothing into it. Reading is
  :mod:`app.research.reviews`' job and is tested there.
* **``claim.text`` is Google's record of the claim, not the query.** A response about a
  neighbouring claim is a valid response, so the database's wording has to survive to the
  caller — otherwise nothing downstream can tell the two apart.

The requests are driven through :class:`httpx.MockTransport` by the same private-attribute
assignment :mod:`tests.test_provider_http` uses, and for the same reason: a ``transport``
parameter on the production client would exist only for tests.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ConfigurationError, FactCheckError
from app.domain import Stance
from app.factcheck.google import MAX_QUERY_CHARS, GoogleFactCheckClient

#: Fixed reference instant. Every date in these tests is judged against it, which is the
#: whole reason ``now`` is a parameter rather than a clock read.
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

KEY = "fc-secret-key-value"


@pytest.fixture
def settings() -> Settings:
    """Settings with the fact-check key set, so the client can be constructed."""
    return Settings(_env_file=None, GOOGLE_FACT_CHECK_API_KEY=KEY)


@pytest.fixture
def client(settings: Settings) -> GoogleFactCheckClient:
    return GoogleFactCheckClient(settings)


def wire(
    client: GoogleFactCheckClient, handler: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    """Point ``client`` at ``handler`` and return the list it records requests in."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client._client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return seen


def empty(_request: httpx.Request) -> httpx.Response:
    """The API's answer for a claim nobody has reviewed: no ``claims`` key at all."""
    return httpx.Response(200, json={})


def one(record: dict[str, object]) -> dict[str, object]:
    """A one-record body."""
    return {"claims": [record]}


def review(**fields: object) -> dict[str, object]:
    """A minimal complete ``ClaimReview``, field by field.

    Passing a field replaces it; passing ``None`` **removes** it, which is how these
    tests express a field Google omitted. Nothing here is marked required in the
    reference, so "absent" is a case every field has to have.
    """
    out: dict[str, object] = {
        "publisher": {"name": "Snopes", "site": "snopes.com"},
        "url": "https://www.snopes.com/fact-check/a-claim/",
        "textualRating": "False",
    }
    for key, value in fields.items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def reviewed(**overrides: object) -> dict[str, object]:
    """A minimal complete ``Claim``, with one default review on it."""
    reviews = overrides.pop("claimReview", None)
    record: dict[str, object] = {
        "text": "A claim.",
        "claimReview": reviews if reviews is not None else [review()],
    }
    record.update(overrides)
    return record


# ------------------------------------------------------------- what is sent ----


async def test_the_key_travels_in_a_header_and_never_in_the_url(
    client: GoogleFactCheckClient,
) -> None:
    """``x-goog-api-key``, not ``?key=``.

    Google documents the header as the recommended mechanism and warns that the query
    parameter exposes the key "to theft through URL scans". The URL is the string that
    ends up in proxy logs, in exception text and in this application's own error
    details, so this is the one assertion here that is about a real credential and not
    about a response shape.
    """
    seen = wire(client, empty)

    await client.lookup("who won", now=NOW)

    assert seen[0].headers["x-goog-api-key"] == KEY
    assert KEY not in str(seen[0].url)
    assert "key" not in dict(seen[0].url.params)


async def test_the_page_size_is_clamped_and_the_claim_is_sent_as_written(
    client: GoogleFactCheckClient,
) -> None:
    """The query is the claim, unmodified.

    Nothing is appended — no "fact check", no "true or false" — for the same reason the
    search fan-out appends nothing: a query this service steered would return records
    this service had chosen the shape of. The index is keyed on claim wording, so the
    claim as stated is already the best possible query.
    """
    seen = wire(client, empty)

    await client.lookup("The bridge cost 4.2 billion dollars.", max_results=99, now=NOW)

    params = seen[0].url.params
    assert params["query"] == "The bridge cost 4.2 billion dollars."
    assert str(params["pageSize"]) == "20"
    assert seen[0].method == "GET"
    # Google documents the request body as required-empty for this method.
    assert not seen[0].content


async def test_the_optional_filters_are_omitted_rather_than_neutralised(
    client: GoogleFactCheckClient,
) -> None:
    """No ``languageCode=""`` and no ``maxAgeDays=0``.

    Neither has a documented neutral value, so sending one would be a guess about how
    the API reads an empty filter — and a filter that silently matched nothing would
    look exactly like a claim nobody has reviewed.
    """
    seen = wire(client, empty)

    await client.lookup("who won", language="", max_age_days=0, now=NOW)

    params = dict(seen[0].url.params)
    assert "languageCode" not in params
    assert "maxAgeDays" not in params


async def test_the_filters_are_sent_when_they_are_set(
    client: GoogleFactCheckClient,
) -> None:
    seen = wire(client, empty)

    await client.lookup("who won", language="es", max_age_days=30, now=NOW)

    params = seen[0].url.params
    assert params["languageCode"] == "es"
    assert str(params["maxAgeDays"]) == "30"


async def test_an_over_long_query_is_cut_on_a_word_boundary(
    client: GoogleFactCheckClient,
) -> None:
    """Half a name is a different search term.

    ``/research`` takes caller-supplied claim strings, so "one sentence" is a convention
    rather than a guarantee. Truncating mid-token would search for ``Kamala Har`` and
    return records this dossier would then attribute to a claim nobody made.
    """
    seen = wire(client, empty)
    asked = " ".join(["Kamala Harris"] * 60)

    await client.lookup(asked, now=NOW)

    sent = str(seen[0].url.params["query"])
    assert len(sent) <= MAX_QUERY_CHARS
    # A prefix of what was asked, cut between two words: whatever survived is whole
    # words, so no request can ever go out asking about "Kamala Har".
    assert asked.startswith(sent)
    assert sent.split()[-1] in {"Kamala", "Harris"}
    # And it kept as much as it could. Asserted from the remainder rather than against a
    # hard-coded tail, because which of the two words the cut lands on is arithmetic
    # between MAX_QUERY_CHARS and the token lengths, and neither is this test's subject.
    dropped = asked[len(sent) :].split()
    assert dropped, "nothing was truncated, so this proves nothing about truncation"
    assert len(sent) + 1 + len(dropped[0]) > MAX_QUERY_CHARS


async def test_an_empty_query_raises_rather_than_returning_nothing(
    client: GoogleFactCheckClient,
) -> None:
    """The API requires ``query``, so this would be a 400.

    Returning ``[]`` would report "nobody has reviewed this claim" — a statement about
    the world — on the strength of a bug in the caller.
    """
    seen = wire(client, empty)

    with pytest.raises(FactCheckError):
        await client.lookup("   ", now=NOW)

    assert seen == []


async def test_an_empty_index_answer_is_an_empty_list(
    client: GoogleFactCheckClient,
) -> None:
    """End to end, because this is the commonest response the API gives.

    Most claims have never been formally reviewed. If the normal case raised, every
    dossier would carry a fact-check outcome of ``failed``.
    """
    wire(client, empty)

    assert await client.lookup("who won", now=NOW) == []


async def test_a_client_with_no_key_refuses_to_be_built() -> None:
    """A :class:`ConfigurationError`, which the lookup reports as ``skipped``.

    Distinct from a failure on purpose: a deployment without a fact-check key is a
    supported deployment, and the difference between "not configured" and "asked and got
    nothing back" is what the outcome record exists to carry.
    """
    with pytest.raises(ConfigurationError):
        GoogleFactCheckClient(Settings(_env_file=None))


# --------------------------------------------------------------- what parses ----

#: One record with two publishers on it, which is the shape the whole design is for.
BODY = {
    "claims": [
        {
            "text": "The bridge cost 4.2 billion dollars to build.",
            "claimant": "A Politician",
            "claimDate": "2024-03-11T00:00:00Z",
            "claimReview": [
                {
                    "publisher": {"name": "PolitiFact", "site": "politifact.com"},
                    "url": "https://www.politifact.com/factchecks/2024/mar/15/bridge/",
                    "title": "The bridge did not cost that",
                    "reviewDate": "2024-03-15T09:30:00Z",
                    "textualRating": "Mostly False",
                    "languageCode": "en",
                },
                {
                    "publisher": {"name": "FactCheck.org", "site": "factcheck.org"},
                    "url": "https://www.factcheck.org/2024/03/bridge-cost/",
                    "title": "Bridge cost claim",
                    "reviewDate": "2024-03-18T00:00:00Z",
                    "textualRating": "False",
                    "languageCode": "en",
                },
            ],
        }
    ],
    "nextPageToken": "CAoQAQ",
}


def test_every_field_the_reference_documents_arrives(
    client: GoogleFactCheckClient,
) -> None:
    records = client.parse(BODY, now=NOW)

    assert len(records) == 1
    found = records[0]
    assert found.text == "The bridge cost 4.2 billion dollars to build."
    assert found.claimant == "A Politician"
    assert found.claimed_at == datetime(2024, 3, 11, tzinfo=UTC)
    assert found.date_text == "2024-03-11T00:00:00Z"

    first, second = found.reviews
    assert first.publisher == "PolitiFact"
    assert first.site == "politifact.com"
    assert first.url == "https://www.politifact.com/factchecks/2024/mar/15/bridge/"
    assert first.title == "The bridge did not cost that"
    assert first.rating == "Mostly False"
    assert first.language == "en"
    assert first.reviewed_at == datetime(2024, 3, 15, 9, 30, tzinfo=UTC)
    assert first.date_text == "2024-03-15T09:30:00Z"
    assert second.publisher == "FactCheck.org"
    assert second.rating == "False"
    assert second.reviewed_at == datetime(2024, 3, 18, tzinfo=UTC)


def test_the_reviews_keep_the_order_google_returned_them_in(
    client: GoogleFactCheckClient,
) -> None:
    """Not sorted by date, by rating, or by anything else.

    Reordering would be this client asserting a precedence among publishers, and the
    obvious rule — newest first — would put a syndicated aggregator above the newsroom
    that did the reporting whenever the aggregator republished later.
    """
    assert [r.publisher for r in client.parse(BODY, now=NOW)[0].reviews] == [
        "PolitiFact",
        "FactCheck.org",
    ]


def test_the_client_reads_no_stance_from_a_rating(
    client: GoogleFactCheckClient,
) -> None:
    """The rating survives verbatim and is not interpreted here.

    "Mostly False" is a phrase :mod:`app.research.reviews` maps confidently, so a client
    that quietly did the mapping would look correct in every other test in this file.
    That is why the *absence* is asserted: interpretation is a judgement, the wire layer
    is the one place not allowed to make judgements, and the honest place for the reading
    to happen is the reviewable table a response can be audited against.
    """
    reviews = client.parse(BODY, now=NOW)[0].reviews

    assert [r.rating for r in reviews] == ["Mostly False", "False"]
    assert {r.stance for r in reviews} == {Stance.UNRECOGNISED}
    assert {r.stance_from for r in reviews} == {""}


def test_the_databases_wording_of_the_claim_is_kept_not_the_query(
    client: GoogleFactCheckClient,
) -> None:
    """``text`` is Google's record of the claim, whatever was searched for.

    This is the field that stops a fact check of a neighbouring claim being read as a
    ruling on the caller's. Substituting the query — which would look tidier, and is what
    a reader half expects — would delete the only evidence that the two differ.
    """
    body = one(reviewed(text="The tunnel cost 4.2 billion dollars to build."))

    assert (
        client.parse(body, now=NOW)[0].text
        == "The tunnel cost 4.2 billion dollars to build."
    )


def test_an_absent_claims_key_is_an_empty_answer_not_an_error(
    client: GoogleFactCheckClient,
) -> None:
    """Google omits ``claims`` entirely when nothing matched."""
    assert client.parse({}, now=NOW) == []
    assert client.parse({"nextPageToken": ""}, now=NOW) == []
    assert client.parse({"claims": []}, now=NOW) == []


@pytest.mark.parametrize("payload", [[], "claims", 7, None])
def test_a_body_that_is_not_an_object_is_a_provider_error(
    client: GoogleFactCheckClient, payload: object
) -> None:
    with pytest.raises(FactCheckError):
        client.parse(payload, now=NOW)


def test_a_non_array_claims_is_a_provider_error(
    client: GoogleFactCheckClient,
) -> None:
    """Not silently coerced.

    ``{"claims": {...}}`` would iterate as its keys, and the parser would then report
    zero records for a body that had one in it — an empty fact-check section produced by
    a shape change rather than by the world.
    """
    with pytest.raises(FactCheckError):
        client.parse({"claims": {"text": "x"}}, now=NOW)


def test_a_record_with_no_review_is_dropped(client: GoogleFactCheckClient) -> None:
    """A claim nobody reviewed carries no verdict, so it is not a fact check.

    Google returns these: the index holds the claim and the ``claimReview`` array is
    empty or absent. Reporting one would put an entry in ``fact_checks`` that says a
    verdict exists and cannot show one, and a reader counting entries would read it as
    coverage.
    """
    body = {
        "claims": [
            {"text": "Reviewed by nobody.", "claimReview": []},
            {"text": "Also reviewed by nobody."},
            reviewed(text="Reviewed."),
        ]
    }

    records = client.parse(body, now=NOW)

    assert [r.text for r in records] == ["Reviewed."]


def test_a_record_with_no_text_is_dropped(client: GoogleFactCheckClient) -> None:
    """Without the database's wording there is nothing to match the claim against.

    :func:`app.research.reviews.select` would have nothing to score and a reader would
    have nothing to compare their own claim to, so the review's relevance could neither
    be judged nor shown.
    """
    body = {"claims": [reviewed(text=""), reviewed(text="Reviewed.")]}

    records = client.parse(body, now=NOW)

    assert [r.text for r in records] == ["Reviewed."]


def test_a_body_whose_every_record_is_unreadable_raises(
    client: GoogleFactCheckClient,
) -> None:
    """The distinction ``ensure_parsed`` exists to draw.

    Records arriving and none surviving means this code stopped understanding the
    response — ``claimReview`` renamed, ``text`` renamed — and the alternative to raising
    is reporting "no fact-checker has ruled on this claim", which is the one outcome that
    is both wrong and invisible. Every claim in a review index has at least one review,
    so there is no legitimate body this rejects.
    """
    with pytest.raises(FactCheckError):
        client.parse({"claims": [{"text": ""}, {"claimReview": []}]}, now=NOW)


def test_a_review_with_no_url_is_dropped_and_the_rest_survive(
    client: GoogleFactCheckClient,
) -> None:
    """The URL is the receipt.

    A rating with no link is an assertion this service cannot substantiate and a reader
    cannot check — exactly the unearned authority the response is built to avoid.
    Dropping the review rather than the whole record keeps the publisher that did link.
    """
    body = one(
        {
            "text": "A claim.",
            "claimReview": [
                {
                    "publisher": {"name": "Nowhere", "site": "nowhere.example"},
                    "textualRating": "False",
                },
                review(textualRating="True"),
            ],
        }
    )

    assert [r.publisher for r in client.parse(body, now=NOW)[0].reviews] == ["Snopes"]


def test_a_missing_publisher_name_is_never_filled_from_the_site(
    client: GoogleFactCheckClient,
) -> None:
    """"Who reviewed it" and "what host the URL points at" are different assertions.

    Google documents ``site`` as derived from the review URL — it is not something the
    publisher said — so substituting it would attribute a verdict to an organisation on
    the strength of a hostname.
    """
    body = one(
        reviewed(
            claimReview=[
                review(publisher={"site": "somewhere.example"}, url="https://somewhere.example/check")
            ]
        )
    )

    found = client.parse(body, now=NOW)[0].reviews[0]

    assert found.publisher == ""
    assert found.site == "somewhere.example"


def test_an_absent_rating_stays_empty(client: GoogleFactCheckClient) -> None:
    """Not turned into a stance, and not a reason to drop the review.

    A review Google returned with no ``textualRating`` still has a URL, a publisher and a
    date, all of which are worth reporting. What it does not have is a verdict, and
    writing ``"unrated"`` into the publisher's own field would be this service putting
    words in their mouth.
    """
    body = one(reviewed(claimReview=[review(textualRating=None)]))

    found = client.parse(body, now=NOW)[0].reviews[0]

    assert found.rating == ""
    assert found.url == "https://www.snopes.com/fact-check/a-claim/"


def test_an_unparseable_date_keeps_the_string_it_could_not_read(
    client: GoogleFactCheckClient,
) -> None:
    """A date that would not parse is still information about the review.

    Dropping ``date_text`` alongside ``reviewed_at`` would hide the parser gap that
    caused the ``None``, and the response would then look like a review Google gave no
    date for at all.
    """
    body = one(
        reviewed(
            claimDate="sometime in March",
            claimReview=[review(reviewDate="last Tuesday")],
        )
    )

    found = client.parse(body, now=NOW)[0]

    assert found.claimed_at is None
    assert found.date_text == "sometime in March"
    assert found.reviews[0].reviewed_at is None
    assert found.reviews[0].date_text == "last Tuesday"


def test_nanosecond_precision_parses(client: GoogleFactCheckClient) -> None:
    """Google documents "up to nine fractional digits"; Python's limit is six.

    ``datetime.fromisoformat`` truncates rather than raising, which is the behaviour this
    relies on. A rejected timestamp would silently null out the date on every review from
    a publisher whose CMS emits nanoseconds.
    """
    body = one(reviewed(claimReview=[review(reviewDate="2024-03-15T09:30:00.123456789Z")]))

    assert client.parse(body, now=NOW)[0].reviews[0].reviewed_at == datetime(
        2024, 3, 15, 9, 30, 0, 123456, tzinfo=UTC
    )


def test_a_review_dated_in_the_future_is_not_dated(
    client: GoogleFactCheckClient,
) -> None:
    """A date after ``now`` cannot be a publication date.

    It comes back as ``None`` with the string kept rather than trusted: a review dated
    next year sorts to the top of any date-ordered reading of the response and would look
    like the most current word on the claim.
    """
    body = one(reviewed(claimReview=[review(reviewDate="2031-01-01T00:00:00Z")]))

    found = client.parse(body, now=NOW)[0].reviews[0]

    assert found.reviewed_at is None
    assert found.date_text == "2031-01-01T00:00:00Z"


def test_an_old_claim_date_is_kept(client: GoogleFactCheckClient) -> None:
    """A 1998 claim date is ordinary, not implausible.

    :func:`app.providers.dates.resolve` would reject it — its floor is written for web
    publication dates — which is why this parser uses
    :func:`app.providers.dates.parse_absolute` and applies only the future check. An old
    claim resurfacing is the commonest thing a fact-check lookup finds.
    """
    body = one(reviewed(claimDate="1998-06-01T00:00:00Z"))

    assert client.parse(body, now=NOW)[0].claimed_at == datetime(1998, 6, 1, tzinfo=UTC)
