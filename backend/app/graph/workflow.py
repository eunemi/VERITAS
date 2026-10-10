"""The graph itself: seven agents, and the edges between them.

The only module in this package that imports LangGraph. Everything else —
:mod:`app.graph.state`, :mod:`app.graph.verdict` and every agent — is plain Python,
so an agent can be exercised by calling it with a dict and the whole package stays
testable on an install that has no LangGraph in it.

The topology::

    START → claim ─┬→ search ────┬→ evidence → source → contradiction → judge → END
                   ├→ factcheck ─┘                                        ↑
                   └────────────────────── no claims ──────────────────────┘

Search and fact-check are one superstep, not two. They read the same claims and write
different channels, so nothing is gained by ordering them and a fan-out costs the
latency of the slower rather than the sum of both. Evidence is the join.

The third edge out of ``claim`` is the short circuit: no claims means nothing to search
for, and issuing a fan-out to find that out would spend provider quota to arrive at the
``UNCERTAIN`` the judge can already report.

A :class:`~app.reasoning.layer.ReasoningLayer` may be passed to
:class:`VerificationGraph`, and runs *after* the graph rather than inside it. It is
never built here: constructing one resolves an LLM client, which a deployment without
a key cannot do, and the graph must compile in that deployment. Passing it in also
keeps the model out of the topology, where a node that called one would put an
unverifiable step between two verifiable ones.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.domain import Artifact
from app.graph import state as channels
from app.graph.agents import (
    claim,
    contradiction,
    evidence,
    factcheck,
    judge,
    search,
    source,
)
from app.graph.agents.semantic import SemanticJudge
from app.graph.state import AgentNote, GraphState
from app.graph.verdict import Ruling, Thresholds

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from langgraph.graph.state import CompiledStateGraph

    from app.reasoning import Reasoning, ReasoningLayer
    from app.services.claims import ClaimExtractionService

__all__ = ["Outcome", "VerificationGraph", "build", "thresholds_from"]


def thresholds_from(settings: Settings) -> Thresholds:
    return Thresholds(
        min_sources=settings.JUDGE_MIN_SOURCES,
        min_standing=settings.JUDGE_MIN_STANDING,
        min_weight=settings.JUDGE_MIN_WEIGHT,
        contest_margin=settings.JUDGE_CONTEST_MARGIN,
    )


def build(
    *, settings: Settings, extractor: ClaimExtractionService
) -> CompiledStateGraph:
    """Compile the workflow. Cheap, and safe to hold for the process's lifetime."""
    graph: StateGraph = StateGraph(GraphState)

    graph.add_node(claim.NAME, claim.ClaimAgent(settings=settings, extractor=extractor))
    graph.add_node(search.NAME, search.SearchAgent(settings=settings))
    graph.add_node(factcheck.NAME, factcheck.FactCheckAgent(settings=settings))
    graph.add_node(evidence.NAME, evidence.EvidenceAgent())
    graph.add_node(source.NAME, source.SourceAgent(settings=settings))
    graph.add_node(contradiction.NAME, contradiction.ContradictionAgent())
    graph.add_node(judge.NAME, SemanticJudge(settings))

    graph.add_edge(START, claim.NAME)
    graph.add_conditional_edges(
        claim.NAME, _after_claim, [search.NAME, factcheck.NAME, judge.NAME]
    )
    graph.add_edge(search.NAME, evidence.NAME)
    graph.add_edge(factcheck.NAME, evidence.NAME)
    graph.add_edge(evidence.NAME, source.NAME)
    graph.add_edge(source.NAME, contradiction.NAME)
    graph.add_edge(contradiction.NAME, judge.NAME)
    graph.add_edge(judge.NAME, END)

    return graph.compile()


def _after_claim(state: GraphState) -> list[str]:
    """Fan out to both gatherers, or straight to the judge with nothing to gather.

    Returning two names is what makes them concurrent: LangGraph schedules every
    branch of one conditional edge in the same superstep, and evidence — subscribed to
    both — runs once, when both have written.
    """
    if not state.get("claims"):
        return [judge.NAME]
    return [search.NAME, factcheck.NAME]


class Outcome:
    """What one run produced: the ruling, the trace, and the state behind both."""

    __slots__ = ("reasoning", "ruling", "state", "trace")

    def __init__(
        self, state: GraphState, reasoning: tuple[Reasoning, ...] = ()
    ) -> None:
        ruling = state.get("ruling")
        if ruling is None:
            raise ValueError("the graph finished without a ruling")
        self.state = state
        self.ruling: Ruling = ruling
        self.trace: tuple[AgentNote, ...] = state.get("trace", ())
        #: One per claim the reasoning layer read, empty when there was no layer.
        #: Never a substitute for :attr:`ruling`, which is what the graph decided.
        self.reasoning: tuple[Reasoning, ...] = reasoning


class VerificationGraph:
    """Runs an artifact through the workflow.

    Compiles once. ``run`` is re-entrant — the state is per-invocation and no agent
    holds anything across calls — so one instance serves concurrent requests.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        extractor: ClaimExtractionService,
        reasoning: ReasoningLayer | None = None,
    ) -> None:
        self._graph = build(settings=settings, extractor=extractor)
        self._reasoning = reasoning

    async def run(self, artifact: Artifact, *, now: datetime | None = None) -> Outcome:
        """Check ``artifact``.

        ``now`` is threaded through the state rather than read by each agent, so every
        age, freshness and staleness comparison in one run is against one instant.
        """
        final = await self._graph.ainvoke(
            channels.initial(artifact, now=now or datetime.now(UTC))
        )
        return Outcome(final, await self._read(final))

    async def _read(self, state: GraphState) -> tuple[Reasoning, ...]:
        """The reasoning layer over each ruled claim, concurrently.

        Gathered without ``return_exceptions``: ``consider`` reports every failure as
        an ungrounded finding rather than raising, so an exception here would be a bug
        in the layer and should not be swallowed into a partial result.
        """
        layer = self._reasoning
        ruling = state.get("ruling")
        if layer is None or ruling is None or not ruling.claims:
            return ()

        found = {case.claim.ref: case for case in channels.cases(state)}
        work: list[Awaitable[Reasoning]] = []
        for decided in ruling.claims:
            case = found.get(decided.ref)
            if case is None or case.research is None:
                continue
            work.append(
                layer.consider(
                    ruling=decided,
                    research=case.research,
                    conflicts=case.conflicts,
                    credibility=case.grading,
                )
            )
        return tuple(await asyncio.gather(*work))
