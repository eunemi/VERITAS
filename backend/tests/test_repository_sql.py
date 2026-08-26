"""The SQL stores, run against SQLite.

Not PostgreSQL, and that trade is worth stating. What these tests cover is the
half of a repository that is actually easy to get wrong and cheap to check: the
mapping. Whether a frozen dataclass survives a write and a read unchanged, whether
a transition touches the columns it claims to, whether the JSON codec in
:mod:`app.repositories.sql.coding` round-trips a report's interior. None of that is
dialect-specific, and requiring a running server to find out would mean nobody
found out.

What SQLite cannot tell us is left explicit rather than pretended away: ``JSONB``
degrades to ``JSON``, the enum ``CHECK`` constraints are the same by construction
but not exercised here, and foreign keys need turning on per connection (done in
:func:`_engine`, without which the CASCADE tests below would pass vacuously).

The whole module skips where ``aiosqlite`` is missing, the same way the Chroma runs
in ``test_vectorstore.py`` do. A machine without the driver is not a red suite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from importlib.util import find_spec

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# `import app.models` is what registers the tables on `Base.metadata`; without it
# `create_all` would build nothing and every test here would fail on a missing table.
import app.models  # noqa: F401
from app.core.errors import NotFoundError, ValidationError
from app.database.base import Base
from app.domain import (
    ADJUDICATOR,
    Annotation,
    Artifact,
    ArtifactKind,
    AudioDetail,
    Axis,
    ClaimResearch,
    Credibility,
    DateBasis,
    Desk,
    DeskReport,
    Determination,
    Direction,
    Dossier,
    Evidence,
    Exhibit,
    FactCheck,
    Failure,
    ImageDetail,
    LedgerEntry,
    Observation,
    PlateRegion,
    Reading,
    Relevance,
    Reliability,
    Retrieval,
    Review,
    ReviewedClaim,
    Role,
    Signal,
    Source,
    Stance,
    Status,
    TranscriptCue,
    User,
    Verdict,
    Verification,
)
from app.repositories.sql import (
    SqlResearchRepository,
    SqlUserRepository,
    SqlVerificationRepository,
)

#: aiosqlite has no degraded mode — with no driver there is no database to map
#: against, so the whole module has nothing to say. Declared as a module mark rather
#: than a ``pytest.importorskip`` call, which would put a statement above the imports
#: and make every one of them an E402.
pytestmark = pytest.mark.skipif(
    find_spec("aiosqlite") is None, reason="aiosqlite is not installed"
)


@pytest.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory over a fresh in-memory schema, torn down afterwards."""
    engine = _engine()
    async with engine.begin() as connection:
        # Foreign keys are per connection in SQLite, and ``StaticPool`` guarantees
        # there is only ever one — so this single statement is what makes the CASCADE
        # tests below meaningful rather than vacuously green.
        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


def _engine() -> AsyncEngine:
    """An engine on a private in-memory database.

    ``StaticPool`` keeps every session on the *same* connection — without it
    ``:memory:`` gives each checkout its own empty database and nothing written is
    ever found again.
    """
    return create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


# ------------------------------------------------------------- fixtures -----


def submission(content: str = "The bridge reopened on Tuesday.") -> Verification:
    return Verification.submitted(
        artifact=Artifact(kind=ArtifactKind.TEXT, content=content),
        desks=(Desk.TEXT,),
    )


def verdict(determination: Determination = Determination.SUPPORTED) -> Verdict:
    return Verdict(
        determination=determination,
        headline="Two independent records agree.",
        rationale="The transport authority and a wire report both give Tuesday.",
        confidence=0.86,
    )


