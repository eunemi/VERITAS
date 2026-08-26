"""Keyword ranking.

Half of this module needs no libraries: :func:`app.nlp.keywords.keywords` takes
lemmatised tuples rather than a ``Doc``, so the ranking, the normalisation, the
tie-breaking and the frequency fallback are all testable on a bare interpreter. That
is not an accident of the design — it is why the signature is what it is.

The TF-IDF cases are skipped without scikit-learn, and they are the ones worth having:
one asserts the behaviour the module exists for (a term in every sentence must lose to
a term in one), and one drives the ``max_df`` branch that raises ``ValueError`` if the
threshold is applied to too few documents.
"""

from __future__ import annotations

import pytest

from app.nlp.keywords import Lemma, _sanitise, keywords

#: A small stop word list, in the shape NLTK's ``stopwords.words`` returns — including
#: a contraction, because that is the entry scikit-learn's own tokeniser would rewrite
#: and the reason :func:`_sanitise` can leave the list nearly alone.
STOPWORDS = frozenset({"the", "a", "in", "and", "of", "is", "it", "don't"})


def lemmas(*words: str) -> list[Lemma]:
    """Tag every word ``NOUN`` — enough for tests that do not care about weighting."""
    return [(word, "NOUN") for word in words]


def terms(ranked) -> list[str]:
    return [keyword.term for keyword in ranked]


# ------------------------------------------------------------------- no input ----


def test_no_documents_gives_no_keywords() -> None:
    """Empty in, empty out — not an exception and not a one-element tuple."""
    assert keywords([], STOPWORDS, limit=10) == ((), ())


def test_a_document_of_only_stop_words_ranks_nothing() -> None:
    per_sentence, overall = keywords([lemmas("the", "a", "of")], STOPWORDS, limit=10)

    assert per_sentence == ((),)
    assert overall == ()


def test_the_result_is_aligned_with_the_input() -> None:
    """Callers index ``per_sentence`` by sentence, so a dropped row misattributes."""
    documents = [lemmas("bridge"), lemmas("the", "a"), lemmas("tunnel")]

    per_sentence, _ = keywords(documents, STOPWORDS, limit=10)

    assert len(per_sentence) == len(documents)
    assert terms(per_sentence[1]) == []


# ----------------------------------------------------- the frequency fallback ----


def test_one_document_uses_the_fallback_and_ranks_by_weighted_frequency() -> None:
    """A single sentence has no document frequency, so TF-IDF is not even attempted.

    Proper nouns outrank common nouns, which is the fallback's whole opinion and is
    not something TF-IDF would produce. Terms come back lower-cased either way, so
    that the fallback and the vectoriser agree on what counts as the same term.
    """
    document: list[Lemma] = [
        ("bridge", "NOUN"),
        ("Queensferry", "PROPN"),
        ("the", "DET"),
    ]

    per_sentence, overall = keywords([document], STOPWORDS, limit=10)

    assert terms(per_sentence[0]) == ["queensferry", "bridge"]
    assert terms(overall) == ["queensferry", "bridge"]


def test_the_fallback_ignores_parts_of_speech_that_carry_no_content() -> None:
    """Determiners, pronouns and punctuation are not keywords at any weight."""
    document: list[Lemma] = [
        ("bridge", "NOUN"),
        ("the", "DET"),
        ("it", "PRON"),
        (".", "PUNCT"),
        ("very", "ADV"),
    ]

    per_sentence, _ = keywords([document], STOPWORDS, limit=10)

    assert terms(per_sentence[0]) == ["bridge"]


def test_the_fallback_counts_repetition() -> None:
    document = lemmas("bridge", "bridge", "tunnel")

    per_sentence, _ = keywords([document], STOPWORDS, limit=10)

    assert terms(per_sentence[0]) == ["bridge", "tunnel"]
    assert per_sentence[0][1].score == 0.5


