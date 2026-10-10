"""Screening clauses for checkability.

One case per :class:`~app.domain.Unfit` reason, a control that passes, and two tests
about the *order* the rules run in — because most unfit sentences trip more than one
rule and the reason reported is the one a person reads.

The line these tests are really guarding is the one in the module docstring: this
screen decides whether evidence *bears* on a sentence, never whether the sentence is
true. Hence :func:`test_a_false_claim_is_still_checkable`. A screen that quietly
rejected implausible assertions would look like it was working right up until it
dropped the one claim worth checking.
"""

from __future__ import annotations

import pytest

from app.domain import Unfit
from app.nlp.resources import Resources
from app.nlp.screen import screen
from app.nlp.split import Clause, clauses

#: The production default, so these read against the configured behaviour.
MIN_TOKENS = 4


def only_clause(resources: Resources, text: str) -> Clause:
    """The single clause of a single sentence."""
    sentence = next(iter(resources.nlp(text).sents))
    found = clauses(sentence, 0)
    assert len(found) == 1, f"expected one clause, got {[c.text for c in found]}"
    return found[0]


def verdict(resources: Resources, text: str, *, min_tokens: int = MIN_TOKENS):
    return screen(only_clause(resources, text), min_tokens=min_tokens)


# ------------------------------------------------------------------ it passes ----


@pytest.mark.parametrize(
    "sentence",
    [
        "The Queensferry Crossing opened in August 2017.",
        "Network Rail said the line reopened on Tuesday.",
        "The council plans to widen the road next year.",
        "Eleven people died when the walkway collapsed.",
        "The report was leaked to the Financial Times in March.",
    ],
)
def test_a_reportable_assertion_is_checkable(
    nlp_resources: Resources, sentence: str
) -> None:
    checkable, reason = verdict(nlp_resources, sentence)

    assert checkable is True
    assert reason == ""


@pytest.mark.parametrize(
    "sentence",
    [
        "The talks collapsed after eleven days.",
        "The inquiry blamed the council for the deaths.",
        "The scheme failed to deliver a single home.",
    ],
)
def test_a_negative_sentence_is_still_checkable(
    nlp_resources: Resources, sentence: str
) -> None:
    """The reason ``opinion_lexicon`` is not used anywhere in this package.

    "collapsed", "died", "failed", "blamed" are the most negative words in a newsroom
    and the most worth checking. A sentiment lexicon scores every one of these as
    opinion and rejects them, which is why this package does not use one.
    """
    checkable, reason = verdict(nlp_resources, sentence)

    assert checkable is True
    assert reason == ""


def test_a_false_claim_is_still_checkable(nlp_resources: Resources) -> None:
    """Checkability is not plausibility. The desk decides; this does not."""
    checkable, reason = verdict(nlp_resources, "The Moon is made of cheese.")

    assert checkable is True
    assert reason == ""


def test_a_hyphenated_named_subject_is_not_rejected_as_too_short(
    nlp_resources: Resources,
) -> None:
    """Short news headlines often contain a hyphenated proper name."""
    checkable, reason = verdict(nlp_resources, "Chandrayaan-3 landed on Mars.")

    assert checkable is True
    assert reason == ""


# ------------------------------------------------------------------ it refuses ----


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Photo by Reuters.", Unfit.FRAGMENT),
        ("More on this story.", Unfit.FRAGMENT),
        ("It rained.", Unfit.TOO_SHORT),
        ("Why did the bridge cost £4bn?", Unfit.QUESTION),
        ("Read the full report on our website.", Unfit.IMPERATIVE),
        ("The new bridge is beautiful.", Unfit.OPINION),
        ("I think the figure is wrong.", Unfit.OPINION),
        ("Obviously the minister knew about the delay.", Unfit.OPINION),
        ("The tunnel will open in April 2027.", Unfit.PREDICTION),
        ("The bridge would have cost £4bn.", Unfit.HYPOTHETICAL),
        ("If the bridge opens in March, the tunnel closes.", Unfit.HYPOTHETICAL),
        ("The minister for transport commented.", Unfit.ATTRIBUTION_ONLY),
        ("It has happened again.", Unfit.NO_CONTENT),
    ],
)
def test_it_refuses_with_the_right_reason(
    nlp_resources: Resources, sentence: str, expected: str
) -> None:
    checkable, reason = verdict(nlp_resources, sentence)

    assert checkable is False
    assert reason == expected


# ------------------------------------------------------------------- ordering ----


def test_a_question_is_reported_as_a_question(nlp_resources: Resources) -> None:
    """ "Why?" trips three rules. Only one of them tells the writer anything."""
    checkable, reason = verdict(nlp_resources, "Why?")

    assert checkable is False
    assert reason == Unfit.QUESTION


def test_an_imperative_is_reported_as_an_imperative(nlp_resources: Resources) -> None:
    """An instruction has no subject, so a fragment rule running first would win."""
    checkable, reason = verdict(nlp_resources, "Read the report.")

    assert checkable is False
    assert reason == Unfit.IMPERATIVE


def test_a_prediction_is_not_reported_as_a_fragment(nlp_resources: Resources) -> None:
    """The modal *is* the finite verb, so the fragment rule must not fire on it."""
    _, reason = verdict(nlp_resources, "The tunnel will open in April 2027.")

    assert reason != Unfit.FRAGMENT


# --------------------------------------------------------------- the threshold ----


def test_the_length_threshold_is_configurable(nlp_resources: Resources) -> None:
    """`CLAIM_MIN_TOKENS` reaches this rule, and nothing else here depends on it.

    Three content words: "The bridge opened". At the default of four it is too short
    to check; lower the setting by one and it is a claim.
    """
    terse = "The bridge opened."

    assert verdict(nlp_resources, terse, min_tokens=3) == (True, "")
    assert verdict(nlp_resources, terse, min_tokens=MIN_TOKENS) == (
        False,
        Unfit.TOO_SHORT,
    )


def test_punctuation_does_not_count_towards_the_threshold(
    nlp_resources: Resources,
) -> None:
    """Seven tokens, three words. Counting tokens would let this through."""
    clause = only_clause(nlp_resources, 'It rained, "heavily".')

    assert len(clause.tokens) > MIN_TOKENS
    assert screen(clause, min_tokens=MIN_TOKENS) == (False, Unfit.TOO_SHORT)


# ------------------------------------------------------------------ invariants ----


REASONS = frozenset(
    value
    for name, value in vars(Unfit).items()
    if not name.startswith("_") and isinstance(value, str)
)

SENTENCES = [
    "The Queensferry Crossing opened in August 2017.",
    "Photo by Reuters.",
    "Why did the bridge cost £4bn?",
    "The new bridge is beautiful.",
    "The tunnel will open in April 2027.",
    "It has happened again.",
]


@pytest.mark.parametrize("sentence", SENTENCES)
def test_a_reason_is_always_a_known_reason(
    nlp_resources: Resources, sentence: str
) -> None:
    """A typo'd reason string would otherwise reach clients as an unknown code."""
    checkable, reason = verdict(nlp_resources, sentence)

    if checkable:
        assert reason == ""
    else:
        assert reason in REASONS


@pytest.mark.parametrize("sentence", SENTENCES)
def test_screening_never_raises(nlp_resources: Resources, sentence: str) -> None:
    """Difficult prose is a verdict, not an exception. Exceptions are for bugs."""
    assert isinstance(verdict(nlp_resources, sentence), tuple)
