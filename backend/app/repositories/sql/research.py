"""The research store: claims, sources and evidence.

A dossier is written as one transaction. Half a dossier is worse than none — a
claim whose sources are missing reads as a claim nothing was found for, which is a
different and wrong answer — so the claim, its sources and their evidence go in
together or not at all.

Reading is by claim id or by verification id. Both come back as
:class:`app.domain.ClaimResearch`, rebuilt from the three tables and the JSON
columns, so a caller cannot tell whether the research it is holding was just
computed or loaded an hour later.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.session import get_session_factory
from app.domain import (
    ClaimResearch,
    Credibility,
    Dossier,
    Evidence,
    Source,
)
from app.models import ClaimRow, EvidenceRow, SourceRow
from app.repositories.sql import coding
from app.utils.clock import utcnow
from app.utils.ids import new_id


class SqlResearchRepository:
    """Stores dossiers in PostgreSQL and reads them back as domain objects."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None = None
    ) -> None:
        self._session_factory = session_factory

    @property
    def _factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory or get_session_factory()

    async def save_dossier(
        self, dossier: Dossier, *, verification_id: str | None = None
    ) -> tuple[str, ...]:
        """Persist every claim in ``dossier``, returning the new claim ids in order.

        The ids are returned rather than assigned into the dossier because a
        :class:`app.domain.Dossier` is frozen and has no id field — it is a result,
        not a record. A caller that needs to read one claim's research back keeps
        the id it was handed here.
        """
        async with self._factory() as session:
            rows = [
                _claim_row(research, position=position, verification_id=verification_id)
                for position, research in enumerate(dossier.claims)
            ]
            session.add_all(rows)
            await session.commit()
            return tuple(row.id for row in rows)

    async def get_research(self, claim_id: str) -> ClaimResearch | None:
        async with self._factory() as session:
            row = await session.get(ClaimRow, claim_id)
            return _to_domain(row) if row is not None else None

    async def research_for(self, verification_id: str) -> tuple[ClaimResearch, ...]:
        async with self._factory() as session:
            found = await session.execute(
                select(ClaimRow)
                .where(ClaimRow.verification_id == verification_id)
                .order_by(ClaimRow.position)
            )
            return tuple(_to_domain(row) for row in found.scalars())


# ------------------------------------------------- domain <-> row mapping ---


def _claim_row(
    research: ClaimResearch, *, position: int, verification_id: str | None
) -> ClaimRow:
    # Credibility is scored per registrable domain and arrives as a flat tuple on
    # the research rather than attached to the sources it describes. Joining it back
    # on domain here means a stored source carries its own assessment; otherwise
    # reading one source would mean reading the whole claim and re-matching.
    readings: dict[str, Any] = {
        assessment.domain: coding.plain(assessment)
        for assessment in research.credibility
    }
    return ClaimRow(
        id=new_id(),
        verification_id=verification_id,
        position=position,
        text=research.claim,
        queries=list(research.queries),
        fact_checks=coding.plain_all(research.fact_checks),
        researched_at=utcnow(),
        created_at=utcnow(),
        sources=[
            _source_row(source, credibility=readings.get(source.domain))
            for source in research.sources
        ],
    )


def _source_row(source: Source, *, credibility: dict[str, Any] | None) -> SourceRow:
    return SourceRow(
        id=new_id(),
        ref=source.ref,
        url=source.url,
        urls=list(source.urls),
        title=source.title,
        domain=source.domain,
        host=source.host,
        published_at=source.published_at,
        date_basis=source.date_basis,
        date_text=source.date_text,
        cluster=source.cluster,
        retrievals=coding.plain_all(source.retrievals),
        credibility=credibility,
        evidence=[
            _evidence_row(evidence, position=position)
            for position, evidence in enumerate(source.evidence)
        ],
    )


def _evidence_row(evidence: Evidence, *, position: int) -> EvidenceRow:
    return EvidenceRow(
        id=new_id(),
        position=position,
        quote=evidence.quote,
        provider=evidence.provider,
        start_offset=evidence.start,
        end_offset=evidence.end,
        score=evidence.score,
        matched_entities=list(evidence.matched_entities),
        matched_terms=list(evidence.matched_terms),
        matched_numbers=list(evidence.matched_numbers),
    )


def _to_domain(row: ClaimRow) -> ClaimResearch:
    # One reading per domain on the way out, not one per source. The write fans the
    # assessment out across every source that shares a domain, so reading them back
    # verbatim would hand a caller the same publisher's credibility several times
    # over — and `ClaimResearch.credibility` is a per-domain tuple.
    readings: dict[str, Credibility] = {}
    for source_row in row.sources:
        assessment = coding.load_credibility(source_row.credibility)
        if assessment is not None and assessment.domain not in readings:
            readings[assessment.domain] = assessment

    return ClaimResearch(
        claim=row.text,
        queries=tuple(str(query) for query in row.queries or ()),
        sources=tuple(_source(source_row) for source_row in row.sources),
        fact_checks=coding.load_fact_checks(row.fact_checks),
        credibility=tuple(readings.values()),
    )


def _source(row: SourceRow) -> Source:
    return Source(
        ref=row.ref,
        url=row.url,
        urls=tuple(str(url) for url in row.urls or ()),
        title=row.title,
        domain=row.domain,
        host=row.host,
        evidence=tuple(_evidence(evidence_row) for evidence_row in row.evidence),
        retrievals=coding.load_retrievals(row.retrievals),
        published_at=row.published_at,
        date_basis=row.date_basis,
        date_text=row.date_text,
        cluster=row.cluster,
    )


def _evidence(row: EvidenceRow) -> Evidence:
    return Evidence(
        quote=row.quote,
        provider=row.provider,
        start=row.start_offset,
        end=row.end_offset,
        score=row.score,
        matched_entities=tuple(str(term) for term in row.matched_entities or ()),
        matched_terms=tuple(str(term) for term in row.matched_terms or ()),
        matched_numbers=tuple(str(term) for term in row.matched_numbers or ()),
    )
