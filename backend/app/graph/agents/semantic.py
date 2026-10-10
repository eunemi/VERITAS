"""Read the meaning of retrieved passages; keyword overlap is not corroboration."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import VeritasError
from app.domain import Source
from app.graph.agents.judge import _nothing_to_check, _overall
from app.graph.state import AgentNote, Case, GraphState, cases
from app.graph.verdict import Bearing, ClaimRuling, Indication, Judgement
from app.llm.structured import ask


class Citation(BaseModel):
    ref: int = Field(strict=True)
    passage: int = Field(ge=0, strict=True)
    stance: Literal["supports", "refutes", "context"]


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
                ruling=_nothing_to_check(state),
                trace=(AgentNote("judge", "No claims to check"),),
            )
        semaphore = asyncio.Semaphore(3)

        async def read(case: Case) -> ClaimRuling:
            async with semaphore:
                return await self.rule(case, str(state.get("now", "")))

        rulings = tuple(await asyncio.gather(*(read(case) for case in found)))
        ruling = _overall(rulings)
        explanations = [
            f"Claim {item.ref}: {item.insufficiency or item.explanation}"
            for item in rulings[:3]
            if item.insufficiency or item.explanation
        ]
        ruling = replace(ruling, rationale=" ".join([ruling.rationale, *explanations]))
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
                confidence=0
                if ruling.judgement is Judgement.SUPPORTED
                else ruling.confidence,
                rationale=ruling.rationale
                + f" {len(capped)} further claim(s) were not researched. "
                "Submit them separately.",
            )
        return GraphState(
            ruling=ruling,
            trace=(
                AgentNote("judge", "Evidence-grounded semantic assessment completed"),
            ),
        )

    async def rule(self, case: Case, now: str) -> ClaimRuling:
        def unknown(reason: str) -> ClaimRuling:
            return ClaimRuling(
                ref=case.claim.ref,
                claim=case.claim.text,
                judgement=Judgement.UNCERTAIN,
                confidence=0,
                insufficiency=reason,
            )

        standing = {grade.ref: grade.standing or 0 for grade in case.grading}
        ranked = sorted(case.sources, key=lambda s: -standing.get(s.ref, 0))
        sources = {s.ref: s for s in ranked[:8]}
        if not sources:
            return unknown(
                "No live web sources were available for this claim; "
                "it could not be verified."
            )
        passages = {ref: _passages(source) for ref, source in sources.items()}
        try:
            result = await ask(
                self.settings,
                "Fact-check the exact claim using ONLY the supplied live search "
                "passages. Shared words or numbers do not establish truth. Check "
                "subject, date, place, quantities, negation, satire and whether a "
                "page merely repeats an allegation. Current claims need current "
                "evidence. Sources are search excerpts, not full articles. Do not "
                "use memory to fill evidence gaps. Cite source ref and the zero-based "
                "passage index of the provided evidence, with stance. "
                "Return UNCERTAIN for missing context, "
                "weak/irrelevant sources or insufficient coverage. Explain in the "
                "language of the original quote (Devanagari input requires Hindi). "
                "Do not put reference markers in the explanation; use citations. "
                "A decisive verdict needs at least "
                "two independent sources directly supporting that direction.",
                {
                    "checked_at": now,
                    "claim": case.claim.text,
                    "original_quote": case.claim.quote,
                    "sources": [
                        {
                            "ref": ref,
                            "url": s.url,
                            "title": s.title,
                            "published_at": str(s.published_at or "unknown"),
                            "passages": [
                                {"index": n, "text": text}
                                for n, text in enumerate(passages[ref])
                            ],
                        }
                        for ref, s in sources.items()
                    ],
                },
                Answer,
            )
        except VeritasError as exc:
            if exc.details and exc.details.get("status") == 429:
                return unknown(
                    "The evidence reader is rate-limited. Live sources are shown "
                    "below; retry shortly to complete the verdict."
                )
            if exc.details and exc.details.get("status") in (401, 403):
                return unknown(
                    "The verification model rejected its credentials. Live sources "
                    "were found, but a true/false assessment could not run. "
                    "Check the API key for the configured provider."
                )
            return unknown(
                "Live sources were retrieved, but the evidence reader was "
                f"unavailable ({exc.code}). Retry after checking model configuration."
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
        direction = "supports" if judgement is Judgement.SUPPORTED else "refutes"
        directional = [c for c in valid if c.stance == direction]
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
                "to settle this claim. " + result.explanation
            )
        if judgement is Judgement.MIXED and not {"supports", "refutes"}.issubset(
            {c.stance for c in valid}
        ):
            return unknown(
                "The cited evidence does not establish both sides "
                "of the reported disagreement."
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
            for c in valid
            if c.stance != "context"
        )
        return ClaimRuling(
            ref=case.claim.ref,
            claim=case.claim.text,
            judgement=judgement,
            confidence=min(result.confidence, 0.95)
            if judgement is not Judgement.UNCERTAIN
            else 0,
            indications=indications,
            insufficiency=result.explanation
            if judgement is Judgement.UNCERTAIN
            else "",
            support=sum(c.stance == "supports" for c in valid),
            refute=sum(c.stance == "refutes" for c in valid),
            explanation=result.explanation,
        )


def _passages(source: Source) -> list[str]:
    """Short, numbered, literal slices; quotation is never generated by a model."""
    excerpts: list[str] = []
    for snippet in dict.fromkeys(r.snippet for r in source.retrievals if r.snippet):
        start = 0
        while start < min(len(snippet), 1800) and len(excerpts) < 3:
            end = min(start + 600, len(snippet), 1800)
            if end < len(snippet):
                boundary = snippet.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            excerpts.append(snippet[start:end])
            start = end
    return excerpts
