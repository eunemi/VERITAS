"""The fact-check desk: the three things the graph deliberately does not do.

Everything between the claim and the verdict happens inside the graph, and is tested in
``test_graph_*``. What is left to this desk is retrieval, exhibits and persistence, so
those are what this file is about — driven through a fake graph handed a prepared
outcome. No graph is compiled here and LangGraph is never imported, which is the
property ``test_graph_imports`` protects and the reason :class:`Ruled` below stands in
for :class:`app.graph.workflow.Outcome`.

The rules worth breaking a build over:

* **nothing retrieved can enter a finding.** Retrieval runs after the ruling is made
  and decides only which passage a reader is shown and in what order. A query that
  fails, or a store that cannot be opened, must cost ordering and nothing else;
* **no determination beside a source is re-derived here.** Each comes from the judge's
  own indications, matched by ref. A source the arithmetic never weighed reads
  CONSISTENT or REQUIRES_VERIFICATION and never SUPPORTED, which would report a page as
  confirming a claim on the strength of appearing in the same search results;
* **``Reliability.VERIFIED`` is unreachable.** It means a primary record was reached,
  and every source here is a search result. This is the structural form of "do not
  treat any domain as automatically true";
* **a passage is never invented to fill a column,** and a storage failure never loses
  the examination.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from app.core.config import Environment, Settings, StoreBackend, VectorStoreProvider
from app.core.errors import ConfigurationError
from app.desks import examiners
from app.desks.base import ArtifactDesk
from app.desks.factcheck import TITLE_LIMIT, UNDATED, FactCheckDesk, build
from app.domain import (
    Artifact,
    ArtifactKind,
    Band,
    DateBasis,
    Desk,
    Determination,
    Dossier,
    Relevance,
    Reliability,
    Source,
    can_examine,
)
from app.graph import scoring
from app.graph.agents.judge import JudgeAgent
from app.graph.state import GraphState, cases, dossier
from app.graph.verdict import (
    Assessment,
    Bearing,
    ClaimRuling,
    Indication,
    Judgement,
    Ruling,
)
from app.reasoning.answer import Reasoning
from app.repositories.base import ResearchRepository
from app.vectorstore.evidence import Relevant
from tests.graph_bench import CLAIM, MATCHING, RIVAL, passage, rated, reported, state
from tests.research_bench import source as built

TEXT = Artifact(kind=ArtifactKind.TEXT, content=CLAIM)

#: Two independent sources, each repeating the claim's figure — the smallest dossier
#: the judge will rule on, since :attr:`app.graph.verdict.Thresholds.min_sources` is
#: two. Recognisable mastheads because the standing floor is real: an invented domain
#: grades UNKNOWN and never clears it, which is a different test.
PAIR = (
    reported("https://reuters.com/a", ref=1),
    reported("https://theguardian.com/b", ref=2),
)

#: One source, which cannot clear the same gate. The declined path.
SOLO = (reported("https://reuters.com/a"),)


def configured(**overrides: Any) -> Settings:
    """Test settings. ``_env_file=None`` keeps a developer's ``.env`` out of it.

    Retrieval is off unless a test asks for it. It is the one step in this desk that
    reaches outside the process, and leaving it on would have every test here build a
    vector store whose availability decided the ledger.
    """
    return Settings(
        _env_file=None,
        **{
            "ENVIRONMENT": Environment.LOCAL,
            "VERIFICATION_STORE": StoreBackend.MEMORY,
            "VECTOR_STORE_PROVIDER": VectorStoreProvider.MEMORY,
            "EVIDENCE_INDEX_ENABLED": False,
            **overrides,
        },
    )


def indexing(**overrides: Any) -> Settings:
    return configured(EVIDENCE_INDEX_ENABLED=True, **overrides)


# ------------------------------------------------------------------- doubles ----


class Ruled:
    """What the desk reads off an outcome, without the graph that produces one."""

    __slots__ = ("reasoning", "ruling", "state", "trace")

    def __init__(
        self,
        held: GraphState,
        ruling: Ruling,
        reasoning: tuple[Reasoning, ...] = (),
    ) -> None:
        self.state = held
        self.ruling = ruling
        self.reasoning = reasoning
        self.trace = held.get("trace", ())


class FakeGraph:
    """Answers with a prepared outcome and records what it was asked to examine."""

    def __init__(self, outcome: Ruled) -> None:
        self._outcome = outcome
        self.seen: list[Artifact] = []

    async def run(self, artifact: Artifact) -> Ruled:
        self.seen.append(artifact)
        return self._outcome


class FakeIndex:
    """Indexes nothing and answers from a script.

    Not a real :class:`app.services.evidence.EvidenceIndex` over a memory store: what
    these tests vary is *what retrieval returned*, including nothing and an exception,
    and a real embedder would make that a property of the vectors rather than of the
    test.
    """

    def __init__(
        self,
        *,
        relevant: tuple[Relevant, ...] = (),
        indexed: int = 0,
        raises: Exception | None = None,
    ) -> None:
        self._relevant = relevant
        self._indexed = indexed
        self._raises = raises
        self.indexed_claims: list[str] = []
        self.queried: list[str] = []
        self.closed = False

    async def index(self, research: Any) -> int:
        if self._raises is not None:
            raise self._raises
        self.indexed_claims.append(research.claim)
        return self._indexed

    async def relevant(
        self, claim: str, *, top_k: int | None = None
    ) -> tuple[Relevant, ...]:
        if self._raises is not None:
            raise self._raises
        self.queried.append(claim)
        return self._relevant

    async def aclose(self) -> None:
        self.closed = True


class Store(ResearchRepository):
    """Records what it was handed, or fails on demand.

    Subclasses the protocol rather than duck-typing it, so a method added to
    ``ResearchRepository`` breaks here at construction instead of at the one call site
    that happens to use it.
    """

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.saved: list[tuple[Dossier, str | None]] = []

    async def save_dossier(
        self, dossier: Dossier, *, verification_id: str | None = None
    ) -> tuple[str, ...]:
        if self._raises is not None:
            raise self._raises
        self.saved.append((dossier, verification_id))
        return ("claim-1",)

    async def get_research(self, claim_id: str) -> None:
        return None

    async def research_for(self, verification_id: str) -> tuple[()]:
        return ()


# ------------------------------------------------------------------ builders ----


async def judged(held: GraphState) -> Ruled:
    """An outcome whose ruling is the real judge's, over really graded sources."""
    write = await JudgeAgent()(held)
    ruling = write["ruling"]
    assert ruling is not None
    return Ruled({**held, **write}, ruling)


