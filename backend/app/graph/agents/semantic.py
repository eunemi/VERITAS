"""Read the meaning of retrieved passages; keyword overlap is not corroboration."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import VeritasError
from app.domain import Source
from app.graph.rollup import (
    SETTLED_UNCERTAINTY,
    UNGROUNDED_UNCERTAINTY,
    nothing_to_check,
    overall,
)
from app.graph.state import AgentNote, Case, GraphState, cases
from app.graph.verdict import Bearing, ClaimRuling, Indication, Judgement
from app.llm.structured import ask


class Citation(BaseModel):
    ref: int = Field(strict=True)
    passage: int = Field(ge=0, strict=True)
    stance: Literal["supports", "refutes", "context"]
    same_event: bool = Field(
        description="True only if this passage concerns the same subject/event, "
        "place and time as the claim in its original context. Unrelated incidents "
        "with similar wording are false, even if they share a nationality or number.",
    )


class Answer(BaseModel):
    verdict: Literal["SUPPORTED", "REFUTED", "MIXED", "UNCERTAIN"]
    explanation: str = Field(min_length=1, max_length=3000)
    confidence: float = Field(ge=0, le=1)
    citations: list[Citation] = Field(max_length=12)


class SemanticJudge:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(self, state: GraphState) -> GraphState:
        found = cases(state)
        if not found:
            return GraphState(
                ruling=nothing_to_check(state),
                trace=(AgentNote("judge", "No claims to check"),),
            )
        semaphore = asyncio.Semaphore(2)

        async def read(case: Case) -> ClaimRuling:
            async with semaphore:
                artifact = state.get("artifact")
                return await self.rule(
                    case,
                    str(state.get("now", "")),
                    context=_context(artifact.content or "", case) if artifact else "",
                )

        rulings = tuple(await asyncio.gather(*(read(case) for case in found)))
        ruling = overall(rulings)
        explanations = [
            f"Claim {item.ref}: {item.insufficiency or item.explanation}"
            for item in rulings
            if item.insufficiency or item.explanation
        ]
        ruling = replace(
            ruling, rationale="\n\n".join([ruling.rationale, *explanations])
        )
        capped = [
            s
            for s in state.get("skipped", ())
            if "SEARCH_MAX_CLAIMS" in s.reason or "too long" in s.reason
        ]
        if capped:
            ruling = replace(
                ruling,
                judgement=Judgement.UNCERTAIN
                if ruling.judgement is Judgement.SUPPORTED
                else ruling.judgement,
                headline="Only part of the submission could be checked",
                confidence=SETTLED_UNCERTAINTY
                if ruling.judgement is Judgement.SUPPORTED
                else ruling.confidence,
                rationale=ruling.rationale
                + (
                    f"\n\n{len(capped)} further claim(s) were not researched. "
                    "Submit them separately."
                ),
            )
        return GraphState(
            ruling=ruling,
            trace=(
                AgentNote("judge", "Evidence-grounded semantic assessment completed"),
            ),
        )

    async def rule(self, case: Case, now: str, *, context: str = "") -> ClaimRuling:
        def unknown(reason: str) -> ClaimRuling:
            return ClaimRuling(
                ref=case.claim.ref,
                claim=case.claim.text,
                judgement=Judgement.UNCERTAIN,
                confidence=(
                    SETTLED_UNCERTAINTY
                    if case.sources
                    else UNGROUNDED_UNCERTAINTY
                ),
                insufficiency=reason,
            )

        standing = {grade.ref: grade.standing or 0 for grade in case.grading}
        ranked = sorted(case.sources, key=lambda s: -standing.get(s.ref, 0))
        sources = {s.ref: s for s in ranked if _passages(s)}
        sources = dict(list(sources.items())[:8])
        if not sources:
            return unknown(
                "No live web sources were available for this claim; "
                "it could not be verified."
            )
        passages = {ref: _passages(source) for ref, source in sources.items()}
        instruction = (
            "Fact-check the exact claim using ONLY the supplied live search "
            "passages. Shared words or numbers do not establish truth. Check "
            "subject, date, place, quantities, negation, satire and whether a "
            "page merely repeats an allegation. Use submission_context to "
            "resolve which event the claim refers to; it is NOT evidence. "
            "Explain in the language of the original quote (Devanagari input "
            "requires Hindi). "
            "Give a concise two-to-four sentence explanation of what is supported, "
            "what conflicts and what remains unknown. "
            "Do not verify a generic fragment using reports of different events. "
            "Deaths in different cities or attacks on different dates cannot "
            "corroborate each other. An explicitly different quantity for the "
            "same population, event and time can refute an exact-number claim; "
            "do not demand the false number appear verbatim. Return UNCERTAIN "
            "for missing context, weak/irrelevant sources or insufficient "
            "coverage. Confidence is confidence in the assessment, not the "
            "probability of truth. "
            "A decisive verdict needs at least "
            f"{self.settings.JUDGE_MIN_SOURCES} independent sources directly "
            "supporting that direction and referring to the same event."
        )

        def source_payload(passage_chars: int) -> list[dict[str, object]]:
            return [
                {
                    "ref": ref,
                    "url": source.url,
                    "title": source.title,
                    "published_at": str(source.published_at or "unknown"),
                    "passages": [
                        {"index": index, "text": text[:passage_chars]}
                        for index, text in enumerate(passages[ref][:2])
                    ],
                }
                for ref, source in sources.items()
            ]

        request = {
            "checked_at": now,
            "claim": case.claim.text,
            "original_quote": case.claim.quote[:250],
            "submission_context": (context or case.claim.quote)[:300],
            "sources": source_payload(350),
        }
        try:
            result = await ask(
                self.settings,
                instruction,
                request,
                Answer,
                tokens=self.settings.REASONING_MAX_TOKENS,
            )
        except VeritasError as exc:
            status = (exc.details or {}).get("status")
            if status == 429:
                # Bounded backoff retry for rate limits
                await asyncio.sleep(2.0)
                try:
                    result = await ask(
                        self.settings,
                        instruction,
                        {**request, "sources": source_payload(250)},
                        Answer,
                        tokens=self.settings.REASONING_MAX_TOKENS,
                    )
                except VeritasError as retry_error:
                    retry_status = (retry_error.details or {}).get("status")
                    if retry_status in (401, 403):
                        return unknown(
                            "The verification model rejected its credentials. Live "
                            "sources were found, but a true/false assessment could "
                            "not run. Check the API key for the configured provider."
                        )
                    if retry_status == 429:
                        return unknown(
                            "The evidence reader is rate-limited. Live sources are "
                            "shown below; retry shortly to complete the verdict."
                        )
                    return unknown(
                        "Live sources were retrieved, but the evidence reader was "
                        f"unavailable ({retry_error.code}). Retry after checking "
                        "model configuration."
                    )
            elif status in (401, 403):
                return unknown(
                    "The verification model rejected its credentials. Live sources "
                    "were found, but a true/false assessment could not run. "
                    "Check the API key for the configured provider."
                )
            else:
                return unknown(
                    "Live sources were retrieved, but the evidence reader was "
                    f"unavailable ({exc.code}). Retry after checking model "
                    "configuration."
                )

        # The model selects identifiers; the server supplies the verbatim quote.
        valid = [
            c
            for c in result.citations
            if c.ref in passages and c.passage < len(passages[c.ref])
        ]
        if len(valid) != len(result.citations):
            return unknown(
                "The model's citations could not be matched to the retrieved sources."
            )
        judgement = Judgement(result.verdict)
        relevant = [c for c in valid if c.same_event]

        if judgement is Judgement.MIXED and not {
            "supports",
            "refutes",
        }.issubset({c.stance for c in relevant}):
            return unknown(
                "The cited evidence does not establish both sides of the "
                "reported disagreement."
            )

        direction = "supports" if judgement is Judgement.SUPPORTED else "refutes"
        directional = [c for c in relevant if c.stance == direction]

        independent: list[Source] = []
        for citation in directional:
            source = sources[citation.ref]
            grade = case.credibility_of(source.ref)
            if (
                grade is not None
                and (grade.standing or 0) < self.settings.JUDGE_MIN_STANDING
            ):
                continue
            if any(
                s.domain == source.domain
                or (source.cluster is not None and s.cluster == source.cluster)
                for s in independent
            ):
                continue
            independent.append(source)

        if (
            judgement in (Judgement.SUPPORTED, Judgement.REFUTED)
            and len(independent) < self.settings.JUDGE_MIN_SOURCES
        ):
            return unknown(
                "Not enough independent, directly relevant cited sources "
                "refer to the same event to settle this claim. Reports about "
                "other incidents and repeated copies do not corroborate it."
            )

        indications = tuple(
            Indication(
                agent="semantic",
                bearing=Bearing.SUPPORTS if c.stance == "supports" else Bearing.REFUTES,
                weight=1,
                detail=f"{result.explanation} — {sources[c.ref].domain}",
                ref=c.ref,
                quote=passages[c.ref][c.passage],
            )
            for c in relevant
            if c.stance != "context"
        )
        return ClaimRuling(
            ref=case.claim.ref,
            claim=case.claim.text,
            judgement=judgement,
            confidence=(
                min(result.confidence, 0.95)
                if judgement is not Judgement.UNCERTAIN and relevant
                else (SETTLED_UNCERTAINTY if case.sources else UNGROUNDED_UNCERTAINTY)
            ),
            indications=indications,
            insufficiency=result.explanation
            if judgement is Judgement.UNCERTAIN
            else "",
            support=sum(c.stance == "supports" for c in relevant),
            refute=sum(c.stance == "refutes" for c in relevant),
            explanation=result.explanation,
        )


def _passages(source: Source) -> list[str]:
    """Short, numbered, literal slices; quotation is never generated by a model."""
    excerpts = list(dict.fromkeys(p.quote for p in source.evidence if p.quote))[:3]
    for snippet in dict.fromkeys(r.snippet for r in source.retrievals if r.snippet):
        start = 0
        while start < min(len(snippet), 1800) and len(excerpts) < 3:
            end = min(start + 600, len(snippet), 1800)
            if end < len(snippet):
                boundary = snippet.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            excerpt = snippet[start:end].strip()
            if excerpt and not any(excerpt in known for known in excerpts):
                excerpts.append(excerpt)
            start = end
    return excerpts


def _context(text: str, case: Case) -> str:
    """Bound context around the original quote, retaining the headline as an anchor."""
    if len(text) <= 6000:
        return text
    start = (
        text.find(case.claim.quote, max(0, case.claim.start))
        if case.claim.quote
        else -1
    )
    if start < 0 and case.claim.quote:
        start = text.find(case.claim.quote)
    if start < 0:
        start = case.claim.start
    start = max(0, start)
    return text[:1000] + "\n…\n" + text[max(0, start - 1500) : start + 3500]
