"""Evidence selection: quoted, never written.

The module under test is the one where fabrication would be easiest to commit and
hardest to notice — a paraphrase can be made to fit a claim perfectly, and nothing in
the output would look wrong to a reader without the original to hand. So the first
group of tests below is about the mechanical guarantee that makes that impossible:

    retrieval.snippet[evidence.start : evidence.end] == evidence.quote

and the second group is about the two ways a *true* slice can still tell a false
story — spanning an elision, and being presented as relevant when it is not.

The last group is the property most likely to be "fixed" into a bug: a passage that
flatly contradicts the claim must score **high**. A scorer that ranked agreement
first would quietly turn evidence gathering into case building, and the test that
says so is the only thing standing between this and a plausible refactor.
"""

from __future__ import annotations

import pytest

from app.domain.research import Retrieval
from app.research import evidence as ev
from tests.research_bench import BOILERPLATE, WIRE, claim, retrieval

#: The claim every test here is matched against, with two entities, two keywords and
#: two figures — enough that each scoring channel can be isolated.
RATE = claim(
    "The Bank of England held its benchmark rate at 4.75% in March 2026.",
    entities=(
        ("Bank of England", "ORG"),
        ("England", "GPE"),
        ("March 2026", "DATE"),
        ("4.75%", "PERCENT"),
    ),
    keywords=(("benchmark rate", 1.0), ("inflation", 0.8)),
)

#: What the extractor produces with no NLP extras installed: text, nothing else.
UNANALYSED = claim(
    "The rate was held at the same level again this month by the committee."
)

#: Snippets in the shapes the three providers actually return them.
SNIPPETS = [
    pytest.param(WIRE, id="wire"),
    pytest.param(
        "The Bank of England held its rate at 4.75%. [...] Governor Andrew Bailey "
        "said inflation in March 2026 remained above target.",
        id="tavily-chunks",
    ),
    pytest.param(
        "Bank of England holds benchmark rate at 4.75% ... economists had expected "
        "a cut in March 2026 after weak retail figures.",
        id="brave-ellipsis",
    ),
    pytest.param(
        "The Bank of England held its benchmark rate at 4.75%\nInflation in March "
        "2026 was 2.8%, the committee said.",
        id="newline-cut",
    ),
    pytest.param(
        "Analysts at Dr. Fry Ltd. expected the Bank of England to hold at 4.75% in "
        "March 2026. They were right. Read more",
        id="abbreviations",
    ),
    pytest.param(
        "Did the Bank of England hold its benchmark rate at 4.75%? Yes — the "
        "committee voted five to four in March 2026!",
        id="question-and-exclamation",
    ),
]


# --------------------------------------------------------- the offset guarantee ----


@pytest.mark.parametrize("snippet", SNIPPETS)
def test_every_quote_is_a_verbatim_slice_of_the_snippet(snippet: str) -> None:
    """The invariant the whole design rests on, checked against every shape."""
    found = ev.select(
        ev.Needle.of(RATE), [retrieval("tavily", "https://x/1", snippet=snippet)]
    )

    assert found  # otherwise this passes vacuously
    for evidence in found:
        assert snippet[evidence.start : evidence.end] == evidence.quote


def test_offsets_index_the_snippet_of_the_provider_they_name() -> None:
    """Two engines returning different parts of one page is the common case.

    Each :class:`~app.domain.research.Evidence` says which snippet its offsets index,
    and getting that wrong would produce quotes that look verbatim and are not. The
    two snippets here are different lengths on purpose: offsets valid against one are
    wrong against the other, so a mixed-up attribution cannot pass.
    """
    retrievals = [
        retrieval("tavily", "https://x/1", snippet=WIRE),
        retrieval(
            "brave",
            "https://x/1",
            snippet="Rates held at 4.75% by the Bank of England in March 2026.",
        ),
    ]
    source = {r.provider: r.snippet for r in retrievals}

    for evidence in ev.select(ev.Needle.of(RATE), retrievals):
        snippet = source[evidence.provider]
        assert snippet[evidence.start : evidence.end] == evidence.quote


