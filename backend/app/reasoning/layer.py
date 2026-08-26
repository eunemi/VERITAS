"""The final reading: a language model over a dossier this service already decided.

It runs after :class:`~app.graph.agents.judge.JudgeAgent`, and the order is the design.
The verdict, the score and the citations are produced by arithmetic over gathered
evidence; this layer explains that finding in prose and may sharpen the reading of a
dossier the score engine could only weigh mechanically. What it cannot do is add to
the record — see :mod:`app.reasoning.answer` for how that is enforced rather than
requested.

Two clamps are worth stating plainly, because both look like distrust of the model and
neither is:

* **A declined claim stays declined.** If the sufficiency gate found too little to
  rule on, a model returning ``TRUE`` is asserting something the brief does not
  contain. That is invention of a fact, not a difference of judgement, so it is
  refused like any other.
* **Disagreement is recorded, not resolved.** Where both ruled and they differ, the
  model's answer is published with :attr:`~app.reasoning.answer.Reasoning.disputed`
  naming the arithmetic's reading. Hiding either would misrepresent how settled the
  claim is.

Every failure ends the same way: the deterministic finding, restated, with
``grounded=False`` and the reason. A missing key, an unreachable Ollama, a timeout, a
truncated reply and a fabricated statistic all land there. :meth:`ReasoningLayer.
consider` does not raise, so this layer cannot make the pipeline worse than the
pipeline without it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from app.core.errors import VeritasError
from app.domain.credibility import Credibility
from app.domain.research import ClaimResearch
from app.graph.verdict import Assessment, ClaimRuling, Indication
from app.llm.base import LLMClient, Message
from app.reasoning.answer import Reasoning, Ungrounded, read
from app.reasoning.brief import MAX_EXHIBITS, Brief, assemble, render

__all__ = ["SYSTEM", "ReasoningLayer"]

#: Deterministic reasons carried into a fallback explanation.
MAX_REASONS = 3

#: The instructions. Written as a closed world rather than a request for care: the
#: model is told what it may name, and everything it names is checked against the
#: brief afterwards. The prompt exists to make a grounded answer the easy one to
#: give, not to be the thing that keeps an answer grounded.
SYSTEM = """\
You are the final reasoning step of a fact-checking pipeline. You are given one claim
and a numbered brief of the material that was retrieved for it.

The brief is everything you know about this claim. Whatever you may recall about the
subject is not evidence here and must not appear in your answer.

Rules:
- Cite passages by their [E...] ids. Refer to a source, fact check or conflict only by
  its [S...], [R...] or [C...] id, or by a domain that appears in the brief.
- Never name an outlet, publication, author, study or link that is not in the brief.
- Put words in quotation marks only if they appear, exactly, in a passage above.
- State no figure, date or statistic that is not in the brief.
- Weigh the sources: how many are independent of each other, whether they agree, how
  recent they are, and whether any conflict listed above undercuts the rest.
- If the brief does not settle the claim, answer UNCERTAIN. That is a correct answer,
  not a failure, and it is the right one whenever the evidence is thin or two-sided.

Reply with one JSON object and nothing else:

{"verdict": "TRUE" | "MOSTLY_TRUE" | "UNCERTAIN" | "MOSTLY_FALSE" | "FALSE",
 "confidence": integer from 0 to 100,
 "reasoning": "two to four sentences on what the evidence shows and why",
 "evidence": ["E1", "E2"]}

Any answer naming something outside the brief is discarded in full."""


class ReasoningLayer:
    """Reads one claim's dossier with a language model, or falls back to arithmetic."""

    def __init__(
        self,
        client: LLMClient,
        *,
        temperature: float = 0.0,
        max_tokens: int = 700,
        max_exhibits: int = MAX_EXHIBITS,
    ) -> None:
        self._client = client
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_exhibits = max_exhibits

    @property
    def provider(self) -> str:
        return self._client.name

    async def consider(
        self,
        *,
        ruling: ClaimRuling,
        research: ClaimResearch,
        conflicts: Sequence[Indication] = (),
        credibility: Sequence[Credibility] = (),
    ) -> Reasoning:
        """One claim's final reading. Never raises.

        ``credibility`` is separate from ``research`` because the graph carries the
        gradings in their own channel — see :attr:`app.graph.state.Case.grading` — and
        a caller holding a bare dossier has them on it instead.
        """
        brief = assemble(
            research.claim,
            research.sources,
            fact_checks=research.fact_checks,
            conflicts=conflicts,
            credibility=credibility or research.credibility,
            max_exhibits=self._max_exhibits,
        )
        if brief.empty:
            return _fallback(ruling, "no evidence was gathered to read")

        try:
            reply = await self._client.complete(
                [
                    Message(role="system", content=SYSTEM),
                    Message(role="user", content=render(brief)),
                ],
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except VeritasError as error:
            return _fallback(
                ruling, f"{self.provider} did not answer: {error}", brief=brief
            )

        try:
            answer = read(reply.text, brief, model=reply.model)
        except Ungrounded as error:
            return _fallback(ruling, str(error), brief=brief, model=reply.model)

        return _reconciled(answer, ruling, brief)

    async def aclose(self) -> None:
        await self._client.aclose()


def _reconciled(answer: Reasoning, ruling: ClaimRuling, brief: Brief) -> Reasoning:
    verdict, confidence, _ = _deterministic(ruling)

    # The gate is not a threshold the model may argue with. A claim it declined is one
    # nothing was established about, so any verdict beyond UNCERTAIN comes from
    # outside the brief by definition.
    if ruling.insufficiency and answer.verdict is not Assessment.UNCERTAIN:
        return _fallback(
            ruling,
            f"{answer.verdict.value} was returned for a claim there was too little "
            "evidence to rule on",
            brief=brief,
            model=answer.model,
        )

    if answer.verdict is verdict:
        return answer
    return replace(
        answer,
        disputed=f"the score engine read this as {verdict.value} at {confidence}",
    )


def _fallback(
    ruling: ClaimRuling, why: str, *, brief: Brief | None = None, model: str = ""
) -> Reasoning:
    """The deterministic finding, restated, with the refusal on the record.

    Carries the brief's passages as its evidence. They are what the score engine
    weighed, so a refused answer still publishes citations — a reader who is shown a
    verdict with none has no way to check it, and the fallback is the path most likely
    to be taken in production.
    """
    verdict, confidence, prose = _deterministic(ruling)
    return Reasoning(
        verdict=verdict,
        confidence=confidence,
        reasoning=prose,
        evidence=brief.exhibits if brief else (),
        model=model,
        grounded=False,
        rejected=why,
    )


def _deterministic(ruling: ClaimRuling) -> tuple[Assessment, int, str]:
    """The judge's finding as a verdict, a 0-100 confidence and a sentence."""
    score = ruling.score
    verdict = score.assessment if score else Assessment.UNCERTAIN
    confidence = score.value if score else round(ruling.confidence * 100)
    if ruling.insufficiency:
        return verdict, confidence, ruling.insufficiency

    reasons = [
        indication.detail for indication in ruling.indications if indication.detail
    ]
    prose = "; ".join(reasons[:MAX_REASONS])
    return verdict, confidence, prose or f"the evidence reads as {verdict.value}"
