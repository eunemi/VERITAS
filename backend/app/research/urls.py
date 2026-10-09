"""Deciding when two URLs are the same page, and which publisher a URL belongs to.

Two questions, both load-bearing, both with an asymmetric cost of being wrong.

**Is this the same page?** Answering yes when the answer is no merges two results
into one and *deletes a source the provider actually returned* — fabrication by
omission, the worst outcome available to this module. So :func:`normalise` only
ever discards things that provably cannot change which document a server sends:
the fragment, a default port, an analytics parameter. It never strips a query
wholesale. ``youtube.com/watch?v=A`` and ``youtube.com/watch?v=B`` are different
videos, and a blanket query strip makes them one row with one of the two
identities thrown away.

**Whose page is it?** Answering wrongly miscounts independence, and here the
dangerous direction is the opposite one. A Google AMP cache URL is spelled
``www-bbc-co-uk.cdn.ampproject.org/c/s/www.bbc.co.uk/…``: left alone its
registrable domain is ``ampproject.org``, so the BBC carrying a story once looks
like *two* publishers carrying it, and corroboration reads stronger than the
evidence supports. :func:`unwrap` exists for that, and it runs before anything
else.

The general shape, then: :func:`unwrap` recovers the real URL from a mirror,
:func:`normalise` reduces it to one identity per document, and
:func:`registrable_domain` names the publisher. :func:`date_from_path` is the last
resort for a date, and is labelled as a derivation wherever it is used.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from app.research.suffixes import MAX_SUFFIX_LABELS, SUFFIXES, WILDCARD_TLDS

__all__ = [
    "SAME_PAGE_PREFIXES",
    "TRACKING_PARAMS",
    "date_from_path",
    "host_of",
    "normalise",
    "registrable_domain",
    "unwrap",
]

# ------------------------------------------------------------------- tracking ----

#: Query parameters that identify *how a reader arrived*, never *what they arrive
#: at*, and can therefore be dropped without changing which document is served.
#:
#: The membership rule is deliberately strict, because the cost of a wrong entry
#: is a deleted source. A parameter goes in only when it cannot select content.
#: That is why ``cid``, ``id``, ``p``, ``page``, ``v``, ``s`` and ``q`` are
#: absent despite looking like tracking on some sites: on others they are the
#: article key, and there is no way to tell from the URL alone. Under-stripping
#: leaves two rows for one page, which is visible and harmless. Over-stripping
#: silently loses one of them.
TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        # Google Analytics and the wider UTM convention. `utm_` is also matched as a
        # prefix below, which covers the long tail (`utm_id`, `utm_source_platform`).
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_name",
        "utm_cid",
        "utm_reader",
        "utm_viz_id",
        "utm_pubreferrer",
        "utm_swu",
        "utm_brand",
        # Ad-click identifiers. Every one of these is stamped on by the ad network.
        "gclid",
        "gclsrc",
        "dclid",
        "gbraid",
        "wbraid",
        "fbclid",
        "msclkid",
        "twclid",
        "ttclid",
        "li_fat_id",
        "igshid",
        "igsh",
        "yclid",
        "rdt_cid",
        "epik",
        "s_kwcid",
        "_bhlid",
        # Email and marketing automation.
        "mc_cid",
        "mc_eid",
        "_hsenc",
        "_hsmi",
        "hsctatracking",
        "vero_conv",
        "vero_id",
        "oly_anon_id",
        "oly_enc_id",
        "ck_subscriber_id",
        "mkt_tok",
        # Referrer breadcrumbs. Not `source`, which some CMSes use for content.
        "ref",
        "referer",
        "referrer",
        "_openstat",
        "__twitter_impression",
        # Publisher-specific campaign tags, all analytics.
        "at_medium",
        "at_campaign",
        "at_campaign_type",
        "at_custom1",
        "at_custom2",
        "at_custom3",
        "at_custom4",
        "at_link_id",
        "at_link_origin",
        "at_link_type",
        "at_ptr_name",
        "at_bbc_team",
        "ns_campaign",
        "ns_mchannel",
        "ns_source",
        "ns_linkname",
        "ns_fee",
        "cmpid",
        "cmp",
        "ito",
        "smid",
        "smtyp",
        "partner",
        "ncid",
        "sh",
        "srnd",
        "taid",
        "reflink",
        "guccounter",
        "guce_referrer",
        "guce_referrer_sig",
        "xtor",
        "wt.mc_id",
        "wtmc",
        "spm",
        "scm",
        "share_id",
        "campaign_id",
        "ad_id",
        "adset_id",
        "fb_action_ids",
        "fb_action_types",
        "fb_source",
        # AMP plumbing. Dropping these turns the AMP rendering of an article into
        # the article, which is the whole point of handling AMP at all.
        "amp",
        "_amp",
        "outputtype",
        "output",
        "usqp",
        "amp_js_v",
        "amp_gsa",
        "amp_ct",
        "amp_tf",
    }
)

#: Prefixes matched in addition to the exact names above.
_TRACKING_PREFIXES: tuple[str, ...] = (
    "utm_",
    "at_custom",
    "at_link",
    "pk_",
    "piwik_",
    "matomo_",
    "_ga",
    "_gl",
    "_x_tr_",
    "hsa_",
    "vgo_",
)

#: Leftmost host labels that name a *rendering* of a site rather than a different
#: site, so ``www.bbc.co.uk``, ``m.bbc.co.uk`` and ``amp.bbc.co.uk`` are one page.
#:
#: Stripped for identity only. :attr:`app.domain.research.Source.host` keeps what
#: the provider actually sent, because the subdomain is often the section and a
#: reader wants to see it.
SAME_PAGE_PREFIXES: frozenset[str] = frozenset(
    {"www", "www1", "www2", "www3", "m", "mobile", "amp", "en-amp"}
)

# ----------------------------------------------------------------- unwrapping ----

#: Google's AMP cache. The origin host is the leftmost label with dots written as
#: single hyphens, and the origin URL is repeated in the path after ``/c/s/``.
_AMP_CACHE = re.compile(r"\.cdn\.ampproject\.org$", re.IGNORECASE)

#: Google Translate's proxy, which uses the same host encoding as the AMP cache.
_TRANSLATE = re.compile(r"\.translate\.goog$", re.IGNORECASE)

#: The AMP cache path prefixes: ``c`` for the cache, ``v`` for the viewer, and
#: ``s`` present when the origin was HTTPS.
_AMP_PATH = re.compile(r"^/(?:[cv])/(?:s/)?(?P<rest>.+)$")


def unwrap(url: str) -> str:
    """Recover the original URL from a mirror that serves someone else's page.

    Runs before :func:`normalise` and before any domain is read, because an
    unwrapped mirror is attributed to the wrong publisher — and attributing one
    publisher's story to two is the error that makes a dossier overstate its own
    corroboration.

    Idempotent, and a no-op for anything it does not recognise: an unrecognised
    URL is returned unchanged rather than guessed at. Nested mirrors are followed
    to a fixed point, bounded, since an AMP cache URL of a translate URL is
    possible and a cycle must not be.
    """
    for _ in range(3):
        unwrapped = _unwrap_once(url)
        if unwrapped == url:
            return url
        url = unwrapped
    return url


def _unwrap_once(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""

    if _AMP_CACHE.search(host):
        # The path carries the origin URL verbatim, which is more reliable than
        # decoding the host, so prefer it and fall back to the host encoding.
        match = _AMP_PATH.match(parts.path)
        if match:
            rest = match.group("rest")
            query = f"?{parts.query}" if parts.query else ""
            if rest.startswith(("http://", "https://")):
                return rest + query
            return f"https://{rest}{query}"
        origin = _decode_mirror_host(host.rsplit(".cdn.ampproject.org", 1)[0])
        if origin:
            return urlunsplit(("https", origin, parts.path, parts.query, ""))

    if _TRANSLATE.search(host):
        origin = _decode_mirror_host(host.rsplit(".translate.goog", 1)[0])
        if origin:
            # `_x_tr_*` are the proxy's own parameters and are dropped by
            # `_TRACKING_PREFIXES`; leaving them here would be harmless but
            # noisy.
            return urlunsplit(("https", origin, parts.path, parts.query, ""))

    return url


def _decode_mirror_host(label: str) -> str | None:
    """``www-bbc-co-uk`` -> ``www.bbc.co.uk``; ``a--b-com`` -> ``a-b.com``.

    Google's encoding for both the AMP cache and the translate proxy: a dot
    becomes one hyphen and a literal hyphen is doubled. Decoded left to right so
    the two cannot be confused.

    Returns ``None`` for anything that does not decode to a plausible hostname,
    rather than a best guess — a wrong origin host would attribute a page to a
    publisher that never published it.
    """
    if not label or "." in label:
        return None
    out: list[str] = []
    index = 0
    while index < len(label):
        if label[index] == "-":
            if index + 1 < len(label) and label[index + 1] == "-":
                out.append("-")
                index += 2
                continue
            out.append(".")
            index += 1
            continue
        out.append(label[index])
        index += 1
    host = "".join(out)
    if "." not in host or host.startswith((".", "-")) or host.endswith((".", "-")):
        return None
    if ".." in host or not all(part for part in host.split(".")):
        return None
    return host


# ---------------------------------------------------------------- normalising ----


def host_of(url: str) -> str | None:
    """The lower-cased host, or ``None`` when there is not one to read.

    ``None`` for a relative URL, a ``mailto:``, a malformed authority — anything
    that cannot be attributed to a publisher. Callers drop those results rather
    than inventing a host for them.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    try:
        host = parts.hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.rstrip(".").lower()
    return host or None