def test_a_quote_is_never_padded_with_whitespace() -> None:
    """``snippet[start:end]`` is the quote with nothing left to trim."""
    snippet = (
        "   The Bank of England held its benchmark rate at 4.75% in March 2026.   "
    )

    for evidence in ev.select(
        ev.Needle.of(RATE), [retrieval("p", "u", snippet=snippet)]
    ):
        assert evidence.quote == evidence.quote.strip()


# ------------------------------------------------------------------- elisions ----


@pytest.mark.parametrize(
    "marker", ["[...]", "[ ... ]", "...", "....", "…", "\n", "\r\n"]
)
def test_no_quote_spans_an_elision(marker: str) -> None:
    """A slice across a cut joins two passages the page never had adjacent.

    Every character would be genuine and the sentence would be an invention. This is
    the one fabrication that survives the offset guarantee, which is why the split
    happens before sentences are found rather than after.
    """
    left = "The Bank of England held its benchmark rate at 4.75% in March 2026."
    right = "Inflation is expected to fall below target by the end of next year."
    snippet = f"{left}{marker}{right}"

    for evidence in ev.select(
        ev.Needle.of(RATE), [retrieval("p", "u", snippet=snippet)]
    ):
        assert marker not in evidence.quote
        assert not (left[-20:] in evidence.quote and right[:20] in evidence.quote)


def test_both_sides_of_an_elision_stay_available() -> None:
    """Splitting on the marker must not discard what follows it.

    The elision is a boundary, not a truncation point: the passage after ``[...]``
    is frequently the one carrying the claim's figure, and dropping it would lose
    evidence rather than protect against a false one.
    """
    snippet = (
        "Economists surveyed by the agency were split on the decision. [...] "
        "The Bank of England held its benchmark rate at 4.75% in March 2026."
    )
    found = ev.select(ev.Needle.of(RATE), [retrieval("p", "u", snippet=snippet)])

    assert found[0].quote.startswith("The Bank of England held")
    assert found[0].start > snippet.index("[...]")


# ------------------------------------------------------------------ relevance ----


def test_a_page_with_nothing_matching_gets_no_evidence() -> None:
    """An empty tuple, not a plausible-looking first sentence.

    Quoting an arbitrary passage under the heading "evidence" fabricates the
    *relevance* while every character stays genuine — and that is the failure a
    reader has no way to detect.
    """
    unrelated = (
        "Ferry services between Portsmouth and Fishbourne were cancelled on Sunday "
        "after high winds closed the Solent to smaller vessels for several hours."
    )

    assert ev.select(ev.Needle.of(RATE), [retrieval("p", "u", snippet=unrelated)]) == ()


def test_boilerplate_is_not_evidence() -> None:
    """A newsletter block shares ordinary words with everything and anchors nothing."""
    assert (
        ev.select(ev.Needle.of(RATE), [retrieval("p", "u", snippet=BOILERPLATE)]) == ()
    )


def test_an_anchored_claim_requires_an_anchor_not_word_overlap() -> None:
    """Sharing ordinary words with a claim is not evidence about it.

    The passage below repeats most of the claim's function words and none of its
    entities, figures or terms. Accepting it on overlap alone is how a dossier fills
    up with real, honest, useless text.
    """
    wordy = (
        "It was held at its level in the report, which the group said it had "
        "expected in the month before the meeting was held again."
    )
    needle = ev.Needle.of(RATE)

    assert needle.anchored
    assert ev.select(needle, [retrieval("p", "u", snippet=wordy)]) == ()


def test_an_unanalysed_claim_falls_back_to_word_overlap() -> None:
    """With nothing to anchor on, overlap is all there is — and it is a real threshold.

    This is the path a deployment without the NLP extras takes for every claim, so
    "no entities" must not mean "no evidence" and must not mean "any evidence".
    """
    needle = ev.Needle.of(UNANALYSED)
    close = "The rate was held at the same level again this month by the committee."
    far = "A completely unrelated football match ended in a draw on Saturday evening."

    assert not needle.anchored
    assert ev.select(needle, [retrieval("p", "u", snippet=close)])
    assert ev.select(needle, [retrieval("p", "u", snippet=far)]) == ()


