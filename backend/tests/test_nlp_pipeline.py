"""The extractor end to end, against a real parse.

Everything above :mod:`app.nlp` is tested against a stub, so this module is the only
place the four libraries are actually exercised together — and the only place the
claims about offsets can be checked rather than asserted. It is skipped without a
spaCy model, which means a checkout with no NLP stack still runs a green suite and
these are the tests that were not part of it. Worth remembering before trusting a
green run on a machine that cannot load the model.

The invariant this exists to defend is ``source[claim.start:claim.end] ==
claim.quote``. Everything downstream — highlighting a claim in a submission, showing a
desk what it is ruling on, letting a reader check the extractor did not paraphrase —
rests on it, and it is broken by any arithmetic slip anywhere in the package.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.domain import Extraction, Unfit
from app.nlp.pipeline import SpacyClaimExtractor

#: Five sentences over four lines, chosen so that every branch is reached once: a
#: headline with no finite verb, a coordinated sentence that must split in two, an
#: attributed report that must not, a question and a judgement.
ARTICLE = """Queensferry Crossing Opens

The Queensferry Crossing opened on 30 August 2017 and cost £1.35bn.
Transport Scotland said the bridge carries 24 million vehicles a year.
Is it the longest bridge in Scotland?
The view from the deck is magnificent."""

SENTENCE_COUNT = 5


@pytest.fixture
def extractor(settings: Settings) -> SpacyClaimExtractor:
    return SpacyClaimExtractor(settings)


def tuned(settings: Settings, **overrides: object) -> SpacyClaimExtractor:
    """An extractor with some settings changed, to check they are wired through."""
    return SpacyClaimExtractor(settings.model_copy(update=overrides))


# --------------------------------------------------------------- nothing to do ----
#
# These two need no model: `extract` answers before it loads one. They are the reason
# an empty submission is a 200 with an empty list rather than a 500.


async def test_empty_text_yields_an_empty_extraction(
    extractor: SpacyClaimExtractor,
) -> None:
    extraction = await extractor.extract("")

    assert extraction == Extraction(claims=(), entities=(), keywords=(), sentences=0)


async def test_whitespace_only_text_yields_an_empty_extraction(
    extractor: SpacyClaimExtractor,
) -> None:
    """The call :mod:`tests.test_claims_service` defers to this module to check.

    The service passes whitespace straight through rather than judging it, on the
    grounds that what counts as readable is the extractor's business. This is the
    extractor making that call.
    """
    extraction = await extractor.extract("   \n\t  \n ")

    assert extraction.claims == ()
    assert extraction.sentences == 0


# ------------------------------------------------------------------- the parse ----


async def test_it_finds_a_claim_in_every_sentence_and_more(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """"Support multiple claims" in its strongest form: more claims than sentences.

    Five sentences, and one of them coordinates two assertions, so a correct read
    returns six claims. An extractor that treated a sentence as a claim would return
    five and look almost right.
    """
    extraction = await extractor.extract(ARTICLE)

    assert extraction.sentences == SENTENCE_COUNT
    assert len(extraction.claims) > SENTENCE_COUNT


async def test_every_quote_is_lifted_from_the_submission(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """The invariant. Verbatim, by construction: the quote is a slice of the source."""
    extraction = await extractor.extract(ARTICLE)

    assert extraction.claims
    for claim in extraction.claims:
        assert ARTICLE[claim.start : claim.end] == claim.quote


async def test_offsets_are_ordered_and_within_the_text(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    extraction = await extractor.extract(ARTICLE)

    for claim in extraction.claims:
        assert 0 <= claim.start < claim.end <= len(ARTICLE)


async def test_refs_count_up_the_page(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """`ref` is what an annotation points at, so it has to follow the reader's eye.

    The splitter emits a coordinated sentence's second clause after its first but a
    relative clause's before, so the numbering is applied after a sort rather than as
    the pieces arrive.
    """
    extraction = await extractor.extract(ARTICLE)

    assert [claim.ref for claim in extraction.claims] == list(
        range(1, len(extraction.claims) + 1)
    )
    starts = [claim.start for claim in extraction.claims]
    assert starts == sorted(starts)


async def test_a_line_break_ends_a_sentence(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """Otherwise the headline runs into the body: "…Crossing Opens The Queensferry…".

    Punkt has no reason to break there — there is no full stop — so the boundary comes
    from :mod:`app.nlp.segment` treating a newline as a hard one.
    """
    extraction = await extractor.extract(ARTICLE)

    for claim in extraction.claims:
        assert "\n" not in claim.quote


# ------------------------------------------------------------------ the screen ----


async def test_unfit_sentences_are_returned_with_a_reason(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """Marked, not dropped: a client that shows only the checkable ones can, but a
    client that wants to explain the gap has what it needs."""
    extraction = await extractor.extract(ARTICLE)

    unfit = {claim.reason for claim in extraction.claims if not claim.checkable}
    assert Unfit.QUESTION in unfit
    assert Unfit.OPINION in unfit


async def test_reporting_is_checkable_and_judgement_is_not(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """The distinction the whole screen exists to draw, on adjacent sentences."""
    extraction = await extractor.extract(ARTICLE)
    by_reason = {claim.reason: claim.quote for claim in extraction.claims}

    checkable = [claim.quote for claim in extraction.checkable]
    assert any("Transport Scotland" in quote for quote in checkable)
    assert "magnificent" in by_reason[Unfit.OPINION]


async def test_the_minimum_length_reaches_the_screen(
    nlp_resources: object, settings: Settings
) -> None:
    """`CLAIM_MIN_TOKENS` is a setting, so something has to prove it is read."""
    extraction = await tuned(settings, CLAIM_MIN_TOKENS=200).extract(ARTICLE)

    assert extraction.checkable == ()
    assert Unfit.TOO_SHORT in {claim.reason for claim in extraction.claims}


# ---------------------------------------------------------------- the entities ----


async def test_entity_offsets_locate_the_entity(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """Entity offsets are shifted out of the per-sentence parse into the submission.

    This is where an off-by-one would hide: spaCy reports positions inside the ``Doc``
    it parsed, which here is one sentence, so every one of them is relative to a
    different origin until this package adds the sentence's own start.
    """
    extraction = await extractor.extract(ARTICLE)

    assert extraction.entities
    for entity in extraction.entities:
        assert ARTICLE[entity.start : entity.end] == entity.text
    for claim in extraction.claims:
        for entity in claim.entities:
            assert ARTICLE[entity.start : entity.end] == entity.text


async def test_a_claims_entities_lie_inside_it(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """Filtered by span, so a carried-in subject does not drag its entities along."""
    extraction = await extractor.extract(ARTICLE)

    for claim in extraction.claims:
        for entity in claim.entities:
            assert claim.start <= entity.start
            assert entity.end <= claim.end


async def test_document_entities_are_deduplicated(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """"Queensferry Crossing" is in the headline and the first sentence, once here."""
    extraction = await extractor.extract(ARTICLE)

    keys = [(entity.text.casefold(), entity.label) for entity in extraction.entities]
    assert len(keys) == len(set(keys))


# ---------------------------------------------------------------- the keywords ----


async def test_keywords_are_ranked_and_normalised(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    extraction = await extractor.extract(ARTICLE)

    assert extraction.keywords
    scores = [keyword.score for keyword in extraction.keywords]
    assert scores[0] == 1.0
    assert scores == sorted(scores, reverse=True)
    assert all(0 < score <= 1 for score in scores)


async def test_the_keyword_cap_reaches_the_ranking(
    nlp_resources: object, settings: Settings
) -> None:
    extraction = await tuned(settings, CLAIM_MAX_KEYWORDS=3).extract(ARTICLE)

    assert 0 < len(extraction.keywords) <= 3
    for claim in extraction.claims:
        assert len(claim.keywords) <= 3


async def test_no_claim_is_left_without_keywords_by_the_cap(
    nlp_resources: object, settings: Settings
) -> None:
    """The cap is applied per claim, after the sentence's ranking is narrowed to it.

    Capped the other way round the two halves of the coordinated sentence compete for
    one budget, and since every term in a short sentence ties — one occurrence, one
    sentence, so one weight — the alphabetical tie-break decides which half goes
    unrepresented. Every clause here has content words, so every clause has terms.
    """
    extraction = await tuned(settings, CLAIM_MAX_KEYWORDS=2).extract(ARTICLE)

    assert extraction.claims
    for claim in extraction.claims:
        assert claim.keywords, claim.quote
        assert len(claim.keywords) <= 2


async def test_a_claim_does_not_borrow_another_sentences_keywords(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """Rankings are per sentence, and each claim is filtered to its own clause.

    ``_extract`` walks ``docs`` and ``per_sentence`` by index, so a slip there would
    attach one sentence's terms to another's claims — which no offset test would
    catch, because every offset would still be right. The headline shares no content
    word with any other sentence, which makes it the one place the mistake is visible.
    """
    extraction = await extractor.extract(ARTICLE)
    headline = next(claim for claim in extraction.claims if "Opens" in claim.quote)

    borrowed = {"vehicle", "magnificent", "deck", "view", "million", "transport"}
    words = {word for keyword in headline.keywords for word in keyword.term.split()}
    assert not (words & borrowed)


# ------------------------------------------------------------------- the limit ----


async def test_the_sentence_ceiling_truncates_rather_than_fails(
    nlp_resources: object, settings: Settings
) -> None:
    """`CLAIM_MAX_SENTENCES` bounds the work a single request can cause.

    Truncation, not rejection: a submission over the ceiling still gets an answer
    about its opening, and ``sentences`` reports what was actually read so a client
    can tell that is what happened.
    """
    extraction = await tuned(settings, CLAIM_MAX_SENTENCES=2).extract(ARTICLE)

    assert extraction.sentences == 2
    assert extraction.claims
    # Nothing from the third sentence onwards, which begins after the second newline.
    third_line_start = ARTICLE.index("Transport Scotland")
    assert max(claim.end for claim in extraction.claims) <= third_line_start


# ------------------------------------------------------------------ determinism ----


async def test_the_same_text_reads_the_same_way_twice(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """Two requests for one submission must not disagree.

    The tie-breaking in the keyword ranking and the sort before numbering are both
    here for this. Without them the ordering follows dictionary iteration and a
    resubmission looks like the extractor changing its mind.
    """
    first = await extractor.extract(ARTICLE)
    again = await extractor.extract(ARTICLE)

    assert first == again


async def test_a_single_sentence_still_ranks_keywords(
    nlp_resources: object, extractor: SpacyClaimExtractor
) -> None:
    """One sentence means no document frequency, so this drives the fallback.

    Not an edge case — a single sentence is the commonest submission a fact-checking
    tool gets, and TF-IDF has nothing to say about it.
    """
    extraction = await extractor.extract(
        "The Queensferry Crossing opened on 30 August 2017."
    )

    assert extraction.sentences == 1
    assert len(extraction.claims) == 1
    assert extraction.claims[0].checkable is True
    assert extraction.keywords
    assert extraction.keywords[0].score == 1.0