def furnished_report(desk: Desk = Desk.TEXT) -> DeskReport:
    """A report with every optional container populated.

    Deliberately maximal. An empty report round-trips through almost any codec; the
    fields that break are the nested ones, and they only break when they are there.
    """
    return DeskReport(
        desk=desk,
        verdict=verdict(),
        ledger=(LedgerEntry(key="Sources examined", value="4"),),
        annotations=(
            Annotation(
                ref=1,
                quote="reopened on Tuesday",
                note="Matches the authority's notice.",
                determination=Determination.SUPPORTED,
            ),
        ),
        signals=(Signal(label="Independence", reading="2 of 4 owners", weight=0.4),),
        exhibits=(
            Exhibit(
                ref=1,
                source="transport.gov.example",
                published="2026-08-18",
                relevance=Relevance.HIGH,
                reliability=Reliability.VERIFIED,
                determination=Determination.SUPPORTED,
                extract="The crossing reopens Tuesday 18 August.",
            ),
        ),
    )


def research(claim: str = "The bridge reopened on Tuesday.") -> ClaimResearch:
    return ClaimResearch(
        claim=claim,
        queries=("bridge reopened Tuesday", "crossing reopen date"),
        sources=(
            Source(
                ref=1,
                url="https://transport.gov.example/notices/18",
                urls=("https://transport.gov.example/notices/18",),
                title="Crossing reopens Tuesday",
                domain="gov.example",
                host="transport.gov.example",
                evidence=(
                    Evidence(
                        quote="The crossing reopens Tuesday 18 August.",
                        provider="tavily",
                        start=140,
                        end=180,
                        score=0.91,
                        matched_entities=("Tuesday",),
                        matched_terms=("crossing", "reopen"),
                        matched_numbers=("18",),
                    ),
                ),
                retrievals=(
                    Retrieval(
                        provider="tavily",
                        query="bridge reopened Tuesday",
                        rank=1,
                        url="https://transport.gov.example/notices/18",
                        title="Crossing reopens Tuesday",
                        snippet="The crossing reopens Tuesday 18 August.",
                        score=0.77,
                        published_at=datetime(2026, 8, 15, 9, 0, tzinfo=UTC),
                        date_basis=DateBasis.PROVIDER,
                        date_text="15 August 2026",
                    ),
                ),
                published_at=datetime(2026, 8, 15, 9, 0, tzinfo=UTC),
                date_basis=DateBasis.PROVIDER,
                date_text="15 August 2026",
                cluster=0,
            ),
        ),
        fact_checks=(
            FactCheck(
                source="google",
                claim=ReviewedClaim(
                    text="The bridge reopened on Tuesday.",
                    reviews=(
                        Review(
                            publisher="Example Check",
                            site="check.example",
                            url="https://check.example/bridge",
                            rating="True",
                            title="Bridge reopening claim",
                            language="en",
                            reviewed_at=datetime(2026, 8, 19, tzinfo=UTC),
                            date_text="19 August 2026",
                            stance=Stance.TRUE,
                            stance_from="rating",
                        ),
                    ),
                    claimant="A local paper",
                    claimed_at=datetime(2026, 8, 18, tzinfo=UTC),
                    date_text="18 August 2026",
                ),
                match=0.82,
                matched_entities=("Tuesday",),
                matched_terms=("bridge", "reopened"),
                matched_numbers=(),
            ),
        ),
        credibility=(
            Credibility(
                ref=1,
                domain="gov.example",
                readings=(
                    Reading(
                        axis=Axis.OFFICIAL,
                        score=0.9,
                        observations=(
                            Observation(
                                axis=Axis.OFFICIAL,
                                finding="Government domain",
                                direction=Direction.RAISES,
                                detail="Operates the crossing it reports on.",
                                weight=0.6,
                            ),
                        ),
                    ),
                    Reading(axis=Axis.TRANSPARENCY, score=None),
                ),
                role=Role.OFFICIAL,
            ),
        ),
    )


def dossier(*claims: ClaimResearch) -> Dossier:
    return Dossier(
        claims=claims or (research(),),
        providers=(),
        retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    )


# -------------------------------------------------------- verifications -----


async def test_a_verification_round_trips_unchanged(factory) -> None:
    """The identity that makes the store swappable: what went in comes back equal."""
    store = SqlVerificationRepository(factory)
    record = submission()

    await store.create(record)

    assert await store.get(record.id) == record


async def test_an_unknown_id_reads_as_none(factory) -> None:
    """`None`, not a raise — turning absence into a 404 is the service's call, and
    the in-memory store answers the same way."""
    assert await SqlVerificationRepository(factory).get("nope") is None


