"""The state the agents pass between them.

One ``TypedDict`` of channels, and a per-claim view assembled from it.

The channels are *parallel tuples* indexed by claim rather than a single tuple of
per-claim records, and that shape is what lets the search and fact-check agents run
concurrently: LangGraph merges a superstep by channel, so two nodes writing two keys
merge cleanly while two nodes writing two fields of one object do not. :func:`cases`
zips them back into something a reader can hold, which is what the later agents want.

Nothing here imports LangGraph. ``Annotated`` reducers are read reflectively by the
graph, so the state stays testable — and the agents with it — on an install that has
no LangGraph in it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Annotated, TypedDict

from app.domain import (
    Artifact,
    ClaimResearch,
    Credibility,
    Dossier,
    ExtractedClaim,
    FactCheck,
    ProviderOutcome,
    Retrieval,
    SkippedClaim,
    Source,
)
from app.graph.verdict import Indication, Ruling

__all__ = ["AgentNote", "Case", "GraphState", "cases", "dossier", "initial"]


@dataclass(frozen=True, slots=True)
class AgentNote:
    """What one agent did, for the trace on the finished record."""

    agent: str
    detail: str


def _extend[T](left: tuple[T, ...], right: tuple[T, ...]) -> tuple[T, ...]:
    return (*left, *right)


class GraphState(TypedDict, total=False):
    """The channels every agent reads from and writes to.

    Each of ``claims``, ``queries``, ``retrievals``, ``reviews``, ``research``,
    ``grading`` and ``conflicts`` is aligned to ``claims`` by index.
    """

    artifact: Artifact
    now: datetime

    # Claim
    claims: tuple[ExtractedClaim, ...]
    queries: tuple[tuple[str, ...], ...]
    skipped: tuple[SkippedClaim, ...]

    # Search
    retrievals: tuple[tuple[Retrieval, ...], ...]
    providers: tuple[ProviderOutcome, ...]

    # FactCheck
    reviews: tuple[tuple[FactCheck, ...], ...]
    checkers: tuple[ProviderOutcome, ...]

    # Evidence
    research: tuple[ClaimResearch, ...]

    # Source
    grading: tuple[tuple[Credibility, ...], ...]

    # Contradiction
    conflicts: tuple[tuple[Indication, ...], ...]

    # Judge
    ruling: Ruling | None

    trace: Annotated[tuple[AgentNote, ...], _extend]


@dataclass(frozen=True, slots=True)
class Case:
    """Everything gathered about one claim, gathered back into one object."""

    index: int
    claim: ExtractedClaim
    research: ClaimResearch | None = None
    grading: tuple[Credibility, ...] = ()
    conflicts: tuple[Indication, ...] = ()

    @property
    def sources(self) -> tuple[Source, ...]:
        return self.research.sources if self.research else ()

    @property
    def fact_checks(self) -> tuple[FactCheck, ...]:
        return self.research.fact_checks if self.research else ()

    def credibility_of(self, ref: int) -> Credibility | None:
        """The grading for one source, matched by ref rather than by position."""
        return next((c for c in self.grading if c.ref == ref), None)


def initial(artifact: Artifact, *, now: datetime) -> GraphState:
    """The state a run starts from, with every channel present and empty."""
    return GraphState(
        artifact=artifact,
        now=now,
        claims=(),
        queries=(),
        skipped=(),
        retrievals=(),
        providers=(),
        reviews=(),
        checkers=(),
        research=(),
        grading=(),
        conflicts=(),
        ruling=None,
        trace=(),
    )


def cases(state: GraphState) -> tuple[Case, ...]:
    """The per-claim view of the parallel channels.

    Tolerates short channels: an agent that has not run yet leaves its tuple empty,
    and a reader gets ``None`` or ``()`` for that part rather than an IndexError.
    """
    return tuple(
        Case(
            index=index,
            claim=claim,
            research=_at(state.get("research", ()), index),
            grading=_at(state.get("grading", ()), index) or (),
            conflicts=_at(state.get("conflicts", ()), index) or (),
        )
        for index, claim in enumerate(state.get("claims", ()))
    )


def _at[T](items: Sequence[T], index: int) -> T | None:
    return items[index] if index < len(items) else None


def dossier(state: GraphState) -> Dossier:
    """The gathering half of a run, as the type :mod:`app.services.research` produces.

    Credibility is folded onto each claim's record here because the graph carries the
    gradings in a channel of their own — see :class:`Case` — while a ``Dossier`` holds
    them on the claim. Without the fold, storing a graph run would store its sources
    ungraded, and a dossier from the research service and one from the fact-check desk
    would not be the same object.
    """
    grading = state.get("grading", ())
    return Dossier(
        claims=tuple(
            replace(record, credibility=_at(grading, index) or ())
            for index, record in enumerate(state.get("research", ()))
        ),
        providers=state.get("providers", ()),
        retrieved_at=state["now"],
        skipped=state.get("skipped", ()),
        fact_checkers=state.get("checkers", ()),
    )
