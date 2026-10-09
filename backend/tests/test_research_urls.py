"""URL identity and publisher identity — the two questions independence rests on.

Both are asymmetric, and in *opposite* directions, which is why they get separate
sections and separate standards of proof.

**Same page?** A wrong yes merges two documents and deletes a source a provider
actually returned — fabrication by omission. So most of the first section below is
must-NOT-merge cases: two videos, two paginated pages, two search results, a
case-sensitive path. Each is a URL pair that a slightly more aggressive normaliser
would collapse, and each collapse would silently remove a row.

**Whose page?** A wrong answer here miscounts independence, and the dangerous
direction reverses: an AMP cache URL left wrapped attributes one publisher's story to
two, so corroboration reads stronger than the evidence supports. The second section is
therefore mostly about *not* over-counting publishers.

The third section is the date read out of a path. It is the weakest basis in the
system and the only one this service derives itself, so the tests are about what it
refuses: a month with no day, a future date, an id that resembles one.

:mod:`app.research.suffixes` is knowingly incomplete, and the tests reflect the
argument in its docstring rather than pretending otherwise: an omission understates
independence, which is safe, and only a false entry overstates it. So this file checks
the shape of the answer for hosts the table covers, and checks that an *uncovered* host
fails in the conservative direction.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.research import urls
from app.research.suffixes import MULTI_TENANT, SUFFIXES

NOW = datetime(2026, 3, 14, 9, 30, tzinfo=UTC)


# =============================================================== same document ====


@pytest.mark.parametrize(
    ("spelling", "expected"),
    [
        # Scheme, case, trailing dot, default port, fragment.
        ("http://bbc.co.uk/news/1", "https://bbc.co.uk/news/1"),
        ("https://BBC.CO.UK/news/1", "https://bbc.co.uk/news/1"),
        ("https://bbc.co.uk./news/1", "https://bbc.co.uk/news/1"),
        ("https://bbc.co.uk:443/news/1", "https://bbc.co.uk/news/1"),
        ("http://bbc.co.uk:80/news/1", "https://bbc.co.uk/news/1"),
        ("https://bbc.co.uk/news/1#headline", "https://bbc.co.uk/news/1"),
        # Rendering prefixes: one article, several front doors.
        ("https://www.bbc.co.uk/news/1", "https://bbc.co.uk/news/1"),
        ("https://m.bbc.co.uk/news/1", "https://bbc.co.uk/news/1"),
        ("https://amp.bbc.co.uk/news/1", "https://bbc.co.uk/news/1"),
        ("https://mobile.bbc.co.uk/news/1", "https://bbc.co.uk/news/1"),
        # Trailing slash and an /amp leaf.
        ("https://bbc.co.uk/news/1/", "https://bbc.co.uk/news/1"),
        ("https://bbc.co.uk/news/1/amp", "https://bbc.co.uk/news/1"),
        ("https://bbc.co.uk/news/1/amp/", "https://bbc.co.uk/news/1"),
        # Dot segments and escaping, both RFC 3986 equivalences.
        ("https://bbc.co.uk/news/./1", "https://bbc.co.uk/news/1"),
        ("https://bbc.co.uk/sport/../news/1", "https://bbc.co.uk/news/1"),
        ("https://bbc.co.uk/news/%7Efoo", "https://bbc.co.uk/news/~foo"),
        ("https://bbc.co.uk/news/~foo", "https://bbc.co.uk/news/~foo"),
        # Tracking parameters, by name and by prefix.
        ("https://bbc.co.uk/news/1?utm_source=twitter", "https://bbc.co.uk/news/1"),
        ("https://bbc.co.uk/news/1?fbclid=abc123", "https://bbc.co.uk/news/1"),
        ("https://bbc.co.uk/news/1?at_medium=social", "https://bbc.co.uk/news/1"),
        ("https://bbc.co.uk/news/1?utm_id=9&_ga=2.1", "https://bbc.co.uk/news/1"),
        # Parameter order does not select a document.
        ("https://bbc.co.uk/news?b=2&a=1", "https://bbc.co.uk/news?a=1&b=2"),
        ("https://bbc.co.uk/news?a=1&b=2", "https://bbc.co.uk/news?a=1&b=2"),
        # A bare host is one identity.
        ("https://bbc.co.uk", "https://bbc.co.uk/"),
        ("https://bbc.co.uk/", "https://bbc.co.uk/"),
    ],
)
def test_one_document_has_one_identity(spelling: str, expected: str) -> None:
    """Every spelling that provably cannot change what a server sends."""
    assert urls.normalise(spelling) == expected


def test_the_amp_cache_url_of_a_page_is_that_page() -> None:
    """Left wrapped, this is a second publisher carrying the story.

    Its registrable domain would be ``ampproject.org``, so one BBC article would
    count as two independent sources — corroboration reading stronger than the
    evidence supports, which is the failure the whole service exists to avoid.
    """
    wrapped = "https://www-bbc-co-uk.cdn.ampproject.org/c/s/www.bbc.co.uk/news/1"

    assert urls.normalise(urls.unwrap(wrapped)) == "https://bbc.co.uk/news/1"
    assert (
        urls.registrable_domain(urls.host_of(urls.unwrap(wrapped)) or "") == "bbc.co.uk"
    )


def test_the_amp_host_encoding_is_decoded_when_the_path_is_absent() -> None:
    """A dot is one hyphen, a literal hyphen is two. Read left to right."""
    assert urls.unwrap("https://www-bbc-co-uk.cdn.ampproject.org/news/1").startswith(
        "https://www.bbc.co.uk/news/1"
    )
    assert urls.unwrap("https://a--b-com.cdn.ampproject.org/x").startswith(
        "https://a-b.com/x"
    )


def test_a_translate_proxy_url_is_the_page_it_proxies() -> None:
    """Same encoding, same problem: ``translate.goog`` is not a publisher."""
    proxied = "https://www-bbc-co-uk.translate.goog/news/1?_x_tr_sl=en&_x_tr_tl=fr"

    assert urls.normalise(urls.unwrap(proxied)) == "https://bbc.co.uk/news/1"


def test_unwrapping_is_idempotent_and_bounded() -> None:
    """A mirror of a mirror resolves; a cycle cannot hang the request path."""
    once = urls.unwrap(
        "https://www-bbc-co-uk.cdn.ampproject.org/c/s/www.bbc.co.uk/news/1"
    )

    assert urls.unwrap(once) == once


def test_an_unrecognised_url_is_returned_unchanged() -> None:
    """Guessing at a mirror would attribute a page to a publisher that never ran it."""
    for url in (
        "https://bbc.co.uk/news/1",
        "https://ampproject.org/about",
        "https://notahost.cdn.ampproject.org/",
        "mailto:tips@example.com",
    ):
        assert urls.unwrap(url) == url


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # The query selects the content. A blanket strip loses one of the two.
        ("https://youtube.com/watch?v=A", "https://youtube.com/watch?v=B"),
        ("https://example.com/articles?id=1", "https://example.com/articles?id=2"),
        ("https://example.com/list?page=1", "https://example.com/list?page=2"),
        (
            "https://example.com/search?q=rates",
            "https://example.com/search?q=inflation",
        ),
        ("https://example.com/story?p=100", "https://example.com/story?p=200"),
        # RFC 3986 makes paths case-sensitive, and some CMSes mean it.
        ("https://example.com/News/1", "https://example.com/news/1"),
        # A non-default port is a different service.
        ("https://example.com:8443/news/1", "https://example.com/news/1"),
        # A hashbang or a route selects content on older single-page sites.
        ("https://example.com/app#!/story/1", "https://example.com/app#!/story/2"),
        ("https://example.com/app#/story/1", "https://example.com/app#/story/2"),
        # Different subdomains that are not renderings.
        ("https://news.example.com/1", "https://blogs.example.com/1"),
        # A parameter that is absent from the deny-list on purpose.
        ("https://example.com/1?source=rss", "https://example.com/1?source=newsletter"),
    ],
)
def test_two_documents_keep_two_identities(left: str, right: str) -> None:
    """The must-not-merge set. Each pair is one an eager normaliser would collapse.

    Collapsing any of these deletes a result a provider returned, at the layer
    furthest from anyone who could report the loss.
    """
    assert urls.normalise(left) != urls.normalise(right)


def test_a_blank_valued_parameter_is_kept() -> None:
    """``?print`` is how some CMSes switch rendering, and the link has to still work."""
    assert (
        urls.normalise("https://example.com/1?print") == "https://example.com/1?print="
    )
    assert (
        urls.normalise("https://example.com/1?print=") == "https://example.com/1?print="
    )


def test_a_rendering_prefix_is_not_stripped_off_a_bare_domain() -> None:
    """``www.com`` is a domain. Stripping it would leave ``com``, which is not one."""
    assert urls.normalise("https://www.com/x") == "https://www.com/x"
    assert urls.normalise("https://m.co/x") == "https://m.co/x"


def test_normalisation_is_idempotent() -> None:
    """It runs on provider output, and the same page can arrive already normalised."""
    for url in (
        "https://www.bbc.co.uk/news/1/amp/?utm_source=x#top",
        "https://example.com:8443/News/./1?b=2&a=1",
        "https://example.com/app#!/story/1",
    ):
        once = urls.normalise(url)
        assert once is not None
        assert urls.normalise(once) == once


@pytest.mark.parametrize(
    "unusable",
    [
        "mailto:tips@example.com",
        "javascript:void(0)",
        "ftp://files.example.com/x",
        "data:text/html,hello",
        "not a url at all",
        "/relative/path",
        "https://",
        "",
    ],
)
def test_a_url_that_is_not_a_web_page_is_rejected(unusable: str) -> None:
    """``None`` is the signal to drop the result and count it as dropped.

    A source a reader cannot open cannot be checked, and inventing a host for it
    would put a publisher's name against a page that has none.
    """
    assert urls.normalise(unusable) is None
    assert urls.host_of(unusable) is None


def test_a_tracking_parameter_never_selects_content() -> None:
    """The membership rule for the deny-list, asserted rather than trusted.

    ``id``, ``p``, ``page``, ``v``, ``s``, ``q`` and ``cid`` look like tracking on
    some sites and are the article key on others. There is no way to tell from the
    URL, so they stay out: under-stripping leaves two visible rows for one page,
    over-stripping silently loses one of them.
    """
    for name in ("id", "p", "page", "v", "s", "q", "cid", "story", "article"):
        assert name not in urls.TRACKING_PARAMS


# =============================================================== which publisher ====


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        # The default rule needs no table at all.
        ("example.com", "example.com"),
        ("www.example.com", "example.com"),
        ("news.example.com", "example.com"),
        ("a.b.c.example.com", "example.com"),
        # Multi-label registry suffixes, which dot-counting gets wrong.
        ("bbc.co.uk", "bbc.co.uk"),
        ("www.bbc.co.uk", "bbc.co.uk"),
        ("news.bbc.co.uk", "bbc.co.uk"),
        ("theguardian.co.uk", "theguardian.co.uk"),
        ("abc.net.au", "abc.net.au"),
        ("www.abc.net.au", "abc.net.au"),
        ("nhk.or.jp", "nhk.or.jp"),
        ("news.com.au", "news.com.au"),
        ("gov.uk", "gov.uk"),
        ("hmrc.gov.uk", "hmrc.gov.uk"),
        # Multi-tenant hosts, where the subdomain *is* the publisher.
        ("alice.substack.com", "alice.substack.com"),
        ("bob.substack.com", "bob.substack.com"),
        ("someone.medium.com", "someone.medium.com"),
        ("author.wordpress.com", "author.wordpress.com"),
        ("project.github.io", "project.github.io"),
        ("site.blogspot.com", "site.blogspot.com"),
        # Longest match wins, so this is the author and not Blogger.
        ("site.blogspot.co.uk", "site.blogspot.co.uk"),
        # Case and a trailing dot are not publisher-distinguishing.
        ("WWW.BBC.CO.UK", "bbc.co.uk"),
        ("bbc.co.uk.", "bbc.co.uk"),
    ],
)
def test_the_publisher_is_named_correctly(host: str, expected: str) -> None:
    assert urls.registrable_domain(host) == expected


def test_two_authors_on_one_platform_are_two_publishers() -> None:
    """The whole reason :data:`~app.research.suffixes.MULTI_TENANT` exists.

    Collapsing these to ``substack.com`` would report two independent writers as one
    source. That is the conservative direction, but it is still wrong, and on a
    platform this large it is wrong often.
    """
    assert urls.registrable_domain("alice.substack.com") != urls.registrable_domain(
        "bob.substack.com"
    )


def test_two_sections_of_one_publisher_are_one_publisher() -> None:
    """The error that matters more: one masthead read as several sources."""
    assert (
        urls.registrable_domain("news.bbc.co.uk")
        == urls.registrable_domain("sport.bbc.co.uk")
        == urls.registrable_domain("www.bbc.co.uk")
        == "bbc.co.uk"
    )


@pytest.mark.parametrize(
    "degenerate",
    ["localhost", "192.168.0.1", "127.0.0.1", "::1", "2001:db8::1", "co.uk", ""],
)
def test_a_host_with_no_registrable_domain_is_returned_as_it_came(
    degenerate: str,
) -> None:
    """An IP literal has no publisher; ``co.uk`` has no label left to keep.

    Each is a real thing a search result can contain, and each is left intact so a
    caller can see what it got. Trimming them into something domain-shaped would
    invent a publisher; counting them as distinguishable from each other is the only
    honest reading available.
    """
    assert urls.registrable_domain(degenerate) == degenerate


def test_an_uncovered_multi_tenant_host_fails_conservatively() -> None:
    """The table is incomplete by design, so this pins which way an omission goes.

    A platform not in the table collapses its tenants onto one publisher, which
    *understates* independence. The opposite mistake — a false entry, splitting one
    masthead into several — is the one that would overstate it, so incompleteness is
    the acceptable failure and speculation is not.
    """
    assert "unknown-platform.example" not in SUFFIXES
    collapsed = {
        urls.registrable_domain("alice.unknown-platform.example"),
        urls.registrable_domain("bob.unknown-platform.example"),
    }

    assert collapsed == {"unknown-platform.example"}


def test_no_single_label_tld_is_listed() -> None:
    """The default rule already handles them, and a listed one would be inert bulk."""
    assert not [suffix for suffix in SUFFIXES if "." not in suffix]


def test_no_major_publisher_domain_is_in_the_suffix_table() -> None:
    """The one entry that would overstate independence, checked directly.

    List ``nytimes.com`` and ``www.nytimes.com`` becomes its own publisher, so one
    source reads as several. This is the mistake the table's rule exists to prevent.
    """
    for domain in (
        "nytimes.com",
        "bbc.co.uk",
        "theguardian.com",
        "reuters.com",
        "apnews.com",
        "washingtonpost.com",
    ):
        assert domain not in SUFFIXES
        assert urls.registrable_domain(f"www.{domain}") == domain


def test_the_multi_tenant_table_is_disjoint_from_nothing_it_should_overlap() -> None:
    """Every multi-tenant entry is itself a suffix, so the lookup finds it."""
    assert MULTI_TENANT <= SUFFIXES


def test_the_host_is_lower_cased_and_the_trailing_dot_removed() -> None:
    """A root-anchored host is the same host. Two spellings would be two publishers."""
    assert urls.host_of("https://BBC.CO.UK./news/1") == "bbc.co.uk"


def test_www_gov_uk_is_the_case_where_www_is_the_registrant() -> None:
    """The two functions disagree about ``www.gov.uk``, and both are right.

    ``gov.uk`` is a registry suffix, so under the Public Suffix List algorithm the
    registrable domain of ``www.gov.uk`` really is ``www.gov.uk`` — that is the UK
    government's site, sitting beside ``hmrc.gov.uk``, not a rendering of a
    ``gov.uk`` that no one publishes from.

    :func:`~app.research.urls.normalise` nonetheless strips the ``www.``, because for
    *page identity* the question is only whether a server sends the same document, and
    it does. So a page arriving as ``https://www.gov.uk/x`` is filed under publisher
    ``gov.uk``. Recorded here because the disagreement looks like a bug and is not —
    and because "fixing" either side would either split one publisher in two or merge
    ``hmrc.gov.uk`` into a department it is independent of.
    """
    assert urls.registrable_domain("www.gov.uk") == "www.gov.uk"
    assert urls.normalise("https://www.gov.uk/x") == "https://gov.uk/x"
    assert urls.registrable_domain("hmrc.gov.uk") != urls.registrable_domain("gov.uk")


# ========================================================== the date in the path ====


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/news/2026/03/04/business-123", datetime(2026, 3, 4, tzinfo=UTC)),
        ("/news/2026-03-04/business-123", datetime(2026, 3, 4, tzinfo=UTC)),
        ("/news/20260304/business-123", datetime(2026, 3, 4, tzinfo=UTC)),
        ("/2026/03/04/", datetime(2026, 3, 4, tzinfo=UTC)),
        ("/blog/2019/12/31/year-in-review", datetime(2019, 12, 31, tzinfo=UTC)),
        ("/2026/03/04_business-123", datetime(2026, 3, 4, tzinfo=UTC)),
    ],
)
def test_a_dated_path_yields_that_date(path: str, expected: datetime) -> None:
    """News URLs carry the date far more often than search APIs report one."""
    assert urls.date_from_path(f"https://example.com{path}", now=NOW) == expected


@pytest.mark.parametrize(
    "path",
    [
        # A month with no day. Resolving it to a day nobody stated is a fabrication.
        "/news/2026/03/business-123",
        "/archive/2026/03/",
        # A year alone.
        "/news/2026/business-123",
        # An id that resembles a date.
        "/story/20260304123",
        "/id/1234/56/78",
        # Out of range.
        "/news/2026/13/04/x",
        "/news/2026/03/32/x",
        # A real-looking pattern that is not a day.
        "/news/2026/02/31/x",
        # Not in a path at all.
        "/news/business?d=2026/03/04",
        # No date.
        "/news/business-123",
    ],
)
def test_a_path_that_does_not_state_a_full_date_yields_nothing(path: str) -> None:
    """Narrow on purpose: an invented day is hard to notice and impossible to defend."""
    assert urls.date_from_path(f"https://example.com{path}", now=NOW) is None


def test_a_future_date_is_not_a_date() -> None:
    """A path resembling a date rather than stating one.

    ``now`` is passed in rather than read from the clock, so this decision is
    reproducible and every source in one dossier is judged against one instant.
    """
    ahead = "https://example.com/news/2027/01/01/business-123"

    assert urls.date_from_path(ahead, now=NOW) is None
    assert urls.date_from_path(ahead, now=datetime(2027, 6, 1, tzinfo=UTC)) is not None


def test_the_date_is_midnight_utc_and_that_is_a_precision_claim() -> None:
    """The URL gives a day. The time within it is unknown, not zero."""
    found = urls.date_from_path("https://example.com/2026/03/04/x", now=NOW)

    assert found == datetime(2026, 3, 4, 0, 0, tzinfo=UTC)
    assert found is not None
    assert found.tzinfo is UTC


def test_today_is_accepted() -> None:
    """A boundary worth pinning: ``<= now``, not ``< now``."""
    assert urls.date_from_path("https://example.com/2026/03/14/x", now=NOW) == datetime(
        2026, 3, 14, tzinfo=UTC
    )
