"""Deduplication, at both of the levels the word covers.

The two are tested separately and asymmetrically on purpose, because their failure
modes are not comparable.

**Page identity** — :func:`~app.research.dedupe.group` — is a factual question about
URLs. A wrong answer here *merges* two documents into one row, which deletes a real
publisher from the record with nothing left to show it happened. So the tests demand
exactness.

**Story identity** — :func:`~app.research.dedupe.cluster` — is a judgement made from a
few hundred characters of snippet, and it can be wrong. A wrong answer only *marks*:
:attr:`~app.domain.research.ClaimResearch.stories` miscounts while every source stays
in the response and every domain stays counted. So the tests here demand the two
measured cases that decide whether the number is worth anything at all —

* a publisher's boilerplate must **not** merge two of its own unrelated stories, even
  though they measure 0.897 on snippet overlap, above the threshold at any width; and
* syndicated copy under a rewritten headline **must** merge, at title containment
  0.000, which is the case a weighted title-plus-snippet score would always split —

and that the outcome does not depend on provider order or on the process it ran in.

That last one is not a formality. A fingerprint built on :func:`hash` would be salted
per worker, so two servers behind a load balancer would disagree about whether a claim
is corroborated, and the disagreement would appear only under load.
"""

from __future__ import annotations

import dataclasses
import itertools
import subprocess
import sys
from pathlib import Path

import pytest

from app.research import dedupe
from tests.research_bench import (
    BOILERPLATE,
    LOCAL_FERRY,
    LOCAL_FERRY_TITLE,
    LOCAL_PLANNING,
    LOCAL_PLANNING_TITLE,
    WIRE,
    WIRE_REPHRASED,
    WIRE_TITLE,
    WIRE_TITLE_REWRITTEN,
    WIRE_TRUNCATED,
    WIRE_WITH_LEAD,
    partition,
    retrieval,
    source,
    syndication,
)

#: The backend root, for the subprocess that re-runs the clustering under a new seed.
BACKEND = Path(__file__).resolve().parent.parent


# ======================================================== page identity: group ====


def test_every_spelling_of_one_url_is_one_page() -> None:
    """Four URLs, one document, one row — and all four spellings kept.

    Normalisation is lossy: a stripped tracking parameter cannot be recovered, and a
    caller following the link should be able to use exactly what the provider gave.
    """
    spellings = [
        "https://www.bbc.co.uk/news/business-123?utm_source=twitter",
        "http://bbc.co.uk/news/business-123/",
        "https://BBC.co.uk:443/news/business-123#headline",
        "https://www-bbc-co-uk.cdn.ampproject.org/c/s/www.bbc.co.uk/news/business-123",
    ]
    grouping = dedupe.group(
        retrieval(f"engine{index}", url, title="Rates held", snippet=WIRE, rank=index + 1)
        for index, url in enumerate(spellings)
    )

    assert len(grouping.pages) == 1
    page = grouping.pages[0]
    assert page.url == "https://bbc.co.uk/news/business-123"
    assert page.urls == tuple(spellings)
    assert page.domain == "bbc.co.uk"
    assert len(page.retrievals) == 4


def test_a_repeated_spelling_is_recorded_once() -> None:
    """``urls`` is the distinct spellings, not one entry per retrieval."""
    grouping = dedupe.group(
        [
            retrieval("tavily", "https://bbc.co.uk/news/1", snippet=WIRE),
            retrieval("brave", "https://bbc.co.uk/news/1", snippet=WIRE),
        ]
    )

    assert grouping.pages[0].urls == ("https://bbc.co.uk/news/1",)
    assert len(grouping.pages[0].retrievals) == 2


def test_pages_come_out_in_first_appearance_order() -> None:
    """The fan-out's order, so the caller decides what "strongest" means."""
    grouping = dedupe.group(
        [
            retrieval("tavily", "https://b.example/2", snippet=WIRE),
            retrieval("tavily", "https://a.example/1", snippet=WIRE),
            retrieval("brave", "https://b.example/2", snippet=WIRE),
        ]
    )

    assert [page.url for page in grouping.pages] == [
        "https://b.example/2",
        "https://a.example/1",
    ]