def normalise(url: str) -> str | None:
    """One identity per document, for deduplication.

    ``None`` when the URL is not an addressable web page, which is the signal to
    discard the result: a source with no usable URL cannot be checked by a reader,
    and an unusable URL is not worth a row.

    What changes, and why each is safe — every one of these provably cannot alter
    which document a server returns:

    * scheme to ``https``, since a site serving both serves one article;
    * host lower-cased, trailing dot removed, and a rendering prefix from
      :data:`SAME_PAGE_PREFIXES` dropped;
    * a default port removed;
    * ``.`` and ``..`` path segments resolved, percent-escapes of unreserved
      characters decoded, remaining escapes upper-cased — all required by
      RFC 3986 to be equivalent;
    * one trailing slash dropped, and a trailing ``/amp`` segment with it;
    * parameters in :data:`TRACKING_PARAMS` dropped, the rest sorted;
    * the fragment dropped — *unless* it is a hashbang or a route (``#!``,
      ``#/``), which older single-page sites use to select content, and which
      therefore cannot be discarded without risking a merge of two documents.

    What deliberately does not change: path case (RFC 3986 makes paths
    case-sensitive and some CMSes mean it), any query parameter not on the
    deny-list, and a non-default port.
    """
    if not (host := host_of(url)):
        return None
    parts = urlsplit(url)

    for prefix in SAME_PAGE_PREFIXES:
        candidate = host.removeprefix(f"{prefix}.")
        if candidate != host and "." in candidate:
            host = candidate
            break

    port = parts.port
    authority = host if port in (None, 80, 443) else f"{host}:{port}"

    path = _normalise_path(parts.path)
    query = _normalise_query(parts.query)
    fragment = parts.fragment if parts.fragment.startswith(("!", "/")) else ""

    return urlunsplit(("https", authority, path, query, fragment))


