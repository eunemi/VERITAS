"""One contract, both stores, because a seam with one implementation is not a seam.

Every test below runs twice: once against
:class:`~app.vectorstore.memory.InMemoryVectorStore` and once against
:class:`~app.vectorstore.chroma.ChromaVectorStore`. That is the
whole point of the file. A protocol written while looking at one database describes
that database, and the way to find out whether ``VectorStore`` is replaceable is to
replace it and run the same assertions.

The Chroma runs skip where ``chromadb`` is not installed. They are not optional in
CI — a deployment selecting ``VECTOR_STORE_PROVIDER=chroma`` has it — but they must
not turn a machine without it into a red suite, since the in-memory store is a
supported configuration and its coverage is the same coverage.

Scores are asserted as *orderings and bounds*, never as exact figures. Cosine
similarity of two hashed vectors is reproducible; the number a particular store
reports after its own normalisation is not something a caller may depend on, and a
test that pinned it would be asserting an implementation detail in a file whose
subject is the absence of them.
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from app.core.errors import VectorStoreError
from app.vectorstore.base import Document, Match, VectorStore
from app.vectorstore.chroma import ChromaVectorStore, _matches, _scalars
from app.vectorstore.memory import InMemoryVectorStore

#: The two implementations, by name. Parametrising on a string rather than on the
#: classes keeps the skip decision inside :func:`opened`, where the temporary
#: directory Chroma needs is also handled.
STORES = ("memory", "chroma")

COLLECTION = "contract"


@asynccontextmanager
async def opened(provider: str) -> AsyncIterator[VectorStore]:
    """A store of the named kind, closed afterwards.

    Chroma gets a fresh directory per test. Sharing one would make the tests
    order-dependent, and a persistent store is exactly the thing that would hide
    such a dependency until the day the suite ran in a different order.
    """
    if provider == "chroma":
        pytest.importorskip(
            "chromadb",
            reason="chromadb is not installed; the in-memory store covers this",
        )
        with tempfile.TemporaryDirectory() as directory:
            store = ChromaVectorStore(directory)
            try:
                yield store
            finally:
                await store.aclose()
        return
    store = InMemoryVectorStore()
    try:
        yield store
    finally:
        await store.aclose()


def unit(*values: float) -> list[float]:
    """A vector, written as its components. Not normalised: cosine does that."""
    return list(values)


# ------------------------------------------------------------- the contract ----


@pytest.mark.parametrize("provider", STORES)
async def test_a_stored_document_comes_back_with_its_text_and_metadata(
    provider: str,
) -> None:
    """The minimum: what went in comes out, including the metadata beside it.

    Metadata is the half a caller cannot reconstruct. The vector is a lossy
    encoding of the text and the text is in the document, but which source carried
    the passage exists nowhere else once the dossier is out of scope.
    """
    async with opened(provider) as store:
        await store.upsert(
            COLLECTION,
            [Document(id="a", text="the rate was held at 4.75%", metadata={"ref": 3})],
            [unit(1.0, 0.0, 0.0)],
        )

        found = await store.query(COLLECTION, unit(1.0, 0.0, 0.0), top_k=5)

    assert len(found) == 1
    assert isinstance(found[0], Match)
    assert found[0].id == "a"
    assert found[0].text == "the rate was held at 4.75%"
    assert found[0].metadata["ref"] == 3


@pytest.mark.parametrize("provider", STORES)
async def test_the_nearest_document_is_returned_first(provider: str) -> None:
    """Closest first, and the score orders the same way.

    Both halves matter. A caller that trusted the order but not the score, or the
    score but not the order, would be relying on something only one of the two
    stores promises.
    """
    async with opened(provider) as store:
        await store.upsert(
            COLLECTION,
            [
                Document(id="near", text="near"),
                Document(id="far", text="far"),
                Document(id="middling", text="middling"),
            ],
            [unit(1.0, 0.0, 0.0), unit(-1.0, 0.0, 0.0), unit(0.7, 0.7, 0.0)],
        )

        found = await store.query(COLLECTION, unit(1.0, 0.0, 0.0), top_k=3)

    assert [match.id for match in found] == ["near", "middling", "far"]
    assert found[0].score > found[1].score > found[2].score


@pytest.mark.parametrize("provider", STORES)
async def test_similarity_is_higher_for_closer_vectors_in_both_stores(
    provider: str,
) -> None:
    """The one numeric promise: it is a similarity, not a distance.

    Chroma reports cosine distance and this reports ``1 - distance``; the in-memory
    store computes the cosine directly. Getting that inversion wrong in one of them
    would reverse every ranking above it, and no other test in this file would say
    so — they compare within a store, and a consistently inverted store still
    orders its own results consistently.
    """
    async with opened(provider) as store:
        await store.upsert(
            COLLECTION,
            [Document(id="same", text="s"), Document(id="orthogonal", text="o")],
            [unit(1.0, 0.0, 0.0), unit(0.0, 1.0, 0.0)],
        )

        found = await store.query(COLLECTION, unit(1.0, 0.0, 0.0), top_k=2)

    scores = {match.id: match.score for match in found}
    assert scores["same"] == pytest.approx(1.0, abs=1e-6)
    assert scores["orthogonal"] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("provider", STORES)
async def test_top_k_bounds_what_comes_back(provider: str) -> None:
    async with opened(provider) as store:
        await store.upsert(
            COLLECTION,
            [Document(id=f"d{index}", text=str(index)) for index in range(5)],
            [unit(1.0, index / 10) for index in range(5)],
        )

        assert len(await store.query(COLLECTION, unit(1.0, 0.0), top_k=2)) == 2
        assert await store.query(COLLECTION, unit(1.0, 0.0), top_k=0) == []


@pytest.mark.parametrize("provider", STORES)
async def test_upserting_the_same_id_replaces_rather_than_duplicates(
    provider: str,
) -> None:
    """What makes indexing idempotent, and the reason ids are digests of the quote.

    Re-indexing a dossier is a normal thing to do — a claim is re-researched, a
    provider is added — and it must not multiply the evidence behind it. A store
    that appended would inflate every count taken from the index.
    """
    async with opened(provider) as store:
        first = [Document(id="a", text="first")]
        second = [Document(id="a", text="second")]
        await store.upsert(COLLECTION, first, [unit(1.0, 0.0)])
        await store.upsert(COLLECTION, second, [unit(1.0, 0.0)])

        found = await store.query(COLLECTION, unit(1.0, 0.0), top_k=5)

    assert [match.text for match in found] == ["second"]


@pytest.mark.parametrize("provider", STORES)
async def test_collections_do_not_see_each_other(provider: str) -> None:
    """The isolation the evidence index is built on.

    One collection per claim is what stands in for the metadata filter the protocol
    deliberately has not got. If a query could reach another collection's documents,
    a claim could be corroborated by evidence gathered for a different claim — which
    is the worst failure available to this application.
    """
    async with opened(provider) as store:
        await store.upsert("left", [Document(id="a", text="left")], [unit(1.0, 0.0)])
        await store.upsert("right", [Document(id="a", text="right")], [unit(1.0, 0.0)])

        assert [m.text for m in await store.query("left", unit(1.0, 0.0))] == ["left"]
        assert [m.text for m in await store.query("right", unit(1.0, 0.0))] == ["right"]


@pytest.mark.parametrize("provider", STORES)
async def test_querying_an_unwritten_collection_is_empty_not_an_error(
    provider: str,
) -> None:
    """A claim nothing was indexed for is a normal state, not a failure.

    It is what every claim looks like before its dossier is assembled, and a store
    that raised would make the caller's ordinary path an exception handler.
    """
    async with opened(provider) as store:
        assert await store.query("never-written", unit(1.0, 0.0), top_k=3) == []


@pytest.mark.parametrize("provider", STORES)
async def test_deleting_removes_only_what_was_named(provider: str) -> None:
    async with opened(provider) as store:
        await store.upsert(
            COLLECTION,
            [Document(id="a", text="a"), Document(id="b", text="b")],
            [unit(1.0, 0.0), unit(1.0, 0.1)],
        )

        await store.delete(COLLECTION, ["a"])
        found = await store.query(COLLECTION, unit(1.0, 0.0), top_k=5)

    assert [match.id for match in found] == ["b"]


@pytest.mark.parametrize("provider", STORES)
async def test_deleting_something_absent_is_not_an_error(provider: str) -> None:
    async with opened(provider) as store:
        await store.delete(COLLECTION, ["never-there"])


@pytest.mark.parametrize("provider", STORES)
async def test_writing_nothing_is_allowed(provider: str) -> None:
    """The empty dossier. A claim whose sources yielded no passage reaches here."""
    async with opened(provider) as store:
        await store.upsert(COLLECTION, [], [])

        assert await store.query(COLLECTION, unit(1.0, 0.0), top_k=3) == []


@pytest.mark.parametrize("provider", STORES)
async def test_documents_and_vectors_must_be_paired(provider: str) -> None:
    """They are paired positionally, so a length mismatch is a caller bug.

    Named as a :class:`~app.core.errors.VectorStoreError` by both stores rather
    than left to whichever ``IndexError`` or vendor exception happens to surface,
    because the seam's promise is that failures arrive in one type.
    """
    async with opened(provider) as store:
        with pytest.raises(VectorStoreError):
            await store.upsert(COLLECTION, [Document(id="a", text="a")], [])


@pytest.mark.parametrize("provider", STORES)
async def test_changing_the_vector_width_under_a_collection_is_refused(
    provider: str,
) -> None:
    """Swapping embedding model without reindexing, which is silent corruption.

    Old and new vectors are not comparable, so every ranking mixing them is
    meaningless — and meaningless rankings read exactly like real ones. Both stores
    refuse; the in-memory store checks, and Chroma's own refusal is translated.
    """
    async with opened(provider) as store:
        await store.upsert(COLLECTION, [Document(id="a", text="a")], [unit(1.0, 0.0)])

        with pytest.raises(VectorStoreError):
            await store.upsert(
                COLLECTION, [Document(id="b", text="b")], [unit(1.0, 0.0, 0.0)]
            )


# --------------------------------------------------------- the memory store ----


async def test_the_memory_store_orders_ties_deterministically() -> None:
    """Equal scores come back in id order, not insertion order.

    Specific to this store because Chroma's tie-breaking is its own business.
    Passages that share their vocabulary produce identical vectors under
    :class:`~app.llm.hashing.HashingEmbedder`, so ties are common rather than
    theoretical, and a caller taking the first result must not get a different one
    per process.
    """
    store = InMemoryVectorStore()
    await store.upsert(
        COLLECTION,
        [
            Document(id="c", text="c"),
            Document(id="a", text="a"),
            Document(id="b", text="b"),
        ],
        [unit(1.0, 0.0)] * 3,
    )

    found = await store.query(COLLECTION, unit(1.0, 0.0), top_k=3)

    assert [match.id for match in found] == ["a", "b", "c"]


async def test_the_memory_store_refuses_a_query_of_the_wrong_width() -> None:
    """Caught rather than computed. ``zip`` would otherwise silently truncate."""
    store = InMemoryVectorStore()
    await store.upsert(COLLECTION, [Document(id="a", text="a")], [unit(1.0, 0.0, 0.0)])

    with pytest.raises(VectorStoreError, match="dimension"):
        await store.query(COLLECTION, unit(1.0, 0.0))


async def test_a_zero_vector_scores_nothing_rather_than_dividing_by_zero() -> None:
    """A text with no content words embeds to zero, and this is where it lands."""
    store = InMemoryVectorStore()
    await store.upsert(COLLECTION, [Document(id="a", text="a")], [unit(0.0, 0.0)])

    found = await store.query(COLLECTION, unit(1.0, 0.0), top_k=1)

    assert found[0].score == 0.0


# ------------------------------------------------ chroma's translation layer ----
#
# Reached directly, and the two private names below are the reason. Everything in
# ``ChromaVectorStore`` that is not plumbing lives in these two functions, and both
# are pure — they take a mapping and return one. Going through the client would make
# their coverage conditional on an install, and these are exactly the paths where the
# two stores could drift apart without any contract test noticing.


def answer(**fields: object) -> dict[str, object]:
    """A Chroma query response: every field a list of one, one per query vector."""
    return {key: [value] for key, value in fields.items()}


def test_chroma_unwraps_its_batch_of_one() -> None:
    reply = answer(
        ids=["a", "b"],
        documents=["first", "second"],
        metadatas=[{"ref": 1}, {"ref": 2}],
        distances=[0.0, 0.5],
    )

    found = _matches(reply)

    assert [match.id for match in found] == ["a", "b"]
    assert [match.text for match in found] == ["first", "second"]
    assert [match.metadata["ref"] for match in found] == [1, 2]


def test_chroma_turns_distance_into_similarity() -> None:
    """The one conversion that would reverse every ranking if it were wrong.

    Chroma's cosine distance is ``1 - cosine``, so a distance of 0 is the same
    vector and 2 is its opposite. Undoing that here is what makes a Chroma score
    comparable to :func:`app.vectorstore.memory._cosine`'s, and the contract test
    above compares them against the same expected figures.
    """
    found = _matches(
        answer(ids=["same", "orthogonal", "opposite"], distances=[0.0, 1.0, 2.0])
    )

    assert [match.score for match in found] == [1.0, 0.0, -1.0]


def test_chroma_reports_nothing_found_as_an_empty_list() -> None:
    """An empty collection, and Chroma's habit of nulling the parallel fields."""
    assert _matches(answer(ids=[])) == []
    assert _matches({"ids": [[]], "documents": None, "distances": None}) == []


