"""Fans the claims out across the configured search providers."""

from __future__ import annotations

from app.core.config import Settings
from app.graph.state import AgentNote, GraphState
from app.search.fanout import Task, harvest

NAME = "search"


class SearchAgent:
    """One fan-out for every claim, not one per claim."""

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    async def __call__(self, state: GraphState) -> GraphState:
        claims = state["claims"]
        if not claims:
            return GraphState(trace=(AgentNote(NAME, "no claims to search for"),))

        found = await harvest(
            [
                Task(claim=claim.text, queries=formulations)
                for claim, formulations in zip(claims, state["queries"], strict=True)
            ],
            settings=self._settings,
            now=state["now"],
        )
        answered = [o.provider for o in found.outcomes if o.results]
        return GraphState(
            retrievals=found.retrievals,
            providers=found.outcomes,
            trace=(
                AgentNote(
                    NAME,
                    f"{sum(len(r) for r in found.retrievals)} result(s) from "
                    f"{len(answered) or 'no'} provider(s)",
                ),
            ),
        )
