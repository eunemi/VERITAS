"""Web research route.

Synchronous, like ``/extract-claim`` and unlike ``/verify``: this searches, collects
and returns. There is no desk roster to open and nothing to poll, because nothing here
judges the claim — it gathers what the web says about it and hands that to whatever
will.

The endpoint is always a ``200`` when it runs at all, even with every provider dead.
That is the one design decision here worth defending, and it follows from what the
caller needs to be able to tell apart. A ``502`` for "Tavily timed out" would discard
the results Brave returned in the same request; a ``500`` for "no keys are configured"
would be indistinguishable, to a client, from "the web contains nothing about this
claim". So provider trouble is *data* — ``providers[]`` and ``searched`` on the body —
and the status code is reserved for the request itself being wrong.

What that means for a consumer, stated plainly because getting it wrong is the failure
mode this whole feature is built against: **read ``searched`` before concluding
anything from an empty ``sources``.** ``searched: false`` means nothing was looked for.
An expired API key produces exactly the same empty list as a claim nobody has ever
written about, and only that flag separates them.

``fact_checked`` is the same flag for the fact-check lookup, and it needs saying twice
as loudly. An empty ``fact_checks`` list reads naturally as "no fact-checker has ruled
on this claim" — a statement about the world, and one that invites treating the claim as
unexamined. A missing Google key produces the identical empty list. The lookup is also
independently skippable: it has its own key, its own quota and its own outcome, so a
deployment can have a complete web search and no fact-check coverage at all, which is
why ``fact_checkers[]`` is reported separately from ``providers[]``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ResearchServiceDep
from app.api.responses import COMMON_ERRORS, error
from app.schemas.research import ResearchRequest, ResearchResponse

router = APIRouter(tags=["research"], responses=COMMON_ERRORS)


@router.post(
    "/research",
    response_model=ResearchResponse,
    summary="Search multiple independent websites and published fact checks per claim",
    responses={
        413: error("The submission is longer than MAX_TEXT_CHARS."),
        500: error(
            "The configured spaCy model is not installed. Only reachable through the "
            "`text` input; `claims` needs no model."
        ),
    },
)
async def research(
    payload: ResearchRequest, service: ResearchServiceDep
) -> ResearchResponse:
    """Search every configured provider for each claim, and report what was found.

    Two inputs. ``text`` extracts the claims first and researches the checkable ones,
    which needs the NLP extras and produces the better search: the entities and figures
    the extractor finds are what the second and third query formulations are built
    from. ``claims`` researches strings exactly as given, needs no model, and searches
    each claim as written and nothing else.

    Each claim is searched with up to ``SEARCH_QUERIES_PER_CLAIM`` formulations against
    every provider that has a key. Nothing is appended to those queries — no "fact
    check", no "debunked", no "true" — because a query this service steered would
    return evidence this service had selected the shape of. ``queries`` on each result
    is the verbatim record of what was sent, so an unexpected result set can be
    reproduced by hand.

    Results are deduplicated at two levels, which are not the same operation. One page
    returned by three engines under four URL spellings is **merged** into one source
    that lists all four. Several publishers carrying one wire story are **marked** with
    a shared ``cluster`` and never merged: every publisher stays in ``sources`` and
    stays counted in ``domains``, and ``stories`` is the number that treats them as
    one. Compare the two before reading a claim as corroborated — eight domains and one
    story is a single report, not eight confirmations.

    Every ``evidence`` quote is a verbatim slice of a provider's snippet, with the
    offsets and the provider recorded so a client can re-derive it and check. Nothing
    is summarised or paraphrased, no quote spans a snippet's ``[...]`` elision, and a
    source whose snippets contain nothing matching the claim comes back with
    ``evidence: []`` rather than a plausible-looking first sentence.

    Alongside the web search, each claim is looked up in Google's Fact Check Tools
    index — which aggregates the ``ClaimReview`` markup publishers put on their own fact
    checks, so it is an index of other people's work rather than a fact-checker itself.
    What comes back is on ``fact_checks``: the publisher, the review URL, the verdict as
    the publisher worded it, and both dates.

    **A fact check here is evidence, not the answer.** Nothing in this response
    aggregates one into a verdict on the submitted claim, and three things are shaped to
    stop a consumer doing it by accident. ``fact_checks[].claim.text`` is the *database's*
    wording of the claim, which is not the submission's — a review of a neighbouring
    claim is genuine text that would fabricate relevance if presented as a ruling on this
    one, so both wordings travel together and ``match`` says how much they share.
    ``rating`` is the publisher's own string and is never normalised over; ``stance`` is
    this service's reading of it, labelled as derived, and is ``unrecognised`` rather than
    guessed whenever the vocabulary does not fit. ``agreement`` is null the moment two
    reviewers differ, because taking a majority would let two syndicated copies outvote
    the newsroom that did the work.
    """
    if payload.text is not None:
        dossier = await service.from_text(payload.text)
    else:
        # The validator guarantees one input or the other, so this branch has claims.
        dossier = await service.from_claims(payload.claims or [])
    return ResearchResponse.from_domain(dossier)
