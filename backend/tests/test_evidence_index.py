"""The evidence index: what gets stored, what comes back, and what is deduplicated.

Three things are under test here and they fail in different ways.

**Metadata storage.** A vector is a lossy encoding of a passage, and which publisher
carried it exists nowhere else once the dossier is out of scope. So the encode/decode
pair is checked key by key, including the absences — an unknown date and an unassigned
cluster have to survive a store that holds only scalars and come back as ``None``,
not as ``""`` and ``-1``.

**Per-claim isolation.** :mod:`app.vectorstore.base` has no metadata filter, so
separation is by collection name. The test that matters is the one that indexes two
claims into one store and checks neither can see the other's passages: evidence
gathered for one claim corroborating another is the worst failure this application
has available to it.

**Two dedupes, neither of which deletes a publisher.** Identical quotes merge at index
time into one document naming every carrier; truncation variants collapse at query
time and the index keeps both. Both directions are checked, and so is the thing that
makes the second safe — a quote too short to fingerprint is never collapsed, because
containment is 1.0 for any subset however small.

Similarity figures are quoted in the docstrings below because they were measured
against :class:`~app.llm.hashing.HashingEmbedder`, not predicted. Only orderings and
the presence of a floor are asserted; the one exact figure asserted is 1.0 for a
passage whose content words are exactly the claim's, which is cosine's definition
rather than the embedder's choice.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domain.research import ClaimResearch, DateBasis, Evidence, Source
from app.llm.hashing import HashingEmbedder
from app.research import dedupe
from app.services.evidence import EvidenceIndex
from app.vectorstore import evidence as passages
from app.vectorstore.base import Document, Match
from app.vectorstore.memory import InMemoryVectorStore
from tests.research_bench import NOW, source

#: The claim every retrieval test probes with.
CLAIM = "The Bank of England held its benchmark rate at 4.75% on Thursday."

#: A second claim about something else entirely, for the isolation tests.
OTHER_CLAIM = "High winds cancelled Solent ferry sailings from Portsmouth."

#: A passage that restates :data:`CLAIM` and then says more. Measured at 0.71.
HELD = (
    "The Bank of England held its benchmark rate at 4.75% on Thursday, citing "
    "services inflation that has proved more persistent than the committee expected."
)

#: A second engine's cut of the same paragraph, written as a slice so the
#: relationship is structural. Its shingles are a subset of :data:`HELD`'s, so
#: containment is 1.000 and one of the two must be collapsed. Its content words are
#: exactly :data:`CLAIM`'s, so it is the copy the store ranks first, at 1.00.
HELD_SHORTER = HELD[:64]

#: The opposite of :data:`CLAIM`, in the claim's own vocabulary. Measured at 0.57 —
#: second place, ahead of everything unrelated — which is the property that keeps
#: retrieval a measurement rather than case building. Containment against
#: :data:`HELD` is 0.136, well under the collapse threshold, so it is a distinct
#: passage and not a truncation of one.
CUT = (
    "The Bank of England cut its benchmark rate to 4.5% on Thursday, ending a "
    "run of three holds and surprising most of the market."
)

#: Unrelated to :data:`CLAIM` and sharing not one content word with it, so it scores
#: exactly 0.0 and is what the similarity floor is for.
FERRY = (
    "High winds cancelled sailings from Portsmouth on Tuesday, and the operator "
    "said the Solent crossing would stay shut until the weather eased."
)

#: Too short to fingerprint: fewer than three words, so no trigram, so no shingles.
BRIEF = "Rates unchanged."


def carrying(
    url: str,
    *quotes: str,
    ref: int = 1,
    title: str = "",
    provider: str = "tavily",
    lexical: float = 0.5,
    published_at: datetime | None = None,
    date_basis: DateBasis | None = None,
    cluster: int | None = None,
) -> Source:
    """A source whose snippet contains ``quotes``, with offsets that hold.

    The offsets are located in the snippet rather than passed, so
    ``snippet[start:end] == quote`` is true here the way it is for a real selection.
    A test built on evidence whose offsets were zero would not notice code that had
    stopped honouring them.
    """
    snippet = " ".join(quotes)
    return source(
        url,
        title=title,
        snippet=snippet,
        ref=ref,
        provider=provider,
        published_at=published_at,
        date_basis=date_basis,
        cluster=cluster,
        evidence=tuple(
            Evidence(
                quote=quote,
                provider=provider,
                start=snippet.index(quote),
                end=snippet.index(quote) + len(quote),
                score=lexical,
            )
            for quote in quotes
        ),
    )


def dossier(claim: str, *sources: Source) -> ClaimResearch:
    """A dossier in dossier order: strongest source first, as the pipeline builds it."""
    return ClaimResearch(claim=claim, queries=(claim,), sources=sources)


def index(*, top_k: int = 8, min_similarity: float = 0.0) -> EvidenceIndex:
    """An index over a store that never leaves the process."""
    return EvidenceIndex(
        InMemoryVectorStore(),
        HashingEmbedder(256),
        top_k=top_k,
        min_similarity=min_similarity,
    )


def only(research: ClaimResearch) -> passages.Relevant:
    """The single document ``research`` produces, decoded."""
    written = passages.documents(research)
    assert len(written) == 1
    return decoded(written[0])


def decoded(document: Document) -> passages.Relevant:
    """A document read back the way a store would hand it over.

    Goes through :class:`~app.vectorstore.base.Match` rather than reading the
    metadata mapping directly, because the pair that has to agree is the encoder and
    the decoder, and a test that inspected the dict would only be checking one of
    them.
    """
    return passages.decode(
        Match(
            id=document.id,
            text=document.text,
            score=1.0,
            metadata=document.metadata,
        )
    )


# ------------------------------------------------------------ what is stored ----


def test_each_distinct_quote_becomes_one_document() -> None:
    research = dossier(
        CLAIM,
        carrying("https://www.reuters.com/a", HELD, ref=1),
        carrying("https://www.bbc.co.uk/b", CUT, ref=2),
    )

    written = passages.documents(research)

    assert [document.text for document in written] == [HELD, CUT]
    assert [document.id for document in written] == [
        passages.identity(HELD),
        passages.identity(CUT),
    ]


def test_two_passages_from_one_source_are_two_documents() -> None:
    """A page can bear on a claim in more than one place, and both are evidence."""
    research = dossier(CLAIM, carrying("https://www.reuters.com/a", HELD, CUT))

    written = passages.documents(research)

    assert [document.text for document in written] == [HELD, CUT]


def test_the_metadata_written_is_exactly_the_declared_keys() -> None:
    """:data:`app.vectorstore.evidence.KEYS` is the contract the decoder reads.

    Asserted as an exact set in both directions: a key written but not declared
    would never be decoded, and a key declared but not written would decode to its
    default and look like a real absence.
    """
    research = dossier(CLAIM, carrying("https://www.reuters.com/a", HELD))

    written = passages.documents(research)

    assert set(written[0].metadata) == set(passages.KEYS)


def test_the_metadata_written_holds_only_scalars() -> None:
    """What every store can hold, and what :mod:`app.vectorstore.chroma` requires.

    Chroma rejects a list outright rather than storing its ``repr``, so a value that
    was not a scalar would fail against one store and quietly succeed against the
    other. Checked here, on the encoder, so the failure lands in one place.
    """
    research = dossier(
        CLAIM,
        carrying(
            "https://www.reuters.com/a",
            HELD,
            published_at=NOW,
            date_basis=DateBasis.PROVIDER,
            cluster=0,
        ),
    )

    written = passages.documents(research)

    for value in written[0].metadata.values():
        assert isinstance(value, str | int | float)


def test_the_source_behind_a_passage_survives_the_round_trip() -> None:
    """The half of a match that cannot be recomputed from the text."""
    research = dossier(
        CLAIM,
        carrying(
            "https://www.reuters.com/article",
            HELD,
            ref=4,
            title="Bank of England holds rate",
            provider="brave",
            lexical=0.62,
            published_at=NOW,
            date_basis=DateBasis.PROVIDER,
            cluster=2,
        ),
    )

    found = only(research)

    assert found.quote == HELD
    assert found.claim == CLAIM
    assert found.ref == 4
    assert found.url == "https://www.reuters.com/article"
    assert found.domain == "reuters.com"
    assert found.title == "Bank of England holds rate"
    assert found.provider == "brave"
    assert found.lexical == pytest.approx(0.62)
    assert found.published_at == NOW
    assert found.date_basis == DateBasis.PROVIDER.value
    assert found.cluster == 2


def test_an_unknown_date_and_no_cluster_decode_back_to_none() -> None:
    """The sentinels are an encoding detail and must not reach a caller.

    A store holds no ``None``, so absence is written as ``""`` and
    :data:`~app.vectorstore.evidence.NO_CLUSTER`. A caller that saw ``-1`` would
    have to know which numbers are real cluster ids, and cluster 0 exists.
    """
    research = dossier(CLAIM, carrying("https://www.reuters.com/a", HELD))

    found = only(research)

    assert found.published_at is None
    assert found.date_basis is None
    assert found.cluster is None


def test_cluster_zero_is_not_read_as_no_cluster() -> None:
    """The reason the sentinel is ``-1`` rather than ``0``."""
    research = dossier(CLAIM, carrying("https://www.reuters.com/a", HELD, cluster=0))

    assert only(research).cluster == 0


def test_an_empty_dossier_writes_nothing() -> None:
    """A claim whose sources yielded no passage. Normal, not an error."""
    assert passages.documents(dossier(CLAIM)) == ()
    assert passages.documents(dossier(CLAIM, source("https://www.reuters.com/a"))) == ()


# ------------------------------------------------- merging identical quotes ----


def test_one_quote_carried_by_two_publishers_is_one_document_naming_both() -> None:
    """The index-time merge, and the reason it is lossless.

    Two mastheads running the same wire sentence are two publishers, not one, and a
    merge that recorded only the first would delete a real corroboration. So the
    document is one — the vector and the text are identical, and storing them twice
    would inflate every count taken from the index — and ``refs``/``domains`` name
    everyone who carried it.
    """
    research = dossier(
        CLAIM,
        carrying("https://www.reuters.com/a", HELD, ref=1),
        carrying("https://www.bbc.co.uk/b", HELD, ref=2, title="BoE holds"),
    )

    found = only(research)

    assert found.refs == (1, 2)
    assert found.domains == ("reuters.com", "bbc.co.uk")


def test_the_merged_document_reports_the_strongest_carrier() -> None:
    """Dossier order is strength order, so the first carrier is the one to name.

    ``refs`` names all of them, but the single ``url``, ``title`` and date have to
    come from somewhere, and the strongest source is the one a reader should be sent
    to.
    """
    research = dossier(
        CLAIM,
        carrying("https://www.reuters.com/a", HELD, ref=1, title="Reuters"),
        carrying("https://www.bbc.co.uk/b", HELD, ref=2, title="BBC"),
    )

    found = only(research)

    assert found.ref == 1
    assert found.url == "https://www.reuters.com/a"
    assert found.title == "Reuters"
    assert found.refs[0] == found.ref


def test_quotes_differing_only_in_case_and_spacing_are_one_document() -> None:
    """Identity is the folded text, the way :mod:`app.research.evidence` compares.

    Two publishers who differ by a double space and a capital have not said two
    things, and treating them as two passages would report one sentence as two
    independent confirmations.
    """
    research = dossier(
        CLAIM,
        carrying("https://www.reuters.com/a", HELD, ref=1),
        carrying("https://www.bbc.co.uk/b", HELD.upper().replace(" ", "  "), ref=2),
    )

    found = only(research)

    assert found.refs == (1, 2)


def test_a_source_repeating_a_quote_is_named_once() -> None:
    """A page whose snippet was quoted twice at the same place is still one page."""
    research = dossier(CLAIM, carrying("https://www.reuters.com/a", HELD, HELD, ref=1))

    found = only(research)

    assert found.refs == (1,)
    assert found.domains == ("reuters.com",)


# ---------------------------------------------------------- collection names ----


def test_a_collection_name_is_one_a_store_will_accept() -> None:
    """Chroma's naming rules: 3–63 characters, alphanumeric ends, a narrow charset.

    A claim is arbitrary user prose, so the name cannot contain any of it. Digesting
    is what makes the rules hold for every claim rather than for the claims a test
    happened to try.
    """
    name = passages.collection_for("Rates: 4.75%?! — «Café» de España \n\t")

    assert 3 <= len(name) <= 63
    assert name[0].isalnum() and name[-1].isalnum()
    assert set(name) <= set("abcdefghijklmnopqrstuvwxyz0123456789-_")


def test_the_same_claim_reaches_the_same_collection() -> None:
    """No mapping is stored, so indexing and retrieval must agree by derivation."""
    assert passages.collection_for(CLAIM) == passages.collection_for(CLAIM)


def test_a_collection_name_ignores_case_accents_and_spacing() -> None:
    """The three ways two spellings of one claim differ without differing."""
    assert passages.collection_for("Café raised rates") == passages.collection_for(
        "  cafe  RAISED   rates "
    )


def test_different_claims_get_different_collections() -> None:
    assert passages.collection_for(CLAIM) != passages.collection_for(OTHER_CLAIM)


def test_identity_ignores_case_accents_and_spacing_and_separates_the_rest() -> None:
    assert passages.identity("Café  HOLDS") == passages.identity("cafe holds")
    assert passages.identity(HELD) != passages.identity(HELD_SHORTER)


# ------------------------------------------- collapsing truncation variants ----


def relevant(*quotes: str) -> list[passages.Relevant]:
    """``quotes`` as retrieved passages, in the order given, scored downwards."""
    return [
        passages.Relevant(
            quote=quote,
            similarity=1.0 - position / 10,
            claim=CLAIM,
            ref=position + 1,
            url=f"https://example{position}.com/a",
            domain=f"example{position}.com",
            title="",
            provider="tavily",
            lexical=0.5,
            refs=(position + 1,),
            domains=(f"example{position}.com",),
        )
        for position, quote in enumerate(quotes)
    ]


def test_collapse_drops_a_truncation_of_a_passage_already_kept() -> None:
    """Containment 1.000 between the two, measured, and the first one wins."""
    kept = passages.collapse(relevant(HELD_SHORTER, HELD))

    assert [item.quote for item in kept] == [HELD_SHORTER]


def test_collapse_keeps_passages_that_merely_share_a_subject() -> None:
    """:data:`CUT` against :data:`HELD` is containment 0.136 — a distinct passage.

    The pair that makes this worth asserting: same publisher vocabulary, same
    figures, opposite claim. A threshold loose enough to merge them would delete the
    contradiction.
    """
    kept = passages.collapse(relevant(HELD, CUT, FERRY))

    assert [item.quote for item in kept] == [HELD, CUT, FERRY]


def test_collapse_keeps_a_quote_too_short_to_fingerprint() -> None:
    """Containment is 1.0 for any subset, and the empty set is a subset of everything.

    Without :data:`app.research.dedupe.MIN_SHINGLES`, every brief passage in the
    dossier would collapse into the first long one. The alternative to keeping it is
    dropping real evidence for being short.
    """
    assert len(dedupe.shingles(BRIEF)) < dedupe.MIN_SHINGLES

    kept = passages.collapse(relevant(HELD, BRIEF))

    assert [item.quote for item in kept] == [HELD, BRIEF]


def test_collapse_of_nothing_is_nothing() -> None:
    assert passages.collapse([]) == []


# ------------------------------------------------------- indexing and recall ----


async def test_the_index_reports_the_number_of_distinct_passages() -> None:
    """Three passages, two of them the same sentence, so two documents.

    The count is how a caller sees the index-time merge happen. A count equal to the
    dossier's passage total would mean the merge had stopped working, and every
    downstream tally of "how many sources say this" would be wrong.
    """
    research = dossier(
        CLAIM,
        carrying("https://www.reuters.com/a", HELD, ref=1),
        carrying("https://www.bbc.co.uk/b", HELD, ref=2),
        carrying("https://apnews.com/c", CUT, ref=3),
    )

    assert await index().index(research) == 2


async def test_indexing_an_empty_dossier_writes_nothing() -> None:
    assert await index().index(dossier(CLAIM)) == 0


async def test_the_passage_restating_the_claim_comes_back_first() -> None:
    """Measured at 1.00 for :data:`HELD_SHORTER` and 0.57 for :data:`CUT`."""
    store = index(min_similarity=0.05)
    await store.index(
        dossier(
            CLAIM,
            carrying("https://www.bbc.co.uk/b", CUT, ref=1),
            carrying("https://www.reuters.com/a", HELD_SHORTER, ref=2),
        )
    )

    found = await store.relevant(CLAIM)

    assert [item.quote for item in found] == [HELD_SHORTER, CUT]
    assert found[0].similarity == pytest.approx(1.0, abs=1e-6)
    assert found[0].similarity > found[1].similarity


async def test_a_passage_contradicting_the_claim_is_retrieved() -> None:
    """The property most likely to be "fixed" into a bug.

    :data:`CUT` says the rate was cut; the claim says it was held. It is the most
    important passage in the dossier and it outranks the unrelated one by a wide
    margin. Retrieval measures relevance, and a retriever that preferred agreement
    would turn evidence gathering into case building without changing any type.
    """
    store = index()
    await store.index(
        dossier(
            CLAIM,
            carrying("https://www.bbc.co.uk/b", CUT, ref=1),
            carrying("https://portsmouth.co.uk/c", FERRY, ref=2),
        )
    )

    found = await store.relevant(CLAIM)

    assert [item.quote for item in found] == [CUT, FERRY]


async def test_a_claim_cannot_retrieve_another_claims_evidence() -> None:
    """The worst available failure, and the one collection-per-claim rules out.

    Both dossiers go into the same store, which is the situation a shared Chroma
    directory is in permanently. The floor is off, so nothing here is hidden by a
    threshold: separation is structural or it is absent.
    """
    store = index()
    await store.index(dossier(CLAIM, carrying("https://www.reuters.com/a", HELD)))
    await store.index(
        dossier(OTHER_CLAIM, carrying("https://portsmouth.co.uk/c", FERRY, ref=2))
    )

    assert [item.quote for item in await store.relevant(CLAIM)] == [HELD]
    assert [item.quote for item in await store.relevant(OTHER_CLAIM)] == [FERRY]


async def test_a_claim_with_nothing_indexed_retrieves_nothing() -> None:
    """Every claim's state before its dossier is assembled."""
    assert await index().relevant(CLAIM) == ()


