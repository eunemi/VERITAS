"""The application's exception hierarchy.

Everything raised deliberately by application code derives from
:class:`VeritasError`. Each error carries the three things an HTTP layer needs to
render it — a stable machine-readable ``code``, a human ``message``, and a status
— which is what lets :mod:`app.core.exception_handlers` translate any of them
without a chain of ``isinstance`` checks.

Domain code raises these. It does not raise ``HTTPException``: keeping FastAPI's
transport exception out of services and pipelines is what allows those layers to
be tested, and later reused off the web, without importing a web framework.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any


class VeritasError(Exception):
    """Base class for every deliberate application failure.

    Subclasses set ``code`` and ``status``; call sites supply ``message`` and, if
    useful to a client, ``details``.
    """

    #: Stable identifier clients may branch on. Snake case, never reworded.
    code: str = "internal_error"
    #: HTTP status the API layer should use for this class of failure.
    status: int = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.__class__.__doc__ or self.code
        self.details = details or {}
        super().__init__(self.message)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# --------------------------------------------------------------- client ----


class ValidationError(VeritasError):
    """The request was understood but its contents are not usable."""

    code = "validation_error"
    status = HTTPStatus.UNPROCESSABLE_ENTITY


class NotFoundError(VeritasError):
    """The requested resource does not exist."""

    code = "not_found"
    status = HTTPStatus.NOT_FOUND


class AuthenticationError(VeritasError):
    """The request carried no usable credentials."""

    code = "authentication_failed"
    status = HTTPStatus.UNAUTHORIZED


class AuthorizationError(VeritasError):
    """The credentials are valid but do not permit this action."""

    code = "permission_denied"
    status = HTTPStatus.FORBIDDEN


class RateLimitError(VeritasError):
    """Too many requests. Retry after backing off."""

    code = "rate_limited"
    status = HTTPStatus.TOO_MANY_REQUESTS


class PayloadTooLargeError(VeritasError):
    """The submitted artifact exceeds the configured size limit."""

    code = "payload_too_large"
    status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE


class UnsupportedMediaTypeError(VeritasError):
    """The submitted artifact is of a type no desk can examine."""

    code = "unsupported_media_type"
    status = HTTPStatus.UNSUPPORTED_MEDIA_TYPE


# --------------------------------------------------------------- server ----


class ConfigurationError(VeritasError):
    """A required setting is missing or contradictory."""

    code = "configuration_error"
    status = HTTPStatus.INTERNAL_SERVER_ERROR


class ProviderError(VeritasError):
    """An external provider failed.

    Base class for the outbound integrations. ``provider`` names which one, so a
    log line or error body identifies the dependency without the caller having
    to parse the message.
    """

    code = "provider_error"
    status = HTTPStatus.BAD_GATEWAY

    def __init__(
        self,
        message: str | None = None,
        *,
        provider: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = dict(details or {})
        if provider is not None:
            merged.setdefault("provider", provider)
        self.provider = provider
        super().__init__(message, details=merged)


class ProviderTimeoutError(ProviderError):
    """An external provider did not respond within its timeout."""

    code = "provider_timeout"
    status = HTTPStatus.GATEWAY_TIMEOUT


class ProviderUnavailableError(ProviderError):
    """An external provider is configured but not reachable."""

    code = "provider_unavailable"
    status = HTTPStatus.SERVICE_UNAVAILABLE


class LLMError(ProviderError):
    """The language model call failed."""

    code = "llm_error"


class SearchError(ProviderError):
    """The web search call failed."""

    code = "search_error"


class FactCheckError(ProviderError):
    """The fact-check database call failed."""

    code = "fact_check_error"


class VectorStoreError(ProviderError):
    """The vector store call failed."""

    code = "vector_store_error"


class MediaFetchError(ProviderError):
    """A submitted media URL could not be fetched.

    A provider error rather than a validation one: the URL was well-formed and
    permitted, and what failed was the host at the other end of it. A caller who
    submitted a link that has since gone dead needs to see that distinction.
    """

    code = "media_fetch_error"


class StorageError(VeritasError):
    """Persistence failed."""

    code = "storage_error"
    status = HTTPStatus.INTERNAL_SERVER_ERROR


class PipelineError(VeritasError):
    """A verification pipeline could not complete."""

    code = "pipeline_error"
    status = HTTPStatus.INTERNAL_SERVER_ERROR


class NotImplementedYetError(VeritasError):
    """The seam exists but has no implementation behind it yet.

    Used by the provider and desk stubs that this foundation ships with. It is a
    distinct type so that "not built" is never confused with "broken", either in
    logs or by a client.
    """

    code = "not_implemented"
    status = HTTPStatus.NOT_IMPLEMENTED