def declined(
    held: GraphState,
    *,
    why: str = "nothing gathered settles this claim",
    indications: tuple[Indication, ...] = (),
    judgement: Judgement = Judgement.UNCERTAIN,
) -> Ruled:
    """An outcome the judge could not settle, built by hand so the reason is exact.

    The score comes from :func:`app.graph.scoring.declined` rather than a literal,
    because that function owns the invariant tying UNCERTAIN to a stated reason.
    """
    claim = held["claims"][0]
    result = scoring.declined(why, searched=True)
    unsettled = judgement is Judgement.UNCERTAIN
    return Ruled(
        held,
        Ruling(
            judgement=judgement,
            confidence=result.value / 100,
            headline="Not established",
            rationale="Nothing gathered settles this.",
            claims=(
                ClaimRuling(
                    ref=claim.ref,
                    claim=claim.text,
                    judgement=judgement,
                    confidence=result.value / 100,
                    indications=indications,
                    insufficiency=why if unsettled else "",
                    score=result if unsettled else None,
                ),
            ),
        ),
    )


def near(quote: str, *, ref: int, similarity: float, **extra: Any) -> Relevant:
    """One retrieved passage, as the vector store would return it."""
    return Relevant(
        quote=quote,
        similarity=similarity,
        claim=CLAIM,
        ref=ref,
        url=f"https://example{ref}.test/story",
        domain=f"example{ref}.test",
        title="",
        provider="tavily",
        lexical=0.8,
        refs=extra.pop("refs", (ref,)),
        domains=extra.pop("domains", (f"example{ref}.test",)),
        **extra,
    )


