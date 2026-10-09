"""Pointing a ruling back at the words it came from.

Every media desk has the same problem. The pipeline rules on a *normalised* sentence
— squeezed, folded, punctuation-tidied — while the reader displays the raw text a
recogniser produced, and :attr:`app.domain.Annotation.quote` has to be a literal
substring of what is displayed or the frontend's ``indexOf`` misses and the marker
silently never appears.

So the match runs the other way: each fragment of recovered text is normalised and
tested for containment in the ruled claim. A fragment is ``(text, group)``, where
the group is whatever the source considers a contiguous unit — an OCR block, a
speaker turn — and only fragments adjacent within one group are ever joined,
because joining across a boundary produces a quote that appears nowhere.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.domain import Annotation
from app.graph.verdict import ClaimRuling, as_determination
from app.reasoning.answer import Reasoning
from app.research.terms import fold, squeeze

#: Below this a normalised fragment is noise — "the", a page number, an artefact —
#: and is short enough to appear inside an unrelated claim by chance.
MIN_KEY = 4


def key(text: str) -> str:
    """``fold`` already case-folds, so this is whitespace plus accents."""
    return fold(squeeze(text))


def attach(
    fragments: Sequence[tuple[str, int]],
    rulings: Sequence[ClaimRuling],
    *,
    readings: Mapping[int, Reasoning] | None = None,
) -> tuple[dict[int, int], tuple[Annotation, ...]]:
    """Map fragments to refs, and quote each ref's longest contiguous run.

    Returns ``(anchors, annotations)``: ``anchors`` gives a ref for each fragment
    index that matched, for highlighting; ``annotations`` holds one quote per ref.

    ``readings`` supplies the language model's prose for each ref, keyed the way
    :func:`app.desks.graph.readings` returns it. It changes the note only; the
    determination on an annotation always comes from the ruling.
    """
    normalised = [(ruling, key(ruling.claim)) for ruling in rulings]
    anchors: dict[int, int] = {}
    matched: dict[int, list[int]] = {}

    for index, (text, _) in enumerate(fragments):
        folded = key(text)
        if len(folded) < MIN_KEY:
            continue
        for ruling, claim in normalised:
            if folded in claim:
                anchors[index] = ruling.ref
                matched.setdefault(ruling.ref, []).append(index)
                break

    by_ref = {ruling.ref: ruling for ruling in rulings}
    annotations = []
    for ref, indices in sorted(matched.items()):
        run = _longest_run(indices, fragments)
        ruling = by_ref[ref]
        annotations.append(
            Annotation(
                ref=ref,
                quote=" ".join(fragments[i][0] for i in run),
                note=note(ruling, (readings or {}).get(ref)),
                determination=as_determination(ruling.judgement),
            )
        )
    return anchors, tuple(annotations)


def note(ruling: ClaimRuling, reading: Reasoning | None = None) -> str:
    """The sentence shown beside a marked quote.

    The model's prose when there is grounded prose to show, and the arithmetic's own
    account otherwise. A disagreement is appended rather than resolved: the
    determination beside this note comes from the ruling either way, so a note that
    reads against it would otherwise look like an error in the record.
    """
    if reading is not None and reading.grounded and reading.reasoning:
        if reading.disputed:
            return f"{reading.reasoning} Note: {reading.disputed}."
        return reading.reasoning
    if ruling.insufficiency:
        return ruling.insufficiency
    return f"{ruling.judgement} at {round(ruling.confidence * 100)}% confidence."


def _longest_run(indices: list[int], fragments: Sequence[tuple[str, int]]) -> list[int]:
    runs: list[list[int]] = []
    for index in indices:
        if (
            runs
            and index == runs[-1][-1] + 1
            and fragments[index][1] == fragments[runs[-1][-1]][1]
        ):
            runs[-1].append(index)
        else:
            runs.append([index])
    return max(runs, key=lambda run: sum(len(fragments[i][0]) for i in run))
