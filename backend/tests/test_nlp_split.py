"""Splitting compound sentences.

Half of these assert that a split does *not* happen, and that is the point. The
splitter's failure mode is not missing a claim — that costs one coarse verdict — it
is manufacturing one, attaching evidence to a sentence nobody wrote, and reporting a
verdict on it. Each refusal below is a sentence where the obvious rule would do
exactly that.

Skipped without a spaCy model, since every case here is a claim about a dependency
parse and there is nothing to assert without one.
"""

from __future__ import annotations

import pytest

from app.nlp.resources import Resources
from app.nlp.split import _detokenize, clauses


def only_sentence(resources: Resources, text: str):
    """Parse ``text`` and return its first sentence."""
    return next(iter(resources.nlp(text).sents))


def texts(resources: Resources, text: str, offset: int = 0) -> list[str]:
    return [clause.text for clause in clauses(only_sentence(resources, text), offset)]


# ------------------------------------------------------------- it does split ----


def test_coordinated_verbs_become_two_claims(nlp_resources: Resources) -> None:
    found = texts(nlp_resources, "The bridge opened in March and cost £4bn.")

    assert len(found) == 2
    assert "The bridge opened" in found[0]
    # The subject is carried in: "and cost £4bn" is not a claim.
    assert found[1].startswith("The bridge cost")


def test_a_conjunct_with_its_own_subject_keeps_it(nlp_resources: Resources) -> None:
    """Nothing is carried when the second clause already says who it is about."""
    found = texts(nlp_resources, "The bridge opened in March and the tunnel closed.")

    assert len(found) == 2
    assert "tunnel closed" in found[1]
    assert "bridge" not in found[1]


def test_a_parenthetical_relative_clause_becomes_a_claim(
    nlp_resources: Resources,
) -> None:
    """ "The bridge, which cost £4bn, opened" does assert that the bridge cost £4bn."""
    found = texts(nlp_resources, "The bridge, which cost £4bn, opened in March.")

    assert len(found) == 2
    assert any(
        "bridge" in text and "4bn" in text and "which" not in text for text in found
    )
    # And the main clause reads without the removed words or their punctuation.
    assert any(text == "The bridge opened in March." for text in found)


# --------------------------------------------------------- it does not split ----


@pytest.mark.parametrize(
    ("sentence", "why"),
    [
        (
            "The bridge and the tunnel opened in March.",
            "coordinated nouns are one clause, not two",
        ),
        (
            "The bridge cost £4bn and the tunnel £2bn.",
            "the second verb is elided, so the conjunct is not a verb",
        ),
        (
            "The bridge did not open in March or cost £4bn.",
            "the negation scopes over both halves; splitting inverts the second",
        ),
        (
            "He said the bridge opened and cost £4bn.",
            "the conjunct is inside the complement, so the source asserts only the "
            "reporting",
        ),
        (
            "The people who signed the letter resigned.",
            "a restrictive relative picks out which people; removing it changes who "
            "the sentence is about",
        ),
        (
            "The report, which the minister signed, was leaked.",
            "the relative pronoun is the object, so lifting the clause would need it "
            "reordered",
        ),
    ],
)
def test_it_refuses_to_split(nlp_resources: Resources, sentence: str, why: str) -> None:
    assert len(texts(nlp_resources, sentence)) == 1, why


# --------------------------------------------------------------- invariants ----


SOURCES = [
    "The bridge opened in March and cost £4bn.",
    "The bridge, which cost £4bn, opened in March.",
    "The bridge and the tunnel opened in March.",
    "Network Rail said the line reopened on Tuesday.",
]


@pytest.mark.parametrize("source", SOURCES)
def test_every_clause_locates_itself_in_the_source(
    nlp_resources: Resources, source: str
) -> None:
    """The invariant every offset in the response rests on."""
    for clause in clauses(only_sentence(nlp_resources, source), 0):
        assert 0 <= clause.start < clause.end <= len(source)
        assert (
            source[clause.start : clause.end].strip()
            == source[clause.start : clause.end]
        )


@pytest.mark.parametrize("source", SOURCES)
def test_offsets_are_shifted_by_the_sentence_offset(
    nlp_resources: Resources, source: str
) -> None:
    """A sentence's offsets move with it, so nothing above this sees a local index."""
    plain = clauses(only_sentence(nlp_resources, source), 0)
    shifted = clauses(only_sentence(nlp_resources, source), 1000)

    assert [c.start + 1000 for c in plain] == [c.start for c in shifted]
    assert [c.end + 1000 for c in plain] == [c.end for c in shifted]


