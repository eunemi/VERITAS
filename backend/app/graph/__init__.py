"""The verification workflow: seven agents, one state, one ruling.

A claim is checked by seven steps, and this package is one module per step plus the
graph that orders them. What each does, in running order:

* :mod:`~app.graph.agents.claim` — reads the artifact, settles what will be checked
  and what will be searched for.
* :mod:`~app.graph.agents.search` — one fan-out across the configured providers.
* :mod:`~app.graph.agents.factcheck` — looks the claims up against the published
  fact-check databases. Concurrent with search; neither reads the other.
* :mod:`~app.graph.agents.evidence` — the join. Deduplicates, dates, and selects the
  passages that bear on each claim.
* :mod:`~app.graph.agents.source` — grades each source as a source, on the six axes
  of :mod:`app.domain.credibility`.
* :mod:`~app.graph.agents.contradiction` — looks for disagreement, between the claim
  and the retrieved text and between reviewers.
* :mod:`~app.graph.agents.judge` — decides, or declines to.

Two modules sit under all seven. :mod:`~app.graph.verdict` is the vocabulary;
:mod:`~app.graph.scoring` is the arithmetic — the 0–100 confidence on every finding,
assembled from source credibility, independent confirmation, supporting and
contradicting evidence, recency and contradictions, with each contribution published
beside the total rather than folded into it.

**Declining is a first-class outcome.** :class:`~app.graph.verdict.Judgement` has four
members and ``UNCERTAIN`` is one of them, reached through a sufficiency gate that runs
*before* any weighing: too few independent sources, nothing bearing on the claim, or
nothing pointing either way all return it, each with the reason recorded on
:attr:`~app.graph.verdict.ClaimRuling.insufficiency`. It is not a low confidence on a
truth scale, because "we could not establish this" is a different statement from "this
is somewhat false" and a scale from true to false has no room for the first.

The same rule holds on the five-point :class:`~app.graph.verdict.Assessment` a reader
sees. ``UNCERTAIN`` is not the band between ``MOSTLY_TRUE`` and ``MOSTLY_FALSE``: there
is no lean at which a claim slides into it. It is reached by failing a gate — nothing
pointing either way, a divided balance, or too little substance behind a one-sided
one — and the score beside it is confidence in the finding rather than a probability
that the claim is true, so a firmly refuted claim scores high.

**Only :mod:`~app.graph.workflow` imports LangGraph.** The state is a ``TypedDict`` of
plain tuples and every agent is a callable taking one and returning one, so an agent
can be tested by calling it with a dict — no graph, no runtime, no install. That is
also what keeps the agents composable: the graph decides the order, and no agent
reaches for another. Both halves of that rule are enforced by
``tests/test_graph_imports.py`` rather than left to review.
"""

from __future__ import annotations