async def test_the_similarity_floor_drops_a_passage_sharing_nothing() -> None:
    """Why a floor is needed at all: a vector store answers every query.

    :data:`FERRY` shares no content word with the claim and scores exactly 0.0, and
    without the floor it is returned as the claim's nearest evidence. Both halves are
    asserted, because a floor that dropped everything would pass the first alone.
    """
    research = dossier(CLAIM, carrying("https://portsmouth.co.uk/c", FERRY))

    unfloored = index(min_similarity=0.0)
    await unfloored.index(research)
    floored = index(min_similarity=0.05)
    await floored.index(research)

    assert [item.similarity for item in await unfloored.relevant(CLAIM)] == [0.0]
    assert await floored.relevant(CLAIM) == ()


async def test_top_k_bounds_the_answer() -> None:
    store = index()
    await store.index(
        dossier(
            CLAIM,
            carrying("https://www.reuters.com/a", HELD, ref=1),
            carrying("https://www.bbc.co.uk/b", CUT, ref=2),
            carrying("https://portsmouth.co.uk/c", FERRY, ref=3),
        )
    )

    assert len(await store.relevant(CLAIM, top_k=2)) == 2
    assert await store.relevant(CLAIM, top_k=0) == ()


async def test_indexing_twice_does_not_multiply_the_evidence() -> None:
    """Re-researching a claim is normal. Ids are digests of the quote, so it is safe."""
    research = dossier(
        CLAIM,
        carrying("https://www.reuters.com/a", HELD, ref=1),
        carrying("https://www.bbc.co.uk/b", CUT, ref=2),
    )
    store = index()

    assert await store.index(research) == 2
    assert await store.index(research) == 2
    assert len(await store.relevant(CLAIM)) == 2


