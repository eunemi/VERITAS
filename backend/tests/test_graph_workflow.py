"""The compiled graph: the shape of it, and the one path that needs no network.

Skipped without LangGraph installed — everything else in the package is tested by
calling agents with a dict, and ``test_graph_imports`` is what keeps that possible. This
module is the small remainder that can only be checked against the real runtime.

Two things are worth pinning here that no agent test can reach.

**The fan-out is one superstep.** ``claim`` has a single conditional edge naming both
gatherers, and ``evidence`` subscribes to both. That is the arrangement that makes
search and fact-check concurrent; two sequential edges would compile, run, produce the
same verdict, and cost the sum of two round trips instead of the slower one.

**The short circuit reaches the judge.** With nothing checkable in the artifact the
graph must skip both gatherers and still finish with a ruling. That path spends no
provider quota, so it is also the one end-to-end run this file can do honestly.
"""

from __future__ import annotations

import pytest

pytest.importorskip("langgraph", reason="the graph runtime is an optional dependency")

from app.core.config import Settings
from app.domain import Artifact, ArtifactKind
from app.graph import workflow
from app.graph.state import GraphState
from app.graph.verdict import Judgement
from tests.graph_bench import CLAIM, NOW, claim

#: Every agent, by the name it is registered under.
AGENTS = (
    "claim",
    "search",
    "factcheck",
    "evidence",
    "source",
    "contradiction",
    "judge",
)


class _NeverAsked:
    """A claim extractor that fails if the graph reaches it.

    The runs below are the ``CLAIM`` and ``URL`` kinds, neither of which extracts
    anything, and an extractor that raised would be a clearer failure than one returning
    an empty result — which is indistinguishable from prose with no claims in it.
    """

    async def extract(self, text: str) -> object:
        raise AssertionError(f"the extractor was called with {text!r}")


def compiled() -> object:
    return workflow.build(settings=Settings(), extractor=_NeverAsked())  # type: ignore[arg-type]


def test_every_agent_is_registered_under_its_own_name() -> None:
    """``NAME`` is the node name and the trace label, so a note cannot name a ghost."""
    nodes = set(compiled().get_graph().nodes)
    for name in AGENTS:
        assert name in nodes, name


def test_the_gatherers_are_one_fan_out_and_evidence_is_the_join() -> None:
    """The concurrency, read off the compiled edges rather than trusted."""
    edges = {(edge.source, edge.target) for edge in compiled().get_graph().edges}
    assert ("search", "evidence") in edges
    assert ("factcheck", "evidence") in edges
    assert ("search", "factcheck") not in edges
    assert ("factcheck", "search") not in edges
    assert ("evidence", "source") in edges
    assert ("source", "contradiction") in edges
    assert ("contradiction", "judge") in edges


def test_the_branch_fans_out_to_both_gatherers_when_there_is_something_to_gather() -> (
    None
):
    assert workflow._after_claim(GraphState(claims=(claim(CLAIM),))) == [
        "search",
        "factcheck",
    ]


def test_the_branch_short_circuits_to_the_judge_when_there_is_not() -> None:
    """No claims means no fan-out — a provider call to confirm there is nothing to ask."""
    assert workflow._after_claim(GraphState(claims=())) == ["judge"]


def test_the_thresholds_come_from_configuration() -> None:
    settings = Settings()
    limits = workflow.thresholds_from(settings)
    assert limits.min_sources == settings.JUDGE_MIN_SOURCES
    assert limits.min_standing == settings.JUDGE_MIN_STANDING
    assert limits.min_weight == settings.JUDGE_MIN_WEIGHT
    assert limits.contest_margin == settings.JUDGE_CONTEST_MARGIN


async def test_an_artifact_with_nothing_to_check_runs_end_to_end_and_declines() -> None:
    """A URL nothing has fetched: no claims, no providers touched, still a ruling.

    The whole graph, in the one configuration where running it makes no request — which
    is also the configuration a rating system gets wrong, since an artifact with no
    claims has nothing to refute and scores as unblemished.
    """
    graph = workflow.VerificationGraph(settings=Settings(), extractor=_NeverAsked())
    outcome = await graph.run(
        Artifact(kind=ArtifactKind.URL, url="https://example.com/a"), now=NOW
    )
    assert outcome.ruling.judgement is Judgement.UNCERTAIN
    assert not outcome.ruling.claims
    assert [note.agent for note in outcome.trace] == ["claim", "judge"]


async def test_a_run_holds_nothing_across_invocations() -> None:
    """One compiled graph serves concurrent requests, so no agent may keep state."""
    graph = workflow.VerificationGraph(settings=Settings(), extractor=_NeverAsked())
    artifact = Artifact(kind=ArtifactKind.URL, url="https://example.com/a")
    first = await graph.run(artifact, now=NOW)
    second = await graph.run(artifact, now=NOW)
    assert len(first.trace) == len(second.trace)
    assert first.ruling.rationale == second.ruling.rationale
