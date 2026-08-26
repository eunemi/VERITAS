"""Claim extraction route.

Synchronous, unlike ``/verify``: extraction reads one piece of prose and returns a
list, with no roster of desks to open and nothing to poll. A caller uses it to see
what a document asserts before deciding what to spend a verification on.

The reading is spaCy, NLTK and scikit-learn, and it needs two artifacts that ``pip
install`` does not fetch — the spaCy model and NLTK's punkt data. A missing model is
a ``500`` whose ``details`` name the command that fixes it; missing punkt data is not
an error at all, only a slightly worse segmenter and a warning in the log.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ClaimServiceDep
from app.api.responses import COMMON_ERRORS, error
from app.schemas.claims import ExtractClaimRequest, ExtractClaimResponse

router = APIRouter(tags=["claims"], responses=COMMON_ERRORS)


@router.post(
    "/extract-claim",
    response_model=ExtractClaimResponse,
    summary="Pull the checkable claims out of a piece of prose",
    responses={
        413: error("The text is longer than MAX_TEXT_CHARS."),
        500: error("The configured spaCy model is not installed."),
    },
)
async def extract_claim(
    payload: ExtractClaimRequest, service: ClaimServiceDep
) -> ExtractClaimResponse:
    """Return every claim the prose makes, in the order it makes them.

    Each claim is rewritten to stand on its own — a subject carried across a
    conjunction, a relative pronoun resolved — and keeps the verbatim span it came
    from, so the rewrite can be checked against the original and marked in place.

    Sentences that assert nothing checkable are returned too, marked ``checkable:
    false`` with a reason, rather than dropped: "the extractor skipped your second
    paragraph" and "the extractor thinks it is opinion" are different messages.
    """
    extraction = await service.extract(payload.text)
    return ExtractClaimResponse.from_domain(extraction)
