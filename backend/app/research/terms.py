"""Words and figures, tokenised once so that three modules cannot disagree.

:mod:`app.research.queries` builds search queries out of a claim's terms and
:mod:`app.research.evidence` decides which passage of a snippet repeats them. Both
need to answer "what are the words here" and "what are the figures here", and if
each answered it differently the dossier would contain a query built from terms the
evidence scorer could not find.

:mod:`app.research.dedupe` takes only :func:`squeeze` from here and deliberately
normalises and tokenises its own way, because it is doing a different job: it compares
two snippets to *each other*, so a figure has to survive as one token inside the text,
while everything here keeps figures in a separate channel from words. Its thresholds
were measured against its own pipeline, which is the other reason not to share one.
That module says so where it defines it.

**Nothing here imports a dependency, and that is a constraint rather than an
accident.** :mod:`app.nlp` has a tokeniser and a stopword list already, both far
better than these, and both arrive with spaCy and scikit-learn attached. Everything
in :mod:`app.research` runs on text that came back from a search API, on the request
path, and it has to keep working when the NLP extras are not installed — a
deployment that can search but cannot load a language model should still produce a
dossier. So this is a deliberate second, smaller tokeniser, and the two are allowed
to differ: :mod:`app.nlp` is ranking terms in a document a person wrote, and this is
matching terms across snippets three search engines wrote.

The figure handling is the part worth reading closely. A claim's numbers are the
most checkable thing in it, so they are also the easiest thing to appear to check
by accident — which is why :func:`canonical_number` normalises only what is
unambiguously the same figure written differently (thousands separators, ``%``
against the word "percent") and leaves everything else alone. ``4.6`` and ``4.60``
stay different figures here. They are the same quantity, but they are not the same
statement about precision, and a match this module reported between them would put
a figure in :attr:`~app.domain.research.Evidence.matched_numbers` that the passage
does not contain.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

__all__ = [
    "STOPWORDS",
    "canonical_number",
    "content_words",
    "fold",
    "numbers",
    "squeeze",
    "subphrase",
    "words",
]

#: Letter runs, with internal apostrophes and hyphens kept: ``don't`` and
#: ``state-of-the-art`` are each one token. Digits are excluded on purpose — they
#: are handled by :func:`numbers`, which understands separators and percentages that
#: a word tokeniser would split in the middle.
_WORD = re.compile(r"[^\W\d_]+(?:['’‐-][^\W\d_]+)*", re.UNICODE)

#: A figure, with optional thousands separators, decimals and percentage.
#:
#: The leading guard is what keeps this from firing inside an identifier: the ``19``
#: of ``covid-19`` is not a figure anyone is checking, and ``3`` out of ``v3.2.1``
#: is not either. Currency symbols are matched but not captured — ``$5bn`` and
#: ``5bn`` carry the same figure, and the magnitude word is a word, so
#: :func:`words` already has it.
_NUMBER = re.compile(
    r"""
    (?<![\w.])
    [$£€¥]?
    (?P<digits>
        \d{1,3}(?:,\d{3})+(?:\.\d+)?      # 1,234 or 1,234,567.89
      | \d+(?:\.\d+)?                     # 1234 or 1234.89
    )
    \s*
    (?P<percent>%|percent|per\s+cent|pc\b)?
    """,
    re.VERBOSE | re.IGNORECASE,
)

#: Function words, dropped when comparing what two texts are *about*.
#:
#: Short and hand-written, because the job is narrow: these are the words that would
#: otherwise make every snippet look like every claim. It is not a linguistic
#: resource and it is not trying to be scikit-learn's list — notably it keeps
#: negations (``not``, ``no``, ``never``) and comparatives (``more``, ``less``),
#: since "unemployment did *not* fall" and "unemployment fell" must not reduce to
#: the same set of terms. Dropping a negation here would make a contradiction look
#: like a corroboration.
STOPWORDS: frozenset[str] = frozenset(
    [
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "and",
        "or",
        "but",
        "nor",
        "so",
        "yet",
        "for",
        "of",
        "in",
        "on",
        "at",
        "to",
        "from",
        "by",
        "with",
        "within",
        "into",
        "onto",
        "over",
        "under",
        "about",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "has",
        "have",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "will",
        "would",
        "shall",
        "should",
        "can",
        "could",
        "may",
        "might",
        "must",
        "it",
        "its",
        "it's",
        "they",
        "them",
        "their",
        "there",
        "here",
        "he",
        "him",
        "his",
        "she",
        "her",
        "hers",
        "we",
        "us",
        "our",
        "you",
        "your",
        "i",
        "me",
        "my",
        "as",
        "if",
        "then",
        "than",
        "too",
        "very",
        "just",
        "also",
        "only",
        "even",
        "still",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "said",
        "says",
        "say",
        "told",
        "according",
    ]
)


def squeeze(text: str) -> str:
    """Collapse whitespace runs to single spaces and strip the ends.

    Used for comparing and for building queries, never for anything a quote is
    sliced out of: collapsing whitespace shifts every offset after it, and
    :class:`~app.domain.research.Evidence` offsets index the provider's original
    string.
    """
    return " ".join(text.split())


def words(text: str) -> tuple[str, ...]:
    """Every word token in ``text``, case-folded, in order, with repeats.

    Repeats are kept because a term used three times in a snippet is more likely to
    be its subject than one used once, and a caller that wants the set can take
    one.

    Case-folded rather than lower-cased: ``casefold`` handles the cases
    ``lower`` does not (German ``ß``, Greek final sigma), and a match that failed on
    a Turkish dotless *i* would drop a real source.
    """
    return tuple(match.group().casefold() for match in _WORD.finditer(text))


def content_words(text: str) -> tuple[str, ...]:
    """:func:`words` without the function words, and without single letters.

    Single letters go too: an initial from ``J. Smith`` is not a term two texts can
    meaningfully share.
    """
    return tuple(w for w in words(text) if len(w) > 1 and w not in STOPWORDS)


def numbers(text: str) -> tuple[str, ...]:
    """Every figure in ``text``, canonicalised, in order, without repeats.

    Order is preserved rather than sorted so that a caller reporting them back —
    :attr:`~app.domain.research.Evidence.matched_numbers` — lists them as the text
    does.
    """
    found: list[str] = []
    for match in _NUMBER.finditer(text):
        figure = canonical_number(match.group("digits"), percent=match.group("percent"))
        if figure not in found:
            found.append(figure)
    return tuple(found)


def canonical_number(digits: str, *, percent: str | None = None) -> str:
    """One figure in the form two texts can be compared on.

    Two normalisations, and only two, because each is a case where the difference is
    provably typographic rather than a difference in what was claimed:

    * thousands separators are removed, so ``1,234`` and ``1234`` are one figure;
    * a trailing ``percent``, ``per cent`` or ``pc`` becomes ``%``, so "rose 4.6
      percent" matches "rose 4.6%".

    Everything else is left exactly as written. ``4.6`` and ``4.60`` stay distinct,
    ``1.2 million`` and ``1200000`` stay distinct, and ``2,019`` and ``2019`` become
    the same figure — which is the one case where this rule is a little generous,
    and is accepted because a thousands separator in a year is a typo rather than a
    different year.
    """
    core = digits.replace(",", "")
    return f"{core}%" if percent else core


def fold(text: str) -> str:
    """Case-folded and accent-stripped, for comparing names across publishers.

    Used where one masthead writes ``Lech Wałęsa`` and another writes ``Lech
    Walesa``, and by :mod:`app.research.evidence` so a claim naming the first still
    matches a snippet spelling the second. Never used on anything quoted: this
    changes characters, and a quote must keep the ones the provider sent.
    """
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def subphrase(needle: Sequence[str], haystack: Sequence[str]) -> bool:
    """Whether ``needle``'s tokens appear consecutively in ``haystack``.

    Token-wise rather than by substring, which is the difference between knowing that
    ``US`` is not part of ``USA`` and guessing that it is. Both callers are deciding
    whether one name contains another — :mod:`app.research.queries` to drop a
    redundant query term, :mod:`app.research.evidence` to decide whether a passage
    actually names the claim's entity — and in both a false positive is a quiet
    error rather than a loud one.
    """
    if not needle or len(needle) > len(haystack):
        return False
    span = len(needle)
    first = needle[0]
    return any(
        haystack[start] == first
        and list(haystack[start : start + span]) == list(needle)
        for start in range(len(haystack) - span + 1)
    )
