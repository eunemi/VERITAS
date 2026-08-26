"""Assembles retrievals into dossiers: deduplicated sources, dated, with passages."""

from __future__ import annotations

from app.graph.state import AgentNote, GraphState
from app.research import dossier

NAME = "evidence"


class EvidenceAgent:
    """The join. Reads what search and fact-check gathered, produces the dossier.

    Runs after both because :func:`app.research.dossier.for_claim` builds one record
    per claim out of both halves — the retrievals it dedupes into sources and selects
    passages from, and the reviews it carries alongside them.
    """

    async def __call__(self, state: GraphState) -> GraphState:
        claims = state["claims"]
        if not claims:
            return GraphState(trace=(AgentNote(NAME, "no claims to assemble"),))

        retrievals = state.get("retrievals", ())
        reviews = state.get("reviews", ())
        assembled = tuple(
            dossier.for_claim(
                claim,
                queries=state["queries"][index],
                retrievals=retrievals[index] if index < len(retrievals) else (),
                fact_checks=reviews[index] if index < len(reviews) else (),
                now=state["now"],
            )
            for index, claim in enumerate(claims)
        )
        passages = sum(len(s.evidence) for r in assembled for s in r.sources)
        return GraphState(
            research=assembled,
            trace=(
                AgentNote(
                    NAME,
                    f"{sum(len(r.sources) for r in assembled)} source(s), "
                    f"{passages} passage(s) bearing on the claims",
                ),
            ),
        )
