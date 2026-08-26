"""The fact-check database seam.

Which database is queried is decided by ``FACT_CHECK_PROVIDER``. One is registered —
Google's Fact Check Tools API, which indexes the ``ClaimReview`` markup publishers put on
their own pages, and is therefore an index of other people's fact checks rather than a
fact-checker itself.

The types the seam speaks live in :mod:`app.domain.factcheck`; import them from
:mod:`app.domain`. What lives here is the wire: :mod:`app.factcheck.base` for the
contract, :mod:`app.factcheck.google` for the one implementation,
:mod:`app.factcheck.lookup` for the per-claim fan-out.
"""

from __future__ import annotations

from app.core.config import FactCheckProvider, Settings
from app.core.registry import ProviderRegistry
from app.factcheck.base import FactCheckClient
from app.factcheck.google import GoogleFactCheckClient
from app.factcheck.google import build as _build_google

#: Fact-check lookups, keyed by provider.
fact_check_clients: ProviderRegistry[FactCheckProvider, FactCheckClient] = (
    ProviderRegistry("fact-check")
)

fact_check_clients.register(FactCheckProvider.GOOGLE, _build_google)


def get_fact_check_client(settings: Settings) -> FactCheckClient:
    """Return the configured fact-check client."""
    return fact_check_clients.resolve(settings.FACT_CHECK_PROVIDER, settings)


__all__ = [
    "FactCheckClient",
    "GoogleFactCheckClient",
    "fact_check_clients",
    "get_fact_check_client",
]
