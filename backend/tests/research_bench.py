"""Builders and a small corpus for the :mod:`app.research` tests.

Not in :mod:`tests.stubs`, and the reason is the property these tests exist to
protect. ``tests/stubs.py`` imports :mod:`app.nlp`, which imports ``anyio`` at module
scope; everything under ``app/research`` runs on the request path in deployments where
the NLP extras are not installed, and a test module that could only be *collected* on
a machine with spaCy present would be unable to prove that. So the research tests
import this instead, and it depends on nothing but the standard library and
:mod:`app.domain`.

The snippets here are long, and that is deliberate. Similarity thresholds behave
completely differently on a 40-character fragment than on the 200–500 characters a
real provider returns — containment is trivially 1.0 for anything short enough to be a
subset of something else — so a corpus of toy strings would measure a pipeline nobody
runs. Every snippet below is within the length band :mod:`app.search` actually sees.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from app.domain.claims import Entity, ExtractedClaim, Keyword
from app.domain.research import DateBasis, Evidence, Retrieval, Source
from app.research.urls import registrable_domain

#: A fixed instant, so a URL-path date resolves the same way on every run.
NOW = datetime(2026, 3, 14, 9, 30, tzinfo=UTC)


def claim(
    text: str,
    *,
    ref: int = 1,
    entities: tuple[tuple[str, str], ...] = (),
    keywords: tuple[tuple[str, float], ...] = (),
    checkable: bool = True,
    reason: str = "",
) -> ExtractedClaim:
    """An :class:`~app.domain.claims.ExtractedClaim` whose offsets are real.

    ``entities`` is ``(text, label)`` pairs and the offsets are located in ``text`` by
    :meth:`str.find`, so ``claim.text[entity.start : entity.end] == entity.text``
    holds the way it does for a genuine extraction. Building entities with offsets of
    zero would let a test pass against code that had quietly stopped honouring them.
    """
    located: list[Entity] = []
    for label_text, label in entities:
        start = text.find(label_text)
        if start < 0:  # pragma: no cover - a mistake in the test, not the code
            raise AssertionError(f"{label_text!r} is not in {text!r}")
        located.append(
            Entity(
                text=label_text, label=label, start=start, end=start + len(label_text)
            )
        )
    return ExtractedClaim(
        ref=ref,
        text=text,
        quote=text,
        start=0,
        end=len(text),
        checkable=checkable,
        reason=reason,
        entities=tuple(located),
        keywords=tuple(Keyword(term=term, score=score) for term, score in keywords),
    )


def retrieval(
    provider: str,
    url: str,
    *,
    title: str = "",
    snippet: str = "",
    rank: int = 1,
    query: str = "boe rate decision",
    score: float | None = None,
    published_at: datetime | None = None,
    date_basis: DateBasis | None = None,
    date_text: str | None = None,
) -> Retrieval:
    """One provider's report of one URL, with the defaults a test rarely cares about."""
    return Retrieval(
        provider=provider,
        query=query,
        rank=rank,
        url=url,
        title=title,
        snippet=snippet,
        score=score,
        published_at=published_at,
        date_basis=date_basis,
        date_text=date_text,
    )


def source(
    url: str,
    *,
    title: str = "",
    snippet: str = "",
    ref: int = 1,
    provider: str = "tavily",
    rank: int = 1,
    retrievals: tuple[Retrieval, ...] = (),
    published_at: datetime | None = None,
    date_basis: DateBasis | None = None,
    date_text: str | None = None,
    evidence: tuple[Evidence, ...] = (),
    cluster: int | None = None,
) -> Source:
    """A :class:`~app.domain.research.Source` for testing clustering directly.

    ``domain`` and ``host`` are read off ``url`` rather than passed, because a source
    whose domain disagrees with its URL is not a state the pipeline can produce and a
    test built on one would be checking something that cannot happen.

    ``evidence`` and ``cluster`` default to empty and ``None``, which is what the
    clustering tests want — clustering never reads the first and assigns the second, so
    a source carrying either would make those tests look like they exercised more than
    they do. Both are settable because
    :mod:`app.research.credibility` reads them: it is graded on whether a passage bore
    on the claim, and on whether another source in the dossier is the same story.
    """
    host = url.split("/")[2].casefold()
    return Source(
        ref=ref,
        url=url,
        urls=(url,),
        title=title,
        domain=registrable_domain(host),
        host=host,
        evidence=evidence,
        retrievals=retrievals
        or (
            retrieval(provider, url, title=title, snippet=snippet, rank=rank),
        ),
        published_at=published_at,
        date_basis=date_basis,
        date_text=date_text,
        cluster=cluster,
    )


# ---------------------------------------------------------------- the corpus ----

#: A wire story's body, as a provider would return it: one paragraph, ~330 characters.
WIRE = (
    "The Bank of England held its benchmark rate at 4.75% on Thursday, citing "
    "services inflation that has proved more persistent than the committee "
    "expected. Four of the nine members of the Monetary Policy Committee voted "
    "for a quarter-point cut, the closest the vote has been since August. "
    "Governor Andrew Bailey said the path was still downward."
)

