"""Two kinds of identity: one page found twice, and one story published eight times.

"Deduplicate sources" sounds like one operation and is two, at different levels, with
opposite risk profiles.

**Page identity** is deciding that ``bbc.co.uk/news/123?utm_source=twitter`` and
``https://www.bbc.co.uk/news/123`` are one document. That is a factual question about
URLs, :func:`app.research.urls.normalise` answers it with transforms that provably
cannot change which document a server returns, and getting it right is what stops
three engines returning one page from looking like three sources.

**Story identity** is deciding that a Reuters report, the same report on
apnews.com, and the same report behind eight regional mastheads are one story. That
is a judgement, it is made from a hundred-odd characters of snippet, and it can be
wrong. So the two are treated completely differently: pages are *merged* — they are
the same row — and stories are only ever *marked*. A false merge deletes a real
publisher from the record and nobody can see that it happened; a false cluster label
miscounts :attr:`~app.domain.research.ClaimResearch.stories` while every source stays
visible and every domain stays counted. Both are errors and only one is silent.

The clustering method is containment — ``|A ∩ B| / min(|A|, |B|)`` over word trigrams
— rather than the textbook Jaccard, and that choice is the whole reason this works at
snippet length. Two engines truncate the same page at different points, so their
shingle sets are systematically *different sizes*, and that difference is provider
noise rather than a signal about the pages. Jaccard's union denominator charges for
it: the same Reuters body at two truncation lengths measures 0.263 by Jaccard and
1.000 by containment. Every size-symmetric metric — cosine, and the MinHash and
SimHash sketches that estimate them — has the same defect. Containment's ``min()``
denominator does not: a truncated snippet is a shingle *subset*, and containment is 1
for a subset.

Containment's strength is also its weakness, and the gate is built accordingly. Three
conditions must all hold before two sources are called one story: containment at or
above :data:`CONTAINMENT_THRESHOLD`, at least :data:`MIN_ANCHORS` shared anchors
(figures and mid-sentence proper nouns), and at least :data:`MIN_SHINGLES` trigrams on
the shorter side. The floor exists because containment is 1.0 for *any* subset,
including a three-word fragment inside an unrelated article. The anchor requirement
exists because thresholds cannot tell syndication from a publisher's own boilerplate:
two unrelated stories from one site behind the same newsletter sign-up block measure
0.882 — above the threshold at any shingle width — and share zero anchors, while
genuine syndicated pairs share four or more.

Everything here is stdlib-only and deterministic. No :func:`hash` on a string
anywhere: it is salted per process, so a fingerprint built on it would cluster
differently in each worker, and two servers behind a load balancer would disagree
about whether a claim is corroborated. Sets are intersected exactly instead.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace

from app.domain.research import DateBasis, Retrieval, Source
from app.research import terms, urls

__all__ = [
    "CONTAINMENT_THRESHOLD",
    "MIN_ANCHORS",
    "MIN_SHINGLES",
    "SHINGLE_WIDTH",
    "TITLE_RESCUE_CEILING",
    "TITLE_RESCUE_FLOOR",
    "TITLE_RESCUE_TITLE",
    "Grouping",
    "PageGroup",
    "anchors",
    "cluster",
    "containment",
    "flatten",
    "group",
    "shingles",
]

#: Words per shingle.
#:
#: Three. At one word, a three-token fragment measures containment 1.000 against an
#: unrelated article; at two it is thin; at three, zero false merges across 4,640
#: independent pairs; at four and five the only change is lost recall.
SHINGLE_WIDTH = 3

#: Snippet containment at or above which two sources may be one story.
#:
#: 0.85 — the top of the measured recall plateau. Recall is flat from 0.70 to 0.85 and
#: falls off above it, while false merges stay at zero across the whole range, so this
#: is the most merge-averse setting that costs nothing.
CONTAINMENT_THRESHOLD = 0.85

#: Shared anchors required. The defence against a publisher's own boilerplate, which
#: no threshold separates from syndication. Not optional.
MIN_ANCHORS = 2

#: Trigrams required on the shorter side, below which no clustering is attempted.
#:
#: Containment is 1.0 for any subset however small, which is the property that buys
#: truncation-invariance and the property that would merge a fragment into anything.
MIN_SHINGLES = 5

#: The title rescue: a band in which a similar headline may add a merge.
#:
#: Titles can add a merge and can never veto one, and they are never averaged with the
#: snippet score. Syndicated copy routinely keeps the body verbatim under a rewritten
#: headline — title containment 0.000, snippet containment 1.000 — and a weighted sum
#: turns the commonest syndication pattern into a guaranteed false split.
TITLE_RESCUE_TITLE = 0.70
TITLE_RESCUE_FLOOR = 0.75
TITLE_RESCUE_CEILING = CONTAINMENT_THRESHOLD


@dataclass(frozen=True, slots=True)
class PageGroup:
    """Every retrieval of one page, collapsed onto one identity.

    The intermediate between :func:`app.search.fanout.harvest` and
    :class:`~app.domain.research.Source`: this settles what counts as one page, and
    :mod:`app.research.dossier` adds the evidence and the date.
    """

    #: The normalised URL — the identity the retrievals were grouped on.
    url: str
    #: Every distinct spelling a provider returned, in the order first seen.
    urls: tuple[str, ...]
    #: Host of the normalised URL, lower-cased.
    host: str
    #: Registrable domain: the unit of publisher identity.
    domain: str
    #: Every retrieval of this page, in the order they arrived.
    retrievals: tuple[Retrieval, ...]

    @property
    def title(self) -> str:
        """The title from whichever provider ranked this page highest.

        Chosen rather than composed. Providers disagree about titles — one appends
        the masthead, another truncates — and each one's own string stays on its
        :class:`~app.domain.research.Retrieval`, so a reader can see the
        disagreement. Taking the best-ranked provider's is a rule; splicing the
        longest prefix of one onto another would be this service writing a headline.
        """
        best = min(self.retrievals, key=lambda retrieval: retrieval.rank)
        return best.title


@dataclass(frozen=True, slots=True)
class Grouping:
    """The result of :func:`group`: the pages, and what could not be used."""

    pages: tuple[PageGroup, ...]
    #: URLs that are not addressable web pages — a ``mailto:``, a malformed
    #: authority. Returned rather than silently dropped so the caller can say how
    #: many results went nowhere instead of reporting a thinner search as a complete
    #: one.
    dropped: tuple[str, ...] = ()


def group(retrievals: Iterable[Retrieval]) -> Grouping:
    """Collapse ``retrievals`` onto one entry per page, in first-appearance order.

    Each URL is unwrapped first — an AMP cache or a translation mirror is a wrapper
    around a URL, and leaving it wrapped would file the same article twice — and then
    normalised. Ordering follows the retrievals, which the fan-out emits provider by
    provider, so the caller decides what "strongest" means rather than inheriting it
    from here.
    """
    pages: dict[str, list[Retrieval]] = {}
    spellings: dict[str, list[str]] = {}
    dropped: list[str] = []

    for retrieval in retrievals:
        target = urls.normalise(urls.unwrap(retrieval.url))
        if target is None:
            dropped.append(retrieval.url)
            continue
        pages.setdefault(target, []).append(retrieval)
        seen = spellings.setdefault(target, [])
        if retrieval.url not in seen:
            seen.append(retrieval.url)

    built: list[PageGroup] = []
    for target, found in pages.items():
        host = urls.host_of(target) or ""
        built.append(
            PageGroup(
                url=target,
                urls=tuple(spellings[target]),
                host=host,
                domain=urls.registrable_domain(host) if host else "",
                retrievals=tuple(found),
            )
        )
    return Grouping(pages=tuple(built), dropped=tuple(dropped))


# --------------------------------------------------------------- syndication ----


def cluster(sources: Sequence[Source]) -> tuple[Source, ...]:
    """Label the sources that are telling the same story, and change nothing else.

    Returns every source given, in the same order, with
    :attr:`~app.domain.research.Source.cluster` set on the members of any
    multi-source cluster and left ``None`` on the ones that stand alone. Nothing is
    dropped and nothing is merged — the whole point of a label is that the count can
    be corrected by a reader who disagrees with it.

    Called per claim: two claims' sources are not candidates to be one story, and
    comparing across them would let an unrelated claim's coverage absorb a source.

    Deterministic by construction, not by convention. Similarity is symmetric,
    components are single-link, and the union always reparents the lexicographically
    greater root onto the lesser, so neither the parent forest nor the resulting
    components depend on the order the providers happened to answer in.
    """
    if len(sources) < 2:
        return tuple(sources)

    prints = {source.url: _Print.of(source) for source in sources}
    roots = _components(
        sorted(prints), lambda a, b: _same_story(prints[a], prints[b])
    )

    members: dict[str, list[Source]] = {}
    for source in sources:
        members.setdefault(roots[source.url], []).append(source)

    # Only multi-member clusters are numbered. Numbering singletons too would let one
    # consume id 1 and leave the response with a gap where a reader looks for it.
    ranked = sorted(
        (group_ for group_ in members.values() if len(group_) > 1),
        key=lambda group_: min(_origin(source) for source in group_),
    )
    label = {
        source.url: index
        for index, group_ in enumerate(ranked, start=1)
        for source in group_
    }
    return tuple(
        replace(source, cluster=label.get(source.url)) for source in sources
    )


@dataclass(frozen=True, slots=True)
class _Print:
    """One source reduced to what similarity is measured on."""

    snippet: frozenset[tuple[str, ...]]
    title: frozenset[tuple[str, ...]]
    anchors: frozenset[str]

    @classmethod
    def of(cls, source: Source) -> _Print:
        """Fingerprint ``source`` from the longest snippet any provider returned.

        The longest, not a union of all of them: containment is insensitive to extra
        material on the longer side, so the longest single snippet loses nothing —
        and unlike a union it is text a provider actually sent. A fingerprint built
        by pooling several providers' snippets would represent a document none of
        them returned, which is the same mistake as stitching a quote out of two.
        """
        best = max(
            (retrieval.snippet for retrieval in source.retrievals),
            key=len,
            default="",
        )
        return cls(
            snippet=shingles(best),
            title=shingles(source.title),
            # Joined with a terminator, not a space. A title rarely ends in one, so
            # a bare space would leave the snippet's opening word looking
            # mid-sentence and count it as a proper noun — measured: two unrelated
            # stories behind one newsletter block shared the false anchor ``sign``
            # from "Sign up for our newsletter", eroding the only defence there is
            # against boilerplate.
            anchors=anchors(f"{source.title}. {best}"),
        )


def _same_story(left: _Print, right: _Print) -> bool:
    """Whether two fingerprints are one story, under the full gate.

    The conjunction is what makes this lean toward a false split. Every condition has
    a measured failure it exists to prevent, and any one of them alone is unsafe.
    """
    if min(len(left.snippet), len(right.snippet)) < MIN_SHINGLES:
        return False
    if len(left.anchors & right.anchors) < MIN_ANCHORS:
        return False

    overlap = containment(left.snippet, right.snippet)
    if overlap >= CONTAINMENT_THRESHOLD:
        return True
    return (
        TITLE_RESCUE_FLOOR <= overlap < TITLE_RESCUE_CEILING
        and containment(left.title, right.title) >= TITLE_RESCUE_TITLE
    )


def _origin(source: Source) -> tuple[tuple[int, str], int, int, str]:
    """The sort key that picks a cluster's representative and orders the clusters.

    Earliest stated publication date first, as the best available proxy for which
    masthead ran it first; then the strongest rank any provider gave it; then the
    most providers; then the URL, which is already the deduplication identity and so
    guarantees a strict total order.

    An undated source sorts last and can never win by default — ``(1, "")`` after
    every ``(0, iso)``. Only :attr:`~app.domain.research.DateBasis.PROVIDER` counts
    as stated: a modification date or a relative age says nothing reliable about who
    published first, and an ordering built on them would present a guess as
    provenance. Nothing here consults the publisher's reputation, which is the
    fact-check desk's judgement to make and not this module's.
    """
    dated: tuple[int, str] = (
        (0, source.published_at.isoformat())
        if source.published_at is not None and source.date_basis is DateBasis.PROVIDER
        else (1, "")
    )
    return dated, source.best_rank, -len(source.providers), source.url


def _components(
    keys: Sequence[str], related: Callable[[str, str], bool]
) -> dict[str, str]:
    """Single-link connected components, as a map from key to component root.

    Union-find over all pairs. No blocking: at these sizes the whole comparison is
    microseconds, and a blocking key would trade a real recall risk for them.
    """
    parent = {key: key for key in keys}

    def find(key: str) -> str:
        root = key
        while parent[root] != root:
            root = parent[root]
        while parent[key] != root:  # path compression
            parent[key], key = root, parent[key]
        return root

    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            if not related(left, right):
                continue
            first, second = find(left), find(right)
            if first != second:
                # By name, not by tree size: rank-based union would make the forest
                # depend on the order pairs arrived in.
                parent[max(first, second)] = min(first, second)

    return {key: find(key) for key in keys}


# ------------------------------------------------------------ text handling ----


def containment(left: frozenset[object], right: frozenset[object]) -> float:
    """``|A ∩ B| / min(|A|, |B|)``, the overlap coefficient.

    1.0 whenever either set is a subset of the other, which is exactly why it is used
    here and exactly what :data:`MIN_SHINGLES` guards.
    """
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def shingles(text: str, width: int = SHINGLE_WIDTH) -> frozenset[tuple[str, ...]]:
    """The set of word ``width``-grams of ``text``, flattened first.

    Tuples of tokens rather than joined strings, and a set rather than a sketch: the
    intersection is computed exactly, so there is no fingerprint to be salted and no
    estimator error to reason about.
    """
    tokens = _SHINGLE_TOKEN.findall(flatten(text))
    if len(tokens) < width:
        return frozenset()
    return frozenset(
        tuple(tokens[index : index + width])
        for index in range(len(tokens) - width + 1)
    )


def anchors(text: str) -> frozenset[str]:
    """Figures and mid-sentence proper nouns — the boilerplate defence.

    Read before case-folding, because capitalisation is the signal. A sentence-initial
    capital says nothing (every sentence has one), so only capitalised words that are
    *not* sentence-initial count, which is a crude proper-noun detector and the
    reason it is one of three conditions rather than the whole test.

    Known to be weaker on ALL-CAPS headlines and datelines, where the heuristic has
    nothing to distinguish. It degrades toward finding fewer anchors, which fails
    toward a false split rather than a false merge.
    """
    found = {figure.rstrip(".,") for figure in _FIGURE.findall(text)}
    found.discard("")
    for match in _CAPITALISED.finditer(text):
        if not _sentence_initial(text, match.start()):
            found.add(match.group().casefold())
    return frozenset(found)


def flatten(text: str) -> str:
    """Normalise provider text so two engines' copies of one page compare equal.

    The steps are ordered, and the order is not interchangeable:

    1. Unescape entities to a fixpoint, bounded. One pass turns ``&amp;amp;`` into
       ``&amp;`` rather than ``&``, and unescaping *before* stripping tags is what
       makes one engine's ``<b>Bank</b>`` and another's ``&lt;b&gt;Bank&lt;/b&gt;``
       land on the same token.
    2. Strip tags, length-bounded so a stray ``<`` cannot eat the snippet.
    3. NFKC, which folds ``…`` to ``...`` and the exotic spaces to a plain one.
    4. Fold the punctuation NFKC leaves alone — curly quotes, dashes, primes. Without
       this, one engine's typographic apostrophe against another's ASCII one breaks
       every trigram spanning the word on genuinely identical copy.
    5. Delete zero-width and bidi characters, which NFKC also leaves.
    6. Strip markdown emphasis, which some providers add.
    7. Collapse what is left of truncation markers.
    8. ``casefold``, not ``lower``.
    9. Collapse whitespace.

    Accents are deliberately *not* stripped, unlike :func:`app.research.terms.fold`.
    Folding them would only ever raise containment between two spellings of one name,
    so it would very likely help — but :data:`CONTAINMENT_THRESHOLD` and
    :data:`MIN_ANCHORS` were measured against exactly this pipeline, and changing what
    is compared without re-measuring what it takes to merge would leave the thresholds
    describing a pipeline that no longer exists. The cost is that a story naming
    ``Wałęsa`` in one engine's snippet and ``Walesa`` in another's loses the trigrams
    spanning that word, which pushes toward a false split.
    """
    out = text
    for _ in range(3):
        unescaped = html.unescape(out)
        if unescaped == out:
            break
        out = unescaped
    out = _TAG.sub(" ", out)
    out = unicodedata.normalize("NFKC", out)
    out = out.translate(_FOLD)
    out = _MARKDOWN.sub("", out)
    out = _TRUNCATION.sub(" ", out)
    return terms.squeeze(out.casefold())


def _sentence_initial(text: str, start: int) -> bool:
    """Whether the word at ``start`` opens a sentence."""
    index = start - 1
    while index >= 0 and text[index].isspace():
        index -= 1
    return index < 0 or text[index] in ".!?"


#: Tokens for shingling: words, and figures kept whole.
#:
#: A different tokeniser from :func:`app.research.terms.words` on purpose. That one
#: excludes digits because everything else in this package reads figures through
#: :func:`app.research.terms.numbers`, which canonicalises them; here two snippets are
#: compared to each other, and a tokeniser that split ``4.3`` into ``4`` and ``3``
#: would destroy the strongest anchors there are.
#:
#: The character range covers Latin-1 Supplement and Extended-A after case-folding.
#: Scripts outside it — Chinese, Japanese, Thai, Cyrillic, Greek — tokenise to little
#: or nothing, so their snippets fall below :data:`MIN_SHINGLES` and are never
#: clustered. That is a real gap, and it fails toward reporting more stories than
#: there are rather than fewer.
_SHINGLE_TOKEN = re.compile(r"[0-9a-zà-ɏ]+(?:[.,][0-9]+)*")

#: A figure, kept in the text's own spelling — this is an identity to be matched
#: between two snippets, not a quantity to be compared, so no canonicalisation.
_FIGURE = re.compile(r"\d[\d.,]*%?")

#: A capitalised word of three characters or more.
_CAPITALISED = re.compile(r"\b[A-Z][a-zA-Z'’-]{2,}")

_TAG = re.compile(r"<[^>]{0,80}>")
_MARKDOWN = re.compile(r"(\*{1,3}|_{1,3}|`+|~~)")
_TRUNCATION = re.compile(r"(?:\s*\.\s*){2,}|…|⋯|‥")

#: Punctuation NFKC does not fold, plus the invisibles it does not delete.
_FOLD = {
    **{
        ord(char): "'"
        for char in "‘’‚‛′´ʼ‵"
    },
    **{ord(char): '"' for char in "“”„‟″«»"},
    **{ord(char): "-" for char in "‐‑‒–—―−"},
    **dict.fromkeys(
        (
            0x00AD,  # soft hyphen
            0x200B,  # zero-width space
            0x200C,
            0x200D,
            0x200E,
            0x200F,
            0x202A,
            0x202B,
            0x202C,
            0x202D,
            0x202E,
            0x2060,
            0xFEFF,  # byte-order mark
        )
    ),
}
