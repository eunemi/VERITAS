"""Fetching a submitted media URL.

Separate from :mod:`app.providers.http` on purpose: that client decodes every
response as JSON and shares one pooled ``AsyncClient`` across the providers. This
needs raw bytes, a hard size ceiling enforced while reading, and a redirect policy
of its own.

A URL supplied by a caller and then fetched by this server is a request-forgery
primitive — it reaches whatever this process can reach, which includes the cloud
metadata endpoint at ``http://169.254.169.254/`` and this deployment's own database
at ``http://localhost:5432``. :func:`_permitted` is what stands between the two.

"""

from __future__ import annotations

import ipaddress
import re
import socket
from html import unescape
from html.parser import HTMLParser

import anyio.to_thread
import httpx

from app.core.errors import (
    MediaFetchError,
    PayloadTooLargeError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnsupportedMediaTypeError,
    ValidationError,
)

_Address = ipaddress.IPv4Address | ipaddress.IPv6Address

#: Redirects followed by hand, so the guard can run again on each hop.
MAX_REDIRECTS = 3

PROVIDER = "media-fetch"
_UPLOAD_PATH = re.compile(r".*/api/v1/files/media/[0-9a-f]{32}\.[a-z0-9]{1,10}$")


class _PageTextParser(HTMLParser):
    """Collect readable page copy while ignoring executable and presentational markup."""

    _IGNORED = frozenset(
        {"nav", "script", "style", "title", "noscript", "template", "svg"}
    )
    _BLOCKS = frozenset(
        {
            "address",
            "article",
            "aside",
            "blockquote",
            "br",
            "dd",
            "div",
            "dl",
            "dt",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "li",
            "main",
            "nav",
            "ol",
            "p",
            "pre",
            "section",
            "table",
            "td",
            "th",
            "tr",
            "ul",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.content_parts: list[str] = []
        self.fallback_parts: list[str] = []
        self.fallback_content_parts: list[str] = []
        self._ignored = 0
        self._noscript = 0
        self._content_depth = 0

    def _target(self) -> list[str] | None:
        if self._noscript and self._ignored == self._noscript:
            return (
                self.fallback_content_parts
                if self._content_depth
                else self.fallback_parts
            )
        if self._ignored:
            return None
        return self.content_parts if self._content_depth else self.parts

    def _separator(self) -> None:
        target = self._target()
        if target and target[-1:] != [" "]:
            target.append(" ")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "noscript":
            self._noscript += 1
            self._ignored += 1
        elif tag in {"main", "article"}:
            self._content_depth += 1
            self._separator()
        elif tag in self._IGNORED:
            self._ignored += 1
        elif tag in self._BLOCKS:
            self._separator()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "noscript" and self._noscript:
            self._noscript -= 1
            self._ignored -= 1
        elif tag in {"main", "article"} and self._content_depth:
            self._separator()
            self._content_depth -= 1
        elif tag in self._IGNORED and self._ignored:
            self._ignored -= 1
        elif tag in self._BLOCKS:
            self._separator()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._BLOCKS:
            self._separator()

    def handle_data(self, data: str) -> None:
        target = self._target()
        if target is not None and data.strip():
            target.append(data)


def _readable_page_text(data: bytes) -> str:
    """Turn an HTML, JSON, or plain-text response into bounded readable copy."""
    decoded = data.decode("utf-8", errors="replace")
    if "<" not in decoded or ">" not in decoded:
        return " ".join(unescape(decoded).split())

    parser = _PageTextParser()
    try:
        parser.feed(decoded)
        parser.close()
    except Exception:
        # Malformed markup is common on the public web. Returning its decoded text is
        # still more useful to the examination than turning a readable page into a
        # failed verification.
        return " ".join(unescape(decoded).split())
    parts = (
        parser.content_parts
        or parser.fallback_content_parts
        or parser.parts
        or parser.fallback_parts
    )
    return " ".join("".join(parts).split())


async def fetch_text(
    url: str,
    *,
    timeout: float,
    limit: int,
    max_chars: int,
    allow_private: bool = False,
) -> str:
    """Fetch a public page and return only its readable text.

    URL verification uses the same redirect and SSRF protections as media fetching.
    The character ceiling is applied after decoding so a very large HTML response
    cannot send an unbounded prompt to the claim and fact-check desks.
    """
    data = await fetch(
        url,
        timeout=timeout,
        limit=limit,
        accept=("text/", "application/xhtml+xml", "application/json", "application/xml"),
        allow_private=allow_private,
    )
    return _readable_page_text(data)[:max_chars]


def is_managed_upload_url(url: str, *, public_api_url: str) -> bool:
    """Return true only for opaque URLs generated by this API's upload route."""
    return url.startswith(public_api_url.rstrip("/") + "/") and bool(
        _UPLOAD_PATH.fullmatch(url)
    )


async def fetch(
    url: str,
    *,
    timeout: float,
    limit: int,
    accept: tuple[str, ...] = (),
    allow_private: bool = False,
) -> bytes:
    """Fetch ``url`` and return its bytes, or raise.

    ``accept`` is a tuple of permitted media-type prefixes (``("image/",)``), or
    empty to take whatever arrives.

    Redirects are followed manually rather than by httpx, because the guard has to
    run on every hop: an allowed host that answers ``302 Location:
    http://127.0.0.1/`` would otherwise walk straight past it.
    """
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        target = url
        for _ in range(MAX_REDIRECTS + 1):
            await _permitted(target, allow_private=allow_private)
            response = await _send(client, client.build_request("GET", target))
            try:
                location = response.headers.get("location", "")
                if response.is_redirect and location:
                    # Resolved against the URL that answered, so a relative
                    # ``Location`` is joined rather than treated as a host.
                    target = str(response.url.join(location))
                    continue
                return await _read(response, limit=limit, accept=accept)
            finally:
                await response.aclose()

    raise MediaFetchError(
        "The submitted URL redirected too many times.",
        provider=PROVIDER,
        details={"limit": MAX_REDIRECTS},
    )


async def _send(client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    try:
        return await client.send(request, stream=True)
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError(
            "The submitted URL did not respond in time.", provider=PROVIDER
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailableError(
            "The submitted URL could not be reached.",
            provider=PROVIDER,
            details={"reason": type(exc).__name__},
        ) from exc


async def _read(
    response: httpx.Response, *, limit: int, accept: tuple[str, ...] = ()
) -> bytes:
    if response.status_code >= 400:
        raise MediaFetchError(
            f"The submitted URL returned {response.status_code}.",
            provider=PROVIDER,
            details={"status": response.status_code},
        )

    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    if accept and content_type and not content_type.startswith(accept):
        raise UnsupportedMediaTypeError(
            "The URL does not point at a file this desk can read.",
            details={"content_type": content_type, "expected": list(accept)},
        )

    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise PayloadTooLargeError(
            "The file is larger than the configured limit.",
            details={"bytes": int(declared), "limit": limit},
        )

    # The ceiling is enforced against the bytes that actually arrive, not against
    # Content-Length: that header is optional on a chunked response and is not
    # binding on a hostile one. The check above only saves the download.
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise PayloadTooLargeError(
                "The file is larger than the configured limit.",
                details={"limit": limit},
            )
        chunks.append(chunk)

    if not total:
        raise MediaFetchError("The submitted URL returned nothing.", provider=PROVIDER)
    return b"".join(chunks)


async def _permitted(url: str, *, allow_private: bool) -> None:
    """Refuse anything that is not a public http(s) address.

    Every address the host resolves to is checked, not just the first, because a
    name that answers with both a public and a loopback address would otherwise
    pass here and connect to whichever httpx picked.

    What this does *not* close: httpx resolves the name again when it connects, so
    a DNS answer that changes between these two lookups can still slip through.
    Closing that means connecting to an address this function checked and carrying
    the original ``Host`` header — a custom transport, which is a larger change
    than this desk warrants. Stated rather than papered over.
    """
    parsed = httpx.URL(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            "Only http and https URLs are supported.",
            details={"scheme": parsed.scheme},
        )

    host = parsed.host
    if not host:
        raise ValidationError(
            "The submitted URL names no host.", details={"url": url[:200]}
        )

    if allow_private:
        return

    for address in await _resolve(host):
        if not address.is_global or address.is_reserved:
            raise ValidationError(
                "The submitted URL resolves to a non-public address.",
                details={"host": host, "address": str(address)},
            )


async def _resolve(host: str) -> list[_Address]:
    try:
        info = await anyio.to_thread.run_sync(socket.getaddrinfo, host, None)
    except OSError as exc:
        raise MediaFetchError(
            "The submitted URL's host could not be resolved.",
            provider=PROVIDER,
            details={"host": host},
        ) from exc

    found: list[_Address] = []
    for entry in info:
        try:
            found.append(ipaddress.ip_address(entry[4][0]))
        except ValueError:
            continue
    if not found:
        raise MediaFetchError(
            "The submitted URL's host resolved to no usable address.",
            provider=PROVIDER,
            details={"host": host},
        )
    return found
