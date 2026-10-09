"""The grounding gate, which is the whole reason this package exists.

Most of this file is refusals. A model that answers the brief is easy to check and
gets a handful of tests; the many ways a model can answer *past* the brief each get
their own, because each is a separate hole and closing three of four is not a defence.

The doubles below return whatever a test asks for, including replies no real model
would produce. That is the point. The question here is not "what does GPT usually do"
— it is "what happens when a model asserts something the dossier does not contain",
and the only way to ask it is to have a model do exactly that.

No fixtures, and the dossiers come from :mod:`tests.graph_bench`, so these run against
the same material the judge's tests use.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace

import pytest

from app.core.errors import LLMError, ProviderTimeoutError
from app.domain import ClaimResearch, FactCheck, Source
from app.graph.verdict import Assessment, Bearing, ClaimRuling, Indication, Judgement
from app.graph.verdict import Score as Arithmetic
from app.llm.base import Completion, Message
from app.reasoning import (
    Brief,
    Reasoning,
    ReasoningLayer,
    Ungrounded,
    assemble,
    read,
    render,
)
from app.reasoning.answer import MIN_QUOTED_CHARS, SMALL_INTEGER
from tests.graph_bench import CLAIM, MATCHING, RIVAL, graded, rated, reported

# ------------------------------------------------------------------ doubles ----


class Says:
    """An :class:`~app.llm.base.LLMClient` that returns one prepared reply."""

    name = "says"

    def __init__(self, text: str, *, model: str = "test-1") -> None:
        self.text = text
        self.model = model
        self.seen: list[Message] = []

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        self.seen = list(messages)
        return Completion(text=self.text, model=self.model)

    async def aclose(self) -> None:
        return None


class Fails:
    """A client that cannot answer, which is a routine production state."""

    name = "fails"

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        raise self.error

    async def aclose(self) -> None:
        return None


# ----------------------------------------------------------------- builders ----

SOURCES: tuple[Source, ...] = (
    reported("https://reuters.com/a", ref=1),
    reported("https://bbc.co.uk/b", ref=2),
)


def answered(**fields: object) -> str:
    """A model reply as JSON. The defaults are a well-formed grounded answer."""
    body: dict[str, object] = {
        "verdict": "TRUE",
        "confidence": 80,
        "reasoning": "Two independent sources report the same figure.",
        "evidence": ["E1"],
    }
    body.update(fields)
    return json.dumps(body)


def dossier(
    *,
    conflicts: tuple[Indication, ...] = (),
    fact_checks: Sequence[FactCheck] = (),
    max_exhibits: int = 12,
) -> Brief:
    """A two-source brief, both sources carrying the claim's figure."""
    return assemble(
        CLAIM,
        SOURCES,
        fact_checks=fact_checks,
        conflicts=conflicts,
        credibility=graded(SOURCES),
        max_exhibits=max_exhibits,
    )


def researched(sources: tuple[Source, ...] = SOURCES) -> ClaimResearch:
    return ClaimResearch(
        claim=CLAIM,
        queries=("central bank policy rate february 2026",),
        sources=sources,
        credibility=graded(sources),
    )


def ruled(
    verdict: Assessment = Assessment.TRUE,
    *,
    value: int = 72,
    insufficiency: str = "",
) -> ClaimRuling:
    """The judge's finding, for the layer to reconcile against or fall back to."""
    return ClaimRuling(
        ref=1,
        claim=CLAIM,
        judgement=Judgement.UNCERTAIN if insufficiency else Judgement.SUPPORTED,
        confidence=value / 100,
        indications=(
            Indication(
                agent="evidence",
                bearing=Bearing.SUPPORTS,
                weight=0.8,
                detail="two sources repeat the claim's figure",
            ),
        ),
        insufficiency=insufficiency,
        score=Arithmetic(value=value, assessment=verdict, insufficiency=insufficiency),
    )


async def considered(reply: str, ruling: ClaimRuling | None = None) -> Reasoning:
    """Run the layer over the standard dossier with ``reply`` as the model's answer."""
    layer = ReasoningLayer(Says(reply))
    return await layer.consider(ruling=ruling or ruled(), research=researched())


# ---------------------------------------------------------------- the brief ----


