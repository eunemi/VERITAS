"""Serper — Google's results through a third party. **Contract unverified.**

Read this before trusting anything below it.

Every other module in this package was written against its vendor's own reference
documentation. This one could not be, and saying so in a docstring is the only
honest way to ship it:

* ``docs.serper.dev`` does not resolve — the hostname has no DNS record.
* ``serper.dev/docs`` and ``serper.dev/api-reference`` both return 404.
* ``serper.dev/playground``, which the site presents as the API reference, is
  behind a login.
* A live request to ``https://google.serper.dev/search`` returns
  ``403 {"message": "Unauthorized. Sign up for a free account.", ...}`` — but so
  does a deliberately bogus path on the same host, so that response does not even
  confirm the endpoint exists.

So the request shape here — the host, the path, ``POST``, the JSON body, the
``X-API-KEY`` header, ``num`` for the result count — comes from third-party
examples and from the shape of the one sample response embedded in Serper's own
marketing page. **It is a reconstruction, and it may be wrong.**

Shipping it anyway is defensible for three reasons, and only because of all three:

1. **It cannot be enabled by accident.** No ``SERPER_API_KEY`` means
   :attr:`~app.domain.research.ProviderStatus.SKIPPED`, recorded in the dossier
   with a reason. An operator opts in deliberately, and this docstring is what
   they are opting into.
2. **If the reconstruction is wrong it fails loudly.** A wrong path or header
   yields a 4xx, which becomes
   :attr:`~app.domain.research.ProviderStatus.FAILED` carrying the provider's own
   message — not an empty result list. And per :func:`ensure_parsed`, a response
   whose items this module cannot read raises rather than reporting zero results,
   so a renamed field surfaces as a failure instead of as "nothing was found".
   The one outcome that would be genuinely dangerous — a confident, silent,
   sourceless nothing — is the one outcome that cannot happen.
3. **Nothing depends on it.** Tavily and Brave are both verified against official
   documentation, so "multiple independent websites" is satisfied without this
   provider. It is upside, not load-bearing.

The one field in the sample worth flagging: ``date`` appeared on 1 of 10 organic
results, formatted ``"Mar 10, 2022"``. Nothing documents whether it can instead
hold a relative string like ``"2 days ago"``, which is what Google's own result
pages often show. :func:`app.providers.dates.resolve` handles either and labels the
basis by what it actually parsed, so this module does not have to guess.
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

__all__ = ["MAX_RESULTS", "SerperClient", "build"]

#: Reconstructed, like the rest of the request: Serper's page shows 10 organic
#: results and no documented ceiling. Capped at the same 20 the other two
#: providers document, so one provider cannot quietly dominate a dossier.
MAX_RESULTS = 20


class SerperClient(Http):
    """Searches the web through Serper. See this module's docstring first."""

    name = "serper"
    url = "https://google.serper.dev/search"
    error = SearchError

    def __init__(self, settings: Settings) -> None:
        if settings.SERPER_API_KEY is None:
            raise ConfigurationError(
                "SERPER_API_KEY is not set", details={"provider": self.name}
            )
        self._key = settings.SERPER_API_KEY.get_secret_value()
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
        """Results for ``query``, in Google's order as Serper relays it.

        Only ``q`` and ``num`` are sent. The reconstruction covers other
        parameters — ``gl`` and ``hl`` for country and language, ``tbs`` for a
        date restriction — and they are omitted precisely because they are
        unverified: a parameter Serper does not recognise may be ignored, or may
        be a 400, and there is no documentation that says which. Sending the
        minimum is the smallest bet.
        """
        payload = await self.fetch(
            "POST",
            self.url,
            headers={
                "X-API-KEY": self._key,
                "Content-Type": "application/json",
            },
            json={
                "q": query,
                "num": max(1, min(max_results, MAX_RESULTS)),
            },
        )
        return self.parse(payload, now=now)

    def parse(self, payload: Any, *, now: datetime) -> list[SearchResult]:
        """Turn a decoded response body into results.

        Reads ``organic`` only. ``knowledgeGraph``, ``peopleAlsoAsk`` and
        ``relatedSearches`` are all present in the sample and all skipped:
        ``peopleAlsoAsk`` answers are Google's summaries rather than a
        publisher's text, and a knowledge-graph panel is an assertion with no
        single page behind it. Neither is a source, and neither can be quoted as
        one.
        """
        if not isinstance(payload, dict):
            raise SearchError(
                f"{self.name} returned {type(payload).__name__} where an object "
                "was expected",
                provider=self.name,
            )
        raw = payload.get("organic")
        if raw is None:
            # Distinct from a missing `results` in the other clients: Google
            # returning no organic results for a query is ordinary, and this
            # provider's own sample shows the key absent rather than empty on
            # some responses. An absent key is zero results; a present key that
            # is not a list is a contract change.
            return []
        if not isinstance(raw, list):
            raise SearchError(
                f"{self.name} returned a non-array 'organic'",
                provider=self.name,
                details={"keys": sorted(k for k in payload if isinstance(k, str))},
            )

        results: list[SearchResult] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = item.get("link")
            if not isinstance(url, str) or not url:
                continue
            published_at, basis, date_text = _date(item.get("date"), now=now)
            results.append(
                SearchResult(
                    url=url,
                    title=_text(item.get("title")),
                    snippet=_text(item.get("snippet")),
                    # `position` is a rank, not a relevance score. Putting a rank
                    # in `score` would make it look comparable with Tavily's 0-1
                    # relevance, and worse, a low number would read as a weak
                    # result when it means the opposite. Rank is recorded where it
                    # belongs, on `Retrieval.rank`.
                    score=None,
                    published_at=published_at,
                    date_basis=basis,
                    date_text=date_text,
                )
            )
        ensure_parsed(
            self.name, received=len(raw), parsed=len(results), error=self.error
        )
        return results


def _date(
    value: Any, *, now: datetime
) -> tuple[datetime | None, DateBasis | None, str | None]:
    """Serper's ``date``, resolved, or text-only when it will not parse."""
    if not isinstance(value, str) or not value.strip():
        return None, None, None
    found = resolve(value, now=now, basis=DateBasis.PROVIDER)
    if found is None:
        return None, None, value
    published_at, basis = found
    return published_at, basis, value


def _text(value: Any) -> str:
    """A string field, or ``""`` when the provider omitted it."""
    return value if isinstance(value, str) else ""


def build(settings: Settings) -> SerperClient:
    """Factory for the registry in :mod:`app.search`."""
    return SerperClient(settings)
