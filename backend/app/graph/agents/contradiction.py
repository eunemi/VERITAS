"""Looks for disagreement — between the claim and the text, and between reviewers."""

from __future__ import annotations

from app.domain import FactCheck, Source
from app.graph.state import AgentNote, GraphState
from app.graph.verdict import (
    FIGURE_CONFLICT_WEIGHT,
    NEGATION_CONFLICT_WEIGHT,
    REVIEWER_SPLIT_WEIGHT,
    Bearing,
    Indication,
)
from app.research import terms

NAME = "contradiction"

#: Words whose presence flips what a sentence asserts. Deliberately small and
#: hand-written: :data:`app.research.terms.STOPWORDS` keeps negations for exactly this
#: reason, so the set that matters is the one below rather than a linguistic resource.
NEGATIONS = frozenset(
    {
        "not",
        "no",
        "never",
        "nor",
        "denied",
        "denies",
        "deny",
        "false",
        "untrue",
        "incorrect",
        "debunked",
        "misleading",
    }
)


class ContradictionAgent:
    """Surfaces the ways the gathered material disagrees with the claim, or itself.

    There is no stance model here, so this does not read a passage's argument. It
    reads three things that can be checked mechanically, and each is weighted for how
    much it actually establishes:

    * a passage about the claim's subject that carries **different figures** and none
      of the claim's — the strongest of the three, because a rival number is a
      specific assertion rather than a tone;
    * a **negation** on one side of an otherwise-matching passage. Cheap and
      genuinely noisy — "critics said it was not enough" beside a matched figure
      trips it — so it is weighted below a figure conflict and never decides a claim
      alone;
    * **reviewers who disagreed** with each other about the same claim.

    The judge reads :attr:`app.domain.FactCheck.agreement` for the case where every
    reviewer said the same thing. This agent takes the opposite case — agreement is
    ``None`` because they split — so the two do not weigh the same reviews twice.
    """

    async def __call__(self, state: GraphState) -> GraphState:
        research = state.get("research", ())
        if not research:
            return GraphState(trace=(AgentNote(NAME, "nothing to compare"),))

        found = tuple(
            self._for_claim(record.claim, record.sources, record.fact_checks)
            for record in research
        )
        return GraphState(
            conflicts=found,
            trace=(
                AgentNote(NAME, f"{sum(len(f) for f in found)} conflict(s) found"),
            ),
        )

    def _for_claim(
        self,
        claim: str,
        sources: tuple[Source, ...],
        fact_checks: tuple[FactCheck, ...],
    ) -> tuple[Indication, ...]:
        figures = set(terms.numbers(claim))
        negated = _negated(claim)
        found: list[Indication] = []

        for source in sources:
            for passage in source.evidence:
                found.extend(
                    self._against(
                        passage.quote, source.domain, figures, negated, ref=source.ref
                    )
                )

        for check in fact_checks:
            if check.agreement is None and len({r.stance for r in check.reviews}) > 1:
                found.append(
                    Indication(
                        agent=NAME,
                        bearing=Bearing.REFUTES,
                        weight=REVIEWER_SPLIT_WEIGHT,
                        detail=(
                            f"{len(check.reviews)} reviewers of this claim did not "
                            f"agree with each other: "
                            f"{', '.join(sorted({r.rating for r in check.reviews}))}"
                        ),
                    )
                )
        return tuple(found)

    def _against(
        self,
        quote: str,
        domain: str,
        figures: set[str],
        negated: bool,
        *,
        ref: int | None = None,
    ) -> list[Indication]:
        quoted = set(terms.numbers(quote))
        shared = quoted & figures
        found: list[Indication] = []

        # A rival figure only counts when the passage carries none of the claim's. A
        # passage holding both is elaborating on the claim — "rates held at 4.75%,
        # down from 5.25%" — not disputing it.
        rival = {f for f in quoted if _comparable(f, figures)} - figures
        if figures and rival and not shared:
            found.append(
                Indication(
                    agent=NAME,
                    bearing=Bearing.REFUTES,
                    weight=FIGURE_CONFLICT_WEIGHT,
                    detail=(
                        f"{domain} carries {', '.join(sorted(rival))} where the claim "
                        f"states {', '.join(sorted(figures))}"
                    ),
                    ref=ref,
                )
            )
        elif shared and _negated(quote) != negated:
            found.append(
                Indication(
                    agent=NAME,
                    bearing=Bearing.REFUTES,
                    weight=NEGATION_CONFLICT_WEIGHT,
                    detail=(
                        f"{domain} matches the claim's figures but negates what the "
                        f"claim asserts about them"
                    ),
                    ref=ref,
                )
            )
        return found


def _negated(text: str) -> bool:
    return bool(NEGATIONS & set(terms.content_words(text)))


def _comparable(figure: str, against: set[str]) -> bool:
    """Whether ``figure`` is the same kind of quantity as anything in ``against``.

    Percentages compare with percentages and counts with counts. Without this a
    passage mentioning a year beside a claim about a rate reads as a conflict.
    """
    return any(figure.endswith("%") == other.endswith("%") for other in against)
