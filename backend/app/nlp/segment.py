"""Finding the sentence boundaries, as character offsets.

Offsets rather than strings, and that is the whole reason this module exists.
``nltk.sent_tokenize`` returns a list of strings, and a caller that wants to know
*where* a sentence was has to search for it — which finds the wrong occurrence the
moment a sentence repeats, and silently mis-locates every subsequent claim when the
tokeniser normalises a character. Working in offsets means
``source[start:end]`` is the sentence by construction, and every entity, quote and
claim in the response can be expressed in that one coordinate system.

Line breaks are treated as hard boundaries before either tokeniser sees the text.
Real submissions are not a single paragraph: they are a headline, a byline, a
standfirst and then body copy, and both tokenisers, given the lot in one string,
will happily run a headline into the first sentence of the body — "Bridge Opens
Early The bridge opened in March" — which then parses as nonsense and is either
rejected or, worse, accepted as a claim nobody wrote. Splitting on newlines first
makes the headline its own sentence, where the screen can reject it as a fragment
and say so.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.nlp.resources import Resources


def sentence_spans(
    text: str, resources: Resources, *, limit: int
) -> list[tuple[int, int]]:
    """Return ``(start, end)`` for each sentence in ``text``, in order.

    ``end`` is exclusive and neither end includes whitespace, so
    ``text[start:end].strip() == text[start:end]`` for every span returned.

    ``limit`` caps how many are returned. A 100,000-character submission can hold
    several thousand sentences, and the cost of the pipeline is linear in them while
    the value of the two-thousandth claim in one response is nil — so the cap is a
    guard on work, and the caller reports it rather than pretending the tail was
    empty.
    """
    spans: list[tuple[int, int]] = []
    for block_start, block_end in _blocks(text):
        block = text[block_start:block_end]
        for start, end in _split_block(block, resources):
            start, end = _trim(text, block_start + start, block_start + end)
            if start < end:
                spans.append((start, end))
                if len(spans) >= limit:
                    return spans
    return spans


def _split_block(block: str, resources: Resources) -> Iterator[tuple[int, int]]:
    """Sentence spans within one line of text, relative to that line."""
    segmenter = resources.segmenter
    if segmenter is not None:
        yield from segmenter.span_tokenize(block)
        return
    # No punkt data. The loaded model's own boundaries are the next best thing, and
    # this costs a second parse of the text — the pipeline parses each sentence again
    # afterwards. Accepted because it only happens in a degraded path that has
    # already logged why, and because the alternative is a third code path.
    doc = resources.nlp(block)
    for sent in doc.sents:
        yield sent.start_char, sent.end_char


def _blocks(text: str) -> Iterator[tuple[int, int]]:
    """Yield the span of every non-blank line, whitespace already trimmed.

    The running offset is exact rather than approximate: ``split("\\n")`` drops one
    character per break, so adding ``len(line) + 1`` each time tracks the original
    string precisely. Deriving offsets any other way — searching for the line,
    counting from a regex — is where this kind of code usually goes wrong.
    """
    offset = 0
    for line in text.split("\n"):
        start = offset
        offset += len(line) + 1
        stripped = line.strip()
        if not stripped:
            continue
        lead = len(line) - len(line.lstrip())
        yield start + lead, start + lead + len(stripped)


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    """Shrink ``[start, end)`` past any whitespace at either end."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end
