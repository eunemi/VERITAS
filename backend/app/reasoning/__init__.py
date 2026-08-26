"""The reasoning layer: a language model's reading of a dossier, kept inside it.

:func:`build` is how the application gets one, and it returns ``None`` when
``REASONING_ENABLED`` is off — which is a supported configuration, not a degraded one.
The verdict, score and citations come from :mod:`app.graph` either way; this adds an
explanation of them.

Nothing here decides on its own authority. Read :mod:`app.reasoning.answer` for the
constraint the package is built around: the model chooses which rows of a closed table
to cite and how to read them, and every source, quote, figure and outlet published
beside a verdict comes from the dossier rather than from the model's output.
"""

from __future__ import annotations

from app.core.config import Settings
from app.llm import get_llm_client
from app.reasoning.answer import Reasoning, Ungrounded, read
from app.reasoning.brief import Brief, Exhibit, assemble, render
from app.reasoning.layer import SYSTEM, ReasoningLayer

__all__ = [
    "SYSTEM",
    "Brief",
    "Exhibit",
    "Reasoning",
    "ReasoningLayer",
    "Ungrounded",
    "assemble",
    "build",
    "read",
    "render",
]


def build(settings: Settings) -> ReasoningLayer | None:
    """The configured layer, or ``None`` when this deployment reasons without a model.

    Resolving the client here rather than in :class:`ReasoningLayer` is what keeps a
    missing key a startup-time :class:`~app.core.errors.ConfigurationError` for the
    caller that asked for a layer, instead of a per-claim failure inside one.
    """
    if not settings.REASONING_ENABLED:
        return None
    return ReasoningLayer(
        get_llm_client(settings),
        temperature=settings.REASONING_TEMPERATURE,
        max_tokens=settings.REASONING_MAX_TOKENS,
        max_exhibits=settings.REASONING_MAX_EXHIBITS,
    )
