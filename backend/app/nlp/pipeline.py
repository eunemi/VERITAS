"""The spaCy claim extractor: everything above joined up.

The order of operations, and why each step is where it is:

1. **NLTK punkt** finds the sentence boundaries, as character offsets. Before the
   parser, because the parser needs to be handed one sentence at a time and because
   punkt is better at this particular job — see :mod:`app.nlp.segment`.
2. **spaCy** parses each sentence: tags, dependencies, lemmas, named entities.
3. **The splitter** cuts each parsed sentence into separately checkable clauses.
4. **The screen** decides which of those a fact-check desk could act on.
5. **scikit-learn's TF-IDF** ranks the terms of every sentence against the others.

Steps 1 and 2 both run the model, so both happen inside one hold of the parse lock:
:func:`app.nlp.resources.parse_lock` is a plain :class:`threading.Lock` and taking it
twice in one call would deadlock. The whole of that hold is off the event loop —
parsing a long article takes hundreds of milliseconds of pure CPU, and doing it
inline would stall every other request in the process for the duration.

Offsets are absolute throughout. spaCy reports character positions relative to the
``Doc`` it parsed, which here is one sentence, so every one of them is shifted by
that sentence's own start before it leaves this module. Nothing above this file ever
sees a sentence-relative number, and ``source[claim.start:claim.end] ==
claim.quote`` holds for every claim returned.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anyio.to_thread

from app.core.config import Settings
from app.domain import Entity, ExtractedClaim, Extraction, Keyword
from app.nlp.keywords import Lemma, keywords
from app.nlp.resources import Resources, load, parse_lock
from app.nlp.screen import screen
from app.nlp.segment import sentence_spans
from app.nlp.split import Clause, clauses

if TYPE_CHECKING:  # pragma: no cover - spaCy is imported only inside the parse
    from spacy.tokens import Doc


class SpacyClaimExtractor:
    """Reads prose with spaCy, NLTK and scikit-learn.

    Holds no parse state: the loaded model lives in :mod:`app.nlp.resources`, keyed
    by name and shared by every instance, so constructing one of these is free and
    the registry can hand out a new one per request without reloading anything.
    """

    def __init__(self, settings: Settings) -> None:
        self._model = settings.SPACY_MODEL
        self._min_tokens = settings.CLAIM_MIN_TOKENS
        self._max_keywords = settings.CLAIM_MAX_KEYWORDS
        self._max_sentences = settings.CLAIM_MAX_SENTENCES

    async def extract(self, text: str) -> Extraction:
        """Read ``text`` in a worker thread and return what was found."""
        if not text.strip():
            return Extraction(claims=(), entities=(), keywords=(), sentences=0)
        return await anyio.to_thread.run_sync(self._extract, text)

    # -- everything below runs in a worker thread, never on the event loop --

    def _extract(self, text: str) -> Extraction:
        resources = load(self._model)
        spans, docs = self._parse(text, resources)
        if not docs:
            return Extraction(claims=(), entities=(), keywords=(), sentences=0)

        # One entry per parsed sentence, in step with `docs`, so a clause can find
        # the keyword ranking of the sentence it came from by index.
        lemmas = [_lemmas(doc) for doc in docs]
        per_sentence, overall = keywords(
            lemmas, resources.stopwords, limit=self._max_keywords
        )

        found: list[tuple[Clause, tuple[Entity, ...], tuple[Keyword, ...]]] = []
        for index, (doc, (offset, _)) in enumerate(zip(docs, spans, strict=True)):
            sentence_keywords = per_sentence[index] if index < len(per_sentence) else ()
            for sentence in doc.sents:
                for clause in clauses(sentence, offset):
                    found.append(
                        (
                            clause,
                            _entities_within(doc, offset, clause),
                            _keywords_within(
                                clause, sentence_keywords, limit=self._max_keywords
                            ),
                        )
                    )

        # Sorted by position, then numbered, so `ref` counts up the page regardless
        # of the order the splitter produced its pieces in.
        found.sort(key=lambda item: (item[0].start, item[0].end))
        claims: list[ExtractedClaim] = []
        for ref, (clause, entities, terms) in enumerate(found, start=1):
            checkable, reason = screen(clause, min_tokens=self._min_tokens)
            claims.append(
                ExtractedClaim(
                    ref=ref,
                    text=clause.text,
                    quote=text[clause.start : clause.end],
                    start=clause.start,
                    end=clause.end,
                    checkable=checkable,
                    reason=reason,
                    entities=entities,
                    keywords=terms,
                )
            )
        return Extraction(
            claims=tuple(claims),
            entities=_document_entities(docs, spans),
            keywords=overall,
            sentences=len(spans),
        )

    def _parse(
        self, text: str, resources: Resources
    ) -> tuple[list[tuple[int, int]], list[Doc]]:
        """Segment and parse, both under one hold of the parse lock.

        One hold rather than two because the lock is not reentrant and the
        no-punkt path in :mod:`app.nlp.segment` runs the model itself. Also because
        releasing it between the two would let a second request interleave its parse
        with this one's, which is precisely what the lock exists to prevent.
        """
        with parse_lock():
            spans = sentence_spans(text, resources, limit=self._max_sentences)
            if not spans:
                return [], []
            docs = list(resources.nlp.pipe([text[start:end] for start, end in spans]))
        return spans, docs


# ------------------------------------------------------------------ helpers ----


def _lemmas(doc: Doc) -> list[Lemma]:
    """The lemma and coarse part of speech of every content token in a sentence.

    Punctuation, whitespace and pure symbols are dropped here rather than left for
    the vectoriser's token pattern to remove, so that what TF-IDF sees is the same
    list the frequency fallback sees. Two rankings computed over different token sets
    would make the fallback incomparable with the thing it falls back from.
    """
    return [
        (token.lemma_.lower(), token.pos_)
        for token in doc
        if not (token.is_punct or token.is_space or token.pos_ in {"SYM", "X"})
    ]


def _entities_within(doc: Doc, offset: int, clause: Clause) -> tuple[Entity, ...]:
    """The named entities lying inside ``clause``'s source span.

    Filtered by character span rather than by token membership. A clause's tokens can
    include a subject carried in from elsewhere in the sentence, and an entity in
    that subject belongs to the clause it was borrowed *from* — attaching it here as
    well would report the same mention twice at the same offsets under two different
    claims.
    """
    return tuple(
        Entity(
            text=ent.text,
            label=ent.label_,
            start=offset + ent.start_char,
            end=offset + ent.end_char,
        )
        for ent in doc.ents
        if offset + ent.start_char >= clause.start and offset + ent.end_char <= clause.end
    )


def _keywords_within(
    clause: Clause, sentence_keywords: tuple[Keyword, ...], *, limit: int
) -> tuple[Keyword, ...]:
    """The sentence's keywords that this clause actually contains, strongest first.

    A term survives when every word in it is a lemma of this clause. Bigrams are
    checked word by word rather than as a substring because scikit-learn builds them
    from the stop-word-filtered token stream, so "minister canada" is a legitimate
    term for "the prime minister of Canada" and would fail a substring test.

    The cap is applied here, after the filter, which is why ``keywords`` hands over an
    uncapped ranking. Capping the sentence first would let one clause's terms consume
    the other's budget: in "The bridge opened in March and cost £4bn" every term ties,
    so the cap would fall alphabetically and could leave the second clause without
    "£4bn" in order to keep "march".

    Scores are left as they were. They were computed against the sentence, and
    rescaling them per clause would make two claims from one sentence look like they
    had been ranked against different corpora.
    """
    present = {token.lemma_.lower() for token in clause.tokens}
    return tuple(
        keyword
        for keyword in sentence_keywords
        if all(word in present for word in keyword.term.split())
    )[:limit]


def _document_entities(
    docs: list[Doc], spans: list[tuple[int, int]]
) -> tuple[Entity, ...]:
    """Every distinct named thing in the submission, in order of first appearance.

    Distinct on the pair of text and label, so "March" the DATE and "March" a
    surname are two entities while three mentions of "Network Rail" are one. The
    offsets kept are the first mention's — a caller that needs them all reads the
    per-claim lists, which are not deduplicated for exactly that reason.
    """
    seen: set[tuple[str, str]] = set()
    unique: list[Entity] = []
    for doc, (offset, _) in zip(docs, spans, strict=True):
        for ent in doc.ents:
            key = (ent.text.casefold(), ent.label_)
            if key in seen:
                continue
            seen.add(key)
            unique.append(
                Entity(
                    text=ent.text,
                    label=ent.label_,
                    start=offset + ent.start_char,
                    end=offset + ent.end_char,
                )
            )
    return tuple(unique)


def build(settings: Settings) -> Any:
    """Registry factory. Separate from the class so the registry stores a callable."""
    return SpacyClaimExtractor(settings)