def _normalise_path(path: str) -> str:
    """Resolve dot segments, canonicalise escaping, drop a trailing slash."""
    segments: list[str] = []
    for segment in path.split("/"):
        if segment == ".":
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(_recode(segment))

    resolved = "/".join(segments)
    if not resolved.startswith("/"):
        resolved = f"/{resolved}"

    # An `/amp` leaf is a rendering of the article above it, not another article.
    if resolved.endswith("/amp"):
        resolved = resolved[: -len("/amp")]
    elif resolved.endswith("/amp/"):
        resolved = resolved[: -len("/amp/")]

    if len(resolved) > 1 and resolved.endswith("/"):
        resolved = resolved.rstrip("/") or "/"
    return resolved or "/"


def _recode(segment: str) -> str:
    """Decode escapes of unreserved characters; leave everything else escaped.

    RFC 3986 §6.2.2.2: ``%7E`` and ``~`` are the same URL. Re-encoding through
    :func:`quote` with the unreserved set produces upper-case hex for whatever
    genuinely needs escaping, which §6.2.2.1 also requires. Round-tripping like
    this rather than upper-casing in place is what makes ``%7e`` and ``~`` land on
    one identity instead of two.
    """
    return quote(unquote(segment), safe="~!$&'()*+,;=:@")


def _normalise_query(query: str) -> str:
    """Drop analytics parameters, sort what is left.

    Sorted because parameter order does not select a document, so two orderings
    of one query must not become two rows. Blank-valued parameters are kept:
    ``?print`` and ``?print=`` are how some CMSes switch rendering, and a caller
    following the link needs them.
    """
    if not query:
        return ""
    kept = [
        (name, value)
        for name, value in parse_qsl(query, keep_blank_values=True)
        if not _is_tracking(name)
    ]
    return urlencode(sorted(kept), doseq=False)


def _is_tracking(name: str) -> bool:
    lowered = name.lower()
    return lowered in TRACKING_PARAMS or lowered.startswith(_TRACKING_PREFIXES)


# --------------------------------------------------------------------- domain ----


