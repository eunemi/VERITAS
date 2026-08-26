"""Fetching a submitted media URL.

Separate from :mod:`app.providers.http` on purpose: that client decodes every
response as JSON and shares one pooled ``AsyncClient`` across the providers. This
needs raw bytes, a hard size ceiling enforced while reading, and a redirect policy
of its own.

A URL supplied by a caller and then fetched by this server is a request-forgery
primitive — it reaches whatever this process can reach, which includes the cloud
metadata endpoint at ``http://169.254.169.254/`` and this deployment's own database
at ``http://localhost:5432``. :func:`_permitted` is what stands between the two.

One module for every media kind rather than one per desk. The image desk and the
audio desk differ only in the ``accept`` prefixes they pass, and the guard above is
the part that must not exist twice.
"""

from __future__ import annotations

import ipaddress
import socket

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
    empty to take whatever arrives. It is a prefix rather than an exact type
    because a container's media type is not a reliable discriminator — the same
    ``.mp4`` is served as ``video/mp4`` by one host and ``audio/mp4`` by another.

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