def test_single_character_lemmas_are_dropped() -> None:
    """They match nothing useful in a search and crowd out terms that do."""
    document: list[Lemma] = [("x", "NOUN"), ("bridge", "NOUN")]

    per_sentence, _ = keywords([document], STOPWORDS, limit=10)

    assert terms(per_sentence[0]) == ["bridge"]


# --------------------------------------------------------------- the contract ----


def test_the_top_score_is_exactly_one() -> None:
    """Scores are relative within one extraction, so the strongest term anchors them."""
    per_sentence, overall = keywords(
        [lemmas("bridge", "bridge", "tunnel"), lemmas("tunnel", "cost")],
        STOPWORDS,
        limit=10,
    )

    assert overall[0].score == 1.0
    for row in per_sentence:
        assert row[0].score == 1.0


def test_scores_descend() -> None:
    _, overall = keywords(
        [lemmas("bridge", "bridge", "bridge", "tunnel", "tunnel", "cost")],
        STOPWORDS,
        limit=10,
    )

    scores = [keyword.score for keyword in overall]
    assert scores == sorted(scores, reverse=True)
    assert all(0 < score <= 1 for score in scores)


def test_the_limit_caps_the_overall_ranking_and_not_the_rows() -> None:
    """The rows are uncapped on purpose, and this is the contract that says so.

    A caller narrows a row to one clause of its sentence and caps after that, because
    capping first spends the budget on terms the clause does not contain — see
    ``_keywords_within`` in :mod:`app.nlp.pipeline`. So a row comes back ranked in full
    and only ``overall`` obeys ``limit``.
    """
    document = lemmas("bridge", "tunnel", "road", "rail", "ferry")

    per_sentence, overall = keywords([document], STOPWORDS, limit=2)

    assert len(overall) == 2
    assert len(per_sentence[0]) == 5
    assert terms(per_sentence[0])[:2] == terms(overall)


def test_ties_break_on_the_term() -> None:
    """Any deterministic rule would do. Having one is the requirement.

    Without it the same submission comes back with its keywords in a different order
    on a different process, which looks like the extractor changing its mind.
    """
    document = lemmas("tunnel", "bridge", "road")

    first, _ = keywords([document], STOPWORDS, limit=10)
    again, _ = keywords([list(reversed(document))], STOPWORDS, limit=10)

    assert terms(first[0]) == ["bridge", "road", "tunnel"]
    assert terms(again[0]) == terms(first[0])


def test_stop_words_are_matched_case_insensitively_by_lemma() -> None:
    document: list[Lemma] = [("The", "NOUN"), ("bridge", "NOUN")]

    per_sentence, _ = keywords([document], STOPWORDS, limit=10)

    assert terms(per_sentence[0]) == ["bridge"]


# ------------------------------------------------------------------ sanitising ----


def test_sanitise_keeps_a_contraction_whole() -> None:
    """scikit-learn's default pattern turns "don't" into "don", then warns about it.

    The vectoriser splits on whitespace instead, so the entry stays as NLTK wrote it and
    goes on matching the token it was put in the list to remove. Rewriting it to "don"
    would silence the warning by making the stop word stop working.
    """
    cleaned = _sanitise(frozenset({"don't", "you're", "the"}))

    assert cleaned == ["don't", "the", "you're"]


def test_sanitise_drops_what_cannot_match_a_token() -> None:
    """Single characters, and anything with a space in it."""
    cleaned = _sanitise(frozenset({"A", "I", "THE", "of", "as well as"}))

    assert cleaned == ["of", "the"]


def test_sanitise_is_sorted() -> None:
    """Sorted so two runs build byte-identical vectorisers, hence identical ordering."""
    cleaned = _sanitise(frozenset({"the", "and", "of", "in"}))

    assert cleaned == sorted(cleaned)


# ---------------------------------------------------------------------- TF-IDF ----


@pytest.fixture
def sklearn() -> object:
    return pytest.importorskip("sklearn", reason="scikit-learn is not installed")


