"""The judgement vocabulary the graph produces, and the thresholds it turns on.

Two scales, and they are not alternatives. :class:`Judgement` is the four-way channel
the desk boundary consumes; :class:`Assessment` is the five-point finding a reader sees,
carried on a :class:`Score` beside the 0–100 confidence that produced it. Both are
derived from the same weights by :mod:`app.graph.scoring`, which is the only module that
may build a :class:`Score` — one authority, so the number and the label cannot disagree.

Both are separate from :class:`app.domain.enums.Determination`, which is pinned to the
strings the frontend publishes in ``src/lib/types/agents.ts`` and has no ``UNCERTAIN``
member. :func:`as_determination` maps across at the desk boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain import Determination, Stance

__all__ = [
    "FIGURE_CONFLICT_WEIGHT",
    "NEGATION_CONFLICT_WEIGHT",
    "PASSAGE_WEIGHT",
    "REVIEWER_SPLIT_WEIGHT",
    "STANCE_WEIGHTS",
    "Assessment",
    "Bearing",
    "ClaimRuling",
    "Component",
    "Indication",
    "Judgement",
    "Ruling",
    "Score",
    "Thresholds",
    "as_determination",
]


class Judgement(StrEnum):
    """How the judge came down on a claim."""

    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    MIXED = "MIXED"
    #: The evidence gathered does not settle the claim either way. Not a weak
    #: SUPPORTED and not a soft REFUTED — a statement that the question is open.
    UNCERTAIN = "UNCERTAIN"


class Assessment(StrEnum):
    """The five-point finding published beside the score.

    Finer than :class:`Judgement` where the evidence decided the claim and coarser
    where it did not. Two claims can both be ``SUPPORTED`` on a nine-to-one weight and
    a three-to-two one, and which of those a reader is looking at is the thing they
    most want to know — hence the ``MOSTLY`` steps.

    ``UNCERTAIN`` is not the middle of the scale. It is what a claim gets when it never
    reached the scale at all: too little was gathered, or what was gathered points both
    ways. "We could not establish this" is a different sentence from "this is partly
    false", and :attr:`Score.insufficiency` carries which one applies.
    """

    TRUE = "TRUE"
    MOSTLY_TRUE = "MOSTLY_TRUE"
    UNCERTAIN = "UNCERTAIN"
    MOSTLY_FALSE = "MOSTLY_FALSE"
    FALSE = "FALSE"


class Bearing(StrEnum):
    """Which way one indication bears on a claim."""

    SUPPORTS = "supports"
    REFUTES = "refutes"


@dataclass(frozen=True, slots=True)
class Indication:
    """One directional signal, weighted, with the agent that produced it named."""

    agent: str
    bearing: Bearing
    weight: float
    detail: str
    #: The :attr:`app.domain.research.Source.ref` this came from, when it came from
    #: one page in particular. ``None`` for a published review — which is not in the
    #: dossier's source list — and for anything read across a claim as a whole. It is
    #: what lets a desk publish *which* page disagreed rather than only that one did,
    #: without re-deriving the finding from the passages a second time.
    ref: int | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"weight must be between 0 and 1, got {self.weight!r}")


@dataclass(frozen=True, slots=True)
class Component:
    """One named contribution to a score, beside the most it could have contributed.

    Published rather than folded in. A bare 58 is unreadable; 58 with its parts shows
    that the claim scored where it did because nothing recent confirmed it and not
    because something disputed it, and those call for opposite things from a reader.
    """

    name: str
    points: float
    #: The most this component could move the score, signed as ``points`` is — negative
    #: for a deduction. ``points / of`` is the share used, either way.
    of: float
    detail: str


@dataclass(frozen=True, slots=True)
class Score:
    """A 0–100 confidence, the five-point finding it supports, and the arithmetic.

    Produced by :mod:`app.graph.scoring` and by nothing else, so the score and the
    assessment cannot drift apart: the assessment is read off the score and the lean of
    the evidence together, never assigned alongside it.
    """

    #: 0–100. Confidence in the finding, not the probability the claim is true: a
    #: firmly refuted claim scores high.
    value: int
    assessment: Assessment
    components: tuple[Component, ...] = ()
    #: Why the claim could not be placed on the scale. Empty unless ``assessment`` is
    #: :attr:`Assessment.UNCERTAIN`, and never empty when it is.
    insufficiency: str = ""
    #: Set when the claim reached UNCERTAIN by being disputed rather than by being
    #: thinly evidenced. Both are UNCERTAIN on the five-point scale — neither is a
    #: position on it — but they are different findings, and this is what keeps
    #: :attr:`Judgement.MIXED` reachable from a five-value vocabulary that has no
    #: member for it.
    contested: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise ValueError(f"score must be between 0 and 100, got {self.value!r}")
        if (self.assessment is Assessment.UNCERTAIN) != bool(self.insufficiency):
            raise ValueError(
                f"UNCERTAIN requires a reason and a placed claim forbids one, got "
                f"{self.assessment.value} with {self.insufficiency!r}"
            )


@dataclass(frozen=True, slots=True)
class ClaimRuling:
    """The judge's finding on one claim, with the arithmetic behind it."""

    ref: int
    claim: str
    judgement: Judgement
    #: The same number as ``score.value``, on the 0–1 scale the rest of the domain
    #: uses — :attr:`app.domain.verification.Verdict.confidence` rejects anything else.
    confidence: float
    support: float = 0.0
    refute: float = 0.0
    indications: tuple[Indication, ...] = ()
    #: Why the evidence was insufficient. Empty unless ``judgement`` is
    #: :attr:`Judgement.UNCERTAIN`, and never empty when it is.
    insufficiency: str = ""
    score: Score | None = None