def test_the_brief_shows_what_the_dossier_holds_and_nothing_else() -> None:
    rendered = render(dossier())

    assert CLAIM in rendered
    assert "reuters.com" in rendered
    assert "bbc.co.uk" in rendered
    # The passage is the provider's text, character for character.
    assert MATCHING in rendered


def test_the_grading_reaches_the_model() -> None:
    """Standing is the source agent's reading, and weighing sources needs it."""
    assert "standing " in render(dossier())


def test_every_passage_carries_an_id_an_answer_can_name() -> None:
    brief = dossier()

    assert [exhibit.id for exhibit in brief.exhibits] == ["E1", "E2"]
    assert brief.ids == {"S1", "S2", "E1", "E2"}
    assert brief.exhibit("E1") is not None
    assert brief.exhibit("E9") is None


def test_one_prolific_source_does_not_fill_the_brief() -> None:
    """Breadth before depth, because corroboration is what is being weighed.

    A page with four quotable sentences would otherwise crowd out the second source,
    and a brief holding one outlet cannot show a model that two of them agree.
    """
    loud = replace(SOURCES[0], evidence=SOURCES[0].evidence * 4)

    brief = assemble(CLAIM, (loud, SOURCES[1]), max_exhibits=2)

    assert {exhibit.ref for exhibit in brief.exhibits} == {1, 2}


def test_a_source_held_back_by_the_ceiling_is_not_citable() -> None:
    """The id set is what was shown, not what was gathered.

    A domain in the dossier but absent from the brief must not pass the outlet check:
    a model naming it has guessed, and a guess that happens to be right is still a
    citation of something it was never given.
    """
    brief = assemble(CLAIM, SOURCES, max_exhibits=1)

    assert brief.domains == frozenset({"reuters.com"})
    assert "S2" not in brief.ids


def test_a_review_with_no_agreed_reading_is_shown_as_uncounted() -> None:
    """Or a model reads a review this service did not count as one that it did."""
    brief = dossier(fact_checks=rated("Mostly False", "Accurate"))

    assert brief.reviews
    assert "not counted" in brief.reviews[0]
    assert "PUBLISHED FACT CHECKS" in render(brief)


def test_a_conflict_reaches_the_model_with_its_weight() -> None:
    conflict = Indication(
        agent="contradiction",
        bearing=Bearing.REFUTES,
        weight=0.8,
        detail="one source reports a different figure",
    )

    brief = dossier(conflicts=(conflict,))

    assert brief.conflicts == (
        "[C1] one source reports a different figure — counts against the claim "
        "at weight 0.80",
    )


# -------------------------------------------------------- a grounded answer ----


def test_a_grounded_answer_is_read_as_given() -> None:
    answer = read(answered(evidence=["E1", "E2"]), dossier(), model="test-1")

    assert answer.verdict is Assessment.TRUE
    assert answer.confidence == 80
    assert answer.citations == ("E1", "E2")
    assert answer.grounded is True
    assert answer.rejected == ""
    assert answer.model == "test-1"


def test_what_is_published_beside_a_verdict_comes_from_the_dossier() -> None:
    """The lookup that makes a fabricated quotation impossible rather than unlikely.

    The model returns ids. The quote, the url, the domain and the date are all read
    off the brief, so no string the model wrote reaches a reader as a passage
    attributed to a source.
    """
    answer = read(answered(evidence=["E1"]), dossier())

    assert answer.evidence[0].quote == MATCHING
    assert answer.evidence[0].domain == "reuters.com"
    assert answer.evidence[0].url == "https://reuters.com/a"


def test_wrapping_around_the_object_is_tolerated() -> None:
    """A formatting habit is not a claim about the world.

    Being strict here would spend a fallback on something that is not a grounding
    failure, and the fields inside are checked with no leniency at all.
    """
    brief = dossier()

    assert read(f"```json\n{answered()}\n```", brief).verdict is Assessment.TRUE
    assert read(f"Here is my answer:\n{answered()}", brief).verdict is Assessment.TRUE


def test_an_id_is_read_without_case_or_brackets() -> None:
    assert read(answered(evidence=["[e1]"]), dossier()).citations == ("E1",)


def test_a_verdict_written_with_a_space_is_still_one_of_the_five() -> None:
    answer = read(answered(verdict="Mostly True"), dossier())

    assert answer.verdict is Assessment.MOSTLY_TRUE


