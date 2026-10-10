"""Multilingual extraction, keeping every annotation tied to submitted words."""

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import LLMError
from app.domain import ExtractedClaim, Extraction, Keyword
from app.llm.structured import ask


class Claim(BaseModel):
    quote: str = Field(min_length=1)
    text: str = Field(min_length=1)
    checkable: bool
    reason: str = ""
    keywords: list[str] = Field(default_factory=list, max_length=4)


class Claims(BaseModel):
    claims: list[Claim] = Field(max_length=100)


async def extract(text: str, settings: Settings) -> Extraction:
    result = await ask(
        settings,
        "Extract assertions from the entire submission, including short "
        "headlines, Hindi and Hinglish. Keep each quote an EXACT contiguous "
        "substring in the original language. Write text as a self-contained "
        "searchable assertion (English translation is allowed). Preserve dates, "
        "numbers, negation and uncertainty. "
        "Provide up to four distinctive search keywords per claim. "
        "Mark opinions/questions as uncheckable and explain why. Never decide "
        "truth during extraction. Do not omit the remainder of a long submission: "
        "group it as a final uncheckable quote with reason 'input too long' "
        "if necessary.",
        {"text": text},
        Claims,
        tokens=6000,
    )
    claims: list[ExtractedClaim] = []
    for item in result.claims:
        start = text.find(item.quote)
        if start < 0:
            raise LLMError(
                "Claim extraction returned a quote absent from the submission.",
                provider="llm",
            )
        claims.append(
            ExtractedClaim(
                ref=len(claims) + 1,
                text=item.text,
                quote=item.quote,
                start=start,
                end=start + len(item.quote),
                checkable=item.checkable,
                reason=item.reason,
                keywords=tuple(Keyword(term=term, score=1) for term in item.keywords),
            )
        )
    return Extraction(
        claims=tuple(claims), entities=(), keywords=(), sentences=len(claims)
    )
