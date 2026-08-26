"""Builders for the :mod:`app.graph` tests.

Separate from :mod:`tests.research_bench` and built on top of it: that module makes the
nouns a dossier is made of, this one makes the *state* the agents pass between them.

Depends on nothing but the standard library, :mod:`app.domain` and :mod:`app.research`,
so the agent tests run with no LangGraph installed. That is the property
``test_graph_imports`` enforces, and this module is what makes exercising it possible —
an agent is called with a dict here, never through a compiled graph.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain import (
    ClaimResearch,
    Credibility,
    DateBasis,
    Evidence,
    ExtractedClaim,
    FactCheck,
    ProviderOutcome,
    ProviderStatus,
    Review,
    ReviewedClaim,
    Source,
)
from app.graph.state import GraphState
from app.graph.verdict import Indication
from app.research import credibility, reviews
from tests.research_bench import NOW, claim, source

__all__ = [
    "CLAIM",
    "MATCHING",
    "NOW",
    "PUBLISHED",
    "RIVAL",
    "claim",
    "graded",
    "outcome",
    "passage",
    "rated",
    "reported",
    "state",
]

#: One claim, carrying a figure and a date, used by every test below. Numeric because
#: the contradiction agent has nothing to work with otherwise, and the judge's
#: corroboration turns on a passage repeating the claim's own specifics.
CLAIM = "The central bank held its policy rate at 4.75% in February 2026."

#: A passage that repeats the claim's figure.
MATCHING = (
    "The central bank left its benchmark policy rate unchanged at 4.75% following "
    "its February meeting, the third consecutive decision to hold."
)

#: A passage about the same subject carrying a different figure, and none of the
#: claim's own — what the contradiction agent reads as a conflict.
RIVAL = (
    "The central bank raised its benchmark policy rate to 5.25% at its February "
    "meeting, ending a run of three holds and surprising forecasters."
)


#: The date ``reported`` stamps a dated source with — five weeks before :data:`NOW`, so
#: a source is recent without being fresh and the judge's recency term is exercised
#: rather than saturated.
PUBLISHED = datetime(2026, 2, 6, tzinfo=UTC)


def passage(text: str, *, matched: tuple[str, ...] = ("4.75%",)) -> Evidence:
    """One passage, with the offsets a real selection would carry."""
    return Evidence(
        quote=text,
        provider="tavily",
        start=0,
        end=len(text),
        score=0.8,
        matched_numbers=matched,
    )


def reported(
    url: str,
    text: str = MATCHING,
    *,
    ref: int = 1,
    matched: tuple[str, ...] = ("4.75%",),
    cluster: int | None = None,
    dated: bool = True,
) -> Source:
    """A source carrying one passage, dated unless a test wants it undateable.

    ``dated`` is not cosmetic. A page with no stated date leaves
    :attr:`~app.domain.credibility.Axis.DATE` and
    :attr:`~app.domain.credibility.Axis.TRANSPARENCY` unassessed, which is how a test
    builds a source that cannot reach the judge's standing floor without pretending a
    publisher is bad.

    All three date fields move together, because
    :class:`~app.domain.research.Source` documents ``date_basis`` as ``None`` exactly
    when ``published_at`` is — a source with a basis and no date is not a state the
    pipeline can produce, and :mod:`app.graph.scoring` reads the date the other two
    do not.
    """
    return source(
        url,
        ref=ref,
        evidence=(passage(text, matched=matched),) if text else (),
        published_at=PUBLISHED if dated else None,
        date_basis=DateBasis.PROVIDER if dated else None,
        date_text="2026-02-06" if dated else None,
        cluster=cluster,
    )


def graded(sources: tuple[Source, ...]) -> tuple[Credibility, ...]:
    """The credibility the source agent would produce for ``sources``."""
    return credibility.rate(sources, now=NOW, fresh_days=365, stale_days=3650)


def rated(*ratings: str, text: str = CLAIM) -> tuple[FactCheck, ...]:
    """Fact checks whose reviewers published ``ratings``, in a real reviewer's words.

    Built through :func:`app.research.reviews.select` rather than by hand, because
    :attr:`~app.domain.factcheck.Review.stance` is that function's reading of a
    publisher's vocabulary. Presetting it would let a test assert agreement on a stance
    the vocabulary table never produces — and it is the table, not the judge, that
    decides what "Mixture" means.
    """
    published = ReviewedClaim(
        text=text,
        reviews=tuple(
            Review(
                publisher=f"Reviewer {index}",
                site=f"reviewer{index}.example",
                url=f"https://reviewer{index}.example/{index}",
                rating=rating,
            )
            for index, rating in enumerate(ratings, start=1)
        ),
    )
    return reviews.select(claim(text), (published,), source="google", min_match=0.0)


def outcome(
    *, provider: str = "tavily", answered: bool = True, results: int = 3
) -> ProviderOutcome:
    """One provider's outcome. ``answered=False`` is the misconfigured deployment."""
    return ProviderOutcome(
        provider=provider,
        status=ProviderStatus.SEARCHED if answered else ProviderStatus.FAILED,
        queries=("central bank policy rate february 2026",),
        results=results if answered else 0,
        code="" if answered else "search_failed",
    )


def state(
    sources: tuple[Source, ...],
    *,
    text: str = CLAIM,
    claims: tuple[ExtractedClaim, ...] | None = None,
    fact_checks: tuple[FactCheck, ...] = (),
    conflicts: tuple[Indication, ...] = (),
    providers: tuple[ProviderOutcome, ...] | None = None,
    grade: bool = True,
) -> GraphState:
    """The state as it reaches the judge: one claim, researched and graded.

    ``grade=False`` leaves ``grading`` empty, which is the ``CREDIBILITY_ENABLED=False``
    deployment rather than a dossier of ungradeable sources.
    """
    found = claims if claims is not None else (claim(text),)
    record = ClaimResearch(
        claim=text,
        queries=("central bank policy rate february 2026",),
        sources=sources,
        fact_checks=fact_checks,
    )
    return GraphState(
        now=NOW,
        claims=found,
        queries=(("central bank policy rate february 2026",),),
        skipped=(),
        retrievals=(),
        providers=providers if providers is not None else (outcome(),),
        reviews=(fact_checks,),
        checkers=(),
        research=(record,),
        grading=(graded(sources),) if grade else (),
        conflicts=(conflicts,),
        ruling=None,
        trace=(),
    )
