"""Shared fixtures.

Every fixture builds its own application through :func:`app.main.create_app`, so
no test depends on the module-level ``app`` instance or on the environment the
suite happens to run in.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Environment, Settings, StoreBackend, get_settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Deterministic settings.

    ``_env_file=None`` is the important part: without it these tests would read
    the developer's ``.env`` and pass or fail depending on what is in it.

    ``VERIFICATION_STORE`` is pinned to ``memory`` rather than left at its default.
    The default is the database, and the tests that go through HTTP are testing
    routes, services and the error envelope — none of which should need PostgreSQL
    running to pass. The SQL store has its own tests, against SQLite, in
    ``test_repository_sql.py``.

    ``JWT_SECRET_KEY`` is set because ``ENVIRONMENT=local`` is the one case where
    the config validator does not demand it, and token signing raises rather than
    inventing a key — so without this every auth test fails on configuration
    instead of on behaviour.
    """
    return Settings(
        _env_file=None,
        APP_NAME="Veritas Test API",
        APP_VERSION="9.9.9",
        ENVIRONMENT=Environment.LOCAL,
        DEBUG=True,
        LOG_LEVEL="DEBUG",
        LOG_FORMAT="console",
        CORS_ORIGINS=["http://localhost:3000"],
        VERIFICATION_STORE=StoreBackend.MEMORY,
        JWT_SECRET_KEY="test-signing-key-not-used-anywhere-real",
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """An application wired to the test settings."""
    application = create_app(settings)
    # `create_app` passes settings to the factory, but routes receive them through
    # the `get_settings` dependency, which would otherwise return the cached
    # process settings. Overriding it is what keeps the two consistent.
    application.dependency_overrides[get_settings] = lambda: settings
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client speaking to ``app`` in-process.

    ``raise_app_exceptions=False`` makes this behave like a real client: Starlette
    re-raises after its 500 handler has already sent a response, and with the
    default of ``True`` the exception would surface here instead of the response
    body a caller would actually receive. Testing the error envelope requires
    seeing what goes over the wire.
    """
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture(scope="session")
def nlp_resources() -> object:
    """The loaded spaCy pipeline, or a skip.

    Two separate reasons to skip, and both are ordinary rather than a broken
    checkout: the libraries may not be installed, and the spaCy model is a separate
    download that ``pip install -r requirements-dev.txt`` does not fetch. Tests that
    use this fixture are the ones that genuinely need a parser; everything above
    :mod:`app.nlp` is tested against a stub and always runs.

    Session-scoped because loading the model takes the better part of a second and
    it is immutable once loaded — :mod:`app.nlp.resources` caches it process-wide
    anyway, so a narrower scope would buy nothing but a slower suite.
    """
    pytest.importorskip("spacy", reason="spaCy is not installed")
    from app.core.errors import ConfigurationError
    from app.nlp.resources import load

    try:
        return load("en_core_web_sm")
    except ConfigurationError as exc:  # the model, not the library
        pytest.skip(str(exc))

