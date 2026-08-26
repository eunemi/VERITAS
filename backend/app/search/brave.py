"""Brave Search — an independent index, and the most date fields to get wrong.

Verified against Brave's own reference for ``GET /res/v1/web/search`` (the Web
Search API reference and its ``WebSearchApiResponse`` / ``SearchResult`` schemas).

Brave matters to this service for a structural reason: it runs its own crawler and
its own index. Tavily and Serper both ultimately sit on other people's results, so
a claim corroborated by Tavily and Serper may be corroborated by one index twice.
Brave agreeing is closer to genuine independence at the *index* level — which is
half of what "multiple independent websites" asks for; the other half, independent
publishers, is counted in :mod:`app.research.dedupe`.

Three details in the response are traps, and all three are handled here rather
than downstream.

**``text_decorations`` defaults to ``true``.** Left alone, Brave wraps query terms
in ``description`` with highlight markers. Every "verbatim" quote sliced out of
that string would then contain characters the publisher never wrote — the exact
fabrication this service forbids — so the parameter is sent ``false`` on every
request. It is switched off at the request rather than cleaned up in the response
because stripping markers afterwards means editing the string that evidence
offsets index, and a cleaner that guessed wrong would corrupt a quote silently.

**Four date-ish fields, and only one of them is a publication date.**
``article.date`` is documented as "the date when the article was published" and is
the only one that earns :attr:`~app.domain.research.DateBasis.PROVIDER`.
``page_age`` is documented as "based on its published **or** last modified date"
with nothing to say which — so it is
:attr:`~app.domain.research.DateBasis.PROVIDER_MODIFIED`. ``age`` is a relative
string. And ``page_fetched`` / ``fetched_content_timestamp`` are *crawl*
timestamps, always present, and **never read by this module**: when Brave last
fetched a page says nothing about when anyone published it.

**``web`` is nullable.** A 200 response with no web results at all is documented
and legal. That is an empty result list, not an error — Brave searched and found
nothing, which is a real answer and must not be turned into a failure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config import Settings
from app.core.errors import ConfigurationError, SearchError
from app.domain import DateBasis
from app.providers.dates import resolve
from app.providers.http import Http, ensure_parsed
from app.search.base import SearchResult

__all__ = ["MAX_QUERY_CHARS", "MAX_QUERY_WORDS", "MAX_RESULTS", "BraveClient", "build"]

#: Brave's documented ceiling on ``count``.
MAX_RESULTS = 20

#: Brave rejects a query longer than this. Documented as a hard limit, so the
#: query builder in :mod:`app.research.queries` respects it and this module
#: enforces it — a 422 for an over-long query is a failure that costs a whole
#: provider's results for that claim.
MAX_QUERY_CHARS = 400

#: The other half of the same limit: 50 words, whatever their length.
MAX_QUERY_WORDS = 50


class BraveClient(Http):
    """Searches the web through Brave's Web Search API."""

    name = "brave"
    url = "https://api.search.brave.com/res/v1/web/search"
    error = SearchError

    def __init__(self, settings: Settings) -> None:
        if settings.BRAVE_API_KEY is None:
            raise ConfigurationError(
                "BRAVE_API_KEY is not set", details={"provider": self.name}
            )
        self._key = settings.BRAVE_API_KEY.get_secret_value()
        super().__init__(
            timeout=settings.SEARCH_TIMEOUT_SECONDS,
            attempts=settings.SEARCH_ATTEMPTS,
            secrets=(self._key,),
        )

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        now: datetime,
    ) -> list[SearchResult]:
        """Results for ``query``, in Brave's relevance order.

        ``result_filter=web`` asks for only the web results, since the
        discussions, FAQ, news and video blocks are not what evidence is sliced
        out of and each one costs response size.
        """
        payload = await self.fetch(
            "GET",
            self.url,
            headers={
                # The only required header. `Accept` and `Accept-Encoding` are
                # documented as optional and httpx sets sensible values for both.
                "X-Subscription-Token": self._key,
            },
            params={
                "q": clamp_query(query),
                "count": max(1, min(max_results, MAX_RESULTS)),
                # Not a nicety. See the module docstring: on by default, and it
                # would inject markers into the string quotes are sliced from.
                "text_decorations": "false",
                "result_filter": "web",
                # Off for the same reason `text_decorations` is: spelling
                # correction would return results for a query that was never
                # asked, and `queries` in the dossier would no longer be a record
                # of what was actually searched.
                "spellcheck": "false",
            },
        )
        return self.parse(payload, now=now)

    def parse(self, payload: Any, *, now: datetime) -> list[SearchResult]:
        """Turn a decoded response body into results.

        Public so a recorded response can be parsed in a test without a network.

        The nullable-``web`` case is the interesting one, and it is the reason
        this cannot be written as a chain of ``.get()`` calls with a default: a
        missing ``web`` key means "no web results", which is an empty list, while
        a payload that is not an object at all means the contract changed, which
        raises. Collapsing those two would let a schema change be reported to a
        reader as an absence of evidence.
        """
        if not isinstance(payload, dict):
            raise SearchError(
                f"{self.name} returned {type(payload).__name__} where an object "
                "was expected",
                provider=self.name,
            )
        web = payload.get("web")
        if web is None:
            return []
        if not isinstance(web, dict):
            raise SearchError(
                f"{self.name} returned a non-object 'web' field",
                provider=self.name,
            )
        raw = web.get("results")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise SearchError(
                f"{self.name} returned a non-array 'web.results'",
                provider=self.name,
            )

        results: list[SearchResult] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            published_at, basis, date_text = _date(item, now=now)
            results.append(
                SearchResult(
                    url=url,
                    title=_text(item.get("title")),
                    # `description` is Brave's snippet. Undecorated, because the
                    # request said so. `extra_snippets` is deliberately not
                    # appended: joining them would create adjacencies that do not
                    # exist in the page, and a quote spanning the join would be
                    # prose no publisher wrote.
                    snippet=_text(item.get("description")),
                    # Brave documents no relevance score, and inventing one from
                    # the rank would make it comparable across providers, which
                    # it is not.
                    score=None,
                    published_at=published_at,
                    date_basis=basis,
                    date_text=date_text,
                    source=_hostname(item),
                )
            )
        ensure_parsed(
            self.name, received=len(raw), parsed=len(results), error=self.error
        )
        return results


