"""Request and response shapes for claim extraction."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from app.domain import Entity, ExtractedClaim, Extraction, Keyword


class ExtractClaimRequest(BaseModel):
    """Body of ``POST /extract-claim``."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        min_length=1,
        description=(
            "The prose to read. May be a full article; the upper bound is "
            "MAX_TEXT_CHARS, and exceeding it is a 413 rather than a 422."
        ),
    )


class EntityOut(BaseModel):
    """A named thing found in the prose.

    ``label`` is the extractor's own tag — ``PERSON``, ``ORG``, ``GPE``, ``DATE``,
    ``MONEY`` and the rest of the OntoNotes set for the spaCy pipeline — and is
    deliberately an open string rather than an enum, so a better model with a wider
    label set does not need this schema changed to report what it found.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    label: str = Field(description="Entity type, upper case. An open vocabulary.")
    start: int = Field(description="Character offset into the submitted `text`.")
    end: int = Field(description="Exclusive, so `text[start:end]` is this entity.")

    @classmethod
    def from_domain(cls, entity: Entity) -> Self:
        return cls(
            text=entity.text,
            label=entity.label,
            start=entity.start,
            end=entity.end,
        )


class KeywordOut(BaseModel):
    """A term that distinguishes one passage from the rest of the submission.

    No offsets, on purpose. A keyword is a term rather than a span: it is a lemma, so
    "opened" and "opens" arrive as one entry, and a two-word term can pair words the
    source separated with a stop word — "minister canada", from "the prime minister
    of Canada". Neither is a substring of the input, so offering offsets for them
    would be offering a lie.
    """

    model_config = ConfigDict(extra="forbid")

    term: str
    score: float = Field(
        description=(
            "Relative weight in (0, 1], normalised so the strongest term scores 1.0. "
            "A TF-IDF weight against the other sentences of this submission, so it "
            "is comparable within one response and meaningless across two."
        )
    )

    @classmethod
    def from_domain(cls, keyword: Keyword) -> Self:
        return cls(term=keyword.term, score=keyword.score)


class ExtractedClaimOut(BaseModel):
    """One assertion found in the prose.

    ``text`` is the claim rewritten to stand on its own — a subject carried into a
    coordinated clause, a relative pronoun resolved to its antecedent — because the
    fact-check desk receives it without the surrounding prose, and "and cost £4bn" is
    not a checkable claim. ``quote`` is the span it came from, verbatim, so the
    rewrite can always be audited against what was actually written.

    ``start`` and ``end`` locate ``quote`` exactly: ``text[start:end] == quote`` for
    the submitted text. That is what lets a client mark the claim in place instead of
    searching for the string and highlighting the wrong occurrence of it. Note that
    where a parenthetical clause was cut out of the middle of a sentence, the quote is
    *wider* than the rewrite — it still contains the words that were removed, because
    the quote's job is to be what the source says.
    """

    model_config = ConfigDict(extra="forbid")

    ref: int = Field(description="1-based, in order of appearance.")
    text: str
    quote: str
    start: int = Field(description="Character offset of `quote` in the submitted text.")
    end: int = Field(description="Exclusive, so `text[start:end] == quote`.")
    checkable: bool = Field(
        description="False for an assertion that cannot be checked as written."
    )
    reason: str = Field(
        default="",
        description=(
            "Why it is not checkable, empty when it is. One of a stable set: "
            "fragment, too_short, question, imperative, opinion, prediction, "
            "hypothetical, attribution_only, no_content. Note that `false` is not "
            "among them — whether a claim is true is the fact-check desk's finding, "
            "not this endpoint's."
        ),
    )
    entities: list[EntityOut] = Field(
        default_factory=list,
        description="Named things in this claim. Offsets are into the whole text.",
    )
    keywords: list[KeywordOut] = Field(
        default_factory=list, description="What distinguishes it, strongest first."
    )

    @classmethod
    def from_domain(cls, claim: ExtractedClaim) -> Self:
        return cls(
            ref=claim.ref,
            text=claim.text,
            quote=claim.quote,
            start=claim.start,
            end=claim.end,
            checkable=claim.checkable,
            reason=claim.reason,
            entities=[EntityOut.from_domain(e) for e in claim.entities],
            keywords=[KeywordOut.from_domain(k) for k in claim.keywords],
        )


class ExtractClaimResponse(BaseModel):
    """Body of the 200 from ``POST /extract-claim``.

    Two counts, because "how many claims" turned out to be two questions. ``count``
    is every clause returned including the ones marked unfit; ``checkable_count`` is
    the ones a fact-check desk could act on. A single ``count`` beside a list that
    contains both would be ambiguous in exactly the way that produces a UI saying
    "7 claims found" over a list of two.

    ``entities`` and ``keywords`` here are the document's, and are not merely the
    union of the claims'. They include what was found in clauses the screen rejected,
    because a submission of pure opinion still tells you who and what it is about,
    and discarding that along with the sentences would be throwing away the useful
    half of the answer.
    """

    model_config = ConfigDict(extra="forbid")

    claims: list[ExtractedClaimOut]
    count: int = Field(description="Total claims returned, checkable or not.")
    checkable_count: int = Field(description="How many of them are checkable.")
    sentences: int = Field(
        description=(
            "How many sentences were read. Compare with CLAIM_MAX_SENTENCES to tell "
            "a truncated submission from one that simply ended."
        )
    )
    entities: list[EntityOut] = Field(
        default_factory=list,
        description="Distinct named things in the whole text, first mention first.",
    )
    keywords: list[KeywordOut] = Field(
        default_factory=list,
        description="What the submission as a whole is about, strongest first.",
    )

    @classmethod
    def from_domain(cls, extraction: Extraction) -> Self:
        return cls(
            claims=[ExtractedClaimOut.from_domain(c) for c in extraction.claims],
            count=len(extraction.claims),
            checkable_count=len(extraction.checkable),
            sentences=extraction.sentences,
            entities=[EntityOut.from_domain(e) for e in extraction.entities],
            keywords=[KeywordOut.from_domain(k) for k in extraction.keywords],
        )
