"""Application services.

A service takes plain arguments, talks to the repository and the provider seams,
and returns plain objects from :mod:`app.domain`. Services never import FastAPI and
never raise ``HTTPException`` — they raise from :mod:`app.core.errors`, which is
what lets the same service be called from a route, a worker, or a test.

This is where all of the work goes. A route's whole job is to convert a validated
request into a service call and a service's result into a response; if a route
grows a branch, the branch belongs here.
"""

from app.services.claims import ClaimExtractionService
from app.services.limits import ensure_within_limit
from app.services.verification import VerificationService

__all__ = [
    "ClaimExtractionService",
    "VerificationService",
    "ensure_within_limit",
]
