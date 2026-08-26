"""Reading a fact-checker's rating, and deciding whose claim it is.

Two judgements are under test and they fail in opposite directions.

:func:`~app.research.reviews.read_stance` fails by being *confident*. Its inputs are
free text written by hundreds of newsrooms with no shared scale, so the interesting
cases are all near-misses: ``"Not entirely true"`` contains ``"true"``, ``"Originally
True"`` means the claim is dead, ``"True but misleading"`` is two verdicts at once.
Every one of them has a reading that inverts the publisher's meaning, and getting an
inverted
verdict into a dossier is worse than getting none — so the tests below insist that the
answer is :attr:`~app.domain.factcheck.Stance.UNRECOGNISED` wherever the table cannot
answer honestly, and they treat that as a *success*, not a gap.

:func:`~app.research.reviews.select` fails by being *strict*. Reporting no fact checks
when fact checks exist is a false statement about the world that looks identical to the
true one, so the tests here pin the low floor deliberately: a review of a neighbouring
claim must survive with its score and the database's own wording attached, not be
silently dropped for scoring 0.64.

The vocabulary round-trip at the end is the drift guard. It is 45 cases and it exists
because the table is the one place in this codebase where a careless addition —
``"partly accurate"`` next to ``"accurate"`` — would change how an existing rating reads
without touching any code a reviewer would think to look at.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain import ReviewedClaim, Stance
from app.research.reviews import MIN_MATCH, VOCABULARY, read_stance, select
from tests.factcheck_bench import record, review
from tests.research_bench import claim

#: The claim every :func:`select` test scores against. Two entities, two keywords and
#: two figures, so each channel of :func:`app.research.evidence.assess` can be isolated
#: — and one keyword (``inflation``) that is deliberately *not* in the claim text, so
#: that even a word-for-word match scores below 1.0 for a legible reason.
RATE = claim(
    "The Bank of England held its benchmark rate at 4.75% in March 2026.",
    entities=(("Bank of England", "ORG"), ("March 2026", "DATE")),
    keywords=(("benchmark rate", 1.0), ("inflation", 0.8)),
)

#: A different central bank, the same figure and the same month. Scores well above the
#: floor while being a different assertion, which is the case
#: :attr:`~app.domain.factcheck.FactCheck.match` exists to make visible rather than to
#: suppress.
NEIGHBOUR = "The Federal Reserve held rates at 4.75% in March 2026."

#: Shares the subject and nothing else.
DISTANT = "The Bank of England cut rates."


# ------------------------------------------------------- reading the rating ----


@pytest.mark.parametrize(
    ("rating", "stance", "phrase"),
    [
        ("False", Stance.FALSE, "false"),
        ("Mostly false", Stance.MOSTLY_FALSE, "mostly false"),
        ("Half True", Stance.MIXED, "half true"),
        ("Mostly True", Stance.MOSTLY_TRUE, "mostly true"),
        ("TRUE", Stance.TRUE, "true"),
        ("Unproven", Stance.UNSUPPORTED, "unproven"),
        ("Pants on Fire!", Stance.FALSE, "pants on fire"),
        ("Four Pinocchios", Stance.FALSE, "four pinocchios"),
        ("Two Pinocchios", Stance.MIXED, "two pinocchios"),
        ("Geppetto Checkmark", Stance.TRUE, "geppetto checkmark"),
        ("This claim is misleading.", Stance.MOSTLY_FALSE, "misleading"),
    ],
)
def test_a_publisher_rating_reads_as_the_stance_it_means(
    rating: str, stance: Stance, phrase: str
) -> None:
    """Case, punctuation and surrounding prose do not change the reading.

    ``phrase`` is asserted alongside the stance because it is a response field: a
    reader auditing ``stance`` reads ``stance_from`` to see which table entry produced
    it, without needing the table.
    """
    assert read_stance(rating) == (stance, phrase)


def test_the_longest_phrase_wins_over_the_one_inside_it() -> None:
    """``"Mostly false"`` must not be read by the ``"false"`` entry.

    The whole table is written on the assumption that specificity beats brevity, and
    every negative rating in it contains a shorter positive one.
    """
    assert read_stance("Mostly false") == (Stance.MOSTLY_FALSE, "mostly false")
    assert read_stance("Largely true") == (Stance.MOSTLY_TRUE, "largely true")
    # Both map to TRUE, so this proves the *phrase*, not the stance: Snopes' verdict is
    # about an attribution and a response that credited it to `correct` would be
    # reporting a reading the table did not make.
    assert read_stance("Correct Attribution") == (Stance.TRUE, "correct attribution")


@pytest.mark.parametrize(
    "rating",
    ["Originally True", "Was true", "No longer true", "Outdated"],
)
def test_a_rating_about_time_is_never_read_as_true(rating: str) -> None:
    """The commonest shape of misinformation there is.

    Three of these contain ``"true"`` and all four mean the claim does not hold today.
    Reading any of them as :attr:`~app.domain.factcheck.Stance.TRUE` would hand a reader
    the reverse of a verdict whose entire point is that the claim expired.
    """
    stance, _ = read_stance(rating)
    assert stance is Stance.OUTDATED


@pytest.mark.parametrize(
    "rating",
    [
        "Not entirely true",
        "Isn't true",
        # Both apostrophes are in circulation and they tokenise differently. The
        # curly one survives `terms.fold` — NFKD does not map U+2019 to an ASCII
        # quote — so the suffix list has to spell both, and this is what says so.
        "Isn’t true",
        "Hardly accurate",
        "Nothing about this is correct",
        # Two negators, one of them inside the matched phrase. Counted rather than
        # set-tested, or this would read as FALSE.
        "Not true, not false",
    ],
)
def test_a_negator_outside_the_matched_phrase_voids_the_reading(rating: str) -> None:
    """Fails toward "could not read it", which costs a stance and never inverts one.

    The negated forms are an open set — this is free text — so they are vetoed rather
    than enumerated. ``stance_from`` is empty here on purpose: nothing was read, and
    naming the phrase that *almost* matched would invite exactly the inference the veto
    exists to prevent.
    """
    assert read_stance(rating) == (Stance.UNRECOGNISED, "")


@pytest.mark.parametrize(
    ("rating", "stance"),
    [
        ("Not true", Stance.FALSE),
        ("No evidence", Stance.UNSUPPORTED),
        ("Insufficient evidence", Stance.UNSUPPORTED),
        ("No longer true", Stance.OUTDATED),
    ],
)
def test_a_rating_whose_negator_is_its_own_reads_normally(
    rating: str, stance: Stance
) -> None:
    """The counterweight to the veto, and the reason it counts instead of testing.

    ``"No evidence"`` carries its negator inside the phrase that matched. A veto that
    fired on presence alone would send four real, common ratings to
    :attr:`~app.domain.factcheck.Stance.UNRECOGNISED` and lose the distinction between
    "nobody could establish this" and "we could not read the rating".
    """
    got, _ = read_stance(rating)
    assert got is stance


def test_two_conflicting_entries_of_the_same_length_are_left_unread() -> None:
    """A rating that is two verdicts at once is not either of them.

    Both phrases are returned in ``stance_from``, joined, because the response then
    shows *why* it went unread — which is more useful than an empty string and much
    more useful than whichever of the two happened to sort first.
    """
    stance, phrase = read_stance("True but misleading")

    assert stance is Stance.UNRECOGNISED
    assert phrase == "misleading / true"


def test_two_entries_of_the_same_length_that_agree_are_not_a_conflict() -> None:
    """``"Partly true, partly false"`` matches two entries that mean the same thing.

    Both are :attr:`~app.domain.factcheck.Stance.MIXED`, so there is nothing to
    reconcile and refusing to read it would throw away a rating this table covers.
    """
    stance, phrase = read_stance("Partly true, partly false")

    assert stance is Stance.MIXED
    assert phrase in VOCABULARY
    assert VOCABULARY[phrase] is Stance.MIXED


@pytest.mark.parametrize(
    "rating",
    [
        # Deliberate omissions from the table, each for its own reason: a claim can be
        # true and missing context; satire is a genre, not a truth value; an altered
        # photo is a finding about an image.
        "Missing context",
        "Labeled Satire",
        "Altered photo",
        "Miscaptioned",
        "Legend",
        "Research In Progress",
        # The vocabulary is English and does not pretend otherwise.
        "Falso",
        "Engañoso",
        "Verdadero",
        # No rating at all, and a scale this service cannot read.
        "",
        "   ",
        "3/5",
    ],
)
def test_a_rating_outside_the_vocabulary_is_unrecognised(rating: str) -> None:
    """Not a failure. See :class:`~app.domain.factcheck.Stance`.

    Every one of these reaches a reader with :attr:`~app.domain.factcheck.Review.rating`
    intact beside it, which says exactly as much as the publisher did — strictly more
    than a confident wrong answer would.
    """
    assert read_stance(rating) == (Stance.UNRECOGNISED, "")


@pytest.mark.parametrize("phrase", sorted(VOCABULARY))
def test_every_vocabulary_entry_reads_as_itself(phrase: str) -> None:
    """The drift guard, and the reason it is worth 45 cases.

    An entry that no longer reads as its own stance is not a broken test, it is a
    silently wrong response field — and the way that happens is an addition to the table
    rather than a change to the code, so nothing else in this suite would catch it. Two
    ways to trip it: a new entry that is a sub-phrase of this one with a different
    stance, and an entry containing a negator this one does not.
    """
    assert read_stance(phrase) == (VOCABULARY[phrase], phrase)


# ------------------------------------------------------- selecting the record ----


def test_the_databases_own_wording_of_the_claim_scores_highest() -> None:
    """And still not 1.0, for a reason that is in the response rather than hidden.

    Twelve of the thirteen available points: both figures, both entities, one of the two
    keywords and the full word overlap. ``inflation`` is a keyword of the claim that its
    own text does not contain, so nothing could earn that point — and the itemisation is
    reported precisely so a reader can see which channel is short rather than wondering
    what a 0.92 means.
    """
    found = select(RATE, [record(RATE.text)], source="google")

    assert len(found) == 1
    # Exact, not approximate: the score is rounded to four places by `assess` itself, so
    # a tolerance here would only be hiding a change in the arithmetic.
    assert found[0].match == round(12 / 13, 4)
    assert found[0].matched_numbers == ("4.75%", "2026")
    assert found[0].matched_entities == ("Bank of England", "March 2026")
    assert found[0].matched_terms == ("benchmark rate",)
    assert found[0].source == "google"


def test_a_review_of_a_neighbouring_claim_is_kept_and_scored() -> None:
    """The case this whole module is shaped around, and it must not be dropped.

    A different central bank, the same figure, the same month: a genuine fact check of a
    claim that is not the caller's. Dropping it would report that nobody has ruled on
    anything nearby; presenting it without its own wording would attribute a stranger's
    verdict to the caller's claim. So it is kept, it scores well below the word-for-word
    match, and ``claim.text`` says which claim was actually reviewed.
    """
    found = select(RATE, [record(NEIGHBOUR, review(rating="False"))], source="google")

    assert len(found) == 1
    assert found[0].claim.text == NEIGHBOUR
    assert MIN_MATCH < found[0].match < 0.8
    # The entity that makes it a different claim is the one it did not match.
    assert "Bank of England" not in found[0].matched_entities


def test_a_record_with_nothing_in_common_with_the_claim_is_dropped() -> None:
    """:func:`app.research.evidence.assess` returns ``None``, and that is the filter.

    What makes the low :data:`~app.research.reviews.MIN_MATCH` safe: a record sharing no
    entity, figure or keyword never reaches the threshold comparison at all.
    """
    assert select(RATE, [record("Vaccines cause autism.")], source="google") == ()


def test_records_are_ordered_by_match_regardless_of_the_order_they_arrived_in() -> None:
    found = select(
        RATE,
        [record(DISTANT), record(RATE.text), record(NEIGHBOUR)],
        source="google",
    )

    assert [check.claim.text for check in found] == [RATE.text, NEIGHBOUR, DISTANT]
    assert [check.match for check in found] == sorted(
        (check.match for check in found), reverse=True
    )


def test_an_equal_match_keeps_the_databases_own_ranking() -> None:
    """Position is the tiebreak, so nothing depends on an accident of iteration.

    Two organisations reviewing the same claim is the single most useful thing a lookup
    can return, and Google has already ranked them.
    """
    found = select(
        RATE,
        [
            record(RATE.text, review(publisher="PolitiFact")),
            record(RATE.text, review(publisher="FactCheck.org")),
        ],
        source="google",
    )

    assert [check.claim.reviews[0].publisher for check in found] == [
        "PolitiFact",
        "FactCheck.org",
    ]
    assert found[0].match == found[1].match


def test_the_floor_drops_the_tail_and_keeps_what_clears_it() -> None:
    """A sort, not a cut to one: the second reviewer is what a lookup is *for*."""
    records = [record(RATE.text), record(NEIGHBOUR), record(DISTANT)]

    assert len(select(RATE, records, source="google")) == 3
    assert len(select(RATE, records, source="google", min_match=0.5)) == 2
    assert select(RATE, records, source="google", min_match=1.0) == ()


def test_a_record_with_no_reviews_is_dropped_however_well_it_matches() -> None:
    """Being *in* a fact-check database is not a fact check.

    A perfect wording match with no review behind it would put a row in the dossier
    saying a verdict exists, which a reader clicking through would find empty.
    """
    unreviewed = ReviewedClaim(text=RATE.text, reviews=())

    assert select(RATE, [unreviewed], source="google") == ()


# --------------------------------------------------------- reading in place ----


def test_selecting_reads_every_rating_and_changes_nothing_else() -> None:
    """The clients may not interpret; this is the layer that does.

    Asserted field by field because the read is a rebuild of a frozen dataclass, and
    a rebuild is where a field quietly stops being copied.
    """
    when = datetime(2026, 3, 20, 9, 0, tzinfo=UTC)
    original = record(
        RATE.text,
        review(
            publisher="PolitiFact",
            site="politifact.com",
            url="https://politifact.com/factchecks/2026/mar/20/rate/",
            rating="Mostly false",
            title="No, the Bank did not hold",
            language="en",
            reviewed_at=when,
            date_text="2026-03-20T09:00:00Z",
        ),
        claimant="A Senator",
        claimed_at=when,
        date_text="2026-03-20T09:00:00Z",
    )

    read = select(RATE, [original], source="google")[0].claim
    got = read.reviews[0]

    assert got.stance is Stance.MOSTLY_FALSE
    assert got.stance_from == "mostly false"
    # The publisher's own string, untouched. `stance` sits beside it, never over it.
    assert got.rating == "Mostly false"
    assert got.publisher == "PolitiFact"
    assert got.site == "politifact.com"
    assert got.url == "https://politifact.com/factchecks/2026/mar/20/rate/"
    assert got.title == "No, the Bank did not hold"
    assert got.language == "en"
    assert got.reviewed_at == when
    assert got.date_text == "2026-03-20T09:00:00Z"
    assert read.claimant == "A Senator"
    assert read.claimed_at == when
    assert read.date_text == "2026-03-20T09:00:00Z"


def test_the_record_the_client_returned_is_left_alone() -> None:
    """A copy, not a mutation.

    Which means a test — or a cache, or a retry — can assert that reading a rating did
    nothing to what the database actually sent.
    """
    original = record(RATE.text, review(rating="Mostly false"))

    select(RATE, [original], source="google")

    assert original.reviews[0].stance is Stance.UNRECOGNISED
    assert original.reviews[0].stance_from == ""


def test_the_reviews_keep_the_order_and_count_the_database_gave_them() -> None:
    found = select(
        RATE,
        [
            record(
                RATE.text,
                review(publisher="PolitiFact", rating="Mostly false"),
                review(publisher="FactCheck.org", rating="False"),
                review(publisher="Full Fact", rating="Mixture"),
            )
        ],
        source="google",
    )

    assert [r.publisher for r in found[0].reviews] == [
        "PolitiFact",
        "FactCheck.org",
        "Full Fact",
    ]
    assert [r.stance for r in found[0].reviews] == [
        Stance.MOSTLY_FALSE,
        Stance.FALSE,
        Stance.MIXED,
    ]


# ------------------------------------------------------------- no aggregation ----


def test_reviewers_who_agree_report_agreement() -> None:
    found = select(
        RATE,
        [
            record(
                RATE.text,
                review(publisher="PolitiFact", rating="False"),
                review(publisher="FactCheck.org", rating="Untrue"),
            )
        ],
        source="google",
    )

    assert found[0].agreement is Stance.FALSE
    assert found[0].publishers == ("PolitiFact", "FactCheck.org")


@pytest.mark.parametrize(
    ("first", "second"),
    [
        # A genuine disagreement between two newsrooms.
        ("False", "Mostly true"),
        # One rating this service could not read. Not a majority of one.
        ("False", "Miscaptioned"),
        # Adjacent, and still not the same finding.
        ("False", "Mostly false"),
    ],
)
def test_reviewers_who_differ_report_no_agreement(first: str, second: str) -> None:
    """``None`` rather than a majority, and the reviews stay in the response.

    Taking a majority would let two syndicated copies of one wire story outvote the
    newsroom that did the reporting. All three of these cases mean the same thing to a
    caller — there is nothing here to lean on — and the ratings are still all there to
    be read.
    """
    found = select(
        RATE,
        [
            record(
                RATE.text,
                review(publisher="PolitiFact", rating=first),
                review(publisher="Snopes", rating=second),
            )
        ],
        source="google",
    )

    assert found[0].agreement is None
    assert [r.rating for r in found[0].reviews] == [first, second]
