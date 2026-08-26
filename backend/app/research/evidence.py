"""Choosing which passage of a snippet bears on the claim, and quoting it exactly.

This is the module where fabrication would be easiest and least visible. A summary
of a source reads better than a quote from it, a paraphrase can be made to fit the
claim perfectly, and neither would look wrong to a reader who does not have the
original to hand. So nothing here writes prose. Every quote is produced by *slicing*
a provider's snippet, and the slice is recorded as offsets so that anyone — a test, a
reviewer, a downstream desk — can check it::

    retrieval.snippet[evidence.start : evidence.end] == evidence.quote

The three things that make that guarantee real rather than decorative:

**Elisions are hard boundaries.** Search snippets are not continuous prose. Tavily
joins reranked chunks from different parts of a page with ``" [...] "``; Google and
Brave cut with ``...`` and leave the marker in. A quote that spanned one of those
markers would be a verbatim slice of the snippet and still a fabrication — two
sentences from opposite ends of an article, presented as consecutive. Splitting on
them first is what prevents a true slice from telling a false story.

**A passage with nothing in common with the claim is not evidence.** It would be
real text, honestly quoted, and irrelevant — and putting it in the dossier under the
heading "evidence" would fabricate the *relevance* even though every character was
genuine. A source with no qualifying passage gets an empty tuple, which
:class:`~app.domain.research.Source` documents as a reportable outcome.

**Nothing here judges the claim.** The score is lexical overlap and is described as
such: it measures that a passage repeats the claim's entities, figures and terms. A
passage that flatly contradicts the claim repeats all of them and therefore scores
*high*, which is intended — a source that disagrees is the most valuable one in the
dossier, and a scorer that ranked agreement above disagreement would be quietly
building a case rather than gathering evidence.

One consequence of that worth stating plainly, because it is a real limit rather
than a subtlety: a passage that disputes the claim's *figure* with a different figure
("rose to 5.2%" against a claim of "fell to 4.6%") earns nothing from the figure
channel, since the figures do not match. It still qualifies and still ranks, on the
entity and term channels. Ranking it below a passage carrying the claim's own number
is a deliberate choice — the passage with the same figure is the one that can be
checked against the claim directly — not an oversight about contradiction.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from app.domain.claims import ExtractedClaim
from app.domain.research import Evidence, Retrieval
from app.research import terms

__all__ = [
    "MAX_EVIDENCE",
    "MIN_OVERLAP",
    "MIN_QUOTE_CHARS",
    "Match",
    "Needle",
    "assess",
    "passages",
    "select",
]

#: Passages kept per source, strongest first.
#:
#: Three: enough for the passage that matched plus a second one qualifying it, and few
#: enough that a desk reading the dossier is reading evidence rather than a corpus.
MAX_EVIDENCE = 3

#: Shortest quotable passage.
#:
#: A fragment below this carries no proposition — ``"Yes."``, ``"Read more"`` — and
#: quoting it would fill the dossier with text that is verbatim and says nothing.
MIN_QUOTE_CHARS = 24

#: Word overlap a passage needs when the claim offers nothing else to match on.
#:
#: Used *only* for a claim with no entities, no figures and no keywords, which is what
#: a deployment without the NLP extras produces. With anything to anchor on, an anchor
#: is required instead: sharing ordinary words with a claim is not evidence about it.
MIN_OVERLAP = 0.34

#: Weights for the three channels. Figures hardest, by a factor of three over terms.
#:
#: A passage carrying the claim's own number can be checked against the claim; one
#: that merely shares its topic words is background reading. Entities sit between:
#: naming who the claim is about is a strong signal, and unlike a figure it is rarely
#: unique to the claim.
NUMBER_WEIGHT = 3.0
ENTITY_WEIGHT = 2.0
TERM_WEIGHT = 1.0

#: Tavily's chunk join, and the ellipses the other two providers cut with.
#:
#: The ``[...]`` alternative is spelled out here rather than imported from
#: :data:`app.search.tavily.CHUNK_SEPARATOR`, because :mod:`app.research` does not
#: import :mod:`app.search`. It is duplicated knowledge, and
#: ``test_tavily_keeps_the_chunk_separator_verbatim`` is what keeps the two in step:
#: it asserts the client passes the separator through untouched, which is the only
#: reason this pattern has anything to find.
_ELISION = re.compile(r"\s*(?:\[\s*\.\.\.\s*\]|\.{3,}|…|[\r\n]+)\s*")

#: A sentence terminator, any closing punctuation after it, then whitespace. The
#: closing quote or bracket is captured so it stays *inside* the sentence being cut.
_SENTENCE_END = re.compile(r"""(?<=[.!?])(?P<tail>["'”’»)\]]*)\s+""")

#: Words that end in a period without ending a sentence. Short and Anglocentric,
#: which is what a regex sentence splitter is: the alternative is NLTK's Punkt, and
#: everything in this package has to work when NLTK is not installed.
_ABBREVIATIONS = frozenset(
    ["mr", "mrs", "ms", "dr", "prof", "rev", "hon", "sen", "rep", "gov", "st", "sr", "jr", "inc", "corp", "co", "ltd", "plc", "dept", "univ", "vs", "etc", "al", "eg", "ie", "cf", "approx", "est", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sept", "sep", "oct", "nov", "dec", "no", "fig", "vol", "pp", "ed", "u.s", "u.k", "e.u"]
)


@dataclass(frozen=True, slots=True)
class Needle:
    """One claim reduced to the terms a snippet can be matched against.

    Built once per claim and reused across every source, which is the only reason it
    is a type rather than a few locals: the alternative recomputes the same
    tokenisation for every retrieval of every source of every claim.
    """

    #: The claim's figures, canonicalised by :func:`app.research.terms.numbers`.
    numbers: tuple[str, ...]
    #: Entity texts as the claim spells them — what goes into ``matched_entities``.
    entities: tuple[str, ...]
    #: Keyword terms as the extractor spells them.
    terms: tuple[str, ...]
    #: Folded token sequences for :attr:`entities`, positionally parallel to it.
    entity_tokens: tuple[tuple[str, ...], ...]
    #: Folded token sequences for :attr:`terms`, positionally parallel to it.
    term_tokens: tuple[tuple[str, ...], ...]
    #: Every content word of the claim, for the fallback overlap channel.
    words: frozenset[str]

    @classmethod
    def of(cls, claim: ExtractedClaim) -> Needle:
        """Reduce ``claim``. Entities and keywords come from the extractor; figures
        are read off the claim text, because they are in it whether or not the
        extractor tagged them.

        Unlike :func:`app.research.queries.build`, this keeps an entity that is a
        sub-phrase of another — ``Harris`` alongside ``Kamala Harris``. In a query
        the shorter one is redundant and spends characters; in matching it is an
        independent signal, and keeping both grades the result: a passage using the
        full name matches both, one using only the surname matches one.
        """
        entities: list[str] = []
        seen: set[str] = set()
        for entity in claim.entities:
            text = terms.squeeze(entity.text)
            key = text.casefold()
            if not text or key in seen:
                continue
            # A purely numeric entity — ``2019``, ``4.6%`` — is already counted by
            # the figure channel, and counting it twice would let one match earn
            # both weights.
            if not terms.content_words(text):
                continue
            seen.add(key)
            entities.append(text)

        keywords: list[str] = []
        for keyword in claim.keywords:
            term = terms.squeeze(keyword.term)
            key = term.casefold()
            if not term or key in seen:
                continue
            seen.add(key)
            keywords.append(term)

        return cls(
            numbers=terms.numbers(claim.text),
            entities=tuple(entities),
            terms=tuple(keywords),
            entity_tokens=tuple(_tokens(text) for text in entities),
            term_tokens=tuple(_tokens(term) for term in keywords),
            words=frozenset(terms.content_words(claim.text)),
        )

    @property
    def anchored(self) -> bool:
        """Whether the claim offers a figure, entity or term to require a match on."""
        return bool(self.numbers or self.entities or self.terms)


def select(
    needle: Needle,
    retrievals: Sequence[Retrieval],
    *,
    limit: int = MAX_EVIDENCE,
) -> tuple[Evidence, ...]:
    """The passages of ``retrievals`` that bear on ``needle``, strongest first.

    Every provider's snippet is read, not just the first: engines surface different
    parts of the same page, and the passage carrying the claim's figure is often in
    only one of them. Each :class:`~app.domain.research.Evidence` records which
    snippet it was sliced from, so quoting from several costs one field and keeps the
    offset guarantee exact.

    A passage two providers both returned is kept once, attributed to whichever of
    them scored highest — that both engines returned it is recorded on
    :attr:`~app.domain.research.Source.retrievals`, and spending the evidence budget
    on the same sentence twice would push out a passage that says something else.
    """
    found: list[Evidence] = []
    for retrieval in retrievals:
        snippet = retrieval.snippet
        for start, end in passages(snippet):
            quote = snippet[start:end]
            scored = assess(needle, quote)
            if scored is None:
                continue
            found.append(
                Evidence(
                    quote=quote,
                    provider=retrieval.provider,
                    start=start,
                    end=end,
                    score=scored.score,
                    matched_entities=scored.entities,
                    matched_terms=scored.terms,
                    matched_numbers=scored.numbers,
                )
            )

    # Stable, so equal scores keep retrieval order and then position in the snippet.
    found.sort(key=lambda evidence: -evidence.score)
    return tuple(_undouble(found)[:limit])


def passages(snippet: str) -> tuple[tuple[int, int], ...]:
    """Quotable spans of ``snippet``, as ``(start, end)`` offsets into it.

    Elisions first, so no span can cross one, then sentences within each piece. The
    offsets index ``snippet`` itself and the spans exclude surrounding whitespace, so
    ``snippet[start:end]`` is the quote with nothing to trim.

    Sentences are not truncated, however long. A cut sentence is still a verbatim
    slice and can still reverse the meaning of the passage — a trailing ``did not``
    is the easiest thing in the world to amputate — and provider snippets are capped
    at a few hundred characters anyway, so there is nothing to gain by risking it.
    """
    spans: list[tuple[int, int]] = []
    for piece_start, piece_end in _pieces(snippet):
        for start, end in _sentences(snippet, piece_start, piece_end):
            span = _tighten(snippet, start, end)
            if span is not None:
                spans.append(span)
    return tuple(spans)


# ------------------------------------------------------------------ scoring ----


@dataclass(frozen=True, slots=True)
class Match:
    """How much of a claim some other piece of text repeats.

    Public because :mod:`app.research.reviews` scores a fact-checker's wording of a
    claim against the claim under check, and that has to be the *same* arithmetic as
    the one used here. A second scoring scale would mean two numbers in one response
    both called a score, on different denominators, and a reader comparing them would
    be comparing nothing.
    """

    score: float
    numbers: tuple[str, ...]
    entities: tuple[str, ...]
    terms: tuple[str, ...]


def assess(needle: Needle, text: str) -> Match | None:
    """Score ``text`` against ``needle``, or ``None`` if it does not qualify.

    The score is ``earned / possible`` over four channels — figures, entities, terms,
    and a word-overlap channel worth one point. That makes it a legible fraction
    rather than an arbitrary number: 1.0 is a passage repeating everything the claim
    contains, and a reader comparing it against ``matched_numbers`` can see which
    channel earned it.

    ``None`` is the load-bearing return value, not the number. It means ``text`` has
    nothing in common with the claim, and every caller treats it the same way: the
    text does not go in the dossier. A quote with no overlap would fabricate
    relevance; a fact check of a different claim would fabricate a verdict.
    """
    tokens = _tokens(text)
    figures = terms.numbers(text)

    matched_numbers = tuple(n for n in needle.numbers if n in figures)
    matched_entities = tuple(
        text
        for text, wanted in zip(needle.entities, needle.entity_tokens, strict=True)
        if terms.subphrase(wanted, tokens)
    )
    matched_terms = tuple(
        term
        for term, wanted in zip(needle.terms, needle.term_tokens, strict=True)
        if terms.subphrase(wanted, tokens)
    )

    present = set(tokens)
    overlap = (
        len(needle.words & present) / len(needle.words) if needle.words else 0.0
    )

    if needle.anchored:
        if not (matched_numbers or matched_entities or matched_terms):
            return None
    elif overlap < MIN_OVERLAP:
        return None

    possible = (
        NUMBER_WEIGHT * len(needle.numbers)
        + ENTITY_WEIGHT * len(needle.entities)
        + TERM_WEIGHT * len(needle.terms)
        + 1.0
    )
    earned = (
        NUMBER_WEIGHT * len(matched_numbers)
        + ENTITY_WEIGHT * len(matched_entities)
        + TERM_WEIGHT * len(matched_terms)
        + overlap
    )
    return Match(
        score=round(earned / possible, 4),
        numbers=matched_numbers,
        entities=matched_entities,
        terms=matched_terms,
    )


def _undouble(found: Sequence[Evidence]) -> list[Evidence]:
    """Drop passages already represented, best-first.

    Containment rather than equality, because providers truncate the same sentence at
    different points and two quotes where one contains the other are one passage.
    The higher-scoring one survives, not the longer one: the score is the reason the
    passage is in the dossier at all.
    """
    kept: list[Evidence] = []
    folded: list[str] = []
    for evidence in found:
        key = terms.fold(terms.squeeze(evidence.quote))
        if any(key in other or other in key for other in folded):
            continue
        folded.append(key)
        kept.append(evidence)
    return kept


# ------------------------------------------------------------ segmentation ----


def _pieces(snippet: str) -> Iterator[tuple[int, int]]:
    """The spans between elision markers, which no quote may cross."""
    cursor = 0
    for match in _ELISION.finditer(snippet):
        if match.start() > cursor:
            yield cursor, match.start()
        cursor = match.end()
    if cursor < len(snippet):
        yield cursor, len(snippet)


def _sentences(text: str, start: int, end: int) -> Iterator[tuple[int, int]]:
    """Sentence spans within ``text[start:end]``, offset against ``text``.

    A piece with no terminator yields itself, which is the common case: Brave's
    ``description`` and Tavily's chunks are frequently one unterminated fragment.
    """
    cursor = start
    for match in _SENTENCE_END.finditer(text, start, end):
        stop = match.end("tail")
        if match.end() >= end or not _is_boundary(text, match.start(), match.end()):
            continue
        yield cursor, stop
        cursor = match.end()
    yield cursor, end


def _is_boundary(text: str, after: int, resumes: int) -> bool:
    """Whether the terminator ending at ``after`` really ends a sentence.

    Two cheap tests that between them cover most of what a regex can get wrong: a
    following lower-case letter means the period was internal punctuation, and a
    preceding abbreviation or single initial means it belonged to the word.
    """
    if resumes < len(text) and text[resumes].islower():
        return False
    if text[after - 1] != ".":
        return True
    word = re.search(r"([\w.]+)\.$", text[:after])
    if word is None:
        return True
    stem = word.group(1).casefold().rstrip(".")
    return len(stem) > 1 and stem not in _ABBREVIATIONS


def _tighten(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Trim whitespace off a span, or reject it as too short to be a passage."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if end - start < MIN_QUOTE_CHARS:
        return None
    return start, end


def _tokens(text: str) -> tuple[str, ...]:
    """Folded word tokens, so ``Wałęsa`` in a claim matches ``Walesa`` in a snippet."""
    return terms.words(terms.fold(text))