def test_a_url_that_is_not_a_web_page_is_reported_not_swallowed() -> None:
    """A dropped result must be countable, or a thinner search reads as a complete one."""
    grouping = dedupe.group(
        [
            retrieval("tavily", "mailto:tips@example.com", snippet=WIRE),
            retrieval("tavily", "not a url at all", snippet=WIRE),
            retrieval("tavily", "https://bbc.co.uk/news/1", snippet=WIRE),
        ]
    )

    assert len(grouping.pages) == 1
    assert grouping.dropped == ("mailto:tips@example.com", "not a url at all")


def test_the_title_is_the_best_ranked_providers_own_string() -> None:
    """Chosen, never composed. Splicing two would be this service writing a headline."""
    page = dedupe.group(
        [
            retrieval("tavily", "https://bbc.co.uk/1", title="Rates held — BBC", rank=7),
            retrieval("brave", "https://bbc.co.uk/1", title="Rates held", rank=2),
        ]
    ).pages[0]

    assert page.title == "Rates held"
    # Both remain visible, so a reader can see the providers disagreed.
    assert {r.title for r in page.retrievals} == {"Rates held — BBC", "Rates held"}


def test_grouping_nothing_yields_nothing() -> None:
    assert dedupe.group([]) == dedupe.Grouping(pages=(), dropped=())


# ===================================================== story identity: cluster ====


def test_syndicated_copy_under_a_rewritten_headline_is_one_story() -> None:
    """The commonest syndication pattern, and the one a weighted score would split.

    Title containment is 0.000 between the wire headline and the rewrite, over body
    copy that is a verbatim subset. Averaging the two similarities would put this
    below any usable threshold and report three independent reports where there is
    one.
    """
    titles = dedupe.containment(
        dedupe.shingles(WIRE_TITLE), dedupe.shingles(WIRE_TITLE_REWRITTEN)
    )
    clustered = dedupe.cluster(syndication())

    assert titles == 0.0
    assert [item.cluster for item in clustered[:3]] == [1, 1, 1]


def test_one_publishers_boilerplate_does_not_merge_two_of_its_stories() -> None:
    """The measured case :data:`~app.research.dedupe.MIN_ANCHORS` exists for.

    These two snippets measure 0.897 — above
    :data:`~app.research.dedupe.CONTAINMENT_THRESHOLD` — because a newsletter block is
    most of both. No threshold separates that from syndication; only the anchors do,
    and they share none.
    """
    overlap = dedupe.containment(
        dedupe.shingles(LOCAL_PLANNING), dedupe.shingles(LOCAL_FERRY)
    )
    shared = dedupe.anchors(f"{LOCAL_PLANNING_TITLE}. {LOCAL_PLANNING}") & dedupe.anchors(
        f"{LOCAL_FERRY_TITLE}. {LOCAL_FERRY}"
    )
    clustered = dedupe.cluster(syndication())

    assert overlap >= dedupe.CONTAINMENT_THRESHOLD
    assert shared == frozenset()
    assert [item.cluster for item in clustered[3:]] == [None, None]


def test_boilerplate_alone_cannot_manufacture_a_story() -> None:
    """The degenerate version: two sources whose snippets are *only* the block."""
    clustered = dedupe.cluster(
        [
            source("https://a.example/1", title="First report", snippet=BOILERPLATE),
            source("https://b.example/2", title="Second report", snippet=BOILERPLATE),
        ]
    )

    assert [item.cluster for item in clustered] == [None, None]


