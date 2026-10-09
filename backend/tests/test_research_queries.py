"""The query ladder: what gets asked, and what deliberately does not.

Most of what follows is about the two refusals in
:mod:`app.research.queries`' docstring, because they are the assertions that
would otherwise decay. Adding ``fact check`` to a query measurably improves the
results a reviewer sees, so the reason it is absent has to be pinned down by a test
rather than left to whoever next tries to improve recall.

The rest checks that :attr:`~app.domain.research.ClaimResearch.queries` is a
reproducible record: the same claim yields the same strings in the same order, and
each of them is within the tightest limit any provider imposes, so the recorded
query is the one every engine was actually sent.
"""

from __future__ import annotations

import pytest

from app.research import queries, terms
from tests.research_bench import claim

#: The rate claim, with the four entity shapes the builder treats differently: a
#: multi-word name, a sub-phrase of it, a date, and a purely numeric one.
RATE = claim(
    "The Bank of England held its benchmark rate at 4.75% in March 2026.",
    entities=(
        ("Bank of England", "ORG"),
        ("England", "GPE"),
        ("March 2026", "DATE"),
        ("4.75%", "PERCENT"),
    ),
    keywords=(
        ("benchmark rate", 1.0),
        ("inflation", 0.8),
        ("monetary policy", 0.6),
        ("committee", 0.5),
        ("England", 0.45),
        ("services", 0.3),
    ),
)

#: What a claim looks like when the NLP extras are absent: text and nothing else.
UNANALYSED = claim("The rate was held at 4.75% in March 2026.")


def test_the_first_query_is_the_claim_itself() -> None:
    """The rung a reader checking the recorded queries will recognise."""
    assert queries.build(RATE)[0] == RATE.text


def test_the_ladder_runs_from_faithful_to_broad() -> None:
    """Three rungs: the sentence, its terms, its skeleton."""
    built = queries.build(RATE)

    assert len(built) == 3
    assert built[1] == (
        "Bank of England March 2026 4.75% 2026 benchmark rate inflation "
        "monetary policy committee"
    )
    assert built[2] == "Bank of England March 2026 4.75% 2026"


@pytest.mark.parametrize(
    "stance",
    [
        "fact check",
        "factcheck",
        "debunk",
        "hoax",
        "true",
        "false",
        "real",
        "fake",
        "myth",
        "verified",
        "misleading",
        "claim review",
    ],
)
def test_no_stance_word_is_added(stance: str) -> None:
    """The refusal that matters most, and the easiest one to undo by accident.

    Appending ``fact check`` genuinely does surface fact-checkers, which is why this
    is a test and not a comment: a search steered by a word this service chose
    returns evidence shaped by that choice, and the dossier would then be reporting
    on the query rather than on the claim.

    Checked against every claim in the module, so a stance word cannot be introduced
    on a rung that this file only exercises with one input.
    """
    for source in (RATE, UNANALYSED):
        for query in queries.build(source):
            words = query.casefold()
            assert stance not in words or stance in source.text.casefold()


def test_nothing_is_phrase_quoted() -> None:
    """Rung 1 is the extractor's rewrite — a string no publisher ever wrote.

    Quoting it would force exact-phrase matching and reliably return nothing, and
    the dossier would report the absence as a fact about the web.
    """
    for query in queries.build(RATE):
        assert '"' not in query
        assert "'" not in query.replace("’", "")


def test_no_operator_syntax_is_added() -> None:
    """No ``site:``, no ``-word``, no ``OR``. The claim's words, and nothing else."""
    for query in queries.build(RATE):
        assert "site:" not in query
        assert " OR " not in query
        assert not any(token.startswith("-") for token in query.split())


def test_every_query_word_comes_from_the_claim() -> None:
    """The general form of both refusals: no vocabulary is invented.

    Rung 1 is the claim, and rungs 2 and 3 are built from entities and keywords the
    extractor supplied — so every token in every query has to be traceable to one of
    those three, and nothing may appear that the claim did not contain.
    """
    allowed = set(terms.words(RATE.text))
    for keyword in RATE.keywords:
        allowed.update(terms.words(keyword.term))
    for entity in RATE.entities:
        allowed.update(terms.words(entity.text))

    for query in queries.build(RATE):
        assert set(terms.words(query)) <= allowed