async def test_a_truncated_copy_is_retrieved_once_and_still_indexed() -> None:
    """The query-time dedupe, and the promise that it deletes nothing.

    Two documents are written, because the strings differ and index-time merging is
    a fact about strings. One passage comes back, because they are the same paragraph
    cut in two places. The store still holds both, so a later query — a different
    claim, a different threshold — can still reach the copy this one collapsed.
    """
    vectors = InMemoryVectorStore()
    store = EvidenceIndex(vectors, HashingEmbedder(256), min_similarity=0.05)
    written = await store.index(
        dossier(
            CLAIM,
            carrying("https://www.reuters.com/a", HELD, ref=1),
            carrying("https://apnews.com/d", HELD_SHORTER, ref=2),
        )
    )

    found = await store.relevant(CLAIM)

    assert written == 2
    assert [item.quote for item in found] == [HELD_SHORTER]
    assert len(vectors.stored(passages.collection_for(CLAIM))) == 2


async def test_a_retrieved_passage_names_every_publisher_behind_it() -> None:
    """End to end: the merge recorded at index time survives retrieval.

    This is the number a reader needs. One sentence carried by two mastheads is one
    passage and two publishers, and a caller counting matches would see one.
    """
    store = index(min_similarity=0.05)
    await store.index(
        dossier(
            CLAIM,
            carrying("https://www.reuters.com/a", HELD, ref=1),
            carrying("https://www.bbc.co.uk/b", HELD, ref=2),
        )
    )

    found = await store.relevant(CLAIM)

    assert len(found) == 1
    assert found[0].refs == (1, 2)
    assert found[0].domains == ("reuters.com", "bbc.co.uk")
