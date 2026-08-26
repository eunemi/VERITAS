"""How much a *source* stands up as a source — never whether what it says is true.

This module exists because "score the sources" is the single most dangerous feature in
a fact-checking service, and the danger is not inaccuracy. It is that a plausible
number attached to a domain becomes an argument. Once ``bbc.co.uk`` scores 0.9,
everything on ``bbc.co.uk`` inherits the 0.9, a claim published there is 0.9 likely to
be true, and a service that set out to check claims has quietly started checking
mastheads instead. Every design decision below is a brace against that one failure.

**Nothing here is a truth value, and the types cannot express one.** This module
imports neither :class:`~app.domain.enums.Determination` nor
:class:`~app.domain.factcheck.Stance`, so there is no field on any type in it that
could carry a verdict — not accidentally, and not by a later edit that looked
reasonable. A :class:`Credibility` says *this publisher signs its work, holds the
record it is describing, dated the page, and is not a reprint of the source next to
it*. It says nothing whatever about the claim, and the arithmetic has no channel
through which it could.

**No domain is automatically anything.** There is a registry of publisher
*character* — see :mod:`app.research.registries` — and it grades none of its entries
for truthfulness. An entry says what kind of publisher a domain is: whether it holds
the official record, whether it republishes other people's work, whether it is
editorially independent of a government. Those are checkable facts about an
institution. "Reliable" is not one of them, which is why :class:`Role` has no such
member. Recognising a domain is worth a bounded amount and cannot on its own produce a
strong reading — :data:`MIN_AXES` is what makes that structural rather than a matter of
tuning.

**Six axes, reported separately, because they disagree.** The precedent is
:class:`~app.domain.verification.Exhibit`, which keeps ``relevance`` and
``reliability`` apart on the grounds that collapsing them hides the case a reader most
needs to see. The same holds here and more sharply: a government statistics agency is
maximally official and minimally independent of the government whose record it is
publishing; a first-hand blog post is maximally independent and anonymous. One number
for either would be a summary of nothing. :attr:`Credibility.standing` exists because
callers do need to order a list, and it is a mean over the axes that could be
assessed — with :attr:`Credibility.coverage` beside it, because a 1.0 drawn from one
axis out of six is not a strong source and must not read as one.

**An axis that could not be assessed says so.** :attr:`Reading.score` is ``None``
rather than 0.5, and the difference is the same one :attr:`Dossier.searched` draws: a
source with no stated date is not a source with a bad date, and a middling default
would make the two indistinguishable while looking like a measurement. Most of what a
reader would want to know about transparency — is there a byline, are there citations,
is there a corrections policy — requires fetching the page, which this service does
not do. So ``None`` here is common, and it is the design working.

**Every reading is itemised.** :class:`Observation` carries what was seen, which way
it bears, and how much it moved the axis, in the same spirit as
:attr:`~app.domain.research.Evidence.matched_numbers` and
:attr:`~app.domain.factcheck.Review.stance_from`: a number a reader cannot take apart
is a number they have to trust, and this is not a service that asks to be trusted.

The framing is borrowed from the Admiralty grading used in intelligence assessment,
which scores the *source* and the *information* on two separate scales precisely so
that a reliable source reporting something implausible stays legible as both. This
module is the first scale only. The second is the desks' job.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "BAND_MODERATE",
    "BAND_STRONG",
    "MIN_AXES",
    "Axis",
    "Band",
    "Credibility",
    "Direction",
    "Observation",
    "Reading",
    "Role",
]


class Axis(StrEnum):
    """The six things assessed about a source, each independently reportable.

    Declaration order is reporting order. The values are the wire strings.

    They are separate axes rather than inputs to one number because they routinely
    point in opposite directions for the same page, and every one of those cases is
    something a reader needs to see rather than have averaged away.
    """

    #: Whether anyone is *accountable* for what the page says: a masthead with an
    #: editorial chain, a named institution, a publisher that issues corrections.
    #: Explicitly not a track record of being right — this service has no way to
    #: measure that and any number claiming to would be invented.
    RELIABILITY = "reliability"
    #: Whether this publisher *holds the record* the claim is about. A statute on a
    #: legislature's own site, a filing on a regulator's, a figure on the statistics
    #: agency that computed it. Authority over the record is not authority over its
    #: interpretation, and this axis makes no claim to the second.
    OFFICIAL = "official"
    #: Whether the page says who published it and when, in a form that can be checked.
    #: Frequently unassessable without fetching the page; see the module docstring.
    TRANSPARENCY = "transparency"
    #: Whether the page substantiates anything — quotable passages bearing on the
    #: claim, carrying its figures rather than only its topic. Measured from what the
    #: search providers returned, so it is a statement about the retrieved text and
    #: not about the whole document.
    EVIDENCE = "evidence"
    #: Whether the publication date is known, on what basis, and how it sits against
    #: the moment of retrieval. Age alone never sinks this axis: a 2016 debunk is the
    #: reason a rumour is known to be false, and treating old as weak would discard
    #: the primary documents that settle most claims.
    DATE = "date"
    #: Whether this is an independent voice or another copy of one already counted —
    #: a wire report under a second masthead, a sibling title with the same owner, an
    #: aggregator reprinting someone else's reporting.
    INDEPENDENCE = "independence"


#: Declaration order, so every :class:`Credibility` reports its axes the same way.
ORDER: tuple[Axis, ...] = tuple(Axis)


class Role(StrEnum):
    """What kind of publisher a domain is. **Not how truthful it is.**

    Every member is a checkable fact about an institution — who owns it, what records
    it holds, whether it writes what it publishes. None of them is a grade, and the
    absence of a ``RELIABLE`` member is deliberate and load-bearing: there is no value
    in this enum that a scorer could read as "what this domain says is true".

    Several members *lower* an axis, and it is worth being precise about which axis and
    why, because the temptation is to read them as blocklist entries and they are not.
    :attr:`STATE_CONTROLLED` lowers :attr:`Axis.INDEPENDENCE` and can *raise*
    :attr:`Axis.OFFICIAL` on the same source — a ministry's own broadcaster is the
    authority on what the ministry announced and not an independent judge of whether it
    worked. :attr:`USER_GENERATED` lowers :attr:`Axis.RELIABILITY` because nobody is
    accountable for the text, not because the text is wrong; the most valuable source
    in a dossier is sometimes an eyewitness with no masthead behind them.
    """

    #: Holds the official record: a legislature, court, regulator, statistics agency,
    #: central bank, standards body. Raises :attr:`Axis.OFFICIAL`.
    OFFICIAL = "official"
    #: A repository of primary documents it did not itself author — a court-filing
    #: archive, a preprint server, a treaty depositary.
    REFERENCE = "reference"
    #: A wire service. Original reporting, and the origin of most syndication, so it
    #: bears on :attr:`Axis.INDEPENDENCE` for everything downstream of it.
    NEWS_AGENCY = "news_agency"
    #: A newsroom with a masthead, an editorial chain and a corrections process.
    #: Accountability, which is what :attr:`Axis.RELIABILITY` measures.
    ESTABLISHED_MEDIA = "established_media"
    #: An organisation whose published work is fact-checking. Noted rather than
    #: privileged: a fact-checker is a source like any other, which is the premise of
    #: :mod:`app.domain.factcheck`.
    FACT_CHECKER = "fact_checker"
    #: Editorially answerable to a government. Lowers :attr:`Axis.INDEPENDENCE`; see
    #: the class docstring on why that is not a truth finding.
    STATE_CONTROLLED = "state_controlled"
    #: Republishes other publishers' work. Lowers :attr:`Axis.INDEPENDENCE` because a
    #: reprint is not a second witness.
    AGGREGATOR = "aggregator"
    #: The host did not write it and does not vouch for it — a forum, a wiki, a social
    #: platform, a self-publishing service. Lowers :attr:`Axis.RELIABILITY` only.
    USER_GENERATED = "user_generated"


class Direction(StrEnum):
    """Which way an :class:`Observation` moves its axis."""

    RAISES = "raises"
    LOWERS = "lowers"
    #: Observed, bears on the axis, and moves it neither way — the reading that lets a
    #: response show that something *was* checked and found unremarkable, rather than
    #: leaving a reader unable to tell that from not having checked.
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class Observation:
    """One thing observed about a source, and how much it moved one axis.

    The itemisation behind every score. ``finding`` is a stable slug so a client can
    branch on it, ``detail`` is prose for a reader, and ``weight`` is how much of the
    axis this observation accounts for — so a reader can reconstruct the arithmetic
    instead of accepting it.

    The vocabulary of ``finding`` slugs is closed and lives in
    :mod:`app.research.credibility`, in one reviewable place, for the same reason
    :data:`app.research.reviews.VOCABULARY` does: a judgement made in scattered
    conditionals is a judgement nobody can audit.
    """

    axis: Axis
    #: Stable snake-case slug, e.g. ``"official_suffix"``, ``"syndicated_copy"``.
    finding: str
    direction: Direction
    #: Human-readable, and verbatim wherever it quotes the source.
    detail: str
    #: How much of the axis this observation accounts for, in ``[0, 1]``.
    weight: float

    def __post_init__(self) -> None:
        """Reject a weight outside 0–1.

        The same guard :class:`~app.domain.verification.Verdict` puts on
        ``confidence``, for the same reason: a frozen dataclass has no validators, and
        passing 60 for sixty percent is the one mistake this field invites.
        """
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"weight must be between 0 and 1, got {self.weight!r}")


@dataclass(frozen=True, slots=True)
class Reading:
    """One axis, scored or explicitly not.

    ``score`` is ``None`` when nothing available bears on this axis, and that is a
    reportable outcome rather than a gap — a source with no stated date is not a source
    with a bad date. A caller must read :attr:`assessed` before reading ``score``, the
    same way it reads :attr:`~app.domain.research.Dossier.searched` before reading an
    empty ``sources`` list.
    """

    axis: Axis
    #: ``[0, 1]``, or ``None`` when the axis could not be assessed at all.
    score: float | None
    #: What was observed, strongest first. Non-empty whenever ``score`` is not
    #: ``None``: a score with nothing behind it would be exactly the unaccountable
    #: number this module exists to avoid.
    observations: tuple[Observation, ...] = ()

    def __post_init__(self) -> None:
        """Reject a score outside 0–1, and a score with no observations behind it."""
        if self.score is not None and not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be between 0 and 1, got {self.score!r}")
        if self.score is not None and not self.observations:
            raise ValueError(
                f"{self.axis.value} was scored {self.score} with no observations. "
                "Every score must be itemised — see app.domain.credibility."
            )

    @property
    def assessed(self) -> bool:
        """Whether anything available bore on this axis."""
        return self.score is not None

    @property
    def raised(self) -> tuple[Observation, ...]:
        """The observations that moved this axis up."""
        return tuple(o for o in self.observations if o.direction is Direction.RAISES)

    @property
    def lowered(self) -> tuple[Observation, ...]:
        """The observations that moved this axis down."""
        return tuple(o for o in self.observations if o.direction is Direction.LOWERS)


class Band(StrEnum):
    """A coarse reading of :attr:`Credibility.standing`, for ordering a list.

    Four values rather than a number, because the number's precision is not real: the
    difference between 0.61 and 0.64 is arithmetic noise from which axes happened to be
    assessable, and a reader shown two decimal places will compare them anyway.

    :attr:`UNKNOWN` is not the bottom of the scale. It means no axis could be
    assessed — a page from an unrecognised domain with no date and no quotable
    passage — and a caller that renders it as "weak" has turned an absence of
    information into a negative finding about a publisher.
    """

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    UNKNOWN = "unknown"


#: Lowest :attr:`Credibility.standing` that reads as :attr:`Band.STRONG`.
BAND_STRONG = 0.70

#: Lowest :attr:`Credibility.standing` that reads as :attr:`Band.MODERATE`.
BAND_MODERATE = 0.40

#: Axes that must have been assessed before :attr:`Band.STRONG` is available.
#:
#: Four of six, and this is the structural half of "no domain is automatically true".
#: Recognising a domain in the registry moves :attr:`Axis.RELIABILITY`,
#: :attr:`Axis.OFFICIAL` and :attr:`Axis.INDEPENDENCE` — three axes, from one lookup,
#: on no evidence about the page itself. Without this floor a known masthead would
#: reach the top band on identity alone, which is the exact inference this module is
#: built to refuse. With it, a strong reading requires something observed about *the
#: page*: a date, or a passage that bears on the claim.
MIN_AXES = 4


@dataclass(frozen=True, slots=True)
class Credibility:
    """What can be said about one source's standing as a source.

    Points at a :class:`~app.domain.research.Source` by ``ref`` rather than being a
    field on it, and the separation is deliberate:
    :mod:`app.domain.research` documents that nothing in a dossier may be anything
    other than what a provider returned, and every number here is this service's
    judgement. Keeping them in parallel structures means a reader can see which is
    which without knowing how this application works — the same reason a fact check
    sits beside ``sources`` instead of inside it.

    ``readings`` always holds all six axes in :data:`ORDER`, including the ones that
    could not be assessed. A missing entry and an unassessable axis would otherwise be
    indistinguishable, and the second is much more common.
    """

    #: :attr:`app.domain.research.Source.ref`, so the two line up without an index.
    ref: int
    #: The source's registrable domain, repeated here so a credibility record is
    #: legible on its own — in a log line, or in a test failure.
    domain: str
    #: One entry per :class:`Axis`, in :data:`ORDER`.
    readings: tuple[Reading, ...]
    #: What the registry says this domain *is*, or ``None`` when it holds no entry.
    #:
    #: ``None`` is the common case and carries no penalty of its own: the registry is a
    #: few hundred domains and the web is not. An unrecognised domain is assessed on
    #: what can be seen about the page, which is how a first-hand account from a
    #: publisher nobody has heard of stays readable as evidence.
    role: Role | None = None

    def __post_init__(self) -> None:
        """Reject a record that does not report every axis exactly once."""
        seen = tuple(reading.axis for reading in self.readings)
        if seen != ORDER:
            raise ValueError(
                f"readings must hold every axis in order, got {[a.value for a in seen]}"
            )

    def reading(self, axis: Axis) -> Reading:
        """The reading for ``axis``. Always present; see :attr:`readings`."""
        return self.readings[ORDER.index(axis)]

    def score(self, axis: Axis) -> float | None:
        """Shorthand for ``self.reading(axis).score``."""
        return self.reading(axis).score

    @property
    def assessed(self) -> tuple[Axis, ...]:
        """The axes something bore on, in :data:`ORDER`."""
        return tuple(r.axis for r in self.readings if r.assessed)

    @property
    def unassessed(self) -> tuple[Axis, ...]:
        """The axes nothing available bore on."""
        return tuple(r.axis for r in self.readings if not r.assessed)

    @property
    def coverage(self) -> float:
        """How much of the source could be assessed at all, in ``[0, 1]``.

        Reported beside :attr:`standing` and meant to be read with it. A standing of
        1.0 at a coverage of 0.17 is one axis out of six agreeing with itself, and a
        client that shows the first without the second has published a strong claim
        about a source on the strength of a single observation.
        """
        return round(len(self.assessed) / len(ORDER), 4)

    @property
    def standing(self) -> float | None:
        """The mean of the assessed axes, or ``None`` when none could be assessed.

        Unweighted, and that is a decision rather than a default. Weighting the axes
        would encode a general answer to "what makes a source good", which has no
        general answer: officiality is nearly everything for a claim about what a
        statute says and close to irrelevant for a claim about what happened in a
        street. A caller with a claim in hand knows something this service does not,
        and the per-axis readings are published so that caller can weight them itself.

        A plain mean over *assessed* axes only — never over six with the unassessed
        ones counted as zero, which would make "we could not tell" arithmetically
        identical to "we looked and it was bad".
        """
        scores = [r.score for r in self.readings if r.score is not None]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 4)

    @property
    def band(self) -> Band:
        """:attr:`standing` as a coarse label, floored by how little was assessed.

        :attr:`Band.STRONG` requires :data:`MIN_AXES` assessed axes however high the
        mean is. That is what stops a recognised domain from reaching the top band on
        identity alone — see :data:`MIN_AXES`.
        """
        standing = self.standing
        if standing is None:
            return Band.UNKNOWN
        if standing >= BAND_STRONG and len(self.assessed) >= MIN_AXES:
            return Band.STRONG
        if standing >= BAND_MODERATE:
            return Band.MODERATE
        return Band.WEAK

    @property
    def observations(self) -> tuple[Observation, ...]:
        """Every observation across every axis, in :data:`ORDER`.

        For a caller that wants the whole itemisation without walking the readings —
        a log line, or a client rendering one list of reasons.
        """
        return tuple(o for reading in self.readings for o in reading.observations)
