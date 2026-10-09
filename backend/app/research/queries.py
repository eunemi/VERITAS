"""Turning one claim into the handful of queries that will be searched for it.

A claim is a sentence; a search index wants a query, and the two are not the same
thing. This module builds the small ladder of formulations that gets sent — from
most faithful to most forgiving — and its whole job is to do that **without adding
anything the claim did not say.**

The ladder is three rungs, and the order is deliberate:

1. **The claim itself**, whitespace-squeezed and clamped. The most faithful thing
   that can be asked, and the one a reader checking ``ClaimResearch.queries`` will
   recognise.
2. **Its terms**: the named entities, the figures, and the strongest keywords, as
   bare tokens. Search engines match a keyword query differently from a sentence,
   and for a claim carrying an unusual figure this is usually the rung that finds
   the primary source.
3. **Its skeleton**: entities and figures only. The broadest rung, and the one that
   still returns something when the first two are too specific to match anything.

Two decisions here are about honesty rather than recall, and both are refusals.

**No stance words.** Nothing appends ``fact check``, ``debunked``, ``false`` or
``true``. It is tempting — appending "fact check" reliably surfaces fact-checkers —
and it is exactly the wrong thing for this service to do, because the search index
would then be answering a question this module asked rather than the one the claim
poses. An asymmetric addition steers the evidence toward whichever answer the added
word implies, and a symmetric one (searching both "true" and "false") doubles the
request count to shape the results twice. Contradiction is something
:mod:`app.research.evidence` *detects* — a passage that flatly contradicts the claim
scores high there, deliberately — not something the query goes hunting for. Sources
whose business is claim review are reached through a claim-review lookup, which is a
different seam and a different API, not a keyword bolted onto a web search.

**No phrase quoting.** Wrapping rung 1 in quotation marks would force exact-phrase
matching, and the text being searched is the extractor's self-contained *rewrite* of
a sentence — a string that, by construction, no publisher ever wrote. An exact-phrase
search for it would return nothing, reliably, and a dossier reporting "no sources
found" would be describing this module's punctuation rather than the web.

Everything here is pure and synchronous, and imports nothing but the standard
library and :mod:`app.domain`. In particular it does not import :mod:`app.search`:
this module produces strings, and the service turns them into
:class:`app.search.fanout.Task` objects, because that type lives on the network side
of the seam.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.domain.claims import Entity, ExtractedClaim, Keyword
from app.research import terms

__all__ = [
    "DEFAULT_QUERIES",
    "KEYWORDS_PER_QUERY",
    "MAX_QUERY_CHARS",
    "MAX_QUERY_WORDS",
    "build",
    "clamp",
]

#: The tightest query limits across the providers, applied to every query here.
#:
#: These are Brave's documented maxima. :func:`app.search.brave.clamp_query` enforces
#: them again on the way out, and the duplication is intentional twice over. Firstly
#: this module cannot import :mod:`app.search` — the import rule that keeps
#: everything here pure. Secondly, and more importantly, clamping to the *tightest*
#: limit here means every provider is sent the identical string. Clamping only at the
#: wire would send Brave a truncated query and Tavily the full one, while
#: :attr:`~app.domain.research.ClaimResearch.queries` recorded a single query that
#: one of them never saw — a small lie about what was searched, told by an
#: implementation detail.
MAX_QUERY_CHARS = 400
MAX_QUERY_WORDS = 50

#: How many keyword terms rung 2 carries beyond the entities and figures.
#:
#: Four, because a keyword query is a soft conjunction: every term added narrows it,
#: and past roughly a dozen tokens engines start returning nothing at all. The
#: entities and figures are the terms worth spending that budget on — they are what
#: make the claim identifiable — and the keywords are topical context.
KEYWORDS_PER_QUERY = 4

#: Queries per claim when the caller does not say.
#:
#: Three rungs. The cost is multiplicative — three queries against three providers is
#: nine requests per claim — which is why the number is small, and a parameter.
DEFAULT_QUERIES = 3

#: An entity longer than this is a mis-tagged clause rather than a name, and putting
#: it in a query spends the character budget on something no index will match.
MAX_TERM_CHARS = 60


def build(claim: ExtractedClaim, *, limit: int = DEFAULT_QUERIES) -> tuple[str, ...]:
    """The queries to search for ``claim``, most faithful first.

    Deterministic: the same claim yields the same queries in the same order, which is
    what makes :attr:`~app.domain.research.ClaimResearch.queries` a reproducible
    record rather than a note about one run.

    Fewer than ``limit`` queries come back whenever the rungs collapse into each
    other, and a claim the extractor could not analyse — no entities, no keywords,
    which is what a deployment without the NLP extras produces — gets exactly one
    query: itself. That is a narrower search than usual, and it is visible in the
    recorded queries rather than padded out with reformulations that would search the
    same words twice.
    """
    text = terms.squeeze(claim.text)
    if not text or limit < 1:
        return ()

    entities = _entity_terms(claim.entities)
    figures = terms.numbers(text)
    keywords = _keyword_terms(claim.keywords, covered=entities)

    rungs = [text]
    # Rungs 2 and 3 need something the extractor actually identified. Built from
    # figures alone they would be queries like "4.6 2019", which is not a search for
    # this claim so much as for arithmetic.
    if entities or keywords:
        rungs.append(" ".join([*entities, *figures, *keywords[:KEYWORDS_PER_QUERY]]))
    if entities:
        rungs.append(" ".join([*entities, *figures]))

    return _distinct(rungs, limit=limit)


def clamp(
    query: str, *, chars: int = MAX_QUERY_CHARS, words: int = MAX_QUERY_WORDS
) -> str:
    """``query`` cut to the provider limits, on a word boundary.

    Cutting mid-word would change the search rather than shorten it: half of a name
    is a different term, and one that matches a different set of pages.
    """
    tokens = query.split()[:words]
    kept: list[str] = []
    used = 0
    for token in tokens:
        extra = len(token) + (1 if kept else 0)
        if used + extra > chars:
            break
        kept.append(token)
        used += extra
    if not kept and tokens:
        # One token longer than the whole budget. Nothing about it can be preserved,
        # but returning an empty query would drop the search silently.
        return tokens[0][:chars]
    return " ".join(kept)


def _entity_terms(entities: Sequence[Entity]) -> tuple[str, ...]:
    """The entity texts worth putting in a query, in the claim's own order.

    Three kinds are dropped. Repeats, compared case-insensitively but kept in the
    claim's spelling. Purely numeric ones — ``2019``, ``4.6%`` — because
    :func:`app.research.terms.numbers` has already read those off the claim text, and
    reading them twice would only crowd out a real term. And sub-phrases of another
    entity: ``Harris`` adds nothing to a query that already contains ``Kamala
    Harris``, and the character budget it spends is a keyword that would have.
    """
    unique: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        text = terms.squeeze(entity.text)
        key = text.casefold()
        if not text or len(text) > MAX_TERM_CHARS or key in seen:
            continue
        if not terms.content_words(text):
            continue
        seen.add(key)
        unique.append(text)

    tokenised = [terms.words(text) for text in unique]
    return tuple(
        text
        for index, text in enumerate(unique)
        if not any(
            terms.subphrase(tokenised[index], other)
            for position, other in enumerate(tokenised)
            if position != index and len(other) > len(tokenised[index])
        )
    )


def _keyword_terms(
    keywords: Sequence[Keyword], *, covered: Sequence[str]
) -> tuple[str, ...]:
    """Keyword terms, strongest first, minus anything an entity already carries.

    Ties keep the extractor's order rather than falling back to alphabetical, so the
    ranking this reflects is the one TF-IDF produced.
    """
    already = {word for text in covered for word in terms.words(text)}
    ranked = sorted(enumerate(keywords), key=lambda pair: (-pair[1].score, pair[0]))
    chosen: list[str] = []
    seen: set[str] = set()
    for _, keyword in ranked:
        term = terms.squeeze(keyword.term)
        key = term.casefold()
        if not term or key in seen or len(term) > MAX_TERM_CHARS:
            continue
        tokens = terms.words(term)
        if not tokens or all(token in already for token in tokens):
            continue
        seen.add(key)
        chosen.append(term)
    return tuple(chosen)


def _distinct(candidates: Iterable[str], *, limit: int) -> tuple[str, ...]:
    """Clamp each candidate and drop the ones that would search the same thing.

    Two queries built from the same bag of words and figures will be answered from
    the same part of the index, whatever order the tokens are in. Sending both spends
    a request per provider to receive the same pages twice, and — worse for a reader
    — makes ``queries`` look like a broader search than it was.
    """
    kept: list[str] = []
    bags: list[frozenset[str]] = []
    for candidate in candidates:
        query = clamp(terms.squeeze(candidate))
        if not query:
            continue
        bag = frozenset(terms.content_words(query)) | frozenset(terms.numbers(query))
        if bag in bags or query in kept:
            continue
        bags.append(bag)
        kept.append(query)
        if len(kept) == limit:
            break
    return tuple(kept)
