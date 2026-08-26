"""Reading the model's reply, and refusing it when it strays outside the brief.

Everything in this module exists to make one rule enforceable rather than requested:
the model may report what the dossier contains and may not add to it. A prompt cannot
carry that rule, because a prompt is advice and this is a constraint — so the answer
is checked against :class:`~app.reasoning.brief.Brief`, which is the same closed table
the model was shown.

Four things are checked, each closing a different way to invent:

* **Citations.** ``evidence`` must be exhibit ids. The quote stored beside a verdict
  is then looked up from the dossier, so a stored quote is never a string the model
  produced — the worst it can do is cite the wrong passage, which is visible, rather
  than fabricate a plausible one, which is not.
* **Outlets.** Any URL or hostname in the prose must resolve to a domain in the brief.
  This is the check that stops "according to Reuters" appearing beside a dossier
  Reuters is not in.
* **Quotations.** Any quoted run of more than a few words must actually occur in a
  passage or in the claim. A model that paraphrases inside quotation marks has
  attributed words to a source that did not write them.
* **Figures.** Any number must occur in the brief, except a bare integer of 100 or
  less — see :data:`SMALL_INTEGER`. Statistics are the most consequential thing a
  language model invents and the hardest for a reader to check.

Failing any of them raises :class:`Ungrounded`, and :mod:`app.reasoning.layer` answers
that by publishing the deterministic finding instead. **Over-rejection is the safe
direction here and the design leans that way on purpose:** a false rejection costs an
explanation and keeps the arithmetic's verdict, while a false acceptance publishes a
fabrication under this service's name.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.graph.scoring import MAX_SCORE
from app.graph.verdict import Assessment
from app.reasoning.brief import Brief, Exhibit
from app.research.terms import fold, numbers, squeeze
from app.research.urls import host_of, registrable_domain

__all__ = [
    "FIELDS",
    "MIN_QUOTED_CHARS",
    "SMALL_INTEGER",
    "Reasoning",
    "Ungrounded",
    "read",
]

#: The four keys the answer must carry, in the order the prompt lists them.
FIELDS = ("verdict", "confidence", "reasoning", "evidence")

#: Shortest quoted run that is checked against the brief. Below this a quotation is
#: as likely to be a phrase from the claim as an attribution — "the rate", "held" —
#: and checking it would reject ordinary prose for no gain in safety.
MIN_QUOTED_CHARS = 24

#: Largest bare integer allowed without appearing in the brief.
#:
#: The exemption exists because the model legitimately counts the brief's own parts —
#: "three of the four sources", "both reviews" — and its confidence is a number in
#: this range too. Percentages and decimals are never exempt, whatever their value,
#: so ``5.25%`` is checked even though ``5`` would not be; those are the figures a
#: reader takes as fact and cannot verify without the source.
SMALL_INTEGER = 100

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_URL = re.compile(r"https?://[^\s\"'<>()\[\]]+", re.IGNORECASE)
#: Lowercase only, so a missing space after a full stop ("rate.The bank") is not read
#: as a hostname. Deliberately blunt otherwise — see the note on over-rejection.
_HOST = re.compile(r"\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,24}\b")
_QUOTED = re.compile(r"[\"“]([^\"“”]{4,400})[\"”]")
_TOKEN = re.compile(r"\[([A-Za-z]{1,2}\d{1,4})\]|\b([SERC]\d{1,4})\b")

#: Leading labels that make a hostname match an abbreviation instead. Small on
#: purpose: anything not here fails closed, which costs a fallback and not a reader.
_NOT_HOSTS = frozenset({"etc", "eg", "ie", "vs", "al", "no", "fig", "cf", "ibid"})


class Ungrounded(ValueError):
    """The model's answer named something the brief does not contain."""


@dataclass(frozen=True, slots=True)
class Reasoning:
    """One claim's final reading, whether the model's or the arithmetic's."""

    verdict: Assessment
    confidence: int
    reasoning: str
    evidence: tuple[Exhibit, ...] = ()
    model: str = ""
    #: False when the model's answer was refused and this is the deterministic
    #: finding restated. Never quietly true: every caller that publishes this can
    #: say which of the two a reader is looking at.
    grounded: bool = True
    #: Why the answer was refused. Empty exactly when :attr:`grounded`.
    rejected: str = ""
    #: Set when the model's verdict differed from the arithmetic's. Recorded rather
    #: than resolved — a disagreement is information about the dossier.
    disputed: str = ""

    def __post_init__(self) -> None:
        if self.grounded == bool(self.rejected):
            raise ValueError("a refusal must carry its reason and only a refusal may")

    @property
    def citations(self) -> tuple[str, ...]:
        return tuple(exhibit.id for exhibit in self.evidence)


def read(text: str, brief: Brief, *, model: str = "") -> Reasoning:
    """Parse and ground one reply, or raise :class:`Ungrounded`."""
    document = _document(text)
    missing = [name for name in FIELDS if name not in document]
    if missing:
        raise Ungrounded(f"the answer omits {', '.join(missing)}")

    verdict = _verdict(document["verdict"])
    return Reasoning(
        verdict=verdict,
        confidence=_confidence(document["confidence"]),
        reasoning=_prose(document["reasoning"], brief),
        evidence=_cited(document["evidence"], brief, verdict),
        model=model,
    )


# --------------------------------------------------------------- the fields ----