async def test_the_full_transition_sequence(factory) -> None:
    store = SqlVerificationRepository(factory)
    record = submission()
    await store.create(record)

    await store.mark_running(record.id)
    await store.start_desk(record.id, Desk.TEXT)
    await store.add_report(record.id, furnished_report())
    await store.start_desk(record.id, ADJUDICATOR)
    await store.add_report(record.id, furnished_report(ADJUDICATOR))
    await store.complete(record.id)

    stored = await store.get(record.id)
    assert stored is not None
    assert stored.status is Status.COMPLETED
    assert len(stored.reports) == 2
    assert stored.verdict is not None
    assert stored.verdict.determination is Determination.SUPPORTED
    assert all(p.status is Status.COMPLETED for p in stored.desks)
    assert stored.completed_at is not None


async def test_a_report_s_interior_survives_the_json_columns(factory) -> None:
    """The codec's real test. Ledger, annotations, signals and exhibits are stored as
    documents, and a dataclass that comes back as a dict — or a tuple as a list —
    would compare unequal here and nowhere else."""
    store = SqlVerificationRepository(factory)
    record = submission()
    await store.create(record)
    filed = furnished_report()

    await store.add_report(record.id, filed)

    stored = await store.get(record.id)
    assert stored is not None
    assert stored.reports[0] == filed


@pytest.mark.parametrize(
    "detail",
    [
        ImageDetail(
            width=1200,
            height=800,
            text="REOPENS TUESDAY",
            regions=(PlateRegion(ref=1, x=0.1, y=0.2, w=0.3, h=0.1, label="banner"),),
        ),
        AudioDetail(
            duration=12.5,
            language="en",
            text="The crossing reopens Tuesday.",
            envelope=(0.1, 0.4, 0.2),
            spans=((0.0, 4.5), (4.5, 12.5)),
            cues=(TranscriptCue(ref=1, start=0.0, end=4.5, text="The crossing"),),
        ),
    ],
    ids=["image", "audio"],
)
async def test_either_detail_comes_back_as_its_own_type(factory, detail) -> None:
    """`ImageDetail | AudioDetail` is a union a JSON document cannot describe on its
    own, which is why `coding.DETAIL_TYPE` is written alongside it. Without the
    discriminator a decoder has to guess, and a wrong guess is a silently mistyped
    exhibit rather than an error."""
    store = SqlVerificationRepository(factory)
    record = submission()
    await store.create(record)

    filed = DeskReport(desk=Desk.TEXT, verdict=verdict(), detail=detail)
    await store.add_report(record.id, filed)

    stored = await store.get(record.id)
    assert stored is not None
    assert stored.reports[0].detail == detail
    assert type(stored.reports[0].detail) is type(detail)


async def test_failing_records_the_failure_and_blames_the_desk(factory) -> None:
    store = SqlVerificationRepository(factory)
    record = submission()
    await store.create(record)

    await store.fail(
        record.id, Failure(code="not_implemented", message="No desk.", desk=Desk.TEXT)
    )

    stored = await store.get(record.id)
    assert stored is not None
    assert stored.status is Status.FAILED
    assert stored.failure == Failure(
        code="not_implemented", message="No desk.", desk=Desk.TEXT
    )
    assert stored.desks[0].status is Status.FAILED


async def test_a_failure_keeps_the_reports_already_filed(factory) -> None:
    """They are the only record of how far the examination got before it stopped."""
    store = SqlVerificationRepository(factory)
    record = submission()
    await store.create(record)
    await store.add_report(record.id, furnished_report())

    await store.fail(record.id, Failure(code="internal_error", message="Boom."))

    stored = await store.get(record.id)
    assert stored is not None
    assert len(stored.reports) == 1


async def test_a_desk_not_on_the_roster_is_a_no_op(factory) -> None:
    """Matching the in-memory store. A failure recorded against the wrong desk should
    still record the failure rather than raise over the roster mismatch."""
    store = SqlVerificationRepository(factory)
    record = submission()
    await store.create(record)

    await store.start_desk(record.id, Desk.VIDEO)

    stored = await store.get(record.id)
    assert stored is not None
    assert all(p.status is Status.PENDING for p in stored.desks)


