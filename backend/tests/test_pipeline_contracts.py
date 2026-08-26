"""One submission, every stage, nothing faked in between.

Every other module in this suite tests a part. This one tests that the parts are
*reachable from each other*: text goes in at
:meth:`app.services.verification.VerificationService.submit` and a signed record
comes out, having passed through claim extraction, web search, the fact-check
lookup, evidence selection, source credibility, the agent graph, vector retrieval,
the language model, the score engine and the research store — in that order, with
the real code at each step.

Four doubles, and no more, each standing exactly where the world is:

* :class:`tests.search_bench.Fake` and :class:`tests.factcheck_bench.Fake` for the
  two networks. Everything they return is asserted against below, which is what
  makes "nothing was invented" checkable rather than assumed.
* :class:`Scripted` for the model, because a real one is neither offline nor
  deterministic. It answers *out of the brief it was shown* — see its docstring.
* :class:`Recorder` for the research store, because SQLAlchemy against a real
  database is :mod:`tests.test_repository_sql`'s subject. What is verifiable here
  is that a dossier reaches a store at all and that it arrives tagged with the
  verification it belongs to, which is the only reason ``verification_id`` is
  threaded through a desk.

Retrieval is real: an in-memory vector store and the hashing embedder, both of
which ship in the package precisely so this path has no optional dependency.
``EVIDENCE_MIN_SIMILARITY`` is dropped to zero because a hashing embedder is a
genuine embedder and not a semantic one — the assertion below is that the
retrieval stage is wired and answers, not that its neighbours are good ones.

The one substitution that is not a double is :class:`Sequential`: the graph's own
topology, replayed without LangGraph. See its docstring for why, and for the
reducer it reads rather than restates.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast, get_type_hints

import pytest

from app.core.config import (
    Environment,
    SearchProvider,
    Settings,
    StoreBackend,
)
from app.desks.factcheck import FactCheckDesk
from app.desks.text import TextDesk
from app.domain import (
    ADJUDICATOR,
    Artifact,
    ArtifactKind,
    DateBasis,
    Desk,
    Determination,
    Dossier,
    Entity,
    ExtractedClaim,
    Extraction,
    Keyword,
    ProviderStatus,
    Status,
    Unfit,
    Verification,
    desks_for,
)
from app.graph import state as channels
from app.graph.agents.claim import ClaimAgent
from app.graph.agents.contradiction import ContradictionAgent
from app.graph.agents.evidence import EvidenceAgent
from app.graph.agents.factcheck import FactCheckAgent
from app.graph.agents.judge import JudgeAgent
from app.graph.agents.search import SearchAgent
from app.graph.agents.source import SourceAgent
from app.graph.state import GraphState
from app.graph.verdict import Assessment, Ruling, as_determination
from app.llm.base import Completion, Message
from app.llm.hashing import HashingEmbedder
from app.reasoning import ReasoningLayer
from app.reasoning.answer import Reasoning
from app.repositories.base import ResearchRepository
from app.repositories.memory import InMemoryVerificationRepository
from app.services.evidence import EvidenceIndex
from app.services.verification import VerificationService
from app.vectorstore.evidence import Relevant
from app.vectorstore.memory import InMemoryVectorStore
from tests import factcheck_bench, search_bench
from tests.research_bench import NOW, WIRE, WIRE_TITLE
from tests.stubs import StubClaimExtractor, desk_bench, extractor_bench

#: The claim the whole file is about, and the assertion the corpus corroborates.
CLAIM = "The Bank of England held its benchmark rate at 4.75% in March 2026."

#: The sentence the extractor marks unfit, so the ``skipped`` channel is exercised
#: too — a submission is prose, not a claim, and the record has to describe all of it.
OPINION = "That was the right call for the country."

SUBMISSION = f"{CLAIM} {OPINION}"

#: A second body carrying the claim's figure in wholly different words. It has to be
#: different: :mod:`app.research.dedupe` would merge a rephrasing of :data:`WIRE` into
#: one story, and one story is one standing source — below the judge's floor of two,
#: which would decline the claim and never reach the model at all.
STATEMENT = (
    "Minutes published alongside Thursday's decision record a majority on the "
    "Committee in favour of maintaining Bank Rate at 4.75%. Members judged that a "
    "further reduction risked entrenching domestic price pressures before the "
    "spring data arrive, and the summary sets out the conditions under which the "
    "Committee would be prepared to move at its next meeting."
)
STATEMENT_TITLE = "Monetary Policy Summary and minutes of the March meeting"

WIRE_URL = "https://reuters.com/markets/rates/boe-holds-bank-rate-2026-03-12"
STATEMENT_URL = "https://bankofengland.co.uk/monetary-policy-summary/2026/march-2026"
REVIEW_URL = "https://fullfact.org/economy/bank-rate-march-2026/"

#: Every URL a provider returned. Nothing in the finished record may name another.
RETURNED = frozenset({WIRE_URL, STATEMENT_URL})

PUBLISHED = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
REVIEWED = datetime(2026, 3, 13, 9, 0, tzinfo=UTC)

#: Long enough for :func:`app.providers.http.redact` to act on it.
FACT_CHECK_KEY = "fc-secret-key-value"

MODEL = "scripted-1"

#: What the desk prints for a page that carried no bearing passage. Not a quote, and
#: not an invention either — the assertion below has to admit it to stay a statement
#: about fabrication rather than about coverage.
NO_PASSAGE = "No passage in this page bears on the claim."

#: Exhibit ids as :func:`app.reasoning.brief.render` writes them.
_EXHIBIT = re.compile(r"\[(E\d+)\]")

#: The reducers on :class:`~app.graph.state.GraphState`, read off the annotations
#: rather than restated here. A channel that gains one cannot leave
#: :class:`Sequential` merging it by replacement.
_REDUCERS = {
    name: hint.__metadata__[0]
    for name, hint in get_type_hints(GraphState, include_extras=True).items()
    if hasattr(hint, "__metadata__")
}


# ------------------------------------------------------------ the submission ----


def _located(text: str, *, ref: int, **extra: Any) -> ExtractedClaim:
    """A claim whose offsets index :data:`SUBMISSION`, as a real extraction's do."""
    start = SUBMISSION.index(text)
    return ExtractedClaim(
        ref=ref, text=text, quote=text, start=start, end=start + len(text), **extra
    )