def test_a_term_in_every_sentence_loses_to_a_term_in_one(sklearn: object) -> None:
    """The reason this module uses TF-IDF at all.

    "bridge" appears in both sentences and carries no information about either;
    "march" appears in one. A frequency count would tie them.
    """
    documents = [
        lemmas("bridge", "open", "march"),
        lemmas("bridge", "cost", "billion"),
    ]

    per_sentence, _ = keywords(documents, STOPWORDS, limit=10)

    ranked = terms(per_sentence[0])
    assert ranked.index("march") < ranked.index("bridge")


def test_two_documents_do_not_trip_the_max_df_guard(sklearn: object) -> None:
    """The bug this guard exists for: every term pruned, then ``ValueError``.

    A fractional ``max_df`` is a threshold of ``max_df * n_documents``, so with two
    documents ``0.9`` gives 1.8 and prunes anything appearing in both. Here *every*
    term appears in both, so an unguarded threshold empties the vocabulary and
    ``fit_transform`` raises.

    The bigram is what makes this a real test rather than a tautology. The failure is
    caught and the frequency fallback answers instead, and the fallback is unigrams
    only — so "bridge toll" is present exactly when scikit-learn was the one that
    answered.
    """
    documents = [lemmas("bridge", "toll"), lemmas("bridge", "toll")]

    _, overall = keywords(documents, STOPWORDS, limit=10)

    assert "bridge toll" in terms(overall)


def test_bigrams_are_ranked_alongside_unigrams(sklearn: object) -> None:
    """``ngram_range=(1, 2)``: "queensferry crossing" is worth more than either half."""
    documents = [
        lemmas("Queensferry", "crossing", "open"),
        lemmas("tunnel", "close"),
    ]

    _, overall = keywords(documents, STOPWORDS, limit=20)

    assert any(" " in keyword.term for keyword in overall)


def test_a_bigram_need_not_be_a_substring_of_the_source(sklearn: object) -> None:
    """Stop words are removed *before* n-grams are formed, so "of" leaves a gap.

    "minister of Canada" yields the bigram "minister canada", which appears nowhere in
    the text. This is why :class:`~app.domain.Keyword` carries no offsets: offering
    them would mean offering a span that does not exist.
    """
    documents = [
        lemmas("minister", "of", "Canada"),
        lemmas("tunnel", "close"),
    ]

    _, overall = keywords(documents, STOPWORDS, limit=20)

    assert "minister canada" in terms(overall)


def test_a_figure_is_ranked_whole(sklearn: object) -> None:
    """The lemmas are already tokens, and the vectoriser must not re-tokenise them.

    Under scikit-learn's default ``\\b\\w\\w+\\b`` these three become "35bn", "covid"
    plus "19", and — for "3.5" — nothing at all, since it has no two adjacent word
    characters. Those are the terms a fact-checker would actually go and look up, so
    losing them is not a cosmetic problem. Hence ``tokenizer=str.split``.
    """
    documents = [
        lemmas("cost", "1.35bn"),
        lemmas("covid-19", "case"),
        lemmas("rise", "3.5"),
    ]

    per_sentence, _ = keywords(documents, STOPWORDS, limit=20)

    assert "1.35bn" in terms(per_sentence[0])
    assert "covid-19" in terms(per_sentence[1])
    assert "3.5" in terms(per_sentence[2])


def test_every_term_appears_in_some_row_it_was_scored_from(sklearn: object) -> None:
    """The overall ranking is a sum over rows, not a separate vectorisation."""
    documents = [
        lemmas("bridge", "open", "march"),
        lemmas("tunnel", "cost", "billion"),
        lemmas("ferry", "cancel"),
    ]

    per_sentence, overall = keywords(documents, STOPWORDS, limit=50)

    everywhere = {term for row in per_sentence for term in terms(row)}
    assert set(terms(overall)) <= everywhere
