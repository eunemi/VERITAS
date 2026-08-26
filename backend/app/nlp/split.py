"""Splitting a sentence that asserts more than one thing.

"The bridge opened in March and cost £4bn" is two claims. Sent to a fact-check desk
whole, it gets one verdict covering both, and a verdict that is half right is
indistinguishable from one that is wrong. So the sentence is cut at its coordinated
verbs and its parenthetical relative clauses, and each piece is rewritten to stand
alone — the subject carried into the second clause, the relative pronoun resolved to
the noun it stands for.

**This module is deliberately conservative, and every guard here exists because the
alternative is manufacturing a claim nobody made.** A missed split costs one
coarse-grained verdict. A wrong split invents an assertion and then attaches
evidence to it, which is worse than not splitting at all. So each rule below
refuses in the ambiguous case:

``conj`` children of the sentence root only
    "He said the bridge opened and cost £4bn" has ``cost`` conjoined to ``opened``,
    which is inside ``said``'s complement — not to the root. Splitting there yields
    "the bridge cost £4bn" as an assertion of the article, when the article asserts
    only that *he* said it. Requiring the conjunct to hang off the root drops the
    attribution problem, the modal-scope problem and the embedded-clause problem in
    one line.

only when the conjunct is a verb
    "The bridge and the tunnel opened" coordinates two nouns; "The bridge cost £4bn
    and the tunnel £2bn" coordinates a noun with the verb elided. Both have a
    ``conj`` edge and neither is two clauses, so the conjunct must itself be a
    ``VERB`` or ``AUX``.

never under a negation
    "The bridge did not open in March or cost £4bn" denies both halves. The
    negation attaches to the first verb, so a split produces "The bridge cost £4bn"
    — the exact opposite of the sentence. Rather than try to carry ``neg`` scope
    correctly, this refuses to split at all.

restrictive relative clauses are not claims
    "The people who signed the letter resigned" does not assert that the people
    resigned; it asserts it of the subset who signed. Removing the clause changes
    the subject's reference. Non-restrictive clauses — the ones set off by a comma —
    genuinely are parenthetical assertions: "The bridge, which cost £4bn, opened"
    does assert that the bridge cost £4bn. The comma is the distinction English
    itself marks, so the comma is what this tests.

subject relatives only
    "The report, which the minister signed, was leaked" would need the clause
    reordered to "the minister signed the report" — a transformation with its own
    failure modes. Only a relative pronoun in subject position is resolved, where
    substituting the antecedent is all that is required.

What each piece keeps is its own span in the source, so ``quote`` is always the
words that were written even where ``text`` is a rewrite. For the main clause of a
sentence with a relative clause cut out of the middle, that span still covers the
clause — the quote is wider than the rewrite, which is the honest way round.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - spaCy is imported only by the pipeline
    from spacy.tokens import Span, Token

#: Dependency labels that make a token the subject of its clause. ``expl`` is the
#: "there" of "There were three votes" — not a semantic subject, but the thing that
#: has to be carried across a conjunction for the clause to read as English.
_SUBJECTS = frozenset({"nsubj", "nsubjpass", "csubj", "csubjpass", "expl"})

#: Tags for a relative pronoun: ``who``/``whom``/``whose`` (WP, WP$), ``which``
#: and ``that`` in relative use (WDT).
_RELATIVE_TAGS = frozenset({"WDT", "WP", "WP$"})

#: Whitespace before punctuation that should hug the previous word, left behind
#: whenever a clause is removed from the middle of a sentence.
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,;:.!?)\]])")
_SPACE_AFTER_OPEN = re.compile(r"([(\[])\s+")
_REPEATED_COMMA = re.compile(r"(?:\s*,)+(\s*,)")
_MULTI_SPACE = re.compile(r"\s{2,}")

#: Characters a rewrite may be left starting or ending on once the words either side
#: of them have gone. Stripped from both ends of the rewritten text, never from the
#: quote.
_DEBRIS = " ,;:-–—"


@dataclass(frozen=True, slots=True)
class Clause:
    """One assertion's worth of a sentence, with the syntax that produced it.

    Carries the parse rather than only the text because the checkability screen runs
    *after* the split and needs to ask real syntactic questions of each piece —
    whether it has a finite verb, whether its root is a modal, whether anything in
    it is a named entity. Re-parsing the rewritten string to recover that would be
    both slower and less accurate, since a rewrite is not always well-formed.
    """

    #: The clause's main verb: the sentence root, a conjunct of it, or a relative
    #: clause's verb.
    head: Token
    #: The tokens this clause is built from, in document order. A subject carried in
    #: from another clause is included, so the screen sees the clause as rewritten.
    tokens: tuple[Token, ...]
    #: The rewritten, self-contained assertion.
    text: str
    #: Character offset in the *source document* of the verbatim span behind this
    #: clause. Already absolute — the caller's sentence offset is applied here.
    start: int
    #: Exclusive end offset of that span.
    end: int


def clauses(sent: Span, offset: int) -> list[Clause]:
    """Split one parsed sentence into its separately checkable assertions.

    ``offset`` is where ``sent``'s document begins in the submitted text; every
    offset on the returned clauses is shifted by it, so callers never see a
    sentence-relative number.

    Returns at least one clause for any sentence with tokens — a sentence that
    cannot be split is returned whole, which is the common case and not a failure.
    """
    root = sent.root
    if any(child.dep_ == "neg" for child in root.children):
        return [_whole(sent, offset)]

    conjuncts = [
        child
        for child in root.children
        if child.dep_ == "conj" and child.pos_ in {"VERB", "AUX"}
    ]
    relatives = [
        token
        for token in sent
        if token.dep_ == "relcl" and _splittable_relative(token, sent)
    ]
    if not conjuncts and not relatives:
        return [_whole(sent, offset)]

    # Everything the main clause gives up: each conjunct's subtree and the
    # conjunction that introduced it, and each relative clause's subtree.
    removed: set[int] = set()
    for conjunct in conjuncts:
        removed |= _subtree(conjunct)
        removed |= {
            child.i for child in conjunct.children if child.dep_ == "cc"
        } | {child.i for child in root.children if child.dep_ == "cc"}
    for relative in relatives:
        removed |= _subtree(relative)
        removed |= _brackets(relative, sent)

    subject = next((c for c in root.children if c.dep_ in _SUBJECTS), None)
    main_tokens = tuple(token for token in sent if token.i not in removed)
    if not main_tokens:  # pragma: no cover - a root cannot be its own conjunct
        return [_whole(sent, offset)]

    found = [_clause(root, main_tokens, _detokenize(main_tokens), offset)]
    for conjunct in conjuncts:
        found.append(_coordinate(conjunct, subject, offset))
    for relative in relatives:
        resolved = _relative(relative, offset)
        if resolved is not None:
            found.append(resolved)
    found.sort(key=lambda clause: clause.start)
    return found


# ------------------------------------------------------------- the two rules ----


def _coordinate(conjunct: Token, subject: Token | None, offset: int) -> Clause:
    """Build the clause for a coordinated verb, carrying the subject if needed.

    The auxiliary is deliberately *not* carried. "The bridge was built in 2020 and
    opened in 2026" wants "The bridge opened in 2026", not "The bridge was opened in
    2026" — the second clause has its own voice, and borrowing the first's changes
    it.
    """
    own = tuple(
        token
        for token in sorted(conjunct.subtree, key=lambda t: t.i)
        if token.dep_ != "cc"
    )
    carried: tuple[Token, ...] = ()
    if subject is not None and not any(
        child.dep_ in _SUBJECTS for child in conjunct.children
    ):
        carried = tuple(sorted(subject.subtree, key=lambda t: t.i))

    text = _detokenize(carried + own) if carried else _detokenize(own)
    # The span is the conjunct's own words. A carried subject is a rewrite, and
    # widening the quote to cover it would claim the source said something here that
    # it said once, earlier, about both clauses.
    return _clause(conjunct, carried + own, text, offset, span_tokens=own)


def _relative(relative: Token, offset: int) -> Clause | None:
    """Build the clause for a non-restrictive relative, resolving its pronoun.

    "…, which cost £4bn, …" becomes "The bridge cost £4bn": the relative pronoun is
    dropped and the antecedent — its head noun, minus the relative clause itself —
    takes its place.
    """
    pronoun = next(
        (
            token
            for token in relative.subtree
            if token.tag_ in _RELATIVE_TAGS and token.dep_ in _SUBJECTS
        ),
        None,
    )
    if pronoun is None:  # pragma: no cover - guarded by _splittable_relative
        return None

    inside = _subtree(relative)
    antecedent = tuple(
        token
        for token in sorted(relative.head.subtree, key=lambda t: t.i)
        if token.i not in inside and token.dep_ != "punct"
    )
    own = tuple(
        token
        for token in sorted(relative.subtree, key=lambda t: t.i)
        if token.i != pronoun.i
    )
    if not antecedent or not own:
        return None
    return _clause(
        relative, antecedent + own, _detokenize(antecedent + own), offset,
        span_tokens=own,
    )


def _splittable_relative(relative: Token, sent: Span) -> bool:
    """True for a comma-marked relative clause with a subject relative pronoun.

    Both halves matter. The comma is what separates "The bridge, which cost £4bn,
    opened" — a parenthetical assertion — from "The people who signed the letter
    resigned", where the clause picks out *which* people and cannot be lifted off
    without changing who the sentence is about.
    """
    leftmost = min(token.i for token in relative.subtree)
    if leftmost <= sent.start:
        return False
    if relative.doc[leftmost - 1].text != ",":
        return False
    return any(
        token.tag_ in _RELATIVE_TAGS and token.dep_ in _SUBJECTS
        for token in relative.subtree
    )


# ------------------------------------------------------------------ plumbing ----


def _whole(sent: Span, offset: int) -> Clause:
    """The sentence as one clause, unmodified."""
    tokens = tuple(sent)
    return _clause(sent.root, tokens, sent.text.strip(), offset)


def _clause(
    head: Token,
    tokens: tuple[Token, ...],
    text: str,
    offset: int,
    *,
    span_tokens: tuple[Token, ...] | None = None,
) -> Clause:
    """Assemble a clause, computing its source span from ``span_tokens``.

    ``span_tokens`` defaults to ``tokens`` and differs only where a rewrite pulled
    in words from elsewhere in the sentence: the span must cover what this clause
    actually occupies in the source, not what the rewrite borrowed.

    The span is a contiguous range from the first to the last of those tokens, and
    punctuation is excluded from the two ends before it is measured. Both details
    matter and the second is not tidying. A sentence's full stop attaches to its root,
    so it survives into the main clause of "…opened in 2017 and cost £1.35bn." — and
    measuring to it would make that clause's quote the entire sentence, including the
    conjunct that was just split off into a claim of its own. Two claims would then
    quote the same words and a reader highlighting the first would see both.
    """
    bounds = span_tokens if span_tokens is not None else tokens
    inner = tuple(token for token in bounds if not (token.is_punct or token.is_space))
    if inner:
        bounds = inner
    start = min(token.idx for token in bounds)
    last = max(bounds, key=lambda token: token.idx)
    return Clause(
        head=head,
        tokens=tokens,
        text=text,
        start=offset + start,
        end=offset + last.idx + len(last.text),
    )


def _subtree(token: Token) -> set[int]:
    """Document indices of ``token`` and everything beneath it."""
    return {descendant.i for descendant in token.subtree}


def _brackets(relative: Token, sent: Span) -> set[int]:
    """Indices of the commas bracketing a parenthetical clause.

    They belong to the clause they enclose, not to the sentence around it, and
    removing the clause without them leaves "The bridge, opened in March." — a comma
    marking a boundary that no longer exists. Only a comma directly against the
    clause's edge counts, so nothing is taken from a list elsewhere in the sentence.
    """
    doc = relative.doc
    inside = _subtree(relative)
    leftmost, rightmost = min(inside), max(inside)
    found: set[int] = set()
    if leftmost - 1 >= sent.start and doc[leftmost - 1].text == ",":
        found.add(leftmost - 1)
    if rightmost + 1 < sent.end and doc[rightmost + 1].text == ",":
        found.add(rightmost + 1)
    return found


def _detokenize(tokens: tuple[Token, ...]) -> str:
    """Rebuild readable text from a possibly discontiguous run of tokens.

    Spacing is decided from the source offsets rather than from ``text_with_ws``, and
    that is the difference between "The bridge cost £4bn" and "The bridgecost £4bn". A
    token's trailing whitespace belongs to *it*, so when the token that used to
    separate two survivors is removed — a conjunction, a comma, a whole parenthetical
    — its space goes with it and the two words run together. Measuring the gap between
    the tokens that are actually here cannot make that mistake.

    All of this is cosmetic and applies only to the rewritten ``text``. ``quote`` is a
    slice of the source and is never touched by any of it.
    """
    if not tokens:
        return ""

    parts: list[str] = [tokens[0].text]
    for previous, token in zip(tokens, tokens[1:], strict=False):
        adjacent = token.idx == previous.idx + len(previous.text)
        if not adjacent and not token.is_punct:
            parts.append(" ")
        parts.append(token.text)

    text = _MULTI_SPACE.sub(" ", "".join(parts)).strip()
    text = _REPEATED_COMMA.sub(r"\1", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN.sub(r"\1", text)
    text = text.lstrip(_DEBRIS).strip()
    if not text:
        return ""
    if text[0].islower():
        text = text[0].upper() + text[1:]

    # Take the run's own terminator off, clear whatever the cut left leaning against
    # it, then put it back. A clause lifted out of the middle of a sentence ends on
    # the comma that separated it from the next one, and "…in March,." is not prose.
    # The terminator is preserved rather than replaced so a question stays a question.
    body = text.rstrip(".!?")
    terminator = text[len(body) :] or "."
    body = body.rstrip(_DEBRIS)
    return f"{body}{terminator}" if body else ""