@pytest.mark.parametrize(
    "write",
    [
        lambda s: s.mark_running("nope"),
        lambda s: s.start_desk("nope", Desk.TEXT),
        lambda s: s.add_report("nope", furnished_report()),
        lambda s: s.complete("nope"),
        lambda s: s.fail("nope", Failure(code="internal_error", message="x")),
    ],
)
async def test_every_write_to_an_unknown_id_raises(factory, write) -> None:
    """Unlike a read. A write against a record that is not there is a bug in the
    caller, and silently succeeding would hide it."""
    with pytest.raises(NotFoundError):
        await write(SqlVerificationRepository(factory))


async def test_timestamps_come_back_aware(factory) -> None:
    """SQLite has no timestamp type and drops the offset, so a naive datetime here
    would compare unequal to every aware one beside it. `UTCDateTime` is what stops
    that, and this is the only place it shows."""
    store = SqlVerificationRepository(factory)
    record = submission()
    await store.create(record)

    stored = await store.get(record.id)
    assert stored is not None
    assert stored.created_at.tzinfo is not None
    assert stored.created_at == record.created_at


# ---------------------------------------------------------------- users -----


async def test_a_user_round_trips(factory) -> None:
    store = SqlUserRepository(factory)
    user = User.registered(email="Reporter@Example.COM", display_name="Reporter")

    await store.create(user)

    assert await store.get(user.id) == user


async def test_a_user_is_found_by_email_however_it_is_typed(factory) -> None:
    """Lookup normalises, because the address was normalised on the way in — and an
    account nobody can log into because they capitalised their own email is the
    failure this prevents."""
    store = SqlUserRepository(factory)
    user = User.registered(email="reporter@example.com")
    await store.create(user)

    assert await store.get_by_email("  REPORTER@Example.com ") == user


async def test_an_unknown_user_reads_as_none(factory) -> None:
    store = SqlUserRepository(factory)
    assert await store.get("nope") is None
    assert await store.get_by_email("nobody@example.com") is None


async def test_a_duplicate_email_is_a_validation_error(factory) -> None:
    """422, not 500: the request was well-formed, the address is simply taken."""
    store = SqlUserRepository(factory)
    await store.create(User.registered(email="reporter@example.com"))

    with pytest.raises(ValidationError):
        await store.create(User.registered(email="Reporter@example.com"))


async def test_deactivating_a_user_persists(factory) -> None:
    store = SqlUserRepository(factory)
    user = User.registered(email="reporter@example.com")
    await store.create(user)

    await store.update(user.deactivated())

    stored = await store.get(user.id)
    assert stored is not None
    assert stored.is_active is False


async def test_updating_an_unknown_user_raises(factory) -> None:
    store = SqlUserRepository(factory)
    with pytest.raises(NotFoundError):
        await store.update(User.registered(email="ghost@example.com"))