def desk(outcome: Ruled, **kw: Any) -> tuple[FactCheckDesk, FakeGraph]:
    graph = FakeGraph(outcome)
    settings = kw.pop("settings", None) or configured()
    return (
        FactCheckDesk(settings=settings, graph=graph, **kw),  # type: ignore[arg-type]
        graph,
    )


def ledger_of(report: Any) -> dict[str, str]:
    return {entry.key: entry.value for entry in report.ledger}


def signals_of(report: Any) -> dict[str, Any]:
    return {signal.label: signal for signal in report.signals}


def _swapped(source: Source, **changes: Any) -> Source:
    """A source with fields swapped, for the presentation helpers.

    :func:`dataclasses.replace` rather than a builder, because what is under test is
    formatting: the interesting inputs are combinations a real dossier produces rarely,
    and building them through the pipeline would test the pipeline instead.
    """
    return replace(source, **changes)


@pytest.fixture
def quiet() -> Iterator[None]:
    """Silence the desk's logger for a test that provokes it on purpose."""
    logger = logging.getLogger("app.desks.factcheck")
    was = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        logger.setLevel(was)


# ------------------------------------------------------------------- the seam ----


def test_it_is_the_registered_fact_check_examiner() -> None:
    assert examiners.factory(Desk.FACT_CHECK) is not None
    assert isinstance(examiners.resolve(Desk.FACT_CHECK), FactCheckDesk)


def test_it_satisfies_the_protocol_and_claims_the_prose_kinds() -> None:
    made = build(configured())
    assert isinstance(made, ArtifactDesk)
    assert made.desk is Desk.FACT_CHECK
    assert FactCheckDesk.kinds == frozenset(
        {ArtifactKind.TEXT, ArtifactKind.CLAIM, ArtifactKind.URL}
    )
    for kind in FactCheckDesk.kinds:
        assert can_examine(Desk.FACT_CHECK, kind)
    assert not can_examine(Desk.FACT_CHECK, ArtifactKind.IMAGE)


def test_a_memory_deployment_gets_no_store_rather_than_a_no_op_one() -> None:
    """``None`` is what keeps "nothing was written" apart from "it was written"."""
    made = build(configured(VERIFICATION_STORE=StoreBackend.MEMORY))
    assert made._store is None


# ------------------------------------------------------------ nothing to check ----


@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
async def test_empty_content_is_an_insufficiency_and_never_reaches_the_graph(
    body: str,
) -> None:
    examiner, graph = desk(await judged(state(PAIR)))
    report = await examiner.examine(Artifact(kind=ArtifactKind.TEXT, content=body))
    assert graph.seen == []
    assert report.verdict.determination is Determination.INSUFFICIENT
    assert report.verdict.headline == "Nothing was checked"
    assert ledger_of(report) == {"Claims checked": "0"}
    assert report.exhibits == ()


async def test_a_url_says_the_fetch_is_not_built_rather_than_that_it_was_empty() -> (
    None
):
    """Two different states, and a reader who cannot tell them apart is misinformed."""
    examiner, _ = desk(await judged(state(PAIR)))
    report = await examiner.examine(
        Artifact(kind=ArtifactKind.URL, url="https://example.test/story")
    )
    assert "fetching the article behind it is not built yet" in (
        report.verdict.rationale
    )


async def test_the_artifact_reaches_the_graph_unchanged() -> None:
    examiner, graph = desk(await judged(state(PAIR)))
    await examiner.examine(TEXT)
    assert graph.seen == [TEXT]


# ---------------------------------------------------------------- persistence ----