def test_a_fragment_too_short_to_carry_a_proposition_is_not_quoted() -> None:
    """``Yes.`` and ``Read more`` are verbatim and say nothing."""
    snippet = "Bank of England. 4.75%. Yes. Read more"

    for evidence in ev.select(
        ev.Needle.of(RATE), [retrieval("p", "u", snippet=snippet)]
    ):
        assert len(evidence.quote) >= ev.MIN_QUOTE_CHARS


# ------------------------------------------------------------------- scoring ----


def test_a_contradiction_scores_high() -> None:
    """The property most likely to be refactored into a bug.

    A source that disagrees is the most valuable one in the dossier. The score is
    lexical overlap and nothing else — it measures that a passage is *about* the
    claim, and says nothing about whether it supports it.
    """
    denial = (
        "The Bank of England cut its benchmark rate to 4.50% in March 2026, "
        "defying forecasts of a hold."
    )
    found = ev.select(ev.Needle.of(RATE), [retrieval("p", "u", snippet=denial)])

    assert found
    assert found[0].score > 0.5
    # It is ranked and quoted despite disputing the claim's own figure, which it
    # earns nothing for — see the module docstring in app/research/evidence.py.
    assert found[0].matched_numbers == ("2026",)
    assert "Bank of England" in found[0].matched_entities


def test_a_passage_carrying_the_claims_figure_outranks_one_that_does_not() -> None:
    """Figures are weighted hardest because they are what can be checked directly."""
    with_figure = "Inflation data showed the 4.75% level again in March 2026."
    without = (
        "The benchmark rate and inflation were discussed at length by the panel today."
    )
    found = ev.select(
        ev.Needle.of(RATE),
        [retrieval("p", "u", snippet=f"{with_figure} [...] {without}")],
    )

    assert found[0].quote == with_figure
    assert found[0].score > found[1].score


def test_the_score_is_a_legible_fraction() -> None:
    """``earned / possible``, so 1.0 means the passage repeats everything the claim has."""
    for snippet in (WIRE, "Rates held at 4.75% by the Bank of England in March 2026."):
        for evidence in ev.select(
            ev.Needle.of(RATE), [retrieval("p", "u", snippet=snippet)]
        ):
            assert 0 < evidence.score <= 1


def test_the_matched_tuples_explain_the_score() -> None:
    """A reader must be able to see *why* a passage was chosen.

    Everything named in the three tuples has to actually be in the quote, or the
    explanation is decoration.
    """
    found = ev.select(ev.Needle.of(RATE), [retrieval("p", "u", snippet=WIRE)])

    for evidence in found:
        folded = evidence.quote.casefold()
        for matched in evidence.matched_entities + evidence.matched_terms:
            assert matched.casefold() in folded
        for number in evidence.matched_numbers:
            assert number.rstrip("%") in folded


def test_evidence_comes_back_strongest_first() -> None:
    snippet = (
        "The Bank of England held its benchmark rate at 4.75% in March 2026. [...] "
        "Inflation remains a concern for the benchmark rate outlook. [...] "
        "The Bank of England will meet again in May."
    )
    scores = [
        evidence.score
        for evidence in ev.select(
            ev.Needle.of(RATE), [retrieval("p", "u", snippet=snippet)]
        )
    ]

    assert scores == sorted(scores, reverse=True)


def test_the_same_passage_from_two_providers_is_kept_once() -> None:
    """Two engines truncating one sentence differently is one passage.

    Spending the evidence budget on it twice pushes out a passage that says
    something else — and that both engines returned the page is already recorded on
    :attr:`~app.domain.research.Source.retrievals`.
    """
    long_form = (
        "The Bank of England held its benchmark rate at 4.75% in March 2026, "
        "as expected by economists."
    )
    truncated = "The Bank of England held its benchmark rate at 4.75% in March 2026"
    found = ev.select(
        ev.Needle.of(RATE),
        [
            retrieval("tavily", "u", snippet=long_form),
            retrieval("brave", "u", snippet=truncated),
        ],
    )

    assert len(found) == 1
    assert found[0].provider == "tavily"


