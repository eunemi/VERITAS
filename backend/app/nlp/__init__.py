"""The claim-extraction seam.

Which extractor serves a request is decided by ``CLAIM_EXTRACTOR`` and resolved
here. Callers ask for :func:`get_claim_extractor` and never name spaCy.

Unlike the four provider seams, this one has an implementation registered from the
moment the module is imported — and that is only safe because of a discipline the
whole package keeps: **no module in :mod:`app.nlp` imports spaCy, NLTK or
scikit-learn at module scope.** Every one of those imports sits inside a function
body. So this file, the pipeline it registers and the two rule modules it pulls in
all import cleanly on a machine with none of those libraries installed, and the
failure — if it comes — arrives at the one request that asked for a parse, as a
:class:`~app.core.errors.ConfigurationError` naming the command that fixes it. Had
the imports been at the top, ``import app.main`` would need the whole NLP stack to
answer ``/health``.

That is also what lets :mod:`tests.test_claims_api` register a stub over the top and
exercise the endpoint end to end with nothing installed.
"""

from __future__ import annotations

from app.core.config import ClaimExtractorProvider, Settings
from app.core.registry import ProviderRegistry
from app.nlp.base import ClaimExtractor
from app.nlp.pipeline import SpacyClaimExtractor, build

#: Claim extractors, keyed by provider.
claim_extractors: ProviderRegistry[ClaimExtractorProvider, ClaimExtractor] = (
    ProviderRegistry("claim extraction")
)

claim_extractors.register(ClaimExtractorProvider.SPACY, build)


def get_claim_extractor(settings: Settings) -> ClaimExtractor:
    """Return the configured claim extractor.

    Resolved per call rather than cached. The call is cheap — the constructor reads
    five settings and the model itself is cached in :mod:`app.nlp.resources` — and
    resolving late is what makes a registry substitution take effect for a service
    that was built before it.
    """
    return claim_extractors.resolve(settings.CLAIM_EXTRACTOR, settings)


__all__ = [
    "ClaimExtractor",
    "SpacyClaimExtractor",
    "claim_extractors",
    "get_claim_extractor",
]