async def test_the_verification_id_reaches_the_store() -> None:
    """The only reason ``verification_id`` is threaded through a desk at all."""
    store = Store()
    outcome = await judged(state(PAIR))
    examiner, _ = desk(outcome, store=store)
    await examiner.examine(TEXT, verification_id="v-42")

    assert len(store.saved) == 1
    saved, verification_id = store.saved[0]
    assert verification_id == "v-42"
    # The graph's own dossier, gradings folded onto the claims, not a second assembly.
    assert saved == dossier(outcome.state)
    assert saved.claims[0].credibility != ()


async def test_a_verification_id_is_optional_and_not_invented() -> None:
    store = Store()
    examiner, _ = desk(await judged(state(PAIR)), store=store)
    await examiner.examine(TEXT)
    assert store.saved[0][1] is None


async def test_no_store_writes_nothing_and_still_files() -> None:
    examiner, _ = desk(await judged(state(PAIR)))
    report = await examiner.examine(TEXT)
    assert report.verdict.determination is Determination.SUPPORTED


@pytest.mark.usefixtures("quiet")
async def test_a_storage_failure_is_logged_and_the_report_is_still_filed() -> None:
    """The claims were checked whether or not a row was written."""
    store = Store(raises=RuntimeError("the connection dropped"))
    examiner, _ = desk(await judged(state(PAIR)), store=store)
    report = await examiner.examine(TEXT, verification_id="v-1")

    assert store.saved == []
    assert report.verdict.determination is Determination.SUPPORTED
    assert len(report.exhibits) == 2


# ------------------------------------------------------------------ retrieval ----


async def test_retrieval_indexes_this_runs_passages_and_reads_them_back() -> None:
    index = FakeIndex(relevant=(near(MATCHING, ref=1, similarity=0.9),), indexed=3)
    examiner, _ = desk(await judged(state(PAIR)), index=index, settings=indexing())
    report = await examiner.examine(TEXT)

    assert index.indexed_claims == [CLAIM]
    assert index.queried == [CLAIM]
    assert ledger_of(report)["Passages indexed"] == "3"
    assert signals_of(report)["Evidence retrieved"].reading == "1 of 1 claim(s)"


async def test_an_injected_index_is_left_open_for_its_owner_to_close() -> None:
    index = FakeIndex(indexed=1)
    examiner, _ = desk(await judged(state(PAIR)), index=index, settings=indexing())
    await examiner.examine(TEXT)
    assert index.closed is False


async def test_a_desk_built_index_is_closed_by_the_desk(monkeypatch: Any) -> None:
    from app.services import evidence

    index = FakeIndex(indexed=2)
    monkeypatch.setattr(evidence, "build", lambda _settings: index)
    examiner, _ = desk(await judged(state(PAIR)), settings=indexing())
    report = await examiner.examine(TEXT)

    assert index.indexed_claims == [CLAIM]
    assert index.closed is True
    assert ledger_of(report)["Passages indexed"] == "2"


async def test_retrieval_switched_off_indexes_nothing() -> None:
    index = FakeIndex(indexed=5)
    examiner, _ = desk(
        await judged(state(PAIR)),
        index=index,
        settings=configured(EVIDENCE_INDEX_ENABLED=False),
    )
    report = await examiner.examine(TEXT)

    assert index.indexed_claims == []
    assert index.queried == []
    assert "Passages indexed" not in ledger_of(report)
    assert "Evidence retrieved" not in signals_of(report)
    # And the finding is unchanged, because retrieval never fed one.
    assert report.verdict.determination is Determination.SUPPORTED
    assert len(report.exhibits) == 2


@pytest.mark.usefixtures("quiet")
async def test_a_retrieval_failure_costs_ordering_and_nothing_else() -> None:
    """The ruling is already made by the time this runs, so there is nothing to lose."""
    outcome = await judged(state(PAIR))
    broken, _ = desk(
        outcome,
        index=FakeIndex(raises=RuntimeError("the store went away")),
        settings=indexing(),
    )
    degraded = await broken.examine(TEXT)
    intact = await desk(outcome)[0].examine(TEXT)

    assert degraded.verdict == intact.verdict
    assert degraded.exhibits == intact.exhibits


