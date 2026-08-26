"""Grades each source on the six axes of :mod:`app.domain.credibility`."""

from __future__ import annotations

from app.core.config import Settings
from app.domain import Band
from app.graph.state import AgentNote, GraphState
from app.research import credibility

NAME = "source"


class SourceAgent:
    """Reads who is accountable, who holds the record, and who is a second voice.

    Grades the *source*, never the claim, and nothing downstream reorders or drops a
    source because of what comes back — the judge weighs the grading, the dossier
    keeps every source it found either way.
    """

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    async def __call__(self, state: GraphState) -> GraphState:
        research = state.get("research", ())
        if not research:
            return GraphState(trace=(AgentNote(NAME, "no sources to grade"),))

        graded = tuple(
            credibility.rate(
                record.sources,
                now=state["now"],
                fresh_days=self._settings.CREDIBILITY_FRESH_DAYS,
                stale_days=self._settings.CREDIBILITY_STALE_DAYS,
            )
            for record in research
        )
        strong = sum(
            1 for group in graded for c in group if c.band is Band.STRONG
        )
        total = sum(len(group) for group in graded)
        return GraphState(
            grading=graded,
            trace=(
                AgentNote(NAME, f"{total} source(s) graded, {strong} in the top band"),
            ),
        )
