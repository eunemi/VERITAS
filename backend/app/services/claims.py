"""Pulling checkable claims out of prose.

The bridge between the two desks that read copy: the text desk reads how something
is written, the fact-check desk reads one assertion at a time. This service is that
step made explicit, so a caller can perform it on its own — which is what
``POST /api/v1/extract-claim`` exposes.
"""

from __future__ import annotations

import logging

from app.core.config import LLMProvider, Settings
from app.core.errors import VeritasError
from app.domain import Extraction
from app.nlp import get_claim_extractor
from app.services.limits import ensure_within_limit

logger = logging.getLogger(__name__)


class ClaimExtractionService:
    """Turns a piece of prose into the discrete claims it makes."""

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    async def extract(self, text: str) -> Extraction:
        """Return everything read out of ``text``.

        Two steps, and the order matters: the size guard runs before the extractor is
        resolved, so an oversized submission gets a 413 without loading a 12 MB
        model to reject it.

        The extractor is resolved per call rather than held on this service. It is a
        cheap object — the model behind it is cached process-wide in
        :mod:`app.nlp.resources` — and resolving late means a test that registers a
        substitute affects a service built before it, which a constructor-time lookup
        would not.

        Raises :class:`~app.core.errors.PayloadTooLargeError` for oversized input and
        :class:`~app.core.errors.ConfigurationError` when the configured spaCy model
        is not installed. Prose it cannot make claims out of is not an error: a
        submission of pure opinion comes back with every clause marked unfit and a
        reason, which is a 200.
        """
        ensure_within_limit(text, limit=self._settings.MAX_TEXT_CHARS, field="text")
        if self._settings.CLAIM_EXTRACTION_LLM and (
            self._settings.OPENAI_API_KEY
            or self._settings.LLM_PROVIDER is LLMProvider.OLLAMA
        ):
            from app.nlp.llm import extract

            try:
                return await extract(text, self._settings)
            except VeritasError as exc:
                # Claim extraction has a deterministic spaCy implementation. A
                # provider outage or an expired key should not turn a submitted news
                # item into a missing record when the local extractor can still split
                # its claims and the live evidence desks can continue.
                logger.warning(
                    "LLM claim extraction unavailable; using spaCy fallback",
                    extra={"code": exc.code, "provider_message": exc.message},
                )
        extractor = get_claim_extractor(self._settings)
        return await extractor.extract(text)
