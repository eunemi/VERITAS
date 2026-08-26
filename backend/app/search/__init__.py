"""The web-search seam.

Three providers, registered here so that nothing else in the application names a
vendor. Two of them are implemented against their vendor's own reference
documentation; the third, :mod:`app.search.serper`, is a reconstruction from
third-party examples because its documentation is unreachable, and that module's
docstring says so at length. Read it before enabling that key.

``SEARCH_PROVIDER`` selects the single client :func:`get_search_client` returns.
Web research does not use it — it fans out across ``SEARCH_PROVIDERS`` with
:func:`app.search.fanout.harvest`, because one index cannot corroborate itself.

:mod:`app.search.fanout` is deliberately absent from the imports below. It imports
this module to reach the registry, so importing it here would be a cycle; callers
import it directly.
"""

from __future__ import annotations

from app.core.config import SearchProvider, Settings
from app.core.registry import ProviderRegistry
from app.search.base import SearchClient, SearchResult
from app.search.brave import BraveClient
from app.search.brave import build as _build_brave
from app.search.serper import SerperClient
from app.search.serper import build as _build_serper
from app.search.tavily import TavilyClient
from app.search.tavily import build as _build_tavily

#: Web search, keyed by provider.
search_clients: ProviderRegistry[SearchProvider, SearchClient] = ProviderRegistry(
    "search"
)

search_clients.register(SearchProvider.TAVILY, _build_tavily)
search_clients.register(SearchProvider.BRAVE, _build_brave)
search_clients.register(SearchProvider.SERPER, _build_serper)


def get_search_client(settings: Settings) -> SearchClient:
    """Return the configured single search client.

    Raises :class:`app.core.errors.ConfigurationError` when the selected
    provider's API key is not set — deliberately, since a caller that asked for
    one specific engine cannot be served by silently substituting another.
    :func:`app.search.fanout.harvest` treats the same condition as a skip, because
    a fan-out over three providers can lose one and still be useful.
    """
    return search_clients.resolve(settings.SEARCH_PROVIDER, settings)


__all__ = [
    "BraveClient",
    "SearchClient",
    "SearchResult",
    "SerperClient",
    "TavilyClient",
    "get_search_client",
    "search_clients",
]