#: The same body cut shorter, which is what a second engine returns for the same page.
#:
#: A strict prefix, so its shingle set is a *subset* of :data:`WIRE`'s — containment
#: 1.000, Jaccard far lower. That asymmetry is the whole reason
#: :func:`app.research.dedupe.containment` is not Jaccard, and this is the string that
#: demonstrates it.
WIRE_TRUNCATED = WIRE[:238]

#: The same body again, behind a regional masthead that added its own lead-in.
WIRE_WITH_LEAD = (
    "LONDON — Rates are on hold for a third meeting running. " + WIRE
)

#: The wire copy lightly rewritten, the way a subeditor trims to fit a column.
#:
#: Measured at containment 0.788 against :data:`WIRE` — inside the title-rescue band
#: (:data:`~app.research.dedupe.TITLE_RESCUE_FLOOR` to
#: :data:`~app.research.dedupe.TITLE_RESCUE_CEILING`) and below the threshold that
#: would merge it on the snippet alone. So whether this is one story with
#: :data:`WIRE` depends entirely on the headlines, which is what the rescue is for.
WIRE_REPHRASED = (
    WIRE.replace("citing services", "amid services")
    .replace(
        "has proved more persistent than the committee expected",
        "is proving more persistent than the committee expected",
    )
    .replace(
        "the closest the vote has been since August",
        "the narrowest split since August",
    )
)

#: The headline the wire ran under, and the two other mastheads' versions of it.
#:
#: ``REWRITTEN`` shares no trigram with ``WIRE_TITLE`` — measured title containment
#: 0.000 over identical body copy, which is the commonest syndication pattern there
#: is and the one a weighted title-plus-snippet score would always split.
WIRE_TITLE = "Bank of England holds rate at 4.75% as services inflation persists"
WIRE_TITLE_REWRITTEN = "BoE keeps borrowing costs on hold"
WIRE_TITLE_REGIONAL = "Rates unchanged again as committee splits four ways"

#: A publisher's newsletter block, repeated on every article it serves.
#:
#: The reason :data:`~app.research.dedupe.MIN_ANCHORS` exists. Two unrelated stories
#: carrying this measure well above :data:`~app.research.dedupe.CONTAINMENT_THRESHOLD`
#: on snippet overlap alone, at any shingle width, so no threshold can separate a
#: publisher's boilerplate from syndication — only the anchors can.
#:
#: Deliberately free of proper nouns and figures, which is what real newsletter copy
#: is like and what leaves the anchors to come from the story instead.
BOILERPLATE = (
    "Sign up for our free morning newsletter and get the day's biggest stories "
    "delivered straight to your inbox before breakfast every weekday. Our "
    "reporters pick the best long reads from the archive at the weekend, and you "
    "can unsubscribe at any time from the link at the foot of every email we send."
)

#: Two unrelated stories from one site, each behind :data:`BOILERPLATE`.
#:
#: Short leads, because that is what makes the pair dangerous: the shared block is
#: most of both snippets, so the overlap they measure is a fact about the publisher's
#: page furniture and not about either story.
LOCAL_PLANNING = "Councillors approved 40 homes in Ashburton. " + BOILERPLATE
LOCAL_FERRY = "High winds cancelled sailings from Portsmouth. " + BOILERPLATE

#: The two local headlines, which share no anchor either.
LOCAL_PLANNING_TITLE = "Ashburton homes plan approved by councillors"
LOCAL_FERRY_TITLE = "Solent ferry sailings cancelled in high winds"


def syndication() -> list[Source]:
    """One wire report under three mastheads, plus two unrelated local stories.

    Both directions in one list: three sources that must be recognised as one story,
    and two that must not, where the pair that must not scores *higher* on raw snippet
    overlap than the pair that must.

    Defined here rather than in the test module because the hash-seed subprocess needs
    it too, and it must be able to build the corpus without importing ``pytest``.
    """
    return [
        source("https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE, ref=1),
        source(
            "https://apnews.com/b",
            title=WIRE_TITLE_REWRITTEN,
            snippet=WIRE_TRUNCATED,
            ref=2,
        ),
        source(
            "https://heraldscotland.com/c",
            title=WIRE_TITLE_REGIONAL,
            snippet=WIRE_WITH_LEAD,
            ref=3,
        ),
        source(
            "https://devonlive.com/d",
            title=LOCAL_PLANNING_TITLE,
            snippet=LOCAL_PLANNING,
            ref=4,
        ),
        source(
            "https://devonlive.com/e",
            title=LOCAL_FERRY_TITLE,
            snippet=LOCAL_FERRY,
            ref=5,
        ),
    ]


def partition(sources: Sequence[Source]) -> set[frozenset[str]]:
    """The clustering as a set of sets of URLs, independent of ids and of order.

    What "the same clustering" means when comparing two runs: the numbering is an
    artefact of ordering, so comparing ids would flag a relabelling as a difference.
    """
    groups: dict[int | None, set[str]] = {}
    for index, item in enumerate(sources):
        key = item.cluster if item.cluster is not None else -index - 1
        groups.setdefault(key, set()).add(item.url)
    return {frozenset(urls) for urls in groups.values()}