def registrable_domain(host: str) -> str:
    """The publisher-identifying part of ``host``.

    ``www.bbc.co.uk`` -> ``bbc.co.uk``. ``alice.substack.com`` ->
    ``alice.substack.com``, because on a multi-tenant host the subdomain *is* the
    publisher — see :mod:`app.research.suffixes` for why that distinction is
    drawn there and what the table's known gaps cost.

    The rule is the Public Suffix List algorithm, over a curated table: take the
    longest suffix that matches, and keep one more label. Degenerate inputs are
    returned as they came rather than trimmed into something that looks like a
    domain:

    * an IP literal, which has no registrable domain and no publisher;
    * a bare host with no dot, ``localhost``;
    * a host that *is* a suffix, ``co.uk``, where there is no label to keep.

    Each of those is a real thing a search result can contain, and each is left
    intact so a caller can see what it got. Counting them as publishers is
    correct in the only sense available: they are distinguishable from each other.
    """
    host = host.rstrip(".").lower()
    if not host or _is_ip(host):
        return host

    labels = host.split(".")
    if len(labels) < 2:
        return host

    # Longest match first, so `blogspot.co.uk` beats `co.uk` and yields the
    # author rather than Blogger.
    for size in range(min(MAX_SUFFIX_LABELS, len(labels)), 0, -1):
        candidate = ".".join(labels[-size:])
        if candidate in SUFFIXES:
            if len(labels) == size:
                return host
            return ".".join(labels[-(size + 1) :])

    # `*.bd` and friends: every second-level label is a suffix, so the
    # registrable domain is three labels deep.
    if labels[-1] in WILDCARD_TLDS:
        if len(labels) <= 2:
            return host
        return ".".join(labels[-3:])

    return ".".join(labels[-2:])


def _is_ip(host: str) -> bool:
    """IPv4 dotted-quad or a bracket-stripped IPv6 literal.

    :func:`urllib.parse.urlsplit` has already removed the brackets from an IPv6
    authority, so a colon is the only thing left to recognise it by.
    """
    if ":" in host:
        return True
    parts = host.split(".")
    return len(parts) == 4 and all(
        part.isdigit() and len(part) <= 3 and int(part) <= 255 for part in parts
    )


# ----------------------------------------------------------------------- date ----

#: A dated path: ``/2017/08/30/``, ``/2017-08-30/`` or ``/20170830/``, anchored to
#: segment boundaries so a bare id like ``/20170830123/`` is not read as a date and
#: ``/1234/56/78/`` is rejected by the range checks below.
_PATH_DATE = re.compile(
    r"/(?P<y>19\d{2}|20\d{2})"
    r"(?:/(?P<m1>0[1-9]|1[0-2])/(?P<d1>0[1-9]|[12]\d|3[01])"
    r"|-(?P<m2>0[1-9]|1[0-2])-(?P<d2>0[1-9]|[12]\d|3[01])"
    r"|(?P<m3>0[1-9]|1[0-2])(?P<d3>0[1-9]|[12]\d|3[01]))"
    r"(?=[/\-_.]|$)"
)


def date_from_path(url: str, *, now: datetime) -> datetime | None:
    """A publication date read out of a dated URL path, or ``None``.

    The last resort, used only when no provider reported a date — which, for at
    least one of the three, is always. News URLs carry the date far more often
    than search APIs report one, so this recovers a great deal, and it recovers it
    honestly: this is a fact about the URL a provider returned, not a claim by the
    publisher, and every caller records it as
    :attr:`~app.domain.research.DateBasis.URL_PATH` so a reader can weigh it
    accordingly.

    Deliberately narrow. Only a full year-month-day is accepted — a ``/2017/08/``
    archive path would have to be resolved to a day that nobody stated, and an
    invented day is exactly the kind of small fabrication that is hard to notice
    and impossible to defend. Only a date at or before ``now`` is accepted, since
    a future date is a path that resembles one rather than one; ``now`` is passed
    in rather than read from the clock so the decision is reproducible and
    testable.

    Returns midnight UTC. That is a *precision* claim, not a timezone claim: the
    URL gives a day, and the time within it is unknown. Consumers that display a
    date should prefer :attr:`~app.domain.research.Source.date_text` when the
    basis is not :attr:`~app.domain.research.DateBasis.PROVIDER`, and use
    ``published_at`` for ordering.
    """
    path = urlsplit(url).path
    match = _PATH_DATE.search(path)
    if not match:
        return None

    groups = match.groupdict()
    month = groups["m1"] or groups["m2"] or groups["m3"]
    day = groups["d1"] or groups["d2"] or groups["d3"]
    try:
        found = datetime(int(groups["y"]), int(month), int(day), tzinfo=UTC)
    except ValueError:
        # 31 February and friends: a real-looking pattern that is not a date.
        return None

    return found if found <= now else None
