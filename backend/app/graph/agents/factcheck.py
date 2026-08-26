"""Looks each claim up against the published fact-check databases."""

from __future__ import annotations

from app.core.config import Settings
from app.factcheck.lookup import check
from app.graph.state import AgentNote, GraphState
from app.research import reviews

NAME = "factcheck"


class FactCheckAgent:
    """Finds reviews of the claim, and never lets one stand in for a verdict.

    What comes back is attached as evidence about a *published review*. The judge
    weighs it beside everything else; nothing here shortcuts to a determination
    because a reviewer reached one.
    """

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    async def __call__(self, state: GraphState) -> GraphState:
        claims = state["claims"]
        if not claims:
            return GraphState(trace=(AgentNote(NAME, "no claims to look up"),))

        checked = await check(
            [claim.text for claim in claims],
            settings=self._settings,
            now=state["now"],
        )
        selected = tuple(
            reviews.select(
                claim,
                checked.found[index],
                source=str(self._settings.FACT_CHECK_PROVIDER),
                min_match=self._settings.FACT_CHECK_MIN_MATCH,
            )
            for index, claim in enumerate(claims)
        )
        return GraphState(
            reviews=selected,
            checkers=checked.outcomes,
            trace=(
                AgentNote(
                    NAME,
                    f"{sum(len(s) for s in selected)} matching review(s) found",
                ),
            ),
        )
