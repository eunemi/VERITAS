"""Fact checks other people already published, and what this service makes of them.

A fact check is a *source*, not an oracle. Somebody read the claim, did the work, and
published a verdict — which is valuable and is also exactly what this service is for,
so treating one as the answer would be circular. Two organisations reviewing the same
claim reach different ratings often enough that "a fact check exists" and "the claim is
false" are separate facts, and the types here are shaped to keep them separate.

Three properties do that work, and each is a field rather than a convention:

**The reviewer's wording survives.** :attr:`Review.rating` is the publisher's own
string — ``"False"``, ``"Four Pinocchios"``, ``"Mixture"`` — never a normalised value
written over the top of it. Google's API documents that field with one sentence and no
enum ("Textual rating. For instance, 'Mostly false'."), which is an accurate
description of a field with thousands of distinct values in it.

**The reviewer's claim survives.** :attr:`ReviewedClaim.text` is how the *database*
worded the claim, which is not how the caller worded theirs. This is the field that
prevents the failure this module was designed against: a fact check of a similar but
different claim, presented as the verdict on the caller's claim, is a fabrication of
relevance even though every character in it is genuine. Carrying both wordings means a
reader sees "fact-checkers rated the claim *X* as False" rather than "your claim is
False", and can judge for themselves whether *X* is their claim.

**Anything derived is labelled as derived.** :attr:`Review.stance` is this service's
reading of a publisher's vocabulary, and :attr:`Review.stance_from` names the phrase
that produced it; :attr:`FactCheck.match` is this service's measure of how much the two
wordings share. None of them is the publisher's opinion, and a response that mixed them
in with the publisher's own fields would be attributing our arithmetic to them.

What is deliberately absent: any aggregate verdict on the claim. :attr:`FactCheck`
holds no ``verdict`` field, and :attr:`FactCheck.agreement` returns ``None`` the moment
the reviewers disagree rather than picking a winner among them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

__all__ = ["FactCheck", "Review", "ReviewedClaim", "Stance"]


class Stance(StrEnum):
    """This service's reading of a publisher's rating. **Not the publisher's word.**

    Fact-check ratings are free text with no shared scale — that is not a gap in
    Google's API, it is the state of the field. PolitiFact runs six ratings ending in
    "Pants on Fire", the *Washington Post* counts Pinocchios, Snopes has "Mixture" and
    "Miscaptioned" and "Legend". Reducing those to one axis is a judgement, and this
    enum exists so that the judgement is made once, in a reviewable table
    (:mod:`app.research.reviews`), instead of separately and invisibly by every desk
    that wants to know whether two reviewers agreed.

    :attr:`UNRECOGNISED` is the important member and it is not an error. A great many
    real ratings are not points on a true/false scale at all — "Missing context",
    "Labeled Satire", "Altered photo", "Correct Attribution" — and forcing one of them
    onto this axis would say something the publisher did not. A rating this service
    cannot read arrives here with :attr:`Review.rating` intact beside it, which is
    strictly more information than a confident wrong answer.

    The vocabulary is English. A Spanish or Portuguese rating — Google's database holds
    many, and ``languageCode`` filters requests rather than guaranteeing responses —
    reads as :attr:`UNRECOGNISED` rather than being guessed at.
    """

    FALSE = "false"
    MOSTLY_FALSE = "mostly_false"
    MIXED = "mixed"
    MOSTLY_TRUE = "mostly_true"
    TRUE = "true"
    #: Nobody could establish it either way — "Unproven", "No evidence". Distinct from
    #: :attr:`MIXED`, which says part of the claim is right: this says nothing is known.
    UNSUPPORTED = "unsupported"
    #: True once and not now — Snopes' "Outdated", "Originally True". The commonest
    #: shape of misinformation there is, and collapsing it into either
    #: :attr:`TRUE` or :attr:`FALSE` would lose the only interesting thing about it.
    OUTDATED = "outdated"
    #: The rating did not map onto this axis. See the class docstring.
    UNRECOGNISED = "unrecognised"


@dataclass(frozen=True, slots=True)
class Review:
    """One publisher's published review of one claim.

    Every field down to :attr:`date_text` is the database's, verbatim. The two below it
    are this service's and are documented as such.

    Missing values arrive as ``""`` and stay ``""``: Google marks no field of a
    ``ClaimReview`` as required, and this type follows the same rule as
    :class:`~app.search.base.SearchResult` — a field is populated only when the
    provider populated it. In particular :attr:`site` is never substituted for an
    absent :attr:`publisher`, because "this is who reviewed it" and "this is the host
    the review URL points at" are different assertions and only one of them was made.
    """

    #: ``publisher.name`` — the organisation, as it names itself.
    publisher: str
    #: ``publisher.site`` — the host, no scheme and no ``www``, derived by Google from
    #: the review URL. Kept alongside :attr:`publisher` rather than parsed out of
    #: :attr:`url` here, so the value is the database's rather than this
    #: application's; :mod:`app.research.urls` derives its own host when identity
    #: matters.
    site: str
    #: The review itself. The receipt: without it a rating is an assertion this
    #: service cannot substantiate, which is why a review lacking one is dropped.
    url: str
    #: The publisher's rating, exactly as worded. May be ``""`` when the database
    #: returned a review with no rating on it — which is not the same as a publisher
    #: declining to rate, and is why this is not turned into a
    #: :attr:`Stance.UNRECOGNISED` and left at that.
    rating: str
    #: The review's headline, present only "if it can be determined" per Google.
    title: str = ""
    #: BCP-47, as reported. Ratings are only read as English; see :class:`Stance`.
    language: str = ""
    #: When the review was published, parsed from :attr:`date_text`.
    reviewed_at: datetime | None = None
    #: The database's date string, verbatim, kept even when it would not parse — an
    #: unparseable date is still information about the review, and dropping it would
    #: hide the parser gap that caused :attr:`reviewed_at` to be ``None``.
    date_text: str | None = None

    # ---- derived by this service, not by the publisher ----

    #: Where :attr:`rating` falls on :class:`Stance`, per :mod:`app.research.reviews`.
    #:
    #: Defaulted rather than required because a wire client must not set it: reading a
    #: rating is a judgement, and the clients in :mod:`app.factcheck` are the layer
    #: that is not allowed to make judgements. Every :class:`Review` that reaches a
    #: response has passed through :func:`app.research.reviews.select`, which fills
    #: this in.
    stance: Stance = Stance.UNRECOGNISED
    #: The vocabulary phrase that produced :attr:`stance`, so the mapping can be
    #: audited from the response without reading the table. ``""`` when nothing
    #: matched; two phrases joined by ``" / "`` when the rating matched conflicting
    #: entries and was therefore left :attr:`Stance.UNRECOGNISED`.
    stance_from: str = ""


@dataclass(frozen=True, slots=True)
class ReviewedClaim:
    """A claim as a fact-check database holds it, and the reviews published on it.

    Claim-major rather than review-flat because that is the shape of the answer:
    several organisations reviewing one claim is the interesting case, and flattening
    it would repeat the claim text once per review and lose which reviews were about
    the same claim.
    """

    #: How the *database* words the claim. Not the caller's wording, and not a
    #: paraphrase of it — see the module docstring on why the difference matters.
    text: str
    #: Every review the database holds for this claim, in the order it returned them.
    reviews: tuple[Review, ...]
    #: Who the database says made the claim. Often a name, sometimes an outlet,
    #: sometimes ``""``.
    claimant: str = ""
    #: When the claim was made, parsed from :attr:`date_text`. Worth surfacing on its
    #: own: a 2019 claim resurfacing in 2026 is the commonest thing a fact-check
    #: lookup finds, and the review date alone does not show it.
    claimed_at: datetime | None = None
    #: The database's claim-date string, verbatim. Kept on a failed parse, as on
    #: :attr:`Review.date_text`.
    date_text: str | None = None


@dataclass(frozen=True, slots=True)
class FactCheck:
    """A database record that bears on the claim under check, and how closely.

    The nesting is the honesty mechanism: everything the database said is inside
    :attr:`claim`, and everything this service concluded is beside it. A reader — or a
    desk, or a reviewer auditing a response — can tell which is which without knowing
    anything about how this application works.
    """

    #: Which database this came from, e.g. ``"google"``.
    source: str
    #: The database's record, verbatim.
    claim: ReviewedClaim
    #: How much of the claim under check :attr:`ReviewedClaim.text` repeats, on the
    #: same 0–1 scale and the same four channels as
    #: :attr:`app.domain.research.Evidence.score`, so the two are comparable.
    #:
    #: This is a lexical measure, not a relevance judgement, and it is reported rather
    #: than used to make the fact check speak louder. Its one job is to let a reader
    #: see when a fact check is about a *neighbouring* claim: two claims sharing a year
    #: and a topic score well above zero while being different assertions, so a high
    #: number is not a licence to read :attr:`Review.rating` as the verdict on the
    #: caller's claim. That is what :attr:`ReviewedClaim.text` is for.
    match: float
    #: Which of the claim's entities, terms and figures :attr:`ReviewedClaim.text`
    #: actually repeats — the arithmetic behind :attr:`match`, itemised.
    matched_entities: tuple[str, ...] = ()
    matched_terms: tuple[str, ...] = ()
    matched_numbers: tuple[str, ...] = ()

    @property
    def reviews(self) -> tuple[Review, ...]:
        """Shorthand for :attr:`ReviewedClaim.reviews`."""
        return self.claim.reviews

    @property
    def publishers(self) -> tuple[str, ...]:
        """Distinct publisher names, in the order they were returned.

        Names, because that is what a reader recognises. Counting *independent*
        reviewers is a different question — two names can be one newsroom — and
        answering it belongs with the rest of the independence logic in
        :mod:`app.research.dedupe`, not here.
        """
        seen: list[str] = []
        for review in self.reviews:
            if review.publisher and review.publisher not in seen:
                seen.append(review.publisher)
        return tuple(seen)

    @property
    def agreement(self) -> Stance | None:
        """The one stance every review shares, or ``None``.

        ``None`` covers three genuinely different situations — the reviewers
        disagreed, at least one rating could not be read, or there are no reviews —
        and that is deliberate: all three mean the same thing to a caller, which is
        that there is nothing here to lean on. Returning a majority instead would let
        two syndicated copies of one wire story outvote the outlet that did the
        reporting.

        Even when this is not ``None`` it is agreement *among reviewers*, on this
        service's reading of their vocabulary, about the claim as
        :attr:`ReviewedClaim.text` words it. It is not a verdict on the caller's
        claim, and nothing in this codebase turns it into one.
        """
        stances = {review.stance for review in self.reviews}
        if len(stances) != 1:
            return None
        stance = stances.pop()
        return None if stance is Stance.UNRECOGNISED else stance
