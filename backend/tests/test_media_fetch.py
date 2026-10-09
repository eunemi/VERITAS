"""The media fetch, and the request-forgery guard that is the point of it.

A URL supplied by a caller and then fetched by this server reaches whatever this
process can reach: the cloud metadata endpoint at ``http://169.254.169.254/``, this
deployment's own database at ``http://localhost:5432``, anything else inside the
network boundary. :func:`app.media.fetch._permitted` is what stands between the two,
and most of this file is about it.

Nothing here opens a socket. Name resolution is substituted, so the address a host
"resolves" to is chosen by the test — which is the only way to exercise the refusal
paths without either a live DNS answer for a private address or a test that quietly
passes because the lookup failed for an unrelated reason. The redirect tests
substitute the send, so the hop sequence is scripted rather than served.

The rule with the most leverage is :func:`test_a_redirect_to_loopback_is_refused`:
redirects are followed by hand precisely so the guard runs again on every hop, and
an allowed host answering ``302 Location: http://127.0.0.1/`` is the shape of the
attack that a single up-front check does not stop.
"""

from __future__ import annotations

import ipaddress

import httpx
import pytest

from app.core.errors import (
    MediaFetchError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from app.media import fetch as module
from app.media.fetch import MAX_REDIRECTS, _permitted, _read, fetch

#: A perfectly ordinary public address, for the cases that should be allowed.
PUBLIC = ["93.184.216.34"]

#: Addresses that must never be fetched, and why each one is on the list.
REFUSED = {
    "loopback": "127.0.0.1",
    "cloud metadata": "169.254.169.254",
    "rfc1918 private": "10.0.0.7",
    "home network": "192.168.1.10",
    "carrier grade nat": "100.64.0.1",
    "ipv6 loopback": "::1",
    "ipv6 unique local": "fd00::1",
}


@pytest.fixture
def resolves(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Substitute name resolution with a table the test writes.

    Returned as a mutable dict so a test can say what a host answers with. Anything
    not in the table resolves to :data:`PUBLIC`, so a test that only cares about
    the read path does not have to populate it.
    """
    table: dict[str, list[str]] = {}

    async def resolve(host: str) -> list[object]:
        return [ipaddress.ip_address(a) for a in table.get(host, PUBLIC)]

    monkeypatch.setattr(module, "_resolve", resolve)
    return table


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every URL the client was asked for, answering each from ``SCRIPT``.

    Substituting the send rather than injecting a transport, because
    :func:`app.media.fetch.fetch` builds its own client on purpose — it needs a
    redirect policy httpx cannot express — and a transport parameter would be
    production surface whose only caller is a test.
    """
    urls: list[str] = []

    async def send(client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        status, headers, body = SCRIPT.pop(0)
        return httpx.Response(status, headers=headers, content=body, request=request)

    monkeypatch.setattr(module, "_send", send)
    SCRIPT.clear()
    return urls


#: Responses the substituted send returns, in order: ``(status, headers, body)``.
SCRIPT: list[tuple[int, dict[str, str], bytes]] = []


def responds(
    status: int = 200,
    *,
    content_type: str | None = "image/png",
    body: bytes = b"\x89PNG\r\n\x1a\n",
    length: int | None = None,
    location: str | None = None,
) -> None:
    """Queue one response for the substituted send."""
    headers: dict[str, str] = {}
    if content_type is not None:
        headers["content-type"] = content_type
    if length is not None:
        headers["content-length"] = str(length)
    if location is not None:
        headers["location"] = location
    SCRIPT.append((status, headers, body))


def served(
    *,
    content_type: str | None = "image/png",
    body: bytes = b"\x89PNG\r\n\x1a\n",
    length: int | None = None,
    status: int = 200,
) -> httpx.Response:
    """A response to hand straight to :func:`app.media.fetch._read`."""
    headers: dict[str, str] = {}
    if content_type is not None:
        headers["content-type"] = content_type
    if length is not None:
        headers["content-length"] = str(length)
    return httpx.Response(status, headers=headers, content=body)


# ================================================================== the guard ====


async def test_a_public_address_is_allowed(resolves: dict[str, list[str]]) -> None:
    """The baseline. Without this the refusals below could all be false positives."""
    await _permitted("https://example.test/a.png", allow_private=False)


@pytest.mark.parametrize(
    ("why", "address"), sorted(REFUSED.items()), ids=sorted(REFUSED)
)
async def test_a_non_public_address_is_refused(
    resolves: dict[str, list[str]], why: str, address: str
) -> None:
    """One case per address family, so a failure names which one got through.

    ``169.254.169.254`` is the one to read twice: on every major cloud it serves
    this instance's credentials to anything that asks, and a server that fetches
    submitted URLs is exactly something that asks.
    """
    resolves["host.test"] = [address]

    with pytest.raises(ValidationError, match="non-public address"):
        await _permitted("https://host.test/a.png", allow_private=False)


async def test_every_address_a_host_answers_with_is_checked(
    resolves: dict[str, list[str]],
) -> None:
    """A name answering with one public and one loopback address is refused.

    Checking only the first would pass here and then connect to whichever address
    httpx picked — which is not a decision this guard gets to delegate.
    """
    resolves["both.test"] = ["93.184.216.34", "127.0.0.1"]

    with pytest.raises(ValidationError, match="non-public address"):
        await _permitted("https://both.test/a.png", allow_private=False)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://host.test/1"])
async def test_only_http_urls_are_fetched(
    resolves: dict[str, list[str]], url: str
) -> None:
    """``file://`` would read this server's disk through the image desk."""
    with pytest.raises(ValidationError, match="http and https"):
        await _permitted(url, allow_private=False)


async def test_a_url_naming_no_host_is_refused(
    resolves: dict[str, list[str]],
) -> None:
    with pytest.raises(ValidationError, match="names no host"):
        await _permitted("http:///a.png", allow_private=False)


async def test_allowing_private_hosts_skips_resolution_entirely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The setting exists for a developer running MinIO on localhost.

    It short-circuits before the lookup rather than after it, which is what makes
    the escape hatch work offline — and is asserted here so nobody reorders the two
    and leaves a deployment resolving names it was told not to care about.
    """
    calls: list[str] = []

    async def resolve(host: str) -> list[object]:
        calls.append(host)
        return []

    monkeypatch.setattr(module, "_resolve", resolve)

    await _permitted("http://localhost:9000/bucket/a.png", allow_private=True)

    assert calls == []


async def test_a_host_that_does_not_resolve_is_a_fetch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not a validation error: the URL was well formed, the lookup failed."""

    async def resolve(host: str) -> list[object]:
        raise MediaFetchError("nope", provider="media-fetch")

    monkeypatch.setattr(module, "_resolve", resolve)

    with pytest.raises(MediaFetchError):
        await _permitted("https://nowhere.test/a.png", allow_private=False)


# =================================================================== redirects ====


async def test_a_redirect_is_followed(
    resolves: dict[str, list[str]], sent: list[str]
) -> None:
    responds(302, location="https://cdn.test/a.png", content_type=None, body=b"")
    responds(body=b"the image")

    found = await fetch("https://example.test/a.png", timeout=5.0, limit=1024)

    assert found == b"the image"
    assert sent == ["https://example.test/a.png", "https://cdn.test/a.png"]


async def test_a_redirect_to_loopback_is_refused(
    resolves: dict[str, list[str]], sent: list[str]
) -> None:
    """The reason redirects are followed by hand instead of by httpx.

    An allowed host answers ``302 Location: http://127.0.0.1:5432/`` and the guard
    has to run again before the second request is made. With
    ``follow_redirects=True`` httpx would make that request inside ``send`` and this
    function would never see the hop.
    """
    resolves["internal.test"] = ["127.0.0.1"]
    responds(302, location="http://internal.test:5432/", content_type=None, body=b"")

    with pytest.raises(ValidationError, match="non-public address"):
        await fetch("https://example.test/a.png", timeout=5.0, limit=1024)

    assert sent == ["https://example.test/a.png"]


async def test_a_relative_location_is_joined_not_treated_as_a_host(
    resolves: dict[str, list[str]], sent: list[str]
) -> None:
    responds(301, location="/moved/a.png", content_type=None, body=b"")
    responds(body=b"the image")

    await fetch("https://example.test/original.png", timeout=5.0, limit=1024)

    assert sent[1] == "https://example.test/moved/a.png"


async def test_a_redirect_loop_stops(
    resolves: dict[str, list[str]], sent: list[str]
) -> None:
    """Bounded rather than trusting the far end to stop."""
    for _ in range(MAX_REDIRECTS + 1):
        responds(
            302, location="https://example.test/again.png", content_type=None, body=b""
        )

    with pytest.raises(MediaFetchError, match="redirected too many times"):
        await fetch("https://example.test/a.png", timeout=5.0, limit=1024)

    assert len(sent) == MAX_REDIRECTS + 1


async def test_a_redirect_without_a_location_is_read_as_a_response(
    resolves: dict[str, list[str]], sent: list[str]
) -> None:
    """A 302 with no ``Location`` is a broken response, not a hop to nowhere."""
    responds(302, body=b"")

    with pytest.raises(MediaFetchError, match="returned nothing"):
        await fetch("https://example.test/a.png", timeout=5.0, limit=1024)


# ==================================================================== reading ====


async def test_the_bytes_arrive_intact() -> None:
    assert await _read(served(body=b"\x89PNG\r\n\x1a\nbody"), limit=1024) == (
        b"\x89PNG\r\n\x1a\nbody"
    )


async def test_an_error_status_is_reported_with_the_status() -> None:
    with pytest.raises(MediaFetchError, match="returned 404") as caught:
        await _read(served(status=404, body=b"not found"), limit=1024)

    assert caught.value.details["status"] == 404


async def test_a_media_type_outside_the_accepted_prefixes_is_refused() -> None:
    """An HTML error page served with a 200 is the common case here."""
    with pytest.raises(UnsupportedMediaTypeError) as caught:
        await _read(
            served(content_type="text/html", body=b"<html>"),
            limit=1024,
            accept=("image/",),
        )

    assert caught.value.details["content_type"] == "text/html"


async def test_the_check_is_a_prefix_not_an_exact_type() -> None:
    """Which is what lets one audio desk accept both families of container.

    The same ``.mp4`` is served as ``video/mp4`` by one host and ``audio/mp4`` by
    another, so an exact-type list would reject working files.
    """
    found = await _read(
        served(content_type="video/mp4", body=b"ftyp"),
        limit=1024,
        accept=("audio/", "video/"),
    )
    assert found == b"ftyp"


async def test_a_parameterised_media_type_still_matches() -> None:
    """``image/jpeg; charset=binary`` is an image."""
    found = await _read(
        served(content_type="image/jpeg; charset=binary", body=b"\xff\xd8"),
        limit=1024,
        accept=("image/",),
    )
    assert found == b"\xff\xd8"


async def test_no_accepted_prefixes_takes_whatever_arrives() -> None:
    found = await _read(served(content_type="application/octet-stream"), limit=1024)
    assert found


async def test_a_missing_media_type_is_not_treated_as_a_wrong_one() -> None:
    """Some hosts omit the header. Refusing on absence would reject working files,
    and the decoder is what decides whether the bytes are usable anyway."""
    found = await _read(
        served(content_type=None, body=b"\x89PNG"), limit=1024, accept=("image/",)
    )
    assert found == b"\x89PNG"


async def test_a_declared_length_over_the_limit_is_refused_before_reading() -> None:
    """The cheap check: it saves the download rather than enforcing the ceiling."""
    with pytest.raises(PayloadTooLargeError) as caught:
        await _read(served(body=b"x" * 10, length=50_000_000), limit=1024)

    assert caught.value.details["bytes"] == 50_000_000


async def test_the_ceiling_is_enforced_against_the_bytes_that_arrive() -> None:
    """The binding check.

    ``Content-Length`` is optional on a chunked response and is not binding on a
    hostile one, so a body that lies about its size — or says nothing — still has to
    stop at the limit.
    """
    with pytest.raises(PayloadTooLargeError):
        await _read(served(body=b"x" * 4096), limit=1024)


async def test_a_body_at_exactly_the_limit_is_allowed() -> None:
    """The comparison is ``>``, so the configured limit is inclusive."""
    assert await _read(served(body=b"x" * 1024), limit=1024) == b"x" * 1024


async def test_an_empty_body_is_a_fetch_error() -> None:
    """Zero bytes is not an image with no text in it; it is a failed fetch."""
    with pytest.raises(MediaFetchError, match="returned nothing"):
        await _read(served(body=b""), limit=1024)
