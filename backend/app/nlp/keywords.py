"""Keywords, by TF-IDF, with each sentence as a document.

That choice is the whole idea. Run TF-IDF over a corpus of articles and you learn
which terms are rare in the corpus — which is a fact about the corpus, and requires
one. Run it with the *sentences of a single submission* as the documents and you
learn which terms distinguish one sentence from its neighbours, which is a fact about
this text and available from this text alone. A word the writer uses in every
sentence ("bridge", in an article about a bridge) gets a low weight and a word that
appears in one ("£4.2bn") gets a high one, which is exactly the ranking a desk wants
when deciding what to go and look up.

The consequence is that scores are comparable inside one extraction and meaningless
across two, which :class:`~app.domain.Keyword` says in as many words.

Two sharp edges in scikit-learn, both handled below, both discovered the expensive
way:

``max_df`` prunes by strict inequality
    A float ``max_df`` is converted to ``max_df * n_documents`` and any term in
    *more* than that many documents is dropped. With one sentence, ``max_df=0.9``
    gives a threshold of 0.9, every term is in one document, and every term is
    pruned — at which point ``fit_transform`` raises ``ValueError("After pruning, no
    terms remain…")``. So a fractional ``max_df`` is only applied once there are
    enough sentences for it to mean something.

stop words are removed before n-grams are formed
    ``_word_ngrams`` filters the token list and *then* builds bigrams from what
    survives, so "prime minister of Canada" yields the bigram "minister canada" —
    a term that never appears in the source. This is usually an improvement, since it
    is the collocation the stop word was separating, but it does mean a keyword is
    not necessarily a substring of the text. That is why :class:`Keyword` carries no
    offsets: it is a term, not a span.

the default token pattern is not built for lemmas
    ``TfidfVectorizer`` re-tokenises whatever string it is handed, with
    ``\\b\\w\\w+\\b`` — and what it is handed here is already a list of tokens. Letting
    it run a second tokeniser over them costs precisely the terms a fact-checker cares
    about: ``1.35bn`` arrives as ``35bn``, ``covid-19`` splits into two terms, and
    ``3.5`` vanishes for want of two adjacent word characters. So the tokeniser is
    whitespace and the pattern is switched off, and what gets ranked is what spaCy
    lemmatised.

    That also settles a quieter problem. scikit-learn checks each stop word against its
    own tokeniser and warns — once per call, forever — when one does not survive it, and
    NLTK's list contains contractions: under the default pattern ``don't`` becomes
    ``don``, which is not in the list. Splitting on whitespace leaves ``don't`` as
    itself, so it both matches the document token NLTK put it there to remove and stops
    the warning.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

from app.core.logging import get_logger
from app.domain import Keyword

logger = get_logger(__name__)

#: One lemmatised token: its lemma and its coarse part of speech.
Lemma = tuple[str, str]

#: Any whitespace. The vectoriser splits on it, so a stop word containing it could
#: never match a token and is dropped from the list rather than passed on.
_WHITESPACE = re.compile(r"\s")

#: The shortest lemma worth ranking. Applied in one place and used by both paths,
#: because two rankings computed over different vocabularies would make the fallback
#: incomparable with the thing it falls back from.
_MIN_LEMMA_CHARS = 2

#: Below this many sentences a fractional ``max_df`` prunes the vocabulary to
#: nothing or nearly nothing. Five is where "appears in more than 90% of sentences"
#: starts describing a term rather than describing the arithmetic.
_MIN_DOCS_FOR_MAX_DF = 5

#: Below this many sentences there is no document frequency to speak of: every term
#: has the same IDF, the ranking degenerates to term frequency, and the weights would
#: imply a comparison that was never made. The frequency fallback is used instead —
#: honest about being a frequency count rather than dressed up as TF-IDF.
_MIN_DOCS_FOR_TFIDF = 2

#: What a lemma is worth in the fallback ranking, by part of speech. Proper nouns
#: outrank common nouns because they are what a search actually keys on, and verbs
#: and adjectives are included at a discount rather than excluded, so a sentence with
#: no nouns still ranks something.
_POS_WEIGHT = {
    "PROPN": 3.0,
    "NOUN": 2.0,
    "NUM": 1.5,
    "ADJ": 1.0,
    "VERB": 1.0,
}


def keywords(
    documents: Sequence[Sequence[Lemma]],
    stopwords: frozenset[str],
    *,
    limit: int,
) -> tuple[tuple[tuple[Keyword, ...], ...], tuple[Keyword, ...]]:
    """Rank the terms of each sentence, and of the submission as a whole.

    ``documents`` is one lemmatised sentence per entry. Lemmas rather than surface
    forms so that "opened", "opens" and "opening" are one term — the point of having
    a lemmatiser in the pipeline at all.

    Returns ``(per_sentence, overall)``, aligned with ``documents``, each ranked
    strongest first.

    ``limit`` caps ``overall``. The per-sentence rows come back ranked but *uncapped*,
    and that asymmetry is deliberate: a caller narrowing a row to one clause of its
    sentence has to cap after that narrowing, never before. Capping first spends the
    budget on terms the clause does not contain — and in a short sentence, where every
    term ties and the alphabetical tie-break decides, it will drop the clause's own
    subject to make room for its neighbour's.
    """
    if not documents:
        return (), ()

    scored = (
        _tfidf(documents, stopwords) if len(documents) >= _MIN_DOCS_FOR_TFIDF else None
    )
    if scored is None:
        scored = _frequency(documents, stopwords)

    per_sentence = tuple(_rank(row, None) for row in scored)
    totals: defaultdict[str, float] = defaultdict(float)
    for row in scored:
        for term, weight in row.items():
            totals[term] += weight
    return per_sentence, _rank(dict(totals), limit)


# ------------------------------------------------------------------ TF-IDF ----


def _tfidf(
    documents: Sequence[Sequence[Lemma]], stopwords: frozenset[str]
) -> list[dict[str, float]] | None:
    """Per-sentence term weights, or ``None`` if scikit-learn could not produce any.

    ``None`` rather than an exception for the two cases that are properties of the
    text and not faults: a vocabulary that is entirely stop words, and a vocabulary
    pruned empty. Both are ordinary for very short or very repetitive submissions,
    and both have a sensible answer one level up.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:  # pragma: no cover - depends on the environment
        logger.warning(
            "scikit-learn is not installed; ranking keywords by weighted frequency",
            extra={"missing": "scikit-learn"},
        )
        return None

    texts = [
        " ".join(lemma for lemma, _ in document if _usable(lemma))
        for document in documents
    ]
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        # 1 + log(tf). One sentence saying "bridge" four times is about the bridge
        # rather more than a sentence saying it once, but not four times more.
        sublinear_tf=True,
        stop_words=_sanitise(stopwords),
        max_df=0.9 if len(texts) >= _MIN_DOCS_FOR_MAX_DF else 1.0,
        min_df=1,
        # The input is already tokenised, so splitting on whitespace hands the lemmas
        # over unchanged. The default pattern would rewrite them — see the module
        # docstring; `token_pattern=None` is required to say so without a warning.
        tokenizer=str.split,
        token_pattern=None,
    )
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError as exc:
        # "empty vocabulary; perhaps the documents only contain stop words" and
        # "After pruning, no terms remain." Both are the same situation from here.
        logger.info(
            "TF-IDF produced no vocabulary; ranking keywords by weighted frequency",
            extra={"documents": len(texts), "reason": str(exc)},
        )
        return None

    terms = list(vectorizer.get_feature_names_out())
    # Read the CSR arrays directly rather than slicing rows. `matrix[i]` and
    # `getrow(i)` have both moved around between scipy versions; `indptr`/`indices`/
    # `data` is the format's definition and has not.
    indptr, indices, data = matrix.indptr, matrix.indices, matrix.data
    rows: list[dict[str, float]] = []
    for row_index in range(len(texts)):
        row = {
            terms[int(indices[j])]: float(data[j])
            for j in range(int(indptr[row_index]), int(indptr[row_index + 1]))
        }
        rows.append(row)
    return rows