def _extraction() -> Extraction:
    return Extraction(
        claims=(
            _located(
                CLAIM,
                ref=1,
                entities=(
                    Entity(
                        text="The Bank of England",
                        label="ORG",
                        start=0,
                        end=len("The Bank of England"),
                    ),
                ),
                keywords=(Keyword(term="benchmark rate", score=1.0),),
            ),
            _located(OPINION, ref=2, checkable=False, reason=Unfit.OPINION),
        ),
        entities=(
            Entity(
                text="The Bank of England",
                label="ORG",
                start=0,
                end=len("The Bank of England"),
            ),
        ),
        keywords=(Keyword(term="benchmark rate", score=1.0),),
        sentences=2,
    )


# ------------------------------------------------------------------- doubles ----


class Scripted:
    """A model that answers out of the brief it was shown, and adds nothing.

    It cites the brief's first exhibit and writes prose carrying no figure, no
    hostname and no quotation — which is what makes it a useful double rather than a
    convenient one. A double that answered loosely would trip
    :mod:`app.reasoning.answer`'s grounding checks on every run, the layer would
    publish its arithmetic fallback, and this file would never see a model's reading
    reach a record at all. The checks themselves are tested against fabrications in
    ``test_reasoning_answer.py``; here they are the thing being passed.
    """

    name = "scripted"

    def __init__(
        self, *, verdict: str = "MOSTLY_TRUE", confidence: int = 72
    ) -> None:
        self._verdict = verdict
        self._confidence = confidence
        #: Every rendered brief, so a test can read what the model was actually shown.
        self.briefs: list[str] = []
        self.closed = False

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 700,
    ) -> Completion:
        brief = messages[-1].content
        self.briefs.append(brief)
        shown = _EXHIBIT.search(brief)
        if shown is None:
            answer = {
                "verdict": Assessment.UNCERTAIN.value,
                "confidence": 0,
                "reasoning": "No passage was shown, so there is nothing to read.",
                "evidence": [],
            }
        else:
            cited = shown.group(1)
            answer = {
                "verdict": self._verdict,
                "confidence": self._confidence,
                "reasoning": (
                    f"The gathered passages bear on the claim's own specifics, and "
                    f"[{cited}] carries them most directly. This reading is taken "
                    f"from the brief and adds nothing to it."
                ),
                "evidence": [cited],
            }
        return Completion(text=json.dumps(answer), model=MODEL)

    async def aclose(self) -> None:
        self.closed = True