@pytest.mark.usefixtures("quiet")
async def test_an_index_that_cannot_be_opened_is_a_warning_not_a_failure(
    monkeypatch: Any,
) -> None:
    from app.services import evidence

    def unavailable(_settings: Settings) -> None:
        raise ConfigurationError("no vector store is configured")

    monkeypatch.setattr(evidence, "build", unavailable)
    examiner, _ = desk(await judged(state(PAIR)), settings=indexing())
    report = await examiner.examine(TEXT)

    assert report.verdict.determination is Determination.SUPPORTED
    assert "Passages indexed" not in ledger_of(report)


async def test_retrieval_orders_the_sources_a_reader_sees() -> None:
    """The one thing retrieval is used for, and lexical selection cannot produce."""
    index = FakeIndex(
        relevant=(
            near(MATCHING, ref=2, similarity=0.95),
            near(MATCHING, ref=1, similarity=0.10),
        ),
        indexed=2,
    )
    examiner, _ = desk(await judged(state(PAIR)), index=index, settings=indexing())
    report = await examiner.examine(TEXT)
    assert [e.source for e in report.exhibits] == ["theguardian.com", "reuters.com"]


async def test_a_shared_passage_is_credited_to_every_source_that_carried_it() -> None:
    """Otherwise a syndicated report outranks the wire copy it came from by accident."""
    sources = (
        reported("https://reuters.com/a", ref=1, cluster=7),
        reported("https://apnews.com/b", ref=2, cluster=7),
        reported("https://theguardian.com/c", ref=3),
    )
    index = FakeIndex(
        relevant=(
            # Returned under the reprint, recorded as carried by the wire copy too.
            near(MATCHING, ref=2, similarity=0.99, refs=(2, 1)),
            near(MATCHING, ref=3, similarity=0.20),
        ),
        indexed=3,
    )
    examiner, _ = desk(await judged(state(sources)), index=index, settings=indexing())
    report = await examiner.examine(TEXT)
    shown = [e.source for e in report.exhibits]
    assert shown.index("reuters.com") < shown.index("theguardian.com")


async def test_sources_beyond_the_ceiling_are_counted_not_dropped_silently() -> None:
    sources = tuple(reported(f"https://s{n}.test/{n}", ref=n) for n in range(1, 6))
    examiner, _ = desk(declined(state(sources)), settings=configured(EVIDENCE_TOP_K=2))
    report = await examiner.examine(TEXT)

    assert len(report.exhibits) == 2
    assert ledger_of(report)["Sources found"] == "5"
    assert ledger_of(report)["Sources not shown"] == "3"


# ------------------------------------------------------------------- exhibits ----


async def test_every_determination_comes_from_the_judges_indications() -> None:
    """Two modules reading the same evidence is how a record contradicts itself."""
    outcome = await judged(state(PAIR))
    weighed = {i.ref for i in outcome.ruling.claims[0].indications if i.ref is not None}
    report = await desk(outcome)[0].examine(TEXT)

    assert weighed == {1, 2}
    assert [e.determination for e in report.exhibits] == [
        Determination.SUPPORTED,
        Determination.SUPPORTED,
    ]


async def test_a_source_the_arithmetic_never_weighed_is_never_supported() -> None:
    """A page appearing in the same search results is not a confirmation."""
    outcome = declined(state(SOLO))
    report = await desk(outcome)[0].examine(TEXT)
    assert outcome.ruling.claims[0].indications == ()
    # It carried a passage on the claim, so CONSISTENT — and no more than that.
    assert [e.determination for e in report.exhibits] == [Determination.CONSISTENT]


async def test_a_source_that_carried_no_passage_asks_to_be_checked() -> None:
    outcome = declined(state((reported("https://reuters.com/a", ""),)))
    report = await desk(outcome)[0].examine(TEXT)
    assert [e.determination for e in report.exhibits] == [
        Determination.REQUIRES_VERIFICATION
    ]