@pytest.mark.parametrize("source", SOURCES)
def test_clauses_come_back_in_reading_order(
    nlp_resources: Resources, source: str
) -> None:
    starts = [
        clause.start for clause in clauses(only_sentence(nlp_resources, source), 0)
    ]

    assert starts == sorted(starts)


def test_a_rewrite_is_punctuated_and_capitalised(nlp_resources: Resources) -> None:
    """The rewrite is prose a desk can read, not a token dump."""
    for text in texts(nlp_resources, "The bridge opened in March and cost £4bn."):
        assert text[0].isupper()
        assert text.endswith(".")
        assert "  " not in text
        assert " ," not in text


def test_each_clause_of_a_split_quotes_its_own_words(nlp_resources: Resources) -> None:
    """A sentence's full stop attaches to its root, so it survives the split.

    Measuring the main clause's span out to it would make that clause quote the whole
    sentence — conjunct included — and two claims would highlight the same text while
    claiming to be about different things. Punctuation is excluded from both ends of
    every span for this reason.
    """
    source = "The bridge opened in March and cost £4bn."
    found = clauses(only_sentence(nlp_resources, source), 0)
    quotes = [source[clause.start : clause.end] for clause in found]

    assert len(found) == 2
    assert quotes[0] == "The bridge opened in March"
    assert quotes[1] == "cost £4bn"
    assert len(set(quotes)) == len(quotes)


def test_a_parenthetical_leaves_no_orphaned_comma(nlp_resources: Resources) -> None:
    """The commas bracketing a parenthetical belong to it, and go with it.

    Left behind they mark a boundary that no longer exists: "The bridge, opened in
    March." Getting this wrong also strands the removed clause's whitespace, which is
    why the rewrite measures gaps in the source rather than reusing ``text_with_ws``.
    """
    found = texts(nlp_resources, "The bridge, which cost £4bn, opened in March.")

    assert "The bridge opened in March." in found


# ------------------------------------------------------- rewriting, no parser ----
#
# `_detokenize` is where a removed token's whitespace goes missing, and it reads three
# attributes of a token. Supplying those directly means these run without a model.


class FakeToken:
    """The three attributes :func:`_detokenize` reads, as spaCy exposes them."""

    def __init__(self, text: str, idx: int) -> None:
        self.text = text
        self.idx = idx
        self.is_punct = text in {",", ".", "!", "?", ";", ":", "(", ")", "[", "]"}


def rewrite(source: str, *keep: str) -> str:
    """Detokenize the given words of ``source``, matched left to right."""
    tokens: list[FakeToken] = []
    cursor = 0
    for word in keep:
        index = source.index(word, cursor)
        tokens.append(FakeToken(word, index))
        cursor = index + len(word)
    return _detokenize(tuple(tokens))


def test_a_gap_left_by_a_removed_token_becomes_one_space() -> None:
    """ "The bridge" + "cost £4bn" — 15 characters apart in the source, one space here.

    ``text_with_ws`` would give "The bridgecost £4bn" whenever the token holding the
    space was the one removed, which is exactly the case a split creates.
    """
    source = "The bridge, which cost £4bn, opened in March."

    assert (
        rewrite(source, "The", "bridge", "cost", "£", "4bn") == "The bridge cost £4bn."
    )


def test_adjacent_tokens_are_not_separated() -> None:
    """A currency symbol and its amount are two tokens and one word."""
    assert rewrite("cost £4bn", "cost", "£", "4bn") == "Cost £4bn."


def test_a_comma_left_against_the_terminator_is_removed() -> None:
    """ "…in March,." is what a split leaves behind when the sentence had a comma."""
    source = "The bridge opened in March, and cost £4bn."

    assert (
        rewrite(source, "The", "bridge", "opened", "in", "March", ",", ".")
        == "The bridge opened in March."
    )


def test_a_question_keeps_its_question_mark() -> None:
    """The terminator is preserved rather than replaced, so a question stays one."""
    source = "Why did the bridge cost £4bn?"

    assert (
        rewrite(source, "Why", "did", "the", "bridge", "cost", "£", "4bn", "?")
        == "Why did the bridge cost £4bn?"
    )


def test_a_lower_case_fragment_is_capitalised_and_stopped() -> None:
    assert rewrite("and cost £4bn", "cost", "£", "4bn") == "Cost £4bn."


def test_no_tokens_rewrites_to_nothing() -> None:
    assert _detokenize(()) == ""