class Recorder(ResearchRepository):
    """A research store that keeps what it was handed.

    Subclassing the protocol rather than duck-typing it, so a method the store gains
    fails this file at construction instead of at the one call site that uses it.
    """

    def __init__(self) -> None:
        self.saved: list[tuple[Dossier, str | None]] = []

    async def save_dossier(
        self, dossier: Dossier, *, verification_id: str | None = None
    ) -> tuple[str, ...]:
        self.saved.append((dossier, verification_id))
        return tuple(f"claim-{index}" for index, _ in enumerate(dossier.claims, 1))

    async def get_research(self, claim_id: str) -> None:
        return None

    async def research_for(self, verification_id: str) -> tuple[()]:
        return ()


# --------------------------------------------------------------- the topology ----


class Finished:
    """What :class:`app.graph.workflow.Outcome` exposes, assembled the same way."""

    __slots__ = ("reasoning", "ruling", "state", "trace")

    def __init__(
        self, state: GraphState, reasoning: tuple[Reasoning, ...] = ()
    ) -> None:
        ruling = state.get("ruling")
        assert ruling is not None, "the graph finished without a ruling"
        self.state = state
        self.ruling: Ruling = ruling
        self.trace = state.get("trace", ())
        self.reasoning = reasoning


def _merge(state: GraphState, write: GraphState) -> None:
    """Apply one agent's channel writes, reducing the channels that have a reducer."""
    held = cast("dict[str, Any]", state)
    for channel, value in cast("dict[str, Any]", write).items():
        reduce = _REDUCERS.get(channel)
        held[channel] = reduce(held.get(channel, ()), value) if reduce else value