def _sanitise(stopwords: frozenset[str]) -> list[str]:
    """The stop word list as the vectoriser's own tokeniser will see it.

    Since that tokeniser is ``str.split``, this is a lower-casing and very little else
    — which is the point of tokenising on whitespace rather than on ``\\b\\w\\w+\\b``.
    Under the default pattern ``don't`` becomes ``don``, scikit-learn notices that the
    token it produced is not itself a stop word, and warns on every call; here the entry
    stays ``don't`` and removes the document token it was meant to remove.

    Sorted so that two runs on the same text build byte-identical vectorisers. Entries
    carrying whitespace are dropped because no whitespace-split token can equal one.
    """
    return sorted(
        word.lower()
        for word in stopwords
        if _usable(word) and not _WHITESPACE.search(word)
    )


def _usable(lemma: str) -> bool:
    """Whether a term belongs in the vocabulary at all.

    A single character matches nothing useful in a search and crowds out terms that do.
    """
    return len(lemma) >= _MIN_LEMMA_CHARS


# --------------------------------------------------------------- fallback ----


def _frequency(
    documents: Sequence[Sequence[Lemma]], stopwords: frozenset[str]
) -> list[dict[str, float]]:
    """Weighted lemma frequency, for when there is no document frequency to use.

    Unigrams only. Bigrams without IDF would rank "the bridge" alongside "bridge"
    on nothing more than both being present, and there is no signal here to separate
    them.
    """
    rows: list[dict[str, float]] = []
    for document in documents:
        counts: defaultdict[str, float] = defaultdict(float)
        for lemma, pos in document:
            term = lemma.lower()
            weight = _POS_WEIGHT.get(pos)
            if weight is None or term in stopwords or not _usable(term):
                continue
            counts[term] += weight
        rows.append(dict(counts))
    return rows


# ------------------------------------------------------------------ output ----


def _rank(scores: dict[str, float], limit: int | None) -> tuple[Keyword, ...]:
    """The strongest ``limit`` terms, normalised so the top one scores 1.0.

    ``limit=None`` ranks everything. Ties break on the term itself: any deterministic
    rule would do, and having one is the requirement, because the alternative is a
    response whose ordering depends on dictionary iteration order. Short sentences make
    this load-bearing rather than theoretical — every term in them appears once, in one
    sentence, so every weight is equal and the tie-break decides the whole ordering.
    """
    if not scores:
        return ()
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
    top = ordered[0][1]
    if top <= 0:  # pragma: no cover - weights are positive by construction
        return ()
    return tuple(Keyword(term=term, score=weight / top) for term, weight in ordered)
