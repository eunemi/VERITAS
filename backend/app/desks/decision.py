"""The decision desk: read the other desks' reports and sign the record.

It re-examines nothing — see :mod:`app.desks.base` for why that is a separate contract
rather than a sixth examiner — and it does not merge the other desks' exhibits or
annotations into its own report. Those stay on the reports that produced them: each
desk numbers its refs from one, so a merged list would carry several exhibit 1s and a
reader following a citation would land on the wrong page.

What it does is choose which of the filed determinations the record publishes, and
:data:`GRAVITY` is that choice. Nothing here averages determinations together.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.core.config import Settings
from app.domain import Desk, DeskReport, Determination, LedgerEntry, Signal, Verdict

__all__ = ["DecisionDesk", "build"]

#: The order the record is read in: the first determination any desk filed wins.
#:
#: Three groups, and the ordering between them is the whole design. **Adverse**
#: findings come first, so a single desk finding a recording synthetic is never
#: averaged away by four desks finding nothing wrong. **INSUFFICIENT** comes next,
#: above every affirmative: a desk that established nothing is a veto on a record that
#: reads as verified, because "one desk confirmed it and another could not check it" is
#: not a confirmation. The **affirmatives** follow, strongest first, so a desk that
#: reached a finding is not drowned out by one that only reached a weaker one. And
#: REQUIRES_VERIFICATION is last precisely because it is not a finding: it is a desk
#: saying it has surfaced something for another desk to check, which must never
#: outrank what that other desk then found.
GRAVITY: tuple[Determination, ...] = (
    Determination.SYNTHETIC,
    Determination.CONTRADICTED,
    Determination.ANOMALOUS,
    Determination.CONTESTED,
    Determination.INSUFFICIENT,
    Determination.SUPPORTED,
    Determination.CONSISTENT,
    Determination.CLEAR,
    Determination.REQUIRES_VERIFICATION,
)

#: How the record's determination is stated to a reader. Restating it rather than
#: reusing a desk's own headline: the desk was describing its own finding, and a
#: record carrying two desks' findings should not be titled as though it carried one.
HEADLINES: dict[Determination, str] = {
    Determination.SYNTHETIC: "The artifact appears to have been generated",
    Determination.CONTRADICTED: "The evidence contradicts this",
    Determination.ANOMALOUS: "The artifact carries anomalies",
    Determination.CONTESTED: "The evidence is genuinely divided",
    Determination.INSUFFICIENT: "Not enough was established to rule",
    Determination.SUPPORTED: "The evidence supports this",
    Determination.CONSISTENT: "Consistent with what was gathered",
    Determination.CLEAR: "Nothing was found against this",
    Determination.REQUIRES_VERIFICATION: "Surfaced for checking, not yet checked",
}

NOTHING_FILED = "No desk filed a report"


class DecisionDesk:
    """Weighs the examining desks' reports and signs the record."""

    desk = Desk.DECISION

    async def adjudicate(self, reports: Sequence[DeskReport]) -> DeskReport:
        if not reports:
            return self._empty()

        filed = tuple(reports)
        determination = _governing(filed)
        deciding = tuple(r for r in filed if r.verdict.determination is determination)
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=determination,
                headline=HEADLINES[determination],
                rationale=_rationale(deciding, filed, determination),
                confidence=_confidence(deciding),
            ),
            ledger=_ledger(filed),
            signals=tuple(
                Signal(
                    label=_named(report.desk),
                    reading=report.verdict.determination.value,
                    weight=report.verdict.confidence,
                )
                for report in filed
            ),
        )

    def _empty(self) -> DeskReport:
        """Every examining desk failed, or none was rostered.

        Still a signed record rather than an error: the orchestrator has already
        stored why each desk failed, and a record that says nothing was established is
        more use to a reader than one stuck with no verdict on it at all.
        """
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=Determination.INSUFFICIENT,
                headline=NOTHING_FILED,
                rationale=(
                    "No examining desk returned findings, so there is nothing to "
                    "weigh and nothing has been established about this artifact."
                ),
                confidence=0.0,
            ),
            ledger=(LedgerEntry("Desks reporting", "0"),),
        )


def _governing(reports: Sequence[DeskReport]) -> Determination:
    """The determination the record publishes. See :data:`GRAVITY`."""
    filed = {report.verdict.determination for report in reports}
    return next(d for d in GRAVITY if d in filed)


def _confidence(deciding: Sequence[DeskReport]) -> float:
    """The mean confidence of the desks that filed the governing determination.

    Only those desks. A confident CLEAR from a desk reading how a caption is written
    is not evidence for or against a marginal CONTRADICTED from the desk that checked
    what it said, and averaging the two would let the first move the second.
    """
    return round(sum(r.verdict.confidence for r in deciding) / len(deciding), 4)


def _rationale(
    deciding: Sequence[DeskReport],
    filed: Sequence[DeskReport],
    determination: Determination,
) -> str:
    lead = (
        f"{_listed(_the(r.desk) for r in deciding)} filed {determination.value}. "
        f"{deciding[0].verdict.rationale}"
    )
    others = [r for r in filed if r.verdict.determination is not determination]
    if not others:
        return lead
    also = _listed(
        f"{_the(r.desk)} filed {r.verdict.determination.value}" for r in others
    )
    return f"{lead} Also on the record: {also}."


def _ledger(filed: Sequence[DeskReport]) -> tuple[LedgerEntry, ...]:
    return (
        LedgerEntry("Desks reporting", str(len(filed))),
        *(
            LedgerEntry(
                _named(report.desk),
                f"{report.verdict.determination.value} at "
                f"{round(report.verdict.confidence * 100)}%",
            )
            for report in filed
        ),
    )


def _named(desk: Desk) -> str:
    """``Desk.FACT_CHECK`` as "Fact-check desk", for a ledger key or a signal label."""
    return f"{desk.value.capitalize()} desk"


def _the(desk: Desk) -> str:
    return f"the {desk.value} desk"


def _listed(parts: Iterable[str]) -> str:
    items = list(parts)
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def build(settings: Settings | None = None) -> DecisionDesk:
    """Factory for the registry, which resolves desks with no arguments.

    Takes and ignores the settings every other desk factory needs, so that binding
    this one looks like binding any of them.
    """
    return DecisionDesk()