class Sequential:
    """The graph's topology, run without LangGraph.

    :mod:`app.graph.workflow` is the only module in the package that imports
    langgraph, and it is an optional install — so a module that imported it to test
    the pipeline could not run in a deployment that has everything else. The agents
    are plain callables over one ``TypedDict``, which is what makes replaying the
    topology here possible: the same order, the same concurrency between ``search``
    and ``factcheck``, the same short circuit to the judge when the extractor found
    nothing, and the same reducer on ``trace`` — read off the annotation in
    :func:`_merge` rather than hard-coded, because a driver that merged an appending
    channel by replacement would silently lose most of the trace this file asserts on.

    What it does not replay is scheduling. LangGraph runs the two gatherers in one
    superstep and joins them at ``evidence``; ``asyncio.gather`` and a merge after
    both is the same observable sequence for agents that read the state they were
    handed and return only their own writes, which all seven do.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        extractor: Any,
        reasoning: ReasoningLayer | None = None,
    ) -> None:
        self._claim = ClaimAgent(settings=settings, extractor=extractor)
        self._gatherers = (
            SearchAgent(settings=settings),
            FactCheckAgent(settings=settings),
        )
        self._rest = (
            EvidenceAgent(),
            SourceAgent(settings=settings),
            ContradictionAgent(),
        )
        self._judge = JudgeAgent()
        self._reasoning = reasoning
        #: Every run, so the assertions below can describe the pass the record came
        #: from rather than a second pass made to observe one.
        self.finished: list[Finished] = []

    async def run(
        self, artifact: Artifact, *, now: datetime | None = None
    ) -> Finished:
        state = channels.initial(artifact, now=now or NOW)
        _merge(state, await self._claim(state))
        if state.get("claims"):
            for write in await asyncio.gather(*(a(state) for a in self._gatherers)):
                _merge(state, write)
            for agent in self._rest:
                _merge(state, await agent(state))
        _merge(state, await self._judge(state))
        outcome = Finished(state, await self._read(state))
        self.finished.append(outcome)
        return outcome

    async def _read(self, state: GraphState) -> tuple[Reasoning, ...]:
        layer = self._reasoning
        ruling = state.get("ruling")
        if layer is None or ruling is None or not ruling.claims:
            return ()

        found = {case.claim.ref: case for case in channels.cases(state)}
        work: list[Awaitable[Reasoning]] = []
        for decided in ruling.claims:
            case = found.get(decided.ref)
            if case is None or case.research is None:
                continue
            work.append(
                layer.consider(
                    ruling=decided,
                    research=case.research,
                    conflicts=case.conflicts,
                    credibility=case.grading,
                )
            )
        return tuple(await asyncio.gather(*work))


# ---------------------------------------------------------------- one run ----


@dataclass(frozen=True, slots=True)
class Run:
    """Everything one pass through the pipeline produced."""

    record: Verification
    outcome: Finished
    stored: tuple[tuple[Dossier, str | None], ...]
    retrieved: tuple[Relevant, ...]
    briefs: tuple[str, ...]
    searched: tuple[str, ...]
    looked_up: tuple[str, ...]


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        ENVIRONMENT=Environment.LOCAL,
        VERIFICATION_STORE=StoreBackend.MEMORY,
        SEARCH_PROVIDERS=[SearchProvider.TAVILY],
        GOOGLE_FACT_CHECK_API_KEY=FACT_CHECK_KEY,
        EVIDENCE_INDEX_ENABLED=True,
        EVIDENCE_MIN_SIMILARITY=0.0,
    )


def _results() -> list[object]:
    return [
        search_bench.found(
            WIRE_URL,
            title=WIRE_TITLE,
            snippet=WIRE,
            published_at=PUBLISHED,
            date_basis=DateBasis.PROVIDER,
            date_text="12 March 2026",
        ),
        search_bench.found(
            STATEMENT_URL,
            title=STATEMENT_TITLE,
            snippet=STATEMENT,
            published_at=PUBLISHED,
            date_basis=DateBasis.PROVIDER,
            date_text="12 March 2026",
        ),
    ]


async def _run(*, verdict: str = "MOSTLY_TRUE", confidence: int = 72) -> Run:
    settings = _settings()
    searcher = search_bench.Fake("tavily", results=_results())  # type: ignore[arg-type]
    database = factcheck_bench.Fake(
        results=[
            factcheck_bench.record(
                CLAIM,
                factcheck_bench.review(
                    publisher="Full Fact",
                    site="fullfact.org",
                    url=REVIEW_URL,
                    rating="True",
                    reviewed_at=REVIEWED,
                ),
                claimed_at=PUBLISHED,
            )
        ]
    )
    store = Recorder()
    model = Scripted(verdict=verdict, confidence=confidence)
    index = EvidenceIndex(
        InMemoryVectorStore(),
        HashingEmbedder(256),
        top_k=settings.EVIDENCE_TOP_K,
        min_similarity=settings.EVIDENCE_MIN_SIMILARITY,
    )

    with (
        extractor_bench(StubClaimExtractor(extraction=_extraction())),
        search_bench.bench({SearchProvider.TAVILY: searcher}),
        factcheck_bench.bench(database),
    ):
        from app.services.claims import ClaimExtractionService

        graph = Sequential(
            settings=settings,
            extractor=ClaimExtractionService(settings=settings),
            reasoning=ReasoningLayer(model),
        )
        desks = {
            Desk.TEXT: TextDesk(settings=settings),
            Desk.FACT_CHECK: FactCheckDesk(
                settings=settings, graph=graph, index=index, store=store
            ),
        }
        artifact = Artifact(kind=ArtifactKind.TEXT, content=SUBMISSION)
        service = VerificationService(
            repository=InMemoryVerificationRepository(), settings=settings
        )
        with desk_bench(desks):  # type: ignore[arg-type]
            submitted = await service.submit(
                artifact=artifact, desks=desks_for(artifact.kind)
            )
            await service.run(submitted.id)
            record = await service.get(submitted.id)

        # The desk drove the graph; nothing here re-drives it. Everything asserted
        # below therefore describes one pass, which is what makes the counts
        # (one prompt, one dossier saved) mean anything.
        assert len(graph.finished) == 1
        outcome = graph.finished[0]
        retrieved = await index.relevant(CLAIM)

    await index.aclose()
    return Run(
        record=record,
        outcome=outcome,
        stored=tuple(store.saved),
        retrieved=retrieved,
        briefs=tuple(model.briefs),
        searched=tuple(searcher.queries),
        looked_up=tuple(database.queries),
    )


@pytest.fixture(scope="module")
def run() -> Run:
    """One pass through the pipeline, shared by every test below.

    Synchronous, so that the run happens exactly once: every assertion in this file
    is a statement about the *same* record, and a function-scoped async fixture would
    re-search, re-index and re-prompt for each of them.
    """
    return _once()


@pytest.fixture(scope="module")
def contested() -> Run:
    """A second pass in which the model reads the same dossier the other way.

    Its own run, because the disagreement has to be genuine: what is under test is
    that a model contradicting the arithmetic is *recorded* rather than obeyed, and
    that is only observable when the two actually differ. FALSE against a dossier the
    engine scores SUPPORTED is the sharpest disagreement available.
    """
    return _once(verdict=Assessment.FALSE.value, confidence=88)


def _once(**scripted: Any) -> Run:
    # A worker thread, because owning an event loop from synchronous code is only
    # possible off whatever loop the runner may already have resolved this fixture
    # inside — asyncio.run refuses in that case, and that is the runner's choice.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_run(**scripted))).result()


# ------------------------------------------------------- input to a verdict ----


def test_the_record_is_signed(run: Run) -> None:
    assert run.record.status is Status.COMPLETED
    assert run.record.failure is None
    assert run.record.verdict is not None


def test_every_rostered_desk_filed(run: Run) -> None:
    """The roster comes from ``desks_for``, not from this test."""
    assert [report.desk for report in run.record.reports] == [
        Desk.TEXT,
        Desk.FACT_CHECK,
        ADJUDICATOR,
    ]


def test_the_verdict_is_the_adjudicators(run: Run) -> None:
    signed = run.record.report_for(ADJUDICATOR)
    assert signed is not None
    assert run.record.verdict is signed.verdict
    assert signed.verdict.determination is not Determination.INSUFFICIENT


# ------------------------------------------------------------- every stage ----


def test_the_trace_names_every_agent(run: Run) -> None:
    assert {note.agent for note in run.outcome.trace} == {
        "claim",
        "search",
        "factcheck",
        "evidence",
        "source",
        "contradiction",
        "judge",
    }


def test_extraction_ran_and_set_the_opinion_aside(run: Run) -> None:
    state = run.outcome.state
    assert [claim.text for claim in state["claims"]] == [CLAIM]
    assert [skipped.reason for skipped in state["skipped"]] == [Unfit.OPINION]


def test_search_and_the_lookup_were_both_asked(run: Run) -> None:
    assert CLAIM in run.searched
    assert CLAIM in run.looked_up
    assert all(
        outcome.status is ProviderStatus.SEARCHED
        for outcome in run.outcome.state["providers"]
    )
    assert all(
        outcome.status is ProviderStatus.SEARCHED
        for outcome in run.outcome.state["checkers"]
    )


def test_evidence_credibility_and_contradiction_all_wrote(run: Run) -> None:
    case = channels.cases(run.outcome.state)[0]
    assert case.research is not None
    assert len(case.research.sources) == 2
    assert [grade.ref for grade in case.grading] == [1, 2]
    assert all(grade.standing is not None for grade in case.grading)
    # The channel is present and empty: two sources that agree is a finding too, and
    # the contradiction agent writing nothing is different from it not running.
    assert case.conflicts == ()


def test_the_two_sources_stayed_two_stories(run: Run) -> None:
    """The judge's floor is two independent sources. One merged story is one source."""
    case = channels.cases(run.outcome.state)[0]
    assert case.research is not None
    assert case.research.stories == 2
    assert {source.domain for source in case.research.sources} == {
        "reuters.com",
        "bankofengland.co.uk",
    }