def clamp_query(query: str, *, chars: int = MAX_QUERY_CHARS) -> str:
    """``query`` cut to Brave's documented limits, on a word boundary.

    Truncation loses recall, which is a visible and acceptable cost; exceeding the
    limit earns a 422 and loses this provider's results for the claim entirely,
    which is not. Cutting at a word boundary rather than mid-token matters because
    half a name is a different search term, and a search for ``"Kamala Har"``
    would return results this dossier would then attribute to a query nobody
    meant.
    """
    words = query.split()
    if len(words) > MAX_QUERY_WORDS:
        words = words[:MAX_QUERY_WORDS]
    out = " ".join(words)
    while len(out) > chars and words:
        words.pop()
        out = " ".join(words)
    return out


def _date(
    item: dict[str, Any], *, now: datetime
) -> tuple[datetime | None, DateBasis | None, str | None]:
    """The strongest date Brave offered for one result, and what kind it is.

    Tried in order of what the field *means*, not of what is most often present:

    1. ``article.date`` — documented as the publication date. The only
       :attr:`DateBasis.PROVIDER` case Brave has.
    2. ``page_age`` — "published or last modified", indistinguishably, hence
       :attr:`DateBasis.PROVIDER_MODIFIED`.
    3. ``age`` — a relative string like ``"2 days ago"``.

    ``page_fetched`` and ``fetched_content_timestamp`` are absent from that list
    on purpose, and their absence is the whole point of the ordering: they are the
    two fields Brave populates most reliably, so a rule like "use the first date
    that is present" would pick a crawl timestamp for almost every result and
    date a 2019 article to this morning. There is no member of
    :class:`~app.domain.research.DateBasis` that could describe such a value, and
    that is deliberate — see its docstring.

    A field that is present but unparseable does not fall through to a weaker
    field. It returns its own text with no date, because falling through would
    silently replace a publication date this module failed to read with a
    modification date it happened to understand, and the result would be labelled
    as though Brave had reported it that way.
    """
    article = item.get("article")
    if isinstance(article, dict):
        stated = article.get("date")
        if isinstance(stated, str) and stated.strip():
            return _resolve(stated, now=now, basis=DateBasis.PROVIDER)

    page_age = item.get("page_age")
    if isinstance(page_age, str) and page_age.strip():
        return _resolve(page_age, now=now, basis=DateBasis.PROVIDER_MODIFIED)

    age = item.get("age")
    if isinstance(age, str) and age.strip():
        return _resolve(age, now=now, basis=DateBasis.PROVIDER_RELATIVE)

    return None, None, None


def _resolve(
    text: str, *, now: datetime, basis: DateBasis
) -> tuple[datetime | None, DateBasis | None, str | None]:
    """One candidate string resolved, keeping the text either way.

    :func:`app.providers.dates.resolve` decides the basis for itself when the string
    turns out to be relative, which is why ``basis`` here is a claim about the
    field rather than about the value. Brave documents ``page_age`` as ISO 8601
    without giving a format or an example, so a field documented as absolute
    arriving with ``"3 hours ago"`` in it is a real possibility rather than a
    defensive fiction.
    """
    found = resolve(text, now=now, basis=basis)
    if found is None:
        return None, None, text
    published_at, resolved_basis = found
    return published_at, resolved_basis, text


def _hostname(item: dict[str, Any]) -> str | None:
    """Brave's own lower-cased hostname for the result, when it sent one.

    Read from ``meta_url.hostname`` rather than parsed out of the URL, so that the
    value is the provider's and not this application's. :mod:`app.research.urls`
    derives its own host for identity purposes; this field is what Brave said.
    """
    meta = item.get("meta_url")
    if isinstance(meta, dict):
        host = meta.get("hostname")
        if isinstance(host, str) and host:
            return host
    return None


def _text(value: Any) -> str:
    """A string field, or ``""`` when the provider omitted it."""
    return value if isinstance(value, str) else ""


def build(settings: Settings) -> BraveClient:
    """Factory for the registry in :mod:`app.search`."""
    return BraveClient(settings)
