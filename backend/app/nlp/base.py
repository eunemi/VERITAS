"""The seam: what a claim extractor is.

One method, one direction. Everything about spaCy, punkt and TF-IDF sits behind
this Protocol, which is what lets :mod:`app.services.claims` — and the HTTP tests
above it — run against a test double with none of those libraries installed.

``async`` even though the work is CPU-bound and synchronous underneath. Parsing a
long submission takes hundreds of milliseconds and would block the event loop for
all of it, so the implementation hands the parse to a worker thread; making the
contract ``async`` is what lets it, and keeps the door open for an implementation
that calls a model over the network instead.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain import Extraction


@runtime_checkable
class ClaimExtractor(Protocol):
    """Reads prose and returns the assertions in it.

    Implementations raise from :mod:`app.core.errors` — never a library-specific
    exception — so a caller can report *why* extraction failed without knowing
    whether it was built on spaCy, a remote model or a regular expression.
    """

    async def extract(self, text: str) -> Extraction:
        """Return the claims, entities and keywords found in ``text``.

        Never raises for prose it cannot make claims out of: a submission of pure
        opinion returns an :class:`~app.domain.Extraction` whose claims are all
        marked unfit with a reason, and an empty submission returns an empty one.
        Exceptions are for a broken extractor, not for difficult text.
        """
        ...
