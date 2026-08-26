"""The state the agents pass between them, and why it has the shape it does.

Two properties, and both are about concurrency the graph could not otherwise have.

**Channels merge; objects do not.** The per-claim data is held as *parallel tuples*
indexed by claim rather than as one tuple of records, because LangGraph merges a
superstep by channel: two nodes writing ``retrievals`` and ``reviews`` merge cleanly,
while two nodes each returning a whole record with one field filled in would have the
second overwrite the first. That is exactly what search and fact-check do, and it is why
they can run at the same time.

**A reader still gets one object.** :func:`~app.graph.state.cases` zips the channels
back into :class:`~app.graph.state.Case`, and it tolerates channels that are short — an
agent that has not run yet leaves its tuple empty, and every agent downstream reads the
state through this function rather than indexing into it.

Runs with no LangGraph installed. The ``Annotated`` reducer is read reflectively by the
graph, so this module can assert what it does by calling it.
"""

from __future__ import annotations

from typing import get_args, get_type_hints

import pytest

from app.domain import Artifact, ArtifactKind, ClaimResearch
from app.graph import state as channels
from app.graph.state import AgentNote, Case, GraphState, cases
from app.graph.verdict import Bearing, Indication
from tests.graph_bench import CLAIM, NOW, claim, graded, reported

ARTIFACT = Artifact(kind=ArtifactKind.CLAIM, content=CLAIM)
OTHER = "Unemployment fell to 3.9% in February 2026."


def test_a_run_starts_with_every_channel_present_and_empty() -> None:
    """No agent has to distinguish "not written yet" from "written empty".

    An agent reading ``state["claims"]`` on a partially-filled state would raise
    ``KeyError`` rather than find nothing, and the difference would be a crash on the
    path where a provider returned nothing — the path most worth getting right.
    """
    start = channels.initial(ARTIFACT, now=NOW)
    for key in get_type_hints(GraphState):
        assert key in start, key
    assert start["ruling"] is None
    assert start["claims"] == ()
    assert start["now"] is NOW
    assert start["artifact"] is ARTIFACT


def test_the_trace_channel_accumulates_and_nothing_else_does() -> None:
    """One reducer, on the one channel every agent writes.

    Every other channel is written by exactly one agent, so last-value is correct for
    them and a reducer there would be a way for a retried node to silently double its
    contents. The trace is the exception, and this test says the exception is deliberate.
    """
    hints = get_type_hints(GraphState, include_extras=True)
    accumulating = [
        name for name, hint in hints.items() if getattr(hint, "__metadata__", None)
    ]
    assert accumulating == ["trace"]

    _, reducer = get_args(hints["trace"])
    left = (AgentNote("claim", "1 claim to check"),)
    right = (AgentNote("search", "6 results"),)
    assert reducer(left, right) == (*left, *right)


def test_cases_aligns_the_channels_by_index() -> None:
    """Two claims, two dossiers, and the second claim gets the second dossier."""
    first = ClaimResearch(
        claim=CLAIM, queries=("q",), sources=(reported("https://reuters.com/a"),)
    )
    second = ClaimResearch(
        claim=OTHER, queries=("q",), sources=(reported("https://ons.gov.uk/b", ref=2),)
    )
    found = cases(
        GraphState(
            claims=(claim(CLAIM, ref=1), claim(OTHER, ref=2)),
            research=(first, second),
        )
    )
    assert [case.index for case in found] == [0, 1]
    assert [case.claim.text for case in found] == [CLAIM, OTHER]
    assert [case.research for case in found] == [first, second]
    assert [case.sources[0].domain for case in found] == ["reuters.com", "ons.gov.uk"]


def test_a_case_reads_empty_off_a_channel_that_has_not_been_written() -> None:
    """The order the graph runs in makes this the normal state, not an edge case.

    The source agent reads a state where ``conflicts`` is still empty, and the
    contradiction agent reads one where ``ruling`` is ``None``. Both go through
    :func:`cases`, so neither can be written in a way that only works when it runs last.
    """
    (case,) = cases(GraphState(claims=(claim(CLAIM),)))
    assert case.research is None
    assert case.sources == ()
    assert case.fact_checks == ()
    assert case.grading == ()
    assert case.conflicts == ()
    assert case.credibility_of(1) is None


def test_cases_is_empty_before_the_claim_agent_has_run() -> None:
    assert cases(GraphState()) == ()


def test_credibility_is_matched_by_ref_and_not_by_position() -> None:
    """A grading is a parallel tuple, and parallel is not the same as aligned.

    :func:`app.research.credibility.rate` returns one entry per source in the order it
    was given them, but :attr:`~app.domain.Credibility.ref` is what points at a source —
    and a judge that indexed by position would attribute one publisher's standing to
    another the first time anything reordered or filtered the list.
    """
    sources = (
        reported("https://reuters.com/a", ref=1),
        reported("https://theguardian.com/b", ref=2),
    )
    case = Case(index=0, claim=claim(CLAIM), grading=tuple(reversed(graded(sources))))
    for source in sources:
        found = case.credibility_of(source.ref)
        assert found is not None
        assert found.domain == source.domain


def test_an_indication_cannot_carry_a_weight_outside_its_scale() -> None:
    """Cheap, and it catches the mistake the field invites: 80 for four fifths."""
    with pytest.raises(ValueError, match="between 0 and 1"):
        Indication(agent="judge", bearing=Bearing.SUPPORTS, weight=80.0, detail="")
