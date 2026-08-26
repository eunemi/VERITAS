"""Reading a fact-checker's rating, and deciding whether their claim is your claim.

Two judgements live here, and they are here rather than in :mod:`app.factcheck` for the
reason the whole package exists: the clients that talk to a fact-check database are not
allowed to interpret what it says. This module has no network, no vendor knowledge and
no clock, so both judgements can be tested exhaustively with nothing installed.

**Is this rating a verdict, and which one?** :func:`read_stance` maps a publisher's own
words onto :class:`~app.domain.factcheck.Stance` through the table below, and returns
:attr:`~app.domain.factcheck.Stance.UNRECOGNISED` whenever it cannot do so honestly.

**Is this fact check about the claim that was asked?** Google's ``claims:search``
returns its best matches for a query, and its best match for a claim nobody has
reviewed is some other claim about the same subject. Presenting that as the verdict on
the caller's claim would fabricate the relevance — the same failure
:mod:`app.research.evidence` guards against for quotes — so :func:`select` scores the
database's wording of the claim against the caller's and drops what has nothing in
common with it.

The floor is deliberately *low*, and that needs justifying because a low floor looks
like carelessness. Both directions of error are harmful and they are not symmetric in
the way one would expect:

* Too permissive and the dossier attaches a stranger's verdict to the claim. But this
  is not the only defence against that, and not even the main one: the reviewed claim's
  own wording travels with the rating in
  :attr:`~app.domain.factcheck.ReviewedClaim.text`, so a mismatch is visible to a
  reader rather than hidden behind a score.
* Too strict and the service reports that no fact-checker has ruled on a claim when one
  has. That is a false statement about the world, it is invisible — an empty list looks
  the same either way — and it is the more dangerous of the two, because the natural
  next step for a reader is to conclude the claim is unexamined.

So the scoring's job is to catch the tail, not to re-rank Google, which has already
ranked. What makes the low floor safe is that :func:`app.research.evidence.assess`
returns ``None`` outright for a text sharing *no* entity, figure or keyword with the
claim, and that veto is the real filter; :data:`MIN_MATCH` only trims what clears it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.domain.claims import ExtractedClaim
from app.domain.factcheck import FactCheck, Review, ReviewedClaim, Stance
from app.research import terms
from app.research.evidence import Needle, assess

__all__ = ["MIN_MATCH", "NEGATORS", "VOCABULARY", "read_stance", "select"]

#: Overlap a database's claim wording needs with the caller's to be reported at all.
#:
#: 0.15 of the weighted total in :func:`app.research.evidence.assess`. On a claim with
#: two figures, two entities and four keywords the denominator is 15.0, so this asks
#: for roughly one entity, or one keyword plus a little word overlap — a floor that
#: removes the results Google returned because it had nothing better, and keeps
#: everything a person would call related. See the module docstring on why it is not
#: higher.
MIN_MATCH = 0.15

#: Words whose presence outside the matched phrase voids the reading.
#:
#: ``"Not entirely true"`` contains ``"true"``, and a table lookup that found it would
#: report the opposite of what the publisher wrote. Rather than enumerate the negated
#: forms — an open set, since this field is free text — any of these appearing in a
#: rating that is not itself a negated entry in :data:`VOCABULARY` sends the whole
#: rating to :attr:`~app.domain.factcheck.Stance.UNRECOGNISED`. Fails toward admitting
#: the rating could not be read, which costs a stance and never inverts one.
#:
#: Contracted negations are caught by suffix instead of listed, because
#: :func:`app.research.terms.words` keeps the apostrophe inside the token and there are
#: two of them in circulation — ``isn't`` and ``isn’t`` tokenise differently and both
#: occur.
NEGATORS = frozenset({"not", "no", "never", "nothing", "none", "hardly", "barely"})

#: The contracted-negation suffixes :data:`NEGATORS` cannot spell.
_CONTRACTED = ("n't", "n’t")

#: Publisher vocabulary, mapped once, reviewably.
#:
#: Every entry is a rating scheme this service can point at: PolitiFact's six ("True"
#: through "Pants on Fire"), the *Washington Post*'s Pinocchios, Snopes' set including
#: the two that are about *time* rather than truth, and the "Misleading" / "Partly
#: false" / "No evidence" vocabulary the wire agencies and the European
#: fact-checkers share.
#:
#: What is left out is as considered as what is in. "Missing context" is not a truth
#: rating — a claim can be true and missing context — and neither are "Labeled Satire",
#: "Altered photo" or "Legend". Those reach a reader as
#: :attr:`~app.domain.factcheck.Stance.UNRECOGNISED` with the publisher's word intact,
#: which says exactly as much as the publisher did.
#:
#: Two entries look redundant and are not. ``"originally true"`` and ``"was true"``
#: both contain ``"true"`` and both mean :attr:`~app.domain.factcheck.Stance.OUTDATED`;
#: without them, longest-match would find ``"true"`` and report the reverse of a rating
#: whose whole point is that the claim no longer holds.
VOCABULARY: dict[str, Stance] = {
    # ---------------------------------------------------------------- false ----
    "false": Stance.FALSE,
    "untrue": Stance.FALSE,
    "incorrect": Stance.FALSE,
    "not true": Stance.FALSE,
    "fake": Stance.FALSE,
    "fabricated": Stance.FALSE,
    "debunked": Stance.FALSE,
    "misattributed": Stance.FALSE,
    "pants on fire": Stance.FALSE,
    "four pinocchios": Stance.FALSE,
    "bottomless pinocchio": Stance.FALSE,
    # --------------------------------------------------------- mostly false ----
    "mostly false": Stance.MOSTLY_FALSE,
    "mostly inaccurate": Stance.MOSTLY_FALSE,
    "largely false": Stance.MOSTLY_FALSE,
    # "Misleading" is a negative verdict rather than a split one: it says the claim
    # leads a reader to a false conclusion, which is a finding about the claim and not
    # a division of it.
    "misleading": Stance.MOSTLY_FALSE,
    "three pinocchios": Stance.MOSTLY_FALSE,
    # ---------------------------------------------------------------- mixed ----
    "half true": Stance.MIXED,
    "partly false": Stance.MIXED,
    "partly true": Stance.MIXED,
    "partially false": Stance.MIXED,
    "partially true": Stance.MIXED,
    "mixture": Stance.MIXED,
    "mixed": Stance.MIXED,
    "two pinocchios": Stance.MIXED,
    # ---------------------------------------------------------- mostly true ----
    "mostly true": Stance.MOSTLY_TRUE,
    "mostly correct": Stance.MOSTLY_TRUE,
    "mostly accurate": Stance.MOSTLY_TRUE,
    "largely true": Stance.MOSTLY_TRUE,
    "one pinocchio": Stance.MOSTLY_TRUE,
    # ----------------------------------------------------------------- true ----
    "true": Stance.TRUE,
    "correct": Stance.TRUE,
    "accurate": Stance.TRUE,
    "verified": Stance.TRUE,
    # Snopes: the quote really was said by the person it is attributed to. A verdict
    # about an attribution claim, and a positive one.
    "correct attribution": Stance.TRUE,
    "geppetto checkmark": Stance.TRUE,
    # ------------------------------------------------------------ unsupported ----
    "unproven": Stance.UNSUPPORTED,
    "unsupported": Stance.UNSUPPORTED,
    "unsubstantiated": Stance.UNSUPPORTED,
    "unverified": Stance.UNSUPPORTED,
    "no evidence": Stance.UNSUPPORTED,
    "insufficient evidence": Stance.UNSUPPORTED,
    # ---------------------------------------------------------------- dated ----
    "outdated": Stance.OUTDATED,
    "originally true": Stance.OUTDATED,
    "was true": Stance.OUTDATED,
    "no longer true": Stance.OUTDATED,
}

#: :data:`VOCABULARY` as token tuples, longest phrase first.
#:
#: Longest-first is what makes ``"mostly false"`` beat ``"false"`` and
#: ``"correct attribution"`` beat ``"correct"``. Ties broken on the spelling so the
#: order is stable across processes — the ordering decides which phrase lands in
#: :attr:`~app.domain.factcheck.Review.stance_from`, and a response field that
#: depended on dict iteration luck would be untestable.
_PHRASES: tuple[tuple[tuple[str, ...], str, Stance], ...] = tuple(
    sorted(
        (
            (terms.words(terms.fold(phrase)), phrase, stance)
            for phrase, stance in VOCABULARY.items()
        ),
        key=lambda entry: (-len(entry[0]), entry[1]),
    )
)


def read_stance(rating: str) -> tuple[Stance, str]:
    """Read ``rating`` as a stance, with the phrase that produced it.

    Returns :attr:`~app.domain.factcheck.Stance.UNRECOGNISED` and ``""`` when the
    rating is not in the vocabulary, which is a normal outcome and not a failure — see
    :class:`~app.domain.factcheck.Stance`.

    Matching is on whole tokens, longest phrase first, so a rating is read by the most
    specific entry that fits it. Three things send an otherwise-matching rating back
    unread:

    * a :data:`NEGATORS` word outside the matched phrase, because ``"not entirely
      true"`` would otherwise read as ``TRUE``;
    * two entries of the same length disagreeing — ``"Partly true, partly false"``
      matches both, and either answer alone would be half the rating. The conflicting
      phrases are returned in place of the single one, joined by ``" / "``, so the
      response shows *why* it went unread;
    * an empty rating, since the database returning no rating is not the publisher
      declining to give one.
    """
    tokens = terms.words(terms.fold(rating))
    if not tokens:
        return Stance.UNRECOGNISED, ""

    best: list[tuple[tuple[str, ...], str, Stance]] = []
    for wanted, phrase, stance in _PHRASES:
        if not terms.subphrase(wanted, tokens):
            continue
        if best and len(wanted) < len(best[0][0]):
            break
        best.append((wanted, phrase, stance))

    if not best:
        return Stance.UNRECOGNISED, ""

    stances = {stance for _, _, stance in best}
    if len(stances) > 1:
        return Stance.UNRECOGNISED, " / ".join(phrase for _, phrase, _ in best)

    matched, phrase, stance = best[0]
    if _negated(tokens, matched):
        return Stance.UNRECOGNISED, ""
    return stance, phrase


def _negated(tokens: Sequence[str], matched: Sequence[str]) -> bool:
    """Whether a negator sits in ``tokens`` outside the matched phrase.

    ``"no evidence"`` contains its own negator and must survive; ``"not entirely
    true"`` does not and must not. Counting rather than set-testing, so that
    ``"not true, not false"`` — two negators, one of them inside the matched phrase —
    still fails.
    """
    outside = sum(1 for token in tokens if _is_negator(token))
    inside = sum(1 for token in matched if _is_negator(token))
    return outside > inside


def _is_negator(token: str) -> bool:
    return token in NEGATORS or token.endswith(_CONTRACTED)


def select(
    claim: ExtractedClaim,
    found: Iterable[ReviewedClaim],
    *,
    source: str,
    min_match: float = MIN_MATCH,
) -> tuple[FactCheck, ...]:
    """The fact checks in ``found`` that bear on ``claim``, closest wording first.

    Every kept record carries its :attr:`~app.domain.factcheck.FactCheck.match` and
    every review carries a read :attr:`~app.domain.factcheck.Review.stance`, so nothing
    downstream has to re-derive either and nothing downstream can derive them
    differently.

    A record with no reviews is dropped even if its wording matches perfectly: the
    claim being *in* a fact-check database is not a fact check, and reporting it as one
    would put a row in the dossier that a reader clicking through would find empty.

    The sort is on match descending, and it is a sort rather than a filter — dropping
    everything but the closest would throw away the second organisation that reviewed
    the same claim, which is the single most useful thing a lookup can return.
    """
    needle = Needle.of(claim)
    scored: list[tuple[float, int, FactCheck]] = []

    for position, record in enumerate(found):
        if not record.reviews:
            continue
        match = assess(needle, record.text)
        if match is None or match.score < min_match:
            continue
        scored.append(
            (
                match.score,
                position,
                FactCheck(
                    source=source,
                    claim=_read(record),
                    match=match.score,
                    matched_entities=match.entities,
                    matched_terms=match.terms,
                    matched_numbers=match.numbers,
                ),
            )
        )

    # Position as the tiebreak, so equal matches keep the database's own ranking
    # rather than an accident of iteration.
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    return tuple(check for _, _, check in scored)


def _read(record: ReviewedClaim) -> ReviewedClaim:
    """``record`` with every review's rating read into a stance.

    A copy rather than a mutation, because :class:`~app.domain.factcheck.ReviewedClaim`
    is frozen and because the original is what a client returned — keeping it intact
    means a test can assert that reading a rating changed nothing else.
    """
    reviews: list[Review] = []
    for review in record.reviews:
        stance, phrase = read_stance(review.rating)
        reviews.append(
            Review(
                publisher=review.publisher,
                site=review.site,
                url=review.url,
                rating=review.rating,
                title=review.title,
                language=review.language,
                reviewed_at=review.reviewed_at,
                date_text=review.date_text,
                stance=stance,
                stance_from=phrase,
            )
        )
    return ReviewedClaim(
        text=record.text,
        reviews=tuple(reviews),
        claimant=record.claimant,
        claimed_at=record.claimed_at,
        date_text=record.date_text,
    )