def test_naming_a_source_the_brief_carries_is_allowed() -> None:
    answer = read(
        answered(reasoning="reuters.com and bbc.co.uk agree, as [S1] and [S2] show."),
        dossier(),
    )

    assert "reuters.com" in answer.reasoning


# --------------------------------------------------------- invented sources ----


def test_an_unknown_evidence_id_is_refused() -> None:
    with pytest.raises(Ungrounded, match="not in the brief"):
        read(answered(evidence=["E9"]), dossier())


def test_an_outlet_that_is_not_a_source_is_refused() -> None:
    """The check that stops "according to Reuters" beside a dossier without it."""
    with pytest.raises(Ungrounded, match="nytimes.com"):
        read(answered(reasoning="nytimes.com reported the same decision."), dossier())


def test_a_link_to_somewhere_the_dossier_never_went_is_refused() -> None:
    with pytest.raises(Ungrounded, match="example.org"):
        read(
            answered(reasoning="See https://example.org/rates for the schedule."),
            dossier(),
        )


def test_an_id_the_brief_never_issued_is_refused() -> None:
    with pytest.raises(Ungrounded, match="S7"):
        read(answered(reasoning="[S7] corroborates the figure."), dossier())


def test_an_abbreviation_is_not_read_as_an_outlet() -> None:
    """``etc.so`` matches any cheap hostname pattern, and a model writes it.

    The stoplist is short on purpose — anything not on it fails closed, which costs a
    fallback rather than a reader.
    """
    answer = read(
        answered(reasoning="The rate, the date, the direction, etc.so it holds."),
        dossier(),
    )

    assert answer.grounded is True


def test_a_sentence_run_together_is_not_read_as_an_outlet() -> None:
    """Hostnames are matched lowercase only, which is what makes this safe."""
    answer = read(
        answered(reasoning="Both sources agree.The second confirms the first."),
        dossier(),
    )

    assert answer.grounded is True


# ----------------------------------------------------------- invented facts ----


def test_a_quotation_that_is_in_no_passage_is_refused() -> None:
    """A paraphrase inside quotation marks attributes words nobody wrote."""
    invented = "the committee voted unanimously to leave rates untouched"

    with pytest.raises(Ungrounded, match="quotes words"):
        read(answered(reasoning=f'The report says "{invented}".'), dossier())


def test_a_quotation_lifted_from_a_passage_is_allowed() -> None:
    quoted = MATCHING[:60]
    assert len(quoted) > MIN_QUOTED_CHARS

    answer = read(answered(reasoning=f'One source says "{quoted}".'), dossier())

    assert answer.grounded is True


def test_a_short_quoted_phrase_is_not_treated_as_an_attribution() -> None:
    """Below the floor a quotation is as likely to be emphasis as attribution."""
    answer = read(answered(reasoning='Both describe a "hold".'), dossier())

    assert answer.grounded is True


def test_an_invented_statistic_is_refused() -> None:
    """The failure a reader is least able to catch, and so the most damaging.

    A fabricated percentage reads exactly like a real one, and it is the thing a
    reader carries away and repeats.
    """
    with pytest.raises(Ungrounded, match="5.25%"):
        read(
            answered(reasoning="The rate is 5.25% after the February meeting."),
            dossier(),
        )


def test_a_figure_from_a_passage_is_allowed() -> None:
    answer = read(answered(reasoning="Both give 4.75% for February."), dossier())

    assert answer.grounded is True


def test_counting_the_brief_is_allowed() -> None:
    """A model legitimately counts what it was shown, and its confidence is a number.

    Bare integers up to :data:`~app.reasoning.answer.SMALL_INTEGER` are exempt for
    that reason. Percentages and decimals never are, whatever their size.
    """
    assert SMALL_INTEGER == 100

    answer = read(answered(reasoning="2 of the 2 agree, so 85 is fair."), dossier())

    assert answer.grounded is True


def test_a_large_invented_number_is_refused_without_a_percent_sign() -> None:
    with pytest.raises(Ungrounded, match="4200"):
        read(answered(reasoning="Some 4200 economists were surveyed."), dossier())


# -------------------------------------------------------- malformed answers ----


def test_a_reply_with_no_json_is_refused() -> None:
    with pytest.raises(Ungrounded, match="no JSON object"):
        read("I think the claim is true.", dossier())