def test_a_similar_headline_can_add_a_merge() -> None:
    """The title rescue, isolated: same snippets, two different headlines.

    :data:`~app.research.dedupe.WIRE_REPHRASED` measures 0.788 against the wire copy —
    inside the rescue band and below the threshold — so this pair merges when the
    headlines match and does not when they do not. Which is the whole claim the rescue
    makes: a title can add a merge and can never veto one.
    """
    overlap = dedupe.containment(
        dedupe.shingles(WIRE), dedupe.shingles(WIRE_REPHRASED)
    )
    assert dedupe.TITLE_RESCUE_FLOOR <= overlap < dedupe.TITLE_RESCUE_CEILING

    same = dedupe.cluster(
        [
            source("https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE),
            source("https://apnews.com/b", title=WIRE_TITLE, snippet=WIRE_REPHRASED),
        ]
    )
    different = dedupe.cluster(
        [
            source("https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE),
            source(
                "https://apnews.com/b",
                title=WIRE_TITLE_REWRITTEN,
                snippet=WIRE_REPHRASED,
            ),
        ]
    )

    assert [item.cluster for item in same] == [1, 1]
    assert [item.cluster for item in different] == [None, None]


def test_a_short_fragment_is_never_absorbed() -> None:
    """Containment is 1.0 for *any* subset, including a six-word one.

    The fragment below is a strict prefix of the wire copy, so it measures a perfect
    match against it — and against every other article that opens the same way.
    :data:`~app.research.dedupe.MIN_SHINGLES` is what stops an aggregator's one-line
    stub from being declared the same story as the report it links to.
    """
    fragment = "The Bank of England held its"
    assert len(dedupe.shingles(fragment)) < dedupe.MIN_SHINGLES
    assert dedupe.containment(dedupe.shingles(fragment), dedupe.shingles(WIRE)) == 1.0

    clustered = dedupe.cluster(
        [
            source("https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE),
            source("https://aggregator.example/b", title=WIRE_TITLE, snippet=fragment),
        ]
    )

    assert [item.cluster for item in clustered] == [None, None]


def test_clustering_never_drops_reorders_or_merges_a_source() -> None:
    """A label, not a deletion. That is the entire safety argument for clustering.

    Field by field, so a source that came back in the right position with its title or
    its evidence quietly rewritten fails here rather than passing as "not dropped".
    """
    given = syndication()
    clustered = dedupe.cluster(given)

    assert len(clustered) == len(given)
    assert [item.url for item in clustered] == [item.url for item in given]
    for before, after in zip(given, clustered, strict=True):
        assert dataclasses.replace(before, cluster=after.cluster) == after


def test_only_multi_member_clusters_are_numbered() -> None:
    """A singleton consuming id 1 would leave a gap where a reader looks for it."""
    clustered = dedupe.cluster(syndication())
    ids = [item.cluster for item in clustered if item.cluster is not None]

    assert set(ids) == {1}
    assert all(
        item.cluster is None for item in clustered if item.url.endswith(("/d", "/e"))
    )


def test_cluster_ids_are_numbered_from_one_without_gaps() -> None:
    """Two clusters, so the numbering is exercised rather than assumed."""
    other = (
        "The Environment Agency issued eleven flood warnings for the Severn "
        "catchment on Friday after two days of heavy rain across mid Wales, with "
        "river levels at Bewdley expected to peak overnight on Saturday morning."
    )
    clustered = dedupe.cluster(
        [
            *syndication()[:3],
            source("https://a.example/f", title="Severn flood warnings", snippet=other),
            source("https://b.example/g", title="Flood warnings on Severn", snippet=other),
        ]
    )
    ids = sorted({item.cluster for item in clustered if item.cluster is not None})

    assert ids == [1, 2]


def test_a_lone_source_is_returned_untouched() -> None:
    lone = [source("https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE)]

    assert dedupe.cluster(lone) == tuple(lone)
    assert dedupe.cluster([]) == ()


def test_two_independent_reports_of_one_event_stay_two_stories() -> None:
    """Different words about the same decision is corroboration, not syndication.

    This is the merge that would be most damaging to get wrong: it is exactly the
    case where the dossier is supposed to say two publishers reported independently.
    """
    independent = (
        "Rate-setters at the Bank of England left borrowing costs untouched this "
        "month, disappointing mortgage holders who had hoped for relief, after "
        "official figures showed price growth in the services sector barely moving."
    )
    clustered = dedupe.cluster(
        [
            source("https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE),
            source("https://ft.com/b", title="Rate-setters hold firm", snippet=independent),
        ]
    )

    assert [item.cluster for item in clustered] == [None, None]


# ===================================================================== determinism ====


def test_the_clustering_does_not_depend_on_provider_order() -> None:
    """Every ordering of the same five sources yields the same partition.

    Providers answer in whatever order the network allows, and single-link components
    computed with an order-dependent union would put the same claim in one story on
    one request and two on the next.
    """
    baseline = frozenset(partition(dedupe.cluster(syndication())))
    seen = {baseline}

    for order in itertools.permutations(range(5)):
        given = syndication()
        shuffled = [given[index] for index in order]
        seen.add(frozenset(partition(dedupe.cluster(shuffled))))

    assert seen == {baseline}
    assert len(baseline) == 3  # anti-vacuity: three stories, not one blob or five


def test_the_clustering_is_identical_under_a_different_hash_seed() -> None:
    """No :func:`hash` on a string anywhere, proved by running it twice.

    Python salts string hashing per process. A fingerprint or a set-iteration order
    that leaked into the result would cluster differently in each worker, and two
    servers behind a load balancer would disagree about whether a claim is
    corroborated — under load only, which is the worst way to find out.

    A subprocess per seed, because ``PYTHONHASHSEED`` is read once at interpreter
    start and cannot be changed from inside a running one. The program below imports
    only :mod:`app.research.dedupe` and :mod:`tests.research_bench` — no ``pytest`` —
    so the child needs nothing this repository's test runner provides.
    """
    program = (
        "from app.research import dedupe\n"
        "from tests.research_bench import partition, syndication\n"
        "clustered = dedupe.cluster(syndication())\n"
        "print(sorted(sorted(group) for group in partition(clustered)))\n"
        "print([item.cluster for item in clustered])\n"
    )
    outputs = []
    for seed in ("0", "1", "42", "12345"):
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", program],
            cwd=BACKEND,
            env={"PYTHONHASHSEED": seed, "PYTHONPATH": str(BACKEND)},
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        outputs.append(result.stdout)

    assert len(set(outputs)) == 1
    # Anti-vacuity: four identical *empty* outputs would satisfy the line above.
    assert "reuters.com" in outputs[0]


# ================================================================ text handling ====


def test_containment_is_one_for_a_subset() -> None:
    """The property Jaccard does not have, and the reason this metric was chosen.

    Two engines truncate the same page at different points, so their shingle sets are
    systematically different *sizes*. That is provider noise, and a union denominator
    charges for it.
    """
    whole, part = dedupe.shingles(WIRE), dedupe.shingles(WIRE_WITH_LEAD)
    jaccard = len(whole & part) / len(whole | part)

    assert dedupe.containment(whole, part) == 1.0
    assert jaccard < 0.9  # what a size-symmetric metric would have measured


def test_containment_is_symmetric() -> None:
    """Required for the components to be well defined at all."""
    left, right = dedupe.shingles(WIRE), dedupe.shingles(WIRE_TRUNCATED)

    assert dedupe.containment(left, right) == dedupe.containment(right, left)


def test_containment_of_an_empty_set_is_zero() -> None:
    """Not one. ``min()`` over an empty set would otherwise make everything a match."""
    assert dedupe.containment(frozenset(), dedupe.shingles(WIRE)) == 0.0
    assert dedupe.containment(frozenset(), frozenset()) == 0.0


def test_shingles_are_word_trigrams_in_order() -> None:
    assert dedupe.shingles("the rate was held") == frozenset(
        {("the", "rate", "was"), ("rate", "was", "held")}
    )


def test_a_text_shorter_than_the_window_has_no_shingles() -> None:
    assert dedupe.shingles("rate held") == frozenset()


def test_a_figure_survives_shingling_as_one_token() -> None:
    """``4.75`` stays whole. Splitting it into ``4`` and ``75`` would insert two
    trigrams the sentence does not have and destroy the two it does.

    The percent sign is not part of the token here, unlike in
    :func:`~app.research.dedupe.anchors`, and the difference is deliberate: a shingle
    needs the same token whichever way an engine spelled the unit, while an anchor is
    an identity to be matched as written.
    """
    assert ("held", "at", "4.75") in dedupe.shingles("held at 4.75% today")
    assert dedupe.shingles("held at 4.75% today") == dedupe.shingles("held at 4.75 today")


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("The Bank&amp;s rate", "The Bank&s rate"),
        ("The <b>Bank of England</b> held", "The Bank of England held"),
        ("The &lt;b&gt;Bank of England&lt;/b&gt; held", "The <b>Bank of England</b> held"),
        ("The Bank’s rate", "The Bank's rate"),
        ("The Bank–s rate", "The Bank-s rate"),
        ("The Bank​s rate", "The Banks rate"),
        ("The **Bank**s rate", "The Banks rate"),
        ("The  Bank\ts  rate", "The Bank s rate"),
        ("THE BANKS RATE", "the banks rate"),
    ],
)
def test_flatten_lands_two_engines_spellings_on_one_string(left: str, right: str) -> None:
    """One engine's markup against another's plain text, over identical copy.

    Without this, a typographic apostrophe against an ASCII one breaks every trigram
    spanning the word — a false split on copy that is character-for-character the
    same page.
    """
    assert dedupe.flatten(left) == dedupe.flatten(right)


def test_a_tag_becomes_a_space_not_nothing() -> None:
    """``a<br>b`` is two words. Deleting the tag would invent the word ``ab``."""
    assert dedupe.flatten("a<br>b") == dedupe.flatten("a b")


def test_flatten_unescapes_to_a_fixpoint() -> None:
    """One pass turns ``&amp;amp;`` into ``&amp;`` rather than ``&``."""
    assert dedupe.flatten("a &amp;amp; b") == dedupe.flatten("a & b")


def test_flatten_is_idempotent() -> None:
    for text in (WIRE, BOILERPLATE, "The <b>Bank</b>&amp;s ’rate’  "):
        assert dedupe.flatten(dedupe.flatten(text)) == dedupe.flatten(text)


def test_a_stray_angle_bracket_does_not_eat_the_snippet() -> None:
    """The tag pattern is length-bounded, so ``<`` without a ``>`` is just a character."""
    assert "rate" in dedupe.flatten("the < rate was held at 4.75% by the committee")


def test_anchors_ignore_a_sentence_initial_capital() -> None:
    """Every sentence has one, so it says nothing about proper nouns."""
    assert dedupe.anchors("Rates were held.") == frozenset()
    assert "bailey" in dedupe.anchors("The governor Bailey spoke.")


def test_anchors_read_figures() -> None:
    """Kept in the text's own spelling: this is an identity to match, not a quantity."""
    assert dedupe.anchors("held at 4.75% on 12 March") >= {"4.75%", "12"}


def test_anchors_are_not_fooled_by_a_bare_title_join() -> None:
    """The measured bug this guards, recorded because it cost the only real defence.

    A title rarely ends in a terminator. Joined to a snippet with a bare space, the
    snippet's first word is left looking mid-sentence — so ``Councillors`` below reads
    as a proper noun rather than as the ordinary word that happens to open the
    paragraph. Every article on a site whose furniture starts the same way then shares
    that anchor, eroding :data:`~app.research.dedupe.MIN_ANCHORS` exactly where it is
    needed. Callers join with ``". "`` for this reason.
    """
    joined = dedupe.anchors(f"{LOCAL_PLANNING_TITLE}. {LOCAL_PLANNING}")
    bare = dedupe.anchors(f"{LOCAL_PLANNING_TITLE} {LOCAL_PLANNING}")

    assert "councillors" not in joined
    assert "councillors" in bare
    # The real anchors are unaffected either way.
    assert {"40", "ashburton"} <= joined & bare