async def test_closing_an_account_keeps_its_verifications(factory) -> None:
    """SET NULL, not CASCADE. Closing an account must not delete the record of what
    it had examined — the examinations are not the account's to take with it."""
    from sqlalchemy import delete, select

    from app.models import UserRow, VerificationRow

    user = User.registered(email="reporter@example.com")
    await SqlUserRepository(factory).create(user)

    record = submission()
    async with factory() as session:
        session.add(
            VerificationRow(
                id=record.id,
                user_id=user.id,
                artifact_kind=ArtifactKind.TEXT,
                artifact_content="copy",
                status=Status.PENDING,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
        )
        await session.commit()

    async with factory() as session:
        await session.execute(delete(UserRow).where(UserRow.id == user.id))
        await session.commit()

    async with factory() as session:
        found = await session.execute(
            select(VerificationRow).where(VerificationRow.id == record.id)
        )
        orphan = found.scalar_one()
        assert orphan.user_id is None


# ------------------------------------------------------------- research -----


async def test_a_dossier_round_trips_claim_sources_and_evidence(factory) -> None:
    store = SqlResearchRepository(factory)
    original = research()

    (claim_id,) = await store.save_dossier(dossier(original))

    stored = await store.get_research(claim_id)
    assert stored == original


async def test_evidence_offsets_survive_the_column_rename(factory) -> None:
    """`start`/`end` on the domain object, `start_offset`/`end_offset` in the table,
    because END is reserved in PostgreSQL. A rename in one direction only is the
    kind of thing that reads fine and returns zeros."""
    store = SqlResearchRepository(factory)
    (claim_id,) = await store.save_dossier(dossier())

    stored = await store.get_research(claim_id)
    assert stored is not None
    quote = stored.sources[0].evidence[0]
    assert (quote.start, quote.end) == (140, 180)


async def test_credibility_comes_back_once_per_domain(factory) -> None:
    """The write fans one per-domain assessment across every source sharing that
    domain, so a verbatim read would hand back the same publisher's credibility
    several times over. `ClaimResearch.credibility` is per domain, not per source."""
    twin = research()
    second = Source(
        ref=2,
        url="https://transport.gov.example/notices/19",
        urls=("https://transport.gov.example/notices/19",),
        title="Reopening confirmed",
        domain="gov.example",
        host="transport.gov.example",
        evidence=(),
        retrievals=(),
    )
    doubled = ClaimResearch(
        claim=twin.claim,
        queries=twin.queries,
        sources=(*twin.sources, second),
        fact_checks=twin.fact_checks,
        credibility=twin.credibility,
    )

    store = SqlResearchRepository(factory)
    (claim_id,) = await store.save_dossier(dossier(doubled))

    stored = await store.get_research(claim_id)
    assert stored is not None
    assert len(stored.sources) == 2
    assert stored.credibility == twin.credibility


async def test_research_is_found_by_verification_in_claim_order(factory) -> None:
    store = SqlResearchRepository(factory)
    record = submission()
    async with factory() as session:
        from app.models import VerificationRow

        session.add(
            VerificationRow(
                id=record.id,
                artifact_kind=ArtifactKind.TEXT,
                artifact_content="copy",
                status=Status.PENDING,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
        )
        await session.commit()

    first, last = research("First claim."), research("Second claim.")
    await store.save_dossier(dossier(first, last), verification_id=record.id)

    found = await store.research_for(record.id)
    assert [r.claim for r in found] == ["First claim.", "Second claim."]


async def test_research_saved_without_a_verification_still_reads_back(factory) -> None:
    """`verification_id` is nullable: research runs on its own, and a dossier built by
    a script or a worker has no verification to hang off."""
    store = SqlResearchRepository(factory)

    (claim_id,) = await store.save_dossier(dossier())

    assert await store.get_research(claim_id) is not None


async def test_an_unknown_claim_reads_as_none(factory) -> None:
    assert await SqlResearchRepository(factory).get_research("nope") is None


async def test_research_for_an_unknown_verification_is_empty(factory) -> None:
    assert await SqlResearchRepository(factory).research_for("nope") == ()


async def test_deleting_a_verification_takes_its_research_with_it(factory) -> None:
    """CASCADE here, unlike the user link. Research is a product of the examination
    and means nothing without it — an orphaned claim row is not a record anyone can
    read, just a row nobody can reach."""
    from sqlalchemy import delete, func, select

    from app.models import ClaimRow, EvidenceRow, SourceRow, VerificationRow

    record = submission()
    async with factory() as session:
        session.add(
            VerificationRow(
                id=record.id,
                artifact_kind=ArtifactKind.TEXT,
                artifact_content="copy",
                status=Status.PENDING,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
        )
        await session.commit()

    store = SqlResearchRepository(factory)
    await store.save_dossier(dossier(), verification_id=record.id)

    async with factory() as session:
        await session.execute(
            delete(VerificationRow).where(VerificationRow.id == record.id)
        )
        await session.commit()

    async with factory() as session:
        for table in (ClaimRow, SourceRow, EvidenceRow):
            remaining = await session.execute(select(func.count()).select_from(table))
            assert remaining.scalar_one() == 0