def test_a_truncated_reply_is_refused() -> None:
    """What a token ceiling produces, and it must not parse as far as it got.

    Refused as "no JSON object" rather than as bad JSON: the closing brace is what
    the scan looks for, and a reply cut off before it never becomes a document.
    """
    with pytest.raises(Ungrounded, match="no JSON object"):
        read('{"verdict": "TRUE", "confidence": 80, "reasoning": "Both', dossier())


def test_an_object_that_is_not_json_is_refused() -> None:
    """Python-shaped output — a habit of smaller models, and not JSON."""
    with pytest.raises(Ungrounded, match="not valid JSON"):
        read("{'verdict': 'TRUE', 'confidence': 80,}", dossier())


def test_an_answer_that_is_not_an_object_is_refused() -> None:
    """A well-formed reply of the wrong shape, named as such rather than as garbage."""
    with pytest.raises(Ungrounded, match="list, not an object"):
        read('["TRUE", 80]', dossier())


def test_an_object_wrapped_in_an_array_is_still_read() -> None:
    """Wrapping is a formatting habit, and the fields inside are checked either way."""
    answer = read(f"[{answered()}]", dossier())

    assert answer.verdict is Assessment.TRUE


def test_a_missing_field_is_refused() -> None:
    with pytest.raises(Ungrounded, match="evidence"):
        read(
            json.dumps({"verdict": "TRUE", "confidence": 80, "reasoning": "Yes."}),
            dossier(),
        )


def test_a_verdict_outside_the_five_is_refused() -> None:
    with pytest.raises(Ungrounded, match="LIKELY_TRUE"):
        read(answered(verdict="LIKELY_TRUE"), dossier())


def test_an_empty_reasoning_is_refused() -> None:
    with pytest.raises(Ungrounded, match="empty"):
        read(answered(reasoning="   "), dossier())


def test_a_ruling_with_no_citation_is_refused() -> None:
    """A verdict is a claim about evidence, so asserting one without any is not one."""
    with pytest.raises(Ungrounded, match="without citing"):
        read(answered(evidence=[]), dossier())


def test_declining_without_citing_anything_is_allowed() -> None:
    """UNCERTAIN is the one answer that needs nothing behind it."""
    answer = read(
        answered(verdict="UNCERTAIN", evidence=[], reasoning="The sources are thin."),
        dossier(),
    )

    assert answer.verdict is Assessment.UNCERTAIN
    assert answer.citations == ()


# --------------------------------------------------------------- confidence ----


def test_a_proportion_is_read_as_one() -> None:
    """Models answer this field both ways whatever the prompt says.

    ``0.8`` taken literally would publish near-total uncertainty as a considered
    view — a misreading in the direction of confidence, which is the one that
    misleads a reader.
    """
    assert read(answered(confidence=0.8), dossier()).confidence == 80


def test_confidence_is_capped_at_the_score_engine_ceiling() -> None:
    """One ceiling for both paths, or a model's number would outrank arithmetic."""
    assert read(answered(confidence=100), dossier()).confidence == 90


def test_a_confidence_outside_the_range_is_refused() -> None:
    with pytest.raises(Ungrounded, match="outside"):
        read(answered(confidence=140), dossier())


def test_a_confidence_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(Ungrounded, match="not a number"):
        read(answered(confidence="high"), dossier())


def test_a_refusal_must_carry_its_reason() -> None:
    """The flag and the reason move together, so neither can be read alone."""
    with pytest.raises(ValueError, match="refusal"):
        Reasoning(
            verdict=Assessment.TRUE, confidence=80, reasoning="Yes.", grounded=False
        )

    with pytest.raises(ValueError, match="refusal"):
        Reasoning(
            verdict=Assessment.TRUE, confidence=80, reasoning="Yes.", rejected="why"
        )


# ---------------------------------------------------------------- the layer ----


async def test_the_layer_publishes_a_grounded_answer() -> None:
    answer = await considered(answered(evidence=["E1", "E2"]))

    assert answer.grounded is True
    assert answer.verdict is Assessment.TRUE
    assert answer.citations == ("E1", "E2")


async def test_a_refused_answer_falls_back_to_the_arithmetic() -> None:
    """The property that makes this layer safe to deploy at all.

    Whatever the model does, what is published is either grounded in the brief or the
    score engine's own finding, and the two are told apart by a flag rather than by a
    reader's inference.
    """
    answer = await considered(answered(reasoning="nytimes.com agrees."))

    assert answer.grounded is False
    assert answer.verdict is Assessment.TRUE
    assert answer.confidence == 72
    assert "nytimes.com" in answer.rejected
    assert "two sources repeat the claim's figure" in answer.reasoning