def test_the_published_review_was_weighed_as_evidence(run: Run) -> None:
    case = channels.cases(run.outcome.state)[0]
    assert [check.publishers for check in case.fact_checks] == [("Full Fact",)]
    rationale = run.record.report_for(Desk.FACT_CHECK)
    assert rationale is not None
    assert "Full Fact" in rationale.verdict.rationale
    assert "not\nadopted" in rationale.verdict.rationale.replace(" ", "\n")


# ------------------------------------------------------------------ the RAG ----


def test_the_passages_were_indexed_and_read_back(run: Run) -> None:
    report = run.record.report_for(Desk.FACT_CHECK)
    assert report is not None
    ledger = {entry.key: entry.value for entry in report.ledger}
    assert int(ledger["Passages indexed"]) > 0

    signals = {signal.label: signal for signal in report.signals}
    assert signals["Evidence retrieved"].weight == 1.0
    assert run.retrieved != ()


def test_nothing_retrieved_came_from_outside_the_dossier(run: Run) -> None:
    case = channels.cases(run.outcome.state)[0]
    quotes = {
        passage.quote for source in case.sources for passage in source.evidence
    }
    assert {passage.quote for passage in run.retrieved} <= quotes


# --------------------------------------------------------------- the model ----


def test_the_model_was_shown_the_brief_and_only_the_brief(run: Run) -> None:
    assert len(run.briefs) == 1
    brief = run.briefs[0]
    assert brief.startswith(f"CLAIM: {CLAIM}")
    assert "EVIDENCE — the only passages you may cite" in brief
    for url in re.findall(r"https?://\S+", brief):
        assert url.rstrip(")\"'") in RETURNED | {REVIEW_URL}