async def test_a_source_taken_both_ways_is_contested_not_averaged() -> None:
    outcome = declined(
        state(SOLO),
        judgement=Judgement.MIXED,
        indications=(
            Indication(
                agent="judge",
                bearing=Bearing.SUPPORTS,
                weight=1.0,
                detail="repeats the claim's figure",
                ref=1,
            ),
            Indication(
                agent="contradiction",
                bearing=Bearing.REFUTES,
                weight=1.0,
                detail="gives a different figure",
                ref=1,
            ),
        ),
    )
    report = await desk(outcome)[0].examine(TEXT)
    assert [e.determination for e in report.exhibits] == [Determination.CONTESTED]


async def test_a_refuting_indication_reaches_the_row_it_came_from() -> None:
    outcome = declined(
        state((reported("https://reuters.com/a", RIVAL),)),
        judgement=Judgement.REFUTED,
        indications=(
            Indication(
                agent="contradiction",
                bearing=Bearing.REFUTES,
                weight=0.8,
                detail="gives 5.25% where the claim gives 4.75%",
                ref=1,
            ),
        ),
    )
    report = await desk(outcome)[0].examine(TEXT)
    assert [e.determination for e in report.exhibits] == [Determination.CONTRADICTED]
    assert report.verdict.determination is Determination.CONTRADICTED


async def test_no_passage_is_invented_to_fill_the_column() -> None:
    """An arbitrary line in an evidence column fabricates relevance."""
    outcome = declined(state((reported("https://reuters.com/a", ""),)))
    report = await desk(outcome)[0].examine(TEXT)
    assert report.exhibits[0].extract == "No passage in this page bears on the claim."


async def test_the_extract_is_a_passage_the_source_actually_carried() -> None:
    outcome = declined(state((reported("https://reuters.com/a", RIVAL),)))
    report = await desk(outcome)[0].examine(TEXT)
    assert report.exhibits[0].extract == RIVAL


async def test_a_retrieved_passage_is_preferred_over_the_lexical_pick() -> None:
    """Which passage of a page a reader is shown is the other half of retrieval."""
    page = built(
        "https://reuters.com/a",
        ref=1,
        evidence=(passage(MATCHING, matched=()), passage(RIVAL)),
    )
    index = FakeIndex(relevant=(near(RIVAL, ref=1, similarity=0.9),), indexed=2)
    examiner, _ = desk(declined(state((page,))), index=index, settings=indexing())
    report = await examiner.examine(TEXT)
    assert report.exhibits[0].extract == RIVAL


async def test_refs_are_numbered_from_one_in_the_order_shown() -> None:
    report = await desk(await judged(state(PAIR)))[0].examine(TEXT)
    assert [e.ref for e in report.exhibits] == [1, 2]


# ---------------------------------------------------------------- reliability ----


async def test_verified_is_unreachable_whatever_the_publisher() -> None:
    """Every source here is a search result, not a primary record."""
    sources = (
        reported("https://reuters.com/a", ref=1),
        reported("https://who.int/b", ref=2),
        reported("https://someblog.example/c", ref=3),
    )
    report = await desk(await judged(state(sources)))[0].examine(TEXT)
    assert len(report.exhibits) == 3
    for exhibit in report.exhibits:
        assert exhibit.reliability is not Reliability.VERIFIED


def test_an_unknown_band_is_floored_rather_than_read_as_a_finding() -> None:
    from app.desks.factcheck import _RELIABILITY

    assert set(_RELIABILITY) == set(Band)
    assert _RELIABILITY[Band.UNKNOWN] is Reliability.LOW
    assert Reliability.VERIFIED not in set(_RELIABILITY.values())


async def test_an_ungraded_source_is_floored_never_promoted() -> None:
    """``grade=False`` is the ``CREDIBILITY_ENABLED=False`` deployment."""
    report = await desk(await judged(state(PAIR, grade=False)))[0].examine(TEXT)
    assert [e.reliability for e in report.exhibits] == [
        Reliability.LOW,
        Reliability.LOW,
    ]