def test_chroma_fills_in_fields_it_was_not_asked_for() -> None:
    """``include`` can be narrowed, and the ids are the only field always present."""
    found = _matches(answer(ids=["a"]))

    assert len(found) == 1
    assert found[0].text == ""
    assert found[0].metadata == {}
    assert found[0].score == 1.0


def test_chroma_keeps_the_four_metadata_types_it_can_hold() -> None:
    kept = _scalars({"url": "https://a", "ref": 1, "lexical": 0.5, "primary": True})

    assert kept == {"url": "https://a", "ref": 1, "lexical": 0.5, "primary": True}


def test_chroma_drops_a_none_rather_than_inventing_a_value_for_it() -> None:
    """Chroma cannot store ``None``, and a missing key decodes to the same absence.

    :mod:`app.vectorstore.evidence` writes ``""`` and ``-1`` for the absences it
    needs to tell apart from real values; this is the fallback for everything else.
    """
    assert _scalars({"url": "https://a", "published_at": None}) == {"url": "https://a"}


def test_chroma_refuses_metadata_it_would_have_to_mangle() -> None:
    """The drift this package exists to prevent, caught rather than coerced.

    A list stored as its ``repr`` would come back as a string that looks like a
    list, while the in-memory store would hand back the list — two implementations
    of one protocol disagreeing about what was stored, discovered in production by
    whichever one was configured second.
    """
    with pytest.raises(VectorStoreError, match="list"):
        _scalars({"refs": [1, 2]})
