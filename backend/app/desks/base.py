"""The contracts a desk implements.

Two of them, because the six desks do two different jobs. Five read the artifact
and file a report. The sixth — the decision desk — reads the other five's reports
and signs the record; ``src/lib/desks.ts`` states it plainly: "Reads: The five desk
records", "Does not: Re-examine the artifact itself". A single
``examine(artifact)`` contract cannot express that, and giving the adjudicator the
artifact anyway would quietly permit the one thing its charter forbids.

The report types these return are defined in :mod:`app.domain`, not here. That is
the one structural difference from :mod:`app.llm.base`, which owns its
:class:`~app.llm.Completion`: a verification holds its desks' reports, so
``app.domain`` would have to import this module while this module imports
``app.domain`` for :class:`~app.domain.Artifact` — an import cycle. The domain owns
the nouns; this file owns only the verbs.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.domain import Artifact, ArtifactKind, Desk, DeskReport


@runtime_checkable
class ArtifactDesk(Protocol):
    """Examines an artifact and files a report.

    Implementations raise from :mod:`app.core.errors` on failure — never a
    library-specific exception — so the orchestrator can record *why* a desk
    failed without knowing what it was built on.
    """

    #: Which desk this is. Identifies it in the roster, in logs, and on the wire.
    desk: Desk

    #: The artifact kinds it can read. The orchestrator never routes a desk an
    #: artifact outside this set, but declaring it here keeps the capability with
    #: the implementation rather than only in
    #: :data:`app.domain.enums.DEFAULT_DESKS`.
    kinds: frozenset[ArtifactKind]

    async def examine(
        self, artifact: Artifact, *, verification_id: str | None = None
    ) -> DeskReport:
        """Read ``artifact`` and return the findings.

        Called once per verification. Concurrency across desks is the
        orchestrator's decision, so an implementation should not assume it is
        alone and should not hold process-wide mutable state.

        ``verification_id`` is the record this examination belongs to, for a desk
        that writes rows of its own — :class:`app.desks.factcheck.FactCheckDesk`
        stores the dossier it gathered. Keyword-only and optional: a desk that
        persists nothing ignores it, and a caller exercising a desk on its own has
        no record to name. A desk must not read it back to find out what the other
        desks filed; that is the adjudicator's job and the reason it has its own
        contract.
        """
        ...


@runtime_checkable
class Adjudicator(Protocol):
    """Weighs the examining desks' reports and signs the record.

    Takes no artifact, deliberately. Its job is to reconcile findings — including
    findings that disagree — and a desk that could go back to the source would be
    a sixth examiner rather than the thing that decides between the other five.
    """

    desk: Desk

    async def adjudicate(self, reports: Sequence[DeskReport]) -> DeskReport:
        """Return the signed record from the reports filed so far.

        ``reports`` is in running order and may be short: when a desk fails, the
        adjudicator is still asked to decide on what did come in, because a
        partial record with an honest confidence is more use than none.
        """
        ...
