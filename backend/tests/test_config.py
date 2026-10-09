"""Configuration parsing and the guards that stop a bad deploy from starting."""

from __future__ import annotations

import pytest

from app.core.config import (
    Environment,
    LLMProvider,
    Settings,
    get_settings,
)
from app.core.errors import ConfigurationError

#: Cleared before each test so a value in the developer's shell cannot decide the
#: outcome. `_env_file=None` covers the file; this covers the process.
OVERRIDABLE = (
    "ENVIRONMENT",
    "DEBUG",
    "CORS_ORIGINS",
    "JWT_SECRET_KEY",
    "LOG_FORMAT",
    "LOG_LEVEL",
)

REAL_SECRET = "x" * 64


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in OVERRIDABLE:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


def build(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


# ------------------------------------------------------------- parsing ------


def test_comma_separated_origins_become_a_list() -> None:
    """A `.env` file carries `a,b`, not a JSON array."""
    settings = build(CORS_ORIGINS="http://a.test, http://b.test")

    assert settings.CORS_ORIGINS == ["http://a.test", "http://b.test"]


def test_json_array_of_origins_is_still_accepted() -> None:
    settings = build(CORS_ORIGINS='["http://a.test"]')

    assert settings.CORS_ORIGINS == ["http://a.test"]


def test_blank_origins_are_dropped() -> None:
    """A trailing comma should not produce an empty origin that matches nothing."""
    settings = build(CORS_ORIGINS="http://a.test,,  ,")

    assert settings.CORS_ORIGINS == ["http://a.test"]


# The three tests above pass origins as an init keyword argument, which
# pydantic-settings hands straight to validation. A deploy sets an environment
# variable instead, and that path runs the value through the complex-field JSON
# decoder first — a difference that once let this suite pass while `uvicorn` and
# `docker compose up` both died on `CORS_ORIGINS=http://localhost:3000`. These
# cover the path that actually ships.


def test_a_single_bare_origin_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact line in `.env.example`, and the one that used to crash on boot."""
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")

    assert build().CORS_ORIGINS == ["http://localhost:3000"]


def test_comma_separated_origins_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")

    assert build().CORS_ORIGINS == ["http://a.test", "http://b.test"]


def test_json_origins_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test", "http://b.test"]')

    assert build().CORS_ORIGINS == ["http://a.test", "http://b.test"]


def test_a_malformed_json_array_is_reported_against_the_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not swallowed into a single nonsense origin, and not a bare SettingsError."""
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test"')

    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        build()


def test_provider_strings_coerce_to_enums() -> None:
    settings = build(LLM_PROVIDER="ollama")

    assert settings.LLM_PROVIDER is LLMProvider.OLLAMA


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValueError):
        build(LLM_PROVIDER="a-provider-that-does-not-exist")


def test_secrets_do_not_appear_in_the_repr() -> None:
    """A settings object gets logged and dumped; the key must not ride along."""
    settings = build(ENVIRONMENT="staging", JWT_SECRET_KEY=REAL_SECRET)

    assert REAL_SECRET not in repr(settings)
    assert settings.JWT_SECRET_KEY is not None
    assert settings.JWT_SECRET_KEY.get_secret_value() == REAL_SECRET


# ------------------------------------------------------------- guards -------


def test_local_runs_without_a_signing_key() -> None:
    """The tokens on a laptop are thrown away; requiring a key is friction."""
    settings = build(ENVIRONMENT="local")

    assert settings.JWT_SECRET_KEY is None
    assert settings.is_local


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_deployed_environments_require_a_signing_key(environment: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        build(ENVIRONMENT=environment)

    assert raised.value.details["setting"] == "JWT_SECRET_KEY"


def test_an_empty_signing_key_counts_as_missing() -> None:
    """`JWT_SECRET_KEY=` in a `.env` file is not a key."""
    with pytest.raises(ConfigurationError):
        build(ENVIRONMENT="production", JWT_SECRET_KEY="")


def test_production_rejects_a_wildcard_origin() -> None:
    """With `allow_credentials=True`, `*` lets any site call this API."""
    with pytest.raises(ConfigurationError) as raised:
        build(ENVIRONMENT="production", JWT_SECRET_KEY=REAL_SECRET, CORS_ORIGINS="*")

    assert raised.value.details["setting"] == "CORS_ORIGINS"


def test_production_rejects_debug() -> None:
    with pytest.raises(ConfigurationError) as raised:
        build(ENVIRONMENT="production", JWT_SECRET_KEY=REAL_SECRET, DEBUG=True)

    assert raised.value.details["setting"] == "DEBUG"


def test_production_rejects_private_media_hosts() -> None:
    with pytest.raises(ConfigurationError) as raised:
        build(
            ENVIRONMENT="production",
            JWT_SECRET_KEY=REAL_SECRET,
            MEDIA_ALLOW_PRIVATE_HOSTS=True,
        )

    assert raised.value.details["setting"] == "MEDIA_ALLOW_PRIVATE_HOSTS"


def test_a_correct_production_configuration_starts() -> None:
    settings = build(
        ENVIRONMENT="production",
        JWT_SECRET_KEY=REAL_SECRET,
        CORS_ORIGINS="https://veritas.example",
    )

    assert settings.is_production
    assert settings.ENVIRONMENT is Environment.PRODUCTION


def test_staging_may_debug() -> None:
    """The DEBUG guard is about production specifically, not about deploys."""
    settings = build(ENVIRONMENT="staging", JWT_SECRET_KEY=REAL_SECRET, DEBUG=True)

    assert settings.DEBUG


# --------------------------------------------------------------- docs -------


def test_docs_are_closed_in_production() -> None:
    settings = build(ENVIRONMENT="production", JWT_SECRET_KEY=REAL_SECRET)

    assert not settings.docs_enabled


@pytest.mark.parametrize("environment", ["local", "development", "staging"])
def test_docs_are_open_everywhere_else(environment: str) -> None:
    settings = build(ENVIRONMENT=environment, JWT_SECRET_KEY=REAL_SECRET)

    assert settings.docs_enabled


# -------------------------------------------------------------- cache -------


def test_settings_are_built_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    get_settings.cache_clear()
    try:
        first = get_settings()

        assert get_settings() is first

        get_settings.cache_clear()
        assert get_settings() is not first
    finally:
        # The module-level application built at import time holds the settings
        # from before this test; leaving a cleared cache behind is harmless, but
        # leaving one populated from a monkeypatched environment is not.
        get_settings.cache_clear()