def test_the_limit_is_honoured() -> None:
    snippet = " [...] ".join(
        [
            "The Bank of England held its benchmark rate at 4.75% in March 2026.",
            "Inflation was the reason the benchmark rate did not move in March 2026.",
            "The Bank of England said the 4.75% level would stand for now, in March 2026.",
            "Economists at the Bank of England put inflation above target in March 2026.",
        ]
    )
    retrievals = [retrieval("p", "u", snippet=snippet)]

    assert len(ev.select(ev.Needle.of(RATE), retrievals, limit=2)) == 2
    assert len(ev.select(ev.Needle.of(RATE), retrievals)) <= ev.MAX_EVIDENCE


# ------------------------------------------------------------- segmentation ----


@pytest.mark.parametrize(
    "abbreviated",
    [
        "Dr. Fry at the Bank of England expects 4.75% to hold in March 2026.",
        "Analysts at Fry Ltd. put the Bank of England rate at 4.75% in March 2026.",
        "The U.S. and the Bank of England both held at 4.75% in March 2026.",
        "Sen. Fry asked the Bank of England about the 4.75% rate in March 2026.",
    ],
)
def test_a_period_inside_a_word_does_not_end_a_sentence(abbreviated: str) -> None:
    """Otherwise ``Dr.`` produces a two-character quote and truncates the real one."""
    found = ev.select(ev.Needle.of(RATE), [retrieval("p", "u", snippet=abbreviated)])

    assert found
    assert found[0].quote == abbreviated


def test_a_sentence_is_never_truncated() -> None:
    """A cut sentence is a verbatim slice that can reverse the passage's meaning.

    A trailing ``did not`` is the easiest thing in the world to amputate, and the
    result would satisfy every other guarantee in this file.
    """
    long_sentence = (
        "The Bank of England held its benchmark rate at 4.75% in March 2026 and "
        "the Monetary Policy Committee said in its accompanying minutes that it "
        "did not expect inflation to return to the two per cent target before the "
        "middle of the following year, which several members described as an "
        "uncomfortably long horizon given the weakness of recent activity data."
    )
    found = ev.select(ev.Needle.of(RATE), [retrieval("p", "u", snippet=long_sentence)])

    assert found[0].quote == long_sentence


def test_passages_are_returned_in_order_with_usable_offsets() -> None:
    """:func:`~app.research.evidence.passages` is the seam a caller can check against."""
    snippet = WIRE
    spans = ev.passages(snippet)

    assert spans == tuple(sorted(spans))
    for start, end in spans:
        assert 0 <= start < end <= len(snippet)
        assert snippet[start:end] == snippet[start:end].strip()


def test_no_retrievals_yields_no_evidence() -> None:
    empty: list[Retrieval] = []

    assert ev.select(ev.Needle.of(RATE), empty) == ()


# -------------------------------------------------------------------- needle ----


def test_a_subphrase_entity_is_kept_as_a_match_signal() -> None:
    """The deliberate asymmetry with :func:`app.research.queries.build`.

    In a query ``England`` beside ``Bank of England`` is redundant and spends
    characters. In matching it is an independent signal that grades the result: a
    passage using the full name matches both, one using only ``England`` matches one.
    """
    needle = ev.Needle.of(RATE)

    assert "Bank of England" in needle.entities
    assert "England" in needle.entities


def test_a_purely_numeric_entity_is_not_counted_twice() -> None:
    """``4.75%`` is a figure. Counting it as an entity too would pay two weights."""
    needle = ev.Needle.of(RATE)

    assert "4.75%" in needle.numbers
    assert "4.75%" not in needle.entities


def test_figures_are_read_off_the_claim_text_not_the_entities() -> None:
    """They are in the claim whether or not the extractor tagged them."""
    untagged = claim("The rate was held at 4.75% in March 2026.")

    assert ev.Needle.of(untagged).numbers == ("4.75%", "2026")