@dataclass(frozen=True, slots=True)
class Ruling:
    """The judge's finding on the artifact as a whole."""

    judgement: Judgement
    confidence: float
    headline: str
    rationale: str
    claims: tuple[ClaimRuling, ...] = ()
    score: Score | None = None


@dataclass(frozen=True, slots=True)
class Thresholds:
    """What the judge requires before it will rule on a claim at all.

    The sufficiency gate. Every field is a reason to return
    :attr:`Judgement.UNCERTAIN` rather than a weight in a score, which is what keeps
    "we could not tell" from being expressed as a middling number on a truth scale.
    """

    #: Independent sources — syndicated copies and repeat domains discounted — that
    #: must carry a passage bearing on the claim.
    min_sources: int = 2
    #: Lowest :attr:`app.domain.Credibility.standing` that counts toward the above.
    min_standing: float = 0.40
    #: Total indication weight below which nothing has been established either way.
    min_weight: float = 0.60
    #: Share of the total the losing side must reach for a claim to read as contested
    #: rather than settled.
    contest_margin: float = 0.30


#: How the graph's vocabulary reaches the wire. ``UNCERTAIN`` becomes
#: ``INSUFFICIENT``, which ``toneOf`` in ``src/lib/types/agents.ts`` already renders as
#: open rather than adverse — the frontend's own reading of an unresolved result.
_DETERMINATIONS: dict[Judgement, Determination] = {
    Judgement.SUPPORTED: Determination.SUPPORTED,
    Judgement.REFUTED: Determination.CONTRADICTED,
    Judgement.MIXED: Determination.CONTESTED,
    Judgement.UNCERTAIN: Determination.INSUFFICIENT,
}


def as_determination(judgement: Judgement) -> Determination:
    """``judgement`` in the vocabulary the API and frontend already share."""
    return _DETERMINATIONS[judgement]


#: Weight per fact-check stance, and which way it bears. This service's tariff for
#: somebody else's published review — not a verdict inherited from it. ``MIXED``,
#: ``UNSUPPORTED`` and ``UNRECOGNISED`` are absent: none of them points one way, and
#: a reviewer who could not settle the claim is not evidence that it is settled.
STANCE_WEIGHTS: dict[Stance, tuple[Bearing, float]] = {
    Stance.TRUE: (Bearing.SUPPORTS, 1.0),
    Stance.MOSTLY_TRUE: (Bearing.SUPPORTS, 0.7),
    Stance.FALSE: (Bearing.REFUTES, 1.0),
    Stance.MOSTLY_FALSE: (Bearing.REFUTES, 0.7),
}

#: One corroborating passage, before the source's standing scales it.
PASSAGE_WEIGHT = 0.8

#: A figure in the retrieved text that disagrees with the claim's own.
FIGURE_CONFLICT_WEIGHT = 0.8

#: A negation separating the claim from a passage that otherwise matches it.
NEGATION_CONFLICT_WEIGHT = 0.6

#: Reviewers who read the same claim and did not agree with each other.
REVIEWER_SPLIT_WEIGHT = 0.5
