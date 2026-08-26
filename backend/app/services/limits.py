"""Size limits on submitted text.

One function, shared by the two services that accept prose, so the bound and the
error are decided in a single place. It lives in the service layer rather than as a
pydantic ``Field`` constraint for two reasons: the limit is configuration, which a
field constraint evaluated at class-definition time cannot read, and a worker or a
script submitting an artifact should hit the same ceiling as an HTTP request.
"""

from __future__ import annotations

from app.core.errors import PayloadTooLargeError


def ensure_within_limit(text: str, *, limit: int, field: str) -> None:
    """Raise :class:`PayloadTooLargeError` when ``text`` is longer than ``limit``.

    ``field`` names the offending input in ``details`` so a client with several
    text fields in one request learns which one to shorten.
    """
    length = len(text)
    if length > limit:
        raise PayloadTooLargeError(
            f"{field} is {length:,} characters; the limit is {limit:,}.",
            details={"field": field, "characters": length, "limit": limit},
        )