def test_the_models_reading_was_published(run: Run) -> None:
    reading = run.outcome.reasoning[0]
    assert reading.grounded is True
    assert reading.model == MODEL
    assert reading.citations != ()

    report = run.record.report_for(Desk.FACT_CHECK)
    assert report is not None
    assert report.annotations[0].note.startswith(reading.reasoning)
    ledger = {entry.key: entry.value for entry in report.ledger}
    assert ledger["Model reading"] == MODEL
    assert "Readings not grounded" not in ledger


def test_an_agreeing_model_disputes_nothing(run: Run) -> None:
    reading = run.outcome.reasoning[0]
    decided = run.outcome.ruling.claims[0]
    assert decided.score is not None
    assert reading.verdict is decided.score.assessment
    assert reading.disputed == ""


def test_a_disagreement_is_recorded_and_never_resolved(contested: Run) -> None:
    """A model that contradicts the arithmetic is published beside it, not over it."""
    reading = contested.outcome.reasoning[0]
    decided = contested.outcome.ruling.claims[0]
    assert decided.score is not None
    assert reading.verdict is Assessment.FALSE
    assert reading.verdict is not decided.score.assessment

    # Recorded: the disagreement is on the record, and names the number it disagrees
    # with rather than merely asserting that one exists.
    assert reading.disputed != ""
    assert str(decided.score.assessment.value) in reading.disputed
    # Not resolved: still the model's own grounded reading, not a refusal.
    assert reading.grounded is True
    assert reading.rejected == ""


def test_a_disagreeing_model_does_not_move_the_verdict(contested: Run) -> None:
    """The published determination is the engine's, whatever the model concluded."""
    report = contested.record.report_for(Desk.FACT_CHECK)
    ruling = contested.outcome.ruling
    assert report is not None
    assert report.verdict.determination is as_determination(ruling.judgement)
    assert report.verdict.determination is Determination.SUPPORTED
    assert contested.record.verdict is not None
    assert contested.record.verdict.determination is Determination.SUPPORTED

    # And the reader is told, in the note itself, that the two differed.
    assert contested.outcome.reasoning[0].disputed in report.annotations[0].note


def test_the_model_cited_only_evidence_that_exists(run: Run) -> None:
    urls = {exhibit.url for exhibit in run.outcome.reasoning[0].evidence}
    assert urls != set()
    assert urls <= RETURNED


# ------------------------------------------------- score, verdict, storage ----


def test_the_claim_was_settled_rather_than_declined(run: Run) -> None:
    """Everything above depends on this: a declined claim never reaches the model."""
    decided = run.outcome.ruling.claims[0]
    assert decided.insufficiency == ""
    assert decided.support >= 0.6
    assert decided.score is not None
    assert decided.score.assessment in {Assessment.TRUE, Assessment.MOSTLY_TRUE}


def test_the_desk_publishes_the_engines_number_unchanged(run: Run) -> None:
    report = run.record.report_for(Desk.FACT_CHECK)
    ruling = run.outcome.ruling
    assert report is not None
    assert report.verdict.determination is as_determination(ruling.judgement)
    assert report.verdict.confidence == pytest.approx(ruling.confidence)


def test_the_dossier_reached_the_store_tagged_with_its_verification(run: Run) -> None:
    assert len(run.stored) == 1
    dossier, verification_id = run.stored[0]
    assert verification_id == run.record.id
    assert [record.claim for record in dossier.claims] == [CLAIM]
    # Folded on the way in, so a stored dossier is graded and one read back from the
    # research service is the same object.
    assert dossier.claims[0].credibility != ()
    assert dossier.retrieved_at == NOW


def test_no_exhibit_names_a_source_no_provider_returned(run: Run) -> None:
    """The integration-level form of the rule: the record invents nothing.

    Checked on the desk's own exhibits rather than the graph state, because the desk
    is the last thing to touch them before a reader does.
    """
    report = run.record.report_for(Desk.FACT_CHECK)
    assert report is not None
    assert report.exhibits != ()
    domains = {url.split("/")[2] for url in RETURNED}
    permitted = _quotes(run) | {NO_PASSAGE}
    for exhibit in report.exhibits:
        assert any(domain in exhibit.source for domain in domains)
        assert exhibit.extract in permitted


def _quotes(run: Run) -> set[str]:
    """Every passage any source actually carried."""
    return {
        passage.quote
        for case in channels.cases(run.outcome.state)
        for source in case.sources
        for passage in source.evidence
    }