def test_the_build_is_deterministic() -> None:
    """``queries`` is a record. A record that varies per run is not one."""
    assert queries.build(RATE) == queries.build(RATE)


def test_a_subphrase_entity_is_dropped_from_a_query() -> None:
    """``England`` adds nothing to a query already carrying ``Bank of England``.

    The character budget it would spend is a keyword that would have narrowed the
    search. Note this is the opposite of what :class:`app.research.evidence.Needle`
    does with the same entity — see
    ``test_a_subphrase_entity_is_kept_as_a_match_signal``.
    """
    skeleton = queries.build(RATE)[2]

    assert skeleton.count("England") == 1


def test_a_purely_numeric_entity_is_not_repeated() -> None:
    """``4.75%`` is already read off the text by :func:`app.research.terms.numbers`."""
    skeleton = queries.build(RATE)[2]

    assert skeleton.count("4.75%") == 1
    assert "4.75%" in terms.numbers(RATE.text)


def test_a_keyword_an_entity_already_carries_is_dropped() -> None:
    """``England`` is a keyword here and a word of an entity there. Once is enough."""
    terms_rung = queries.build(RATE)[1]

    assert terms_rung.count("England") == 1
    # The keyword it made room for.
    assert "committee" in terms_rung


def test_keywords_are_ordered_by_score_and_capped() -> None:
    """Four, and the four the extractor ranked highest."""
    terms_rung = queries.build(RATE)[1]

    assert terms_rung.endswith("benchmark rate inflation monetary policy committee")
    assert "services" not in terms_rung


def test_an_unanalysed_claim_gets_exactly_one_query() -> None:
    """No entities and no keywords is what a deployment without spaCy produces.

    One query, not three reformulations of the same words. The search is narrower
    and the recorded queries say so, which is the point: padding the list would make
    a thin search look thorough.
    """
    assert queries.build(UNANALYSED) == (UNANALYSED.text,)


def test_rungs_that_would_search_the_same_thing_collapse() -> None:
    """Same bag of words, whatever the order — one query, not two.

    A claim with an entity and no keywords builds rung 2 and rung 3 from the same
    tokens. Sending both spends a request per provider to receive the same pages,
    and inflates ``queries`` into a broader search than happened.
    """
    single = claim("Ofcom fined the broadcaster.", entities=(("Ofcom", "ORG"),))

    assert queries.build(single) == ("Ofcom fined the broadcaster.", "Ofcom")


def test_the_limit_is_honoured() -> None:
    assert len(queries.build(RATE, limit=2)) == 2
    assert len(queries.build(RATE, limit=1)) == 1
    assert queries.build(RATE, limit=0) == ()


def test_an_empty_claim_yields_no_queries() -> None:
    """Nothing to search for is not the same as searching for nothing."""
    assert queries.build(claim("   ")) == ()


def test_every_query_is_within_the_tightest_provider_limit() -> None:
    """Clamped here rather than at the wire, so all three engines get one string.

    Clamping per provider would send Brave a truncated query and Tavily the full
    one while ``queries`` recorded a single string that one of them never saw.
    """
    long_claim = claim(
        "The report said " + " ".join(f"finding{n}" for n in range(200)) + ".",
    )
    for query in queries.build(long_claim):
        assert len(query) <= queries.MAX_QUERY_CHARS
        assert len(query.split()) <= queries.MAX_QUERY_WORDS


def test_clamp_cuts_on_a_word_boundary() -> None:
    """Half of a name is a different term, matching a different set of pages."""
    assert queries.clamp("alpha beta gamma delta", chars=12) == "alpha beta"
    assert queries.clamp("alpha beta gamma delta", words=2) == "alpha beta"


def test_clamp_keeps_something_when_one_token_exceeds_the_budget() -> None:
    """A truncated token searches for the wrong thing; an empty query searches for
    nothing at all, and does it silently."""
    assert queries.clamp("x" * 30, chars=10) == "x" * 10


def test_clamp_leaves_a_query_within_budget_alone() -> None:
    assert queries.clamp("bank of england rate") == "bank of england rate"