async def test_relevance_is_read_across_every_passage_not_the_first() -> None:
    """Evidence is ordered lexically, and a page's figure usually sits further down."""
    page = built(
        "https://reuters.com/a",
        ref=1,
        evidence=(passage(MATCHING, matched=()), passage(MATCHING)),
    )
    report = await desk(declined(state((page,))))[0].examine(TEXT)
    assert report.exhibits[0].relevance is Relevance.HIGH


async def test_a_source_with_no_passage_is_low_relevance() -> None:
    outcome = declined(state((reported("https://reuters.com/a", ""),)))
    report = await desk(outcome)[0].examine(TEXT)
    assert report.exhibits[0].relevance is Relevance.LOW


# --------------------------------------------------------------- how it reads ----


@pytest.mark.parametrize(
    ("basis", "expected"),
    [
        (DateBasis.PROVIDER, "06 Feb 2026"),
        (DateBasis.PROVIDER_MODIFIED, "by 06 Feb 2026"),
        (DateBasis.PROVIDER_RELATIVE, "c. 06 Feb 2026"),
        (DateBasis.URL_PATH, "06 Feb 2026, from the URL"),
    ],
)
def test_a_weaker_date_is_qualified_in_the_cell(
    basis: DateBasis, expected: str
) -> None:
    """A bare date on the wire would throw :class:`DateBasis` away."""
    from app.desks.factcheck import _published

    assert _published(_swapped(SOLO[0], date_basis=basis)) == expected


def test_an_undateable_source_says_so() -> None:
    from app.desks.factcheck import _published

    assert _published(reported("https://reuters.com/a", dated=False)) == UNDATED


def test_a_long_headline_is_clipped_and_keeps_its_masthead() -> None:
    from app.desks.factcheck import _named

    named = _named(_swapped(SOLO[0], title="Headline " * 30))
    assert named.endswith(" (reuters.com)")
    assert named.split(" (")[0].endswith("…")
    assert len(named.split(" (")[0]) == TITLE_LIMIT


def test_an_untitled_source_is_named_by_its_publisher() -> None:
    from app.desks.factcheck import _named

    assert _named(_swapped(SOLO[0], title="")) == "reuters.com"


# ------------------------------------------------------------------ the filing ----


async def test_the_claim_is_marked_with_what_was_submitted_not_the_rewrite() -> None:
    """The frontend locates a marked span with ``indexOf``, and the graph's rewrite
    resolves pronouns, so it is frequently not a substring of the submission."""
    outcome = await judged(state(PAIR))
    report = await desk(outcome)[0].examine(TEXT)
    quote = cases(outcome.state)[0].claim.quote
    assert [a.quote for a in report.annotations] == [quote]
    assert [a.determination for a in report.annotations] == [Determination.SUPPORTED]


async def test_an_unsettled_claim_is_annotated_with_the_reason() -> None:
    outcome = declined(state(SOLO), why="nothing settles it")
    report = await desk(outcome)[0].examine(TEXT)
    assert report.annotations[0].note == "nothing settles it"


async def test_a_settled_claim_with_no_model_reading_states_the_arithmetic() -> None:
    outcome = await judged(state(PAIR))
    report = await desk(outcome)[0].examine(TEXT)
    confidence = round(outcome.ruling.claims[0].confidence * 100)
    assert report.annotations[0].note == f"SUPPORTED at {confidence}% confidence."
    assert "Model reading" not in ledger_of(report)


async def test_the_models_reading_is_published_when_it_ran() -> None:
    outcome = await judged(state(PAIR))
    outcome.reasoning = (
        Reasoning(
            verdict=Assessment.MOSTLY_TRUE,
            confidence=72,
            reasoning="The passages bear on the claim's own figure.",
            model="scripted-1",
        ),
    )
    report = await desk(outcome)[0].examine(TEXT)
    assert report.annotations[0].note == "The passages bear on the claim's own figure."
    assert ledger_of(report)["Model reading"] == "scripted-1"


