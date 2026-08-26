"""Claims, entities and keywords read out of prose.

The text desk reads copy; the fact-check desk reads "a single checkable claim".
This module is the shape that passes between them, and the shape ``POST
/api/v1/extract-claim`` returns so a caller can perform that step explicitly.

Everything here is a plain frozen dataclass. In particular nothing in this module
knows that spaCy exists: :mod:`app.nlp` produces these types and is the only place
a parser is imported, which is what lets the service, the schemas and their tests
run in an environment with no NLP libraries installed at all.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Entity:
    """A named thing mentioned in the text.

    ``label`` is the extractor's own tag rather than a closed enum of ours —
    ``PERSON``, ``ORG``, ``GPE``, ``DATE``, ``MONEY`` and the rest of the OntoNotes
    set for the spaCy pipeline. Fixing it to an enum here would mean either
    discarding labels a model produces or editing the domain every time a model
    changes, and the label's consumer is a person reading a record or a desk
    deciding what kind of evidence to go looking for — both of which cope with an
    unfamiliar tag better than with a dropped entity.
    """

    #: The entity as it appears in the source, verbatim.
    text: str
    #: The extractor's type tag, upper case.
    label: str
    #: Character offset of ``text`` in the submitted prose.
    start: int
    #: Exclusive end offset, so ``source[start:end] == text``.
    end: int


@dataclass(frozen=True, slots=True)
class Keyword:
    """A term that distinguishes one passage from the rest of the text.

    ``score`` is comparable within one extraction and meaningless across two: it is
    a TF-IDF weight computed against the other sentences of the same submission, so
    it says "this term is what makes this sentence different from its neighbours",
    not "this term is rare in English".
    """

    term: str
    #: Relative weight in ``[0, 1]``, normalised so the strongest term scores 1.0.
    score: float


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    """One assertion lifted out of a longer piece of text.

    ``text`` is rewritten to stand alone — a subject carried into a coordinated
    clause, a relative pronoun resolved to its antecedent — because the fact-check
    desk receives it without the surrounding prose and "and cost £4bn" is not a
    checkable claim. ``quote`` keeps the original span so the rewrite can always be
    audited against what was actually written, and ``start``/``end`` locate it
    exactly: ``source[start:end] == quote`` holds for every claim, which is what
    lets a client mark the claim in place without searching for the string and
    finding the wrong occurrence of it.
    """

    #: Position in the source, numbered from 1 in the order the claims appear.
    ref: int
    #: The self-contained, checkable assertion.
    text: str
    #: The exact words in the source that produced it.
    quote: str
    #: Character offset of ``quote`` in the submitted prose.
    start: int
    #: Exclusive end offset, so ``source[start:end] == quote``.
    end: int
    #: False for the sentences that cannot be checked against evidence at all —
    #: opinion, prediction, pure value judgement. They are returned marked rather
    #: than silently dropped, so a submitter can see why a sentence was skipped
    #: instead of assuming the extractor missed it.
    checkable: bool = True
    #: Why it is not checkable. Empty when it is. One of the stable identifiers in
    #: :class:`app.domain.claims.Unfit`, so a client may branch on it.
    reason: str = ""
    #: The named things this claim mentions. Offsets are into the whole submission,
    #: not into ``quote``, so one coordinate system serves the entire response.
    entities: tuple[Entity, ...] = ()
    #: What distinguishes this claim from the others, strongest first.
    keywords: tuple[Keyword, ...] = ()


@dataclass(frozen=True, slots=True)
class Extraction:
    """Everything read out of one submission.

    Document-level ``entities`` and ``keywords`` are not merely the union of the
    claims': they include what was found in sentences the screen rejected. A
    submission whose every sentence is opinion still tells you who and what it is
    about, and that is worth returning rather than discarding along with the
    sentences.
    """

    #: Every assertion found, checkable or not, in order of appearance.
    claims: tuple[ExtractedClaim, ...]
    #: Every distinct named thing in the submission, in order of first appearance.
    entities: tuple[Entity, ...]
    #: What the submission as a whole is about, strongest first.
    keywords: tuple[Keyword, ...]
    #: How many sentences were read. Larger than ``len(claims)`` when sentences were
    #: discarded as unreadable, smaller when one sentence yielded several claims —
    #: either way it is the number that tells a caller whether the extractor saw
    #: what it submitted.
    sentences: int

    @property
    def checkable(self) -> tuple[ExtractedClaim, ...]:
        """The claims a fact-check desk could actually work on."""
        return tuple(claim for claim in self.claims if claim.checkable)


class Unfit:
    """Why a sentence is not a checkable claim.

    Stable strings, not an enum, for the same reason :attr:`Entity.label` is not
    one: these are set by the extractor and read by a person or a client that
    groups by them, and a new extractor with a new reason should not have to widen a
    domain enum to report it. Collected in one class so the strings an extractor
    emits and the strings a test asserts on come from the same place.

    Note what is *not* here: "false". Deciding an assertion is wrong is the
    fact-check desk's work, and this screen only decides whether the desk has
    anything to work with. "The moon is made of cheese" is perfectly checkable.
    """

    #: No subject, or no finite verb: a headline, a caption, a list item.
    FRAGMENT = "fragment"
    #: Too little content to check even if it parses.
    TOO_SHORT = "too_short"
    #: A question asserts nothing.
    QUESTION = "question"
    #: An instruction asserts nothing.
    IMPERATIVE = "imperative"
    #: Framed as the writer's own stance, or resting on a value judgement.
    OPINION = "opinion"
    #: About the future. Not checkable *yet*, which is different from not checkable.
    PREDICTION = "prediction"
    #: Conditional or counterfactual: the sentence does not claim its own content.
    HYPOTHETICAL = "hypothetical"
    #: Reports that someone spoke without reporting what they said.
    ATTRIBUTION_ONLY = "attribution_only"
    #: Parses as an assertion but names nothing evidence could be found about.
    NO_CONTENT = "no_content"
