"""The desk seam.

Six desks examine and adjudicate; five are built. This package holds the two
contracts (:mod:`app.desks.base`) and the registries each desk is bound into.
Adding one means writing a module here and binding its factory at the foot of this
file, the way :mod:`app.llm` and :mod:`app.nlp` bind theirs — the registration lives
with the registry so that importing the package is what makes a desk reachable, and
no caller has to remember to wire anything.

Two registries, mirroring :mod:`app.llm`, which carries ``llm_clients`` and
``embedders`` for the two capabilities of one seam.

There is deliberately **no** ``DESK_PROVIDER`` setting, and the difference is
worth stating so nobody adds one for symmetry: the four provider seams resolve a
single key chosen by *configuration* — one LLM serves the whole process — whereas
these registries resolve many keys chosen by the *request*, since which desks open
on an artifact is a property of the artifact. The key here is the desk, not the
vendor.

A desk module imports :mod:`app.services` and :mod:`app.repositories` *inside* the
method that needs them, never at module scope. ``app.services`` imports the
orchestrator, which imports this package to reach the registries below, so a
top-level import closes that loop and leaves whichever end was imported first
half-initialised. The lazy import is load-bearing, not a style choice.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.registry import ProviderRegistry
from app.desks.base import Adjudicator, ArtifactDesk
from app.desks.decision import DecisionDesk
from app.desks.decision import build as build_decision
from app.desks.factcheck import FactCheckDesk
from app.desks.factcheck import build as build_factcheck
from app.desks.image import ImageDesk
from app.desks.image import build as build_image
from app.desks.text import TextDesk
from app.desks.text import build as build_text
from app.domain import Desk

#: The five desks that read an artifact, keyed by which desk they are.
examiners: ProviderRegistry[Desk, ArtifactDesk] = ProviderRegistry("desk")

#: The desk that weighs the others and signs the record. A registry of its own
#: rather than a branch in the orchestrator, because the two have different
#: contracts; see :mod:`app.desks.base`.
adjudicators: ProviderRegistry[Desk, Adjudicator] = ProviderRegistry("adjudicator")

examiners.register(Desk.TEXT, build_text)
examiners.register(Desk.IMAGE, build_image)

examiners.register(Desk.FACT_CHECK, build_factcheck)
adjudicators.register(Desk.DECISION, build_decision)


def get_examiner(desk: Desk, settings: Settings | None = None) -> ArtifactDesk:
    """Return the desk that examines artifacts for ``desk``."""
    return (
        examiners.resolve(desk, settings)
        if settings is not None
        else examiners.resolve(desk)
    )


def get_adjudicator(desk: Desk) -> Adjudicator:
    """Return the desk that signs records for ``desk``."""
    return adjudicators.resolve(desk)


__all__ = [
    "Adjudicator",
    "ArtifactDesk",
    "DecisionDesk",
    "FactCheckDesk",
    "ImageDesk",
    "TextDesk",
    "adjudicators",
    "examiners",
    "get_adjudicator",
    "get_examiner",
]