async def test_published_reviewers_are_named_and_not_adopted() -> None:
    """A reviewer's rating is somebody else's verdict."""
    held = state(PAIR, fact_checks=rated("True"))
    report = await desk(await judged(held))[0].examine(TEXT)
    rationale = report.verdict.rationale

    assert "This claim has been reviewed before: Reviewer 1." in rationale
    assert "weighed as evidence, not adopted as the finding" in rationale
    # And no exhibit row of their own, which would need standing this service has not
    # established for the reviewer's own page.
    assert all("reviewer1.example" not in e.source for e in report.exhibits)


async def test_an_unreviewed_claim_says_nothing_about_reviewers() -> None:
    report = await desk(await judged(state(PAIR)))[0].examine(TEXT)
    assert "reviewed before" not in report.verdict.rationale


async def test_the_desks_verdict_is_the_rulings_unchanged() -> None:
    outcome = await judged(state(PAIR))
    report = await desk(outcome)[0].examine(TEXT)
    assert report.verdict.headline == outcome.ruling.headline
    assert report.verdict.confidence == pytest.approx(outcome.ruling.confidence)
    assert outcome.ruling.rationale in report.verdict.rationale


# ------------------------------------------------------------------- counting ----


async def test_the_ledger_counts_what_was_gathered() -> None:
    held = state(PAIR, fact_checks=rated("True", "Mostly False"))
    report = await desk(await judged(held))[0].examine(TEXT)
    ledger = ledger_of(report)

    assert ledger["Claims checked"] == "1"
    assert ledger["Sources found"] == "2"
    assert ledger["Publishers"] == "2"
    assert ledger["Independent stories"] == "2"
    assert ledger["Search providers"] == "1 of 1 answered"
    # One reviewed claim, whatever the two reviewers said about it.
    assert ledger["Published reviews"] == "1"


async def test_syndication_is_counted_as_one_story() -> None:
    """Two mastheads carrying one wire report is one story, and a reader shown it as
    two independent confirmations has been misled by arithmetic."""
    sources = (
        reported("https://reuters.com/a", ref=1, cluster=7),
        reported("https://apnews.com/b", ref=2, cluster=7),
    )
    report = await desk(await judged(state(sources)))[0].examine(TEXT)

    assert ledger_of(report)["Sources found"] == "2"
    assert ledger_of(report)["Independent stories"] == "1"
    assert signals_of(report)["Independent reporting"].weight == pytest.approx(0.5)


async def test_absent_counts_are_omitted_rather_than_zero_filled() -> None:
    report = await desk(await judged(state(PAIR)))[0].examine(TEXT)
    ledger = ledger_of(report)
    for absent in (
        "Claims set aside",
        "Published reviews",
        "Passages indexed",
        "Sources not shown",
    ):
        assert absent not in ledger


async def test_every_signal_is_a_share_of_something_counted() -> None:
    index = FakeIndex(relevant=(near(MATCHING, ref=1, similarity=0.8),), indexed=2)
    examiner, _ = desk(await judged(state(PAIR)), index=index, settings=indexing())
    report = await examiner.examine(TEXT)
    signals = signals_of(report)

    assert signals["Claims settled"].reading == "1 of 1"
    assert signals["Source standing"].reading == "mean of 2 graded source(s)"
    assert signals["Independent reporting"].reading == (
        "2 story/stories across 2 source(s)"
    )
    assert signals["Evidence retrieved"].reading == "1 of 1 claim(s)"
    for signal in report.signals:
        assert 0.0 <= signal.weight <= 1.0


async def test_an_unsettled_claim_is_counted_as_unsettled() -> None:
    report = await desk(declined(state(SOLO)))[0].examine(TEXT)
    settled = signals_of(report)["Claims settled"]
    assert settled.reading == "0 of 1"
    assert settled.weight == 0.0