def _document(text: str) -> dict[str, Any]:
    """The JSON object in the reply.

    Lenient about wrapping — a code fence, a sentence before the object, an object
    inside an array — because that is a formatting habit rather than a claim about
    the world, and the fields inside are checked with no leniency at all.

    The scan is first-brace to last-brace, so anything it parses successfully is an
    object: a document that opens with ``{`` is either one or invalid JSON. A reply
    with no braces at all is where a wrong *shape* can still be named, and
    :func:`_no_object` is what names it.
    """
    body = _FENCE.sub("", text.strip()).strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise Ungrounded(_no_object(body))
    try:
        parsed: dict[str, Any] = json.loads(body[start : end + 1])
    except ValueError as error:
        raise Ungrounded(f"the answer is not valid JSON: {error}") from error
    return parsed


def _no_object(body: str) -> str:
    """Why there was no object to read: the wrong shape, or nothing parseable.

    A model that answered with a JSON array got the format wrong; a model whose
    reply was cut off at the token ceiling produced no JSON at all. Both are
    refused, and telling them apart is the difference between a prompt to fix and a
    ``max_tokens`` to raise.
    """
    try:
        parsed: Any = json.loads(body)
    except ValueError:
        return "the answer contains no JSON object"
    return f"the answer is a {type(parsed).__name__}, not an object"


def _verdict(value: Any) -> Assessment:
    if not isinstance(value, str):
        raise Ungrounded(f"verdict is a {type(value).__name__}, not one of the five")
    wanted = squeeze(value).upper().replace(" ", "_").replace("-", "_")
    try:
        return Assessment(wanted)
    except ValueError as error:
        raise Ungrounded(f"{value!r} is not one of the five verdicts") from error


def _confidence(value: Any) -> int:
    """A confidence in 0-100, capped at the same ceiling the score engine uses.

    A float strictly between 0 and 1 is read as a proportion and scaled. Models
    answer this field both ways whatever the prompt says, and ``0.8`` treated
    literally would publish near-total uncertainty as the model's considered view —
    a misreading in the direction of confidence, which is the one that misleads.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise Ungrounded(f"confidence is a {type(value).__name__}, not a number")
    scaled = float(value) * 100 if 0 < float(value) < 1 else float(value)
    if not 0 <= scaled <= 100:
        raise Ungrounded(f"confidence {value!r} is outside 0-100")
    return min(round(scaled), MAX_SCORE)


def _cited(value: Any, brief: Brief, verdict: Assessment) -> tuple[Exhibit, ...]:
    """The cited exhibits, looked up rather than taken from the reply.

    The lookup is the point. Everything published beside a verdict — the quote, the
    url, the domain, the date — comes from the dossier, and the model's contribution
    is which row of the table to read. There is no path by which a string it wrote
    becomes a quotation attributed to a source.
    """
    if not isinstance(value, list):
        raise Ungrounded(f"evidence is a {type(value).__name__}, not a list")

    found: list[Exhibit] = []
    for entry in value:
        if not isinstance(entry, str):
            raise Ungrounded(f"evidence holds a {type(entry).__name__}, not an id")
        exhibit = brief.exhibit(squeeze(entry).upper().strip("[]"))
        if exhibit is None:
            raise Ungrounded(f"evidence cites {entry!r}, which is not in the brief")
        if exhibit not in found:
            found.append(exhibit)

    # A ruling with no citation is an assertion. Allowed only where the brief held no
    # passage to cite — a claim decided on published reviews alone reaches here.
    if not found and brief.exhibits and verdict is not Assessment.UNCERTAIN:
        raise Ungrounded(f"{verdict.value} was returned without citing any evidence")
    return tuple(found)


# -------------------------------------------------------------- the grounds ----


def _prose(value: Any, brief: Brief) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Ungrounded("reasoning is empty")
    prose = squeeze(value)
    _tokens(prose, brief)
    _outlets(prose, brief)
    _quotations(prose, brief)
    _figures(prose, brief)
    return prose


def _tokens(prose: str, brief: Brief) -> None:
    """Every ``[E1]``-shaped reference must be one the brief issued."""
    for match in _TOKEN.finditer(prose):
        cited = (match.group(1) or match.group(2)).upper()
        if cited not in brief.ids:
            raise Ungrounded(f"the reasoning refers to {cited}, which is not shown")


def _outlets(prose: str, brief: Brief) -> None:
    """No outlet, site or link that the brief did not carry."""
    for match in _URL.finditer(prose):
        host = host_of(match.group())
        domain = registrable_domain(host) if host else ""
        if domain and domain not in brief.domains:
            raise Ungrounded(f"the reasoning links to {domain}, which is not a source")

    for match in _HOST.finditer(prose):
        candidate = match.group()
        if candidate.split(".", 1)[0] in _NOT_HOSTS:
            continue
        domain = registrable_domain(candidate)
        if domain and domain not in brief.domains:
            raise Ungrounded(f"the reasoning names {domain}, which is not a source")


def _quotations(prose: str, brief: Brief) -> None:
    """No quotation marks around words the brief does not contain.

    Folded and whitespace-collapsed on both sides, because a model reproducing a
    passage may normalise a curly apostrophe or a line break, and neither changes
    what was said. Anything beyond that is a paraphrase inside quotation marks.
    """
    for match in _QUOTED.finditer(prose):
        quoted = fold(squeeze(match.group(1)))
        if len(quoted) < MIN_QUOTED_CHARS:
            continue
        if not any(quoted in passage for passage in brief.passages):
            raise Ungrounded("the reasoning quotes words that are in no passage")


def _figures(prose: str, brief: Brief) -> None:
    for figure in numbers(prose):
        if figure in brief.figures:
            continue
        if figure.isdigit() and int(figure) <= SMALL_INTEGER:
            continue
        raise Ungrounded(f"the reasoning states {figure}, which is in no passage")
