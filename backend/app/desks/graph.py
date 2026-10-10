"""Shared plumbing for the desks that run the verification graph.

Two desks end in the same place. The image desk recovers text and
sends it into the text pipeline; :class:`app.desks.factcheck.FactCheckDesk` *is* that
pipeline with nothing in front of it. None of them can import the graph at module
scope, for two separate reasons — compiling it imports langgraph, which is slow and is
paid at startup because ``app.desks`` imports every desk; and it reaches
``app.services``, which imports ``app.desks`` right back.

The rest of this module is the small amount of reading a graph :class:`Outcome` that
all three do identically: pairing the model's readings back to the claims they belong
to, and recording that a model was involved at all.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.core.errors import VeritasError
from app.domain import LedgerEntry
from app.graph.verdict import ClaimRuling
from app.reasoning.answer import Reasoning

if TYPE_CHECKING:
    from app.graph.workflow import VerificationGraph
    from app.reasoning import ReasoningLayer

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_GRAPH: tuple[Settings, VerificationGraph] | None = None


def compiled(settings: Settings) -> VerificationGraph:
    """The graph for ``settings``, compiled at most once.

    Cached against the identity of the settings object rather than a module flag:
    ``get_settings`` is itself cached, so a process compiles once, and a test that
    passes its own ``Settings`` gets a graph configured for that test instead of one
    built for production.
    """
    global _GRAPH

    with _LOCK:
        if _GRAPH is not None and _GRAPH[0] is settings:
            return _GRAPH[1]

        from app.graph.workflow import VerificationGraph
        from app.services.claims import ClaimExtractionService

        built = VerificationGraph(
            settings=settings,
            extractor=ClaimExtractionService(settings=settings),
            # The semantic judge already explains and cites each finding.
            reasoning=None,
        )
        _GRAPH = (settings, built)
        return built


def readings(
    rulings: Sequence[ClaimRuling], reasoning: Sequence[Reasoning]
) -> dict[int, Reasoning]:
    """Pair each ruled claim with the model's reading of it.

    By position, and only when the two line up.
    :meth:`app.graph.workflow.VerificationGraph._read` drops a claim it gathered
    nothing for, so a short tuple cannot be assigned to refs by index — and
    publishing one claim's reading against another claim is worse than publishing
    none of them.
    """
    if len(reasoning) != len(rulings):
        return {}
    return {
        ruling.ref: reading for ruling, reading in zip(rulings, reasoning, strict=True)
    }


def model_ledger(reasoning: Sequence[Reasoning]) -> tuple[LedgerEntry, ...]:
    """What the reasoning layer did, or nothing when it did not run.

    Refusals are counted rather than hidden. An ungrounded answer is the check in
    :mod:`app.reasoning.answer` doing its job, and a reader comparing two records
    needs to know which had prose from a model behind it and which fell back to the
    arithmetic.
    """
    if not reasoning:
        return ()

    model = next((r.model for r in reasoning if r.model), "unavailable")
    entries = [LedgerEntry("Model reading", model)]
    refused = sum(1 for r in reasoning if not r.grounded)
    if refused:
        entries.append(
            LedgerEntry("Readings not grounded", f"{refused} of {len(reasoning)}")
        )
    disputed = sum(1 for r in reasoning if r.disputed)
    if disputed:
        entries.append(LedgerEntry("Readings disputing the score", str(disputed)))
    return tuple(entries)


def _reasoning(settings: Settings) -> ReasoningLayer | None:
    """The reasoning layer, or none when this deployment cannot build one.

    ``REASONING_ENABLED`` defaults on and constructing the layer resolves an LLM
    client, which raises when no key is configured. Letting that reach the caller
    would take the entire graph down over the one part of it that is explicitly
    optional, so a deployment with no key loses prose rather than every desk.
    """
    from app.reasoning import build as build_reasoning

    try:
        return build_reasoning(settings)
    except VeritasError as exc:
        logger.warning("reasoning layer unavailable: %s", exc.message)
        return None