async def test_a_fallback_still_carries_citations() -> None:
    """A verdict a reader cannot check is worse than prose a reader cannot read."""
    answer = await considered("not json at all")

    assert answer.grounded is False
    assert answer.citations == ("E1", "E2")


async def test_a_provider_failure_is_a_fallback_and_not_an_exception() -> None:
    """A timeout, a refused key and an unreachable Ollama all arrive here."""
    for error in (
        ProviderTimeoutError("timed out", provider="says"),
        LLMError("bad gateway", provider="says"),
    ):
        layer = ReasoningLayer(Fails(error))

        answer = await layer.consider(ruling=ruled(), research=researched())

        assert answer.grounded is False
        assert "did not answer" in answer.rejected
        assert answer.verdict is Assessment.TRUE


async def test_a_declined_claim_cannot_be_ruled_on_by_the_model() -> None:
    """Asserting a verdict where nothing was established invents the finding itself.

    The sufficiency gate is not a threshold to argue with — it is the statement that
    the brief does not settle the claim — so a model returning a verdict anyway is
    refused for the same reason a fabricated quotation is.
    """
    declined = ruled(Assessment.UNCERTAIN, value=25, insufficiency="only one source")

    answer = await considered(answered(verdict="TRUE"), declined)

    assert answer.grounded is False
    assert answer.verdict is Assessment.UNCERTAIN
    assert "too little evidence" in answer.rejected
    assert answer.reasoning == "only one source"


async def test_the_model_may_always_decline() -> None:
    """Declining is never invention, so it is never refused."""
    answer = await considered(
        answered(verdict="UNCERTAIN", evidence=[], reasoning="The sources are thin.")
    )

    assert answer.grounded is True
    assert answer.verdict is Assessment.UNCERTAIN


async def test_disagreement_is_recorded_rather_than_resolved() -> None:
    """Both readings reach the caller. A reader shown one has been told less."""
    answer = await considered(answered(verdict="MOSTLY_TRUE", evidence=["E1"]))

    assert answer.grounded is True
    assert answer.verdict is Assessment.MOSTLY_TRUE
    assert answer.disputed == "the score engine read this as TRUE at 72"


async def test_agreement_is_left_unremarked() -> None:
    answer = await considered(answered(evidence=["E1"]))

    assert answer.disputed == ""


async def test_an_empty_dossier_is_never_sent_to_a_model() -> None:
    """Nothing to read, nothing to pay for, and nothing a model could ground on."""
    client = Says(answered())
    layer = ReasoningLayer(client)

    answer = await layer.consider(
        ruling=ruled(Assessment.UNCERTAIN, value=25, insufficiency="nothing was found"),
        research=ClaimResearch(claim=CLAIM, queries=(), sources=()),
    )

    assert client.seen == []
    assert answer.grounded is False
    assert answer.rejected == "no evidence was gathered to read"
    assert answer.reasoning == "nothing was found"


async def test_the_prompt_asks_for_what_the_gate_accepts() -> None:
    """The prompt is not the defence, but it must not ask for a rejected shape."""
    client = Says(answered())
    layer = ReasoningLayer(client)

    await layer.consider(ruling=ruled(), research=researched())

    system = client.seen[0].content
    for field in ("verdict", "confidence", "reasoning", "evidence"):
        assert field in system
    assert "UNCERTAIN" in system
    assert client.seen[1].content.startswith("CLAIM:")


async def test_a_rival_figure_reaches_the_model_as_a_conflict() -> None:
    """A recorded conflict is material to read, not a reason to skip the reading."""
    conflict = Indication(
        agent="contradiction",
        bearing=Bearing.REFUTES,
        weight=0.8,
        detail=f"a source reports {RIVAL[:44]}",
    )
    client = Says(
        answered(verdict="UNCERTAIN", evidence=[], reasoning="Two figures are given.")
    )
    layer = ReasoningLayer(client)

    answer = await layer.consider(
        ruling=ruled(), research=researched(), conflicts=(conflict,)
    )

    assert "RECORDED CONFLICTS" in client.seen[1].content
    assert answer.grounded is True
