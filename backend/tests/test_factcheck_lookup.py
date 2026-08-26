"""Fact-check lookup: isolation between claims, and outcomes that cannot lie.

Everything here turns on one asymmetry. An empty ``sources`` list says the web is quiet
about a claim; an empty ``fact_checks`` list says *no fact-checker has ruled on it* — a
statement about the world whose natural reading is that the claim is unexamined, and an
inviting thing for a reader to treat as licence. So the tests below are almost all about
making an expired key, a spent quota and a genuinely unreviewed claim produce three
distinguishable answers, when the naive implementation of each is the same empty tuple.

Two rules do that work and each has tests here:

**A failure costs that claim's records and nothing else.** One rate-limited lookup must
not cancel the other nine, and the outcome must not then report the provider as having
failed on claims it was cancelled out of.

**``SEARCHED`` with zero records and ``FAILED`` are never the same value.** The records
are the same; the outcome is the entire difference, which is why
:class:`~app.factcheck.lookup.Checked` carries both.

The fake is registered over the real database through the registry, and
:func:`tests.factcheck_bench.bench` puts the real factory back afterwards — the registry
in :mod:`app.factcheck` is a module-level singleton, so a fake left behind would make a
later test pass for a reason the deployment does not share.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.core.errors import ConfigurationError, FactCheckError
from app.domain import ProviderStatus
from app.factcheck.lookup import check
from tests.factcheck_bench import Fake, bench, record

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

KEY = "fc-secret-key-value"

CLAIMS = [
    "The Bank of England held its benchmark rate at 4.75% in March 2026.",
    "Unemployment fell to 3.8% last quarter.",
]


def configured(**overrides: object) -> Settings:
    """Settings with a key, so the lookup is not skipped before it starts."""
    return Settings(_env_file=None, GOOGLE_FACT_CHECK_API_KEY=KEY, **overrides)


# ---------------------------------------------------- nothing was looked up ----


async def test_a_missing_key_is_skipped_with_a_reason() -> None:
    """The common case, and it must be legible rather than mysterious.

    No fake: the real factory runs and raises because no key is set. A deployment can
    have complete web research and no fact-check coverage at all — the key is free but
    separate — so this is a first-class outcome and not an edge.
    """
    result = await check(CLAIMS, settings=Settings(_env_file=None), now=NOW)

    assert len(result.outcomes) == 1
    assert result.outcomes[0].status is ProviderStatus.SKIPPED
    assert result.outcomes[0].code == ConfigurationError.code
    assert "GOOGLE_FACT_CHECK_API_KEY" in result.outcomes[0].detail
    # Aligned with the claims even though nothing ran, so a caller can index safely.
    assert result.found == ((), ())


async def test_a_database_that_cannot_be_built_fails_rather_than_skipping() -> None:
    """A rejected setting is not the same as an absent key.

    Recorded rather than raised: the dossier's web research is unaffected, and a
    dossier with no fact checks beats a 500 with neither. But it is ``FAILED``,
    because something is broken and a deployment reading ``SKIPPED`` would go looking
    for a key it has.
    """
    with bench(FactCheckError("google rejected the settings", provider="google")):
        result = await check(CLAIMS, settings=configured(), now=NOW)

    assert result.outcomes[0].status is ProviderStatus.FAILED
    assert result.outcomes[0].code == "fact_check_error"
    assert result.found == ((), ())


async def test_no_claims_is_skipped_and_the_client_is_still_closed() -> None:
    """No request was made, so ``SEARCHED`` would be a claim about an index nobody
    asked anything of. ``found`` is empty rather than a tuple of empties — there are no
    claims to align with.
    """
    fake = Fake()

    with bench(fake):
        result = await check([], settings=configured(), now=NOW)

    assert result.found == ()
    assert result.outcomes[0].status is ProviderStatus.SKIPPED
    assert result.outcomes[0].code == "no_claims"
    assert fake.queries == []
    # `_open` may have built a pool before anyone noticed there was nothing to ask.
    assert fake.closed


# --------------------------------------------------------------- isolation ----


async def test_one_failed_claim_does_not_cancel_the_others() -> None:
    """The central promise, and the reason ``return_exceptions=True`` is load-bearing.

    Without it the first failure cancels every in-flight lookup, so one rate-limited
    claim empties the whole fact-check section — and the outcome then reports the
    provider as having failed on claims it was cancelled out of, which is a false
    statement about what was looked up.
    """
    fake = Fake(
        found={CLAIMS[1]: [record(CLAIMS[1])]},
        error=FactCheckError("429 from google", provider="google"),
        fails=(CLAIMS[0],),
    )

    with bench(fake):
        result = await check(CLAIMS, settings=configured(), now=NOW)

    assert result.found[0] == ()
    assert [r.text for r in result.found[1]] == [CLAIMS[1]]
    outcome = result.outcomes[0]
    assert outcome.status is ProviderStatus.PARTIAL
    assert outcome.results == 1
    assert outcome.code == "fact_check_error"
    # The shortfall is stated, because an answer thinned by a rate limit is otherwise
    # undetectable by a reader.
    assert "1 of 2" in outcome.detail


async def test_every_claim_failing_is_reported_as_failed() -> None:
    """Zero records and a dead provider. The records alone cannot say which."""
    fake = Fake(error=FactCheckError("google is down", provider="google"))

    with bench(fake):
        result = await check(CLAIMS, settings=configured(), now=NOW)

    assert result.found == ((), ())
    assert result.outcomes[0].status is ProviderStatus.FAILED
    assert result.outcomes[0].results == 0


async def test_a_stray_error_is_still_labelled_as_a_fact_check_failure() -> None:
    """An exception that is not a :class:`~app.core.errors.VeritasError` still arrives
    labelled as the kind of thing that went wrong, rather than as an unclassified
    provider error a client cannot branch on.
    """
    with bench(Fake(error=RuntimeError("bad json"))):
        result = await check(CLAIMS, settings=configured(), now=NOW)

    assert result.outcomes[0].status is ProviderStatus.FAILED
    assert result.outcomes[0].code == "fact_check_error"
    assert "bad json" in result.outcomes[0].detail


async def test_the_client_is_closed_even_when_a_lookup_raised() -> None:
    """Or a failed request leaks a connection into the next one."""
    fake = Fake(error=FactCheckError("down", provider="google"))

    with bench(fake):
        await check(CLAIMS, settings=configured(), now=NOW)

    assert fake.closed


async def test_the_key_never_reaches_the_outcome_detail() -> None:
    """Provider messages sometimes echo the request, and ``detail`` is returned to the
    client. The clients redact their own messages; this covers everything else.
    """
    fake = Fake(error=FactCheckError(f"401 for key={KEY}", provider="google"))

    with bench(fake):
        result = await check(CLAIMS, settings=configured(), now=NOW)

    assert KEY not in result.outcomes[0].detail
    assert "***" in result.outcomes[0].detail


# ---------------------------------------------------------------- outcomes ----


async def test_zero_records_is_searched_not_failed() -> None:
    """A claim nobody has reviewed is a finding, and the commonest one there is."""
    with bench(Fake(results=[])):
        result = await check(CLAIMS, settings=configured(), now=NOW)

    assert result.found == ((), ())
    assert result.outcomes[0].status is ProviderStatus.SEARCHED
    assert result.outcomes[0].results == 0
    assert result.outcomes[0].code == ""


async def test_the_outcome_records_every_claim_that_was_looked_up() -> None:
    """``queries`` is the audit trail: an unexpected record set can be reproduced by
    hand from it, and it is what tells a reader which claims a ``PARTIAL`` covered.
    """
    with bench(Fake(results=[record("x")])):
        result = await check(CLAIMS, settings=configured(), now=NOW)

    assert result.outcomes[0].queries == tuple(CLAIMS)
    assert result.outcomes[0].results == 2


async def test_the_provider_is_named_from_the_setting() -> None:
    with bench(Fake()):
        result = await check(CLAIMS, settings=configured(), now=NOW)

    assert result.outcomes[0].provider == "google"


# ------------------------------------------------------------ what was sent ----


async def test_the_claim_is_sent_as_written() -> None:
    """One query per claim, unmodified.

    The formulations in :mod:`app.research.queries` are built to surface *documents*
    — keywords stripped and recombined to widen recall — which is the wrong
    instrument for an index keyed on claim wording, where a reworded variant matches a
    different record. Nothing is appended either: no "fact check", no "debunked".
    """
    fake = Fake()

    with bench(fake):
        await check(CLAIMS, settings=configured(), now=NOW)

    assert fake.queries == CLAIMS


async def test_two_identical_claims_are_looked_up_twice_and_kept_apart() -> None:
    """``found`` is aligned by index, not keyed by text.

    Two claims in one request can be identical after extraction, and a dict keyed on the
    claim would silently drop one — leaving a dossier whose claim list and fact-check
    list disagree about how many claims there were.
    """
    fake = Fake(results=[record("only answer")])

    with bench(fake):
        result = await check(["same", "same"], settings=configured(), now=NOW)

    assert fake.queries == ["same", "same"]
    assert len(result.found) == 2
    assert [r.text for r in result.found[0]] == ["only answer"]
    assert [r.text for r in result.found[1]] == ["only answer"]


async def test_the_records_stay_with_the_claim_they_came_back_for() -> None:
    """Concurrency must not reorder the answers relative to the claims.

    The mapping is positional and nothing downstream re-derives it, so a shuffle here
    would attach a real fact check to the wrong claim — genuine text, fabricated
    relevance, and nothing in the response to reveal it.
    """
    fake = Fake(
        found={
            CLAIMS[0]: [record("about the rate")],
            CLAIMS[1]: [record("about unemployment"), record("also unemployment")],
        }
    )

    with bench(fake):
        result = await check(
            CLAIMS, settings=configured(FACT_CHECK_CONCURRENCY=5), now=NOW
        )

    assert [r.text for r in result.found[0]] == ["about the rate"]
    assert [r.text for r in result.found[1]] == [
        "about unemployment",
        "also unemployment",
    ]
    assert result.outcomes[0].results == 3


@pytest.mark.parametrize("concurrency", [0, 1, 2, 8])
async def test_every_claim_is_looked_up_whatever_the_concurrency_is(
    concurrency: int,
) -> None:
    """Including a misconfigured zero, which the semaphore floors at one rather than
    deadlocking on.
    """
    fake = Fake()
    claims = [f"claim {n}" for n in range(5)]

    with bench(fake):
        result = await check(
            claims,
            settings=configured(FACT_CHECK_CONCURRENCY=concurrency),
            now=NOW,
        )

    assert sorted(fake.queries) == sorted(claims)
    assert len(result.found) == 5
    assert result.outcomes[0].status is ProviderStatus.SEARCHED


async def test_the_settings_reach_the_lookup() -> None:
    """Asserted rather than assumed, because every one of these is invisible in the
    response: a page size that never left the config would look exactly like a database
    that happened to hold ten records.
    """
    fake = Fake()

    with bench(fake):
        await check(
            CLAIMS,
            settings=configured(
                FACT_CHECK_MAX_RESULTS=7,
                FACT_CHECK_LANGUAGE="en",
                FACT_CHECK_MAX_AGE_DAYS=30,
            ),
            now=NOW,
        )

    assert fake.limits == [7, 7]
    assert fake.languages == ["en", "en"]
    assert fake.ages == [30, 30]


async def test_one_clock_is_handed_to_every_lookup() -> None:
    """Every date in one dossier resolves against the moment it was assembled — so a
    review published between the first claim's request and the last one's cannot be
    "in the future" for one and not the other.
    """
    fake = Fake()

    with bench(fake):
        await check(CLAIMS, settings=configured(), now=NOW)

    assert fake.nows == [NOW, NOW]
