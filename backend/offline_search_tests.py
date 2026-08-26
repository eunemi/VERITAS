"""Offline runner for the search and research tests.

Nothing is installed in this environment and nothing can be: ``pip`` is behind a
403. ``httpx``, ``pydantic``, ``anyio`` and ``pytest`` are all absent, so the
committed tests under ``tests/`` cannot run here as written — and the five modules
in ``app/search`` that import ``httpx`` at module scope cannot even be imported.

This script supplies the missing pieces as stubs and then runs the real, committed
test functions against the real, committed application code. What is faked is
exactly the transport, the thread offload, the settings container and the test
framework. Every line of parsing, retry, error-mapping, fan-out, query-building,
evidence-selection, deduplication and assembly logic under test is the shipped one.

The stubs are deliberately faithful where fidelity matters:

* ``httpx.Response.json()`` raises ``ValueError`` on a non-JSON body, which is what
  ``Http._decode`` catches.
* ``httpx.MockTransport`` calls its handler with a request and returns its
  response, and a handler that raises propagates — that is how the timeout and
  connection-error paths get exercised.
* Header lookup is case-insensitive, because ``_retry_after`` reads
  ``"retry-after"`` from a response a provider spelled ``Retry-After``.
* ``anyio.to_thread.run_sync`` calls the function inline. That is *not* faithful —
  the real one runs it off the event loop — but the only caller is
  ``SpacyClaimExtractor.extract``, which every test here replaces with a stub, so
  the stub exists to make ``app.nlp.pipeline`` importable rather than to be run.

What this cannot cover: ``pydantic``, and therefore every schema in ``app/schemas``
and every route in ``app/api``. ``tests/test_research_api.py`` is the module that
asserts the HTTP contract and it does not run here.

Run: python3 offline_search_tests.py [module ...]
"""

from __future__ import annotations

import asyncio
import inspect
import json as jsonlib
import re
import sys
import traceback
import types
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

#: The harness lives in the backend root, so derive it rather than hard-coding a
#: path — the previous absolute string broke the moment the checkout moved.
BACKEND = str(Path(__file__).resolve().parent)
sys.path.insert(0, BACKEND)


# ============================================================ stub: httpx ====

httpx = types.ModuleType("httpx")


class HTTPError(Exception):
    pass


class TimeoutException(HTTPError):
    pass


class ConnectError(HTTPError):
    pass


class Timeout:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds


class Headers(dict):
    """Case-insensitive, like the real thing."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        super().__init__({str(k).lower(): v for k, v in (data or {}).items()})

    def get(self, key: str, default: Any = None) -> Any:
        return super().get(str(key).lower(), default)


def _query_value(value: Any) -> str:
    """Encode one query-string value the way ``httpx.QueryParams`` does.

    A query string holds text, so httpx stringifies on the way in and a test reading
    ``url.params["count"]`` back gets ``"20"``, not ``20``. Booleans are lowercased
    rather than Python-cased for the same reason: ``?flag=true`` is what goes over
    the wire.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class URL:
    def __init__(self, url: str, params: dict[str, Any] | None = None) -> None:
        self._url = url
        self.params = {k: _query_value(v) for k, v in (params or {}).items()}

    def __str__(self) -> str:
        return self._url


class Request:
    def __init__(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> None:
        self.method = method
        self.url = URL(url, params)
        self.headers = Headers(headers)
        self.content = b"" if json is None else jsonlib.dumps(json).encode()

    def json(self) -> Any:
        return jsonlib.loads(self.content)


class Response:
    def __init__(
        self,
        status_code: int,
        *,
        json: Any = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json = json
        if text is not None:
            self.text = text
        elif json is not None:
            self.text = jsonlib.dumps(json)
        else:
            self.text = ""
        self.headers = Headers(headers)

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        if self._json is not None:
            return self._json
        return jsonlib.loads(self.text)


class MockTransport:
    def __init__(self, handler: Any) -> None:
        self.handler = handler


class AsyncClient:
    def __init__(
        self,
        *,
        timeout: Any = None,
        follow_redirects: bool = False,
        headers: Any = None,
        transport: Any = None,
    ) -> None:
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.transport = transport
        self.closed = False

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Any = None,
        params: Any = None,
        json: Any = None,
    ) -> Response:
        if self.transport is None:
            raise RuntimeError("offline harness: a test made an unmocked request")
        request = Request(method, url, headers=headers, params=params, json=json)
        result = self.transport.handler(request)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def aclose(self) -> None:
        self.closed = True


for _name, _obj in {
    "AsyncClient": AsyncClient,
    "ConnectError": ConnectError,
    "HTTPError": HTTPError,
    "Headers": Headers,
    "MockTransport": MockTransport,
    "Request": Request,
    "Response": Response,
    "Timeout": Timeout,
    "TimeoutException": TimeoutException,
    "URL": URL,
}.items():
    setattr(httpx, _name, _obj)
sys.modules["httpx"] = httpx


# ============================================================ stub: anyio ====
#
# ``app.nlp.pipeline`` imports ``anyio.to_thread`` at module scope, and importing it
# is unavoidable for the research service: ``app.services.research`` imports
# ``app.services.claims``, which imports ``app.nlp``, which imports the pipeline.
# Nothing here ever reaches the real offload — the extractor is always a stub — so
# this runs the function inline.

anyio = types.ModuleType("anyio")
to_thread = types.ModuleType("anyio.to_thread")


async def _run_sync(fn: Any, *args: Any, **_kwargs: Any) -> Any:
    return fn(*args)


to_thread.run_sync = _run_sync  # type: ignore[attr-defined]
anyio.to_thread = to_thread  # type: ignore[attr-defined]
sys.modules["anyio"] = anyio
sys.modules["anyio.to_thread"] = to_thread


# ==================================================== stub: app.core.config ==

config = types.ModuleType("app.core.config")


class SearchProvider(StrEnum):
    TAVILY = "tavily"
    SERPER = "serper"
    BRAVE = "brave"


class ClaimExtractorProvider(StrEnum):
    SPACY = "spacy"


class FactCheckProvider(StrEnum):
    GOOGLE = "google"


# The remaining seams. None of the tests below chooses a provider, but every
# ``ProviderRegistry`` is built at import time and keyed by one of these enums, so
# reaching ``app.services.research`` through ``app.services`` needs the whole set
# present. Members and values mirror ``app/core/config.py``; a registry keyed by a
# member this stub spelled differently would resolve nothing.


class Environment(StrEnum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(StrEnum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    HASHING = "hashing"


class VectorStoreProvider(StrEnum):
    CHROMA = "chroma"
    FAISS = "faiss"
    MEMORY = "memory"


class VisionProvider(StrEnum):
    TESSERACT = "tesseract"
    YOLO = "yolo"


class SpeechProvider(StrEnum):
    WHISPER = "whisper"


class StoreBackend(StrEnum):
    DATABASE = "database"
    MEMORY = "memory"


class SecretStr:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "SecretStr('**********')"


def _secret(value: Any) -> SecretStr | None:
    if value is None or isinstance(value, SecretStr):
        return value
    return SecretStr(str(value))


#: Mirrors the defaults in the real ``Settings`` for every field the search and
#: research code reads. Kept in one place so a drift between this and
#: ``app/core/config.py`` is one diff to read.
_DEFAULTS: dict[str, Any] = {
    "SEARCH_PROVIDER": SearchProvider.TAVILY,
    "SEARCH_TIMEOUT_SECONDS": 20.0,
    "SEARCH_MAX_RESULTS": 10,
    "SEARCH_ATTEMPTS": 3,
    "SEARCH_CONCURRENCY": 2,
    "SEARCH_QUERIES_PER_CLAIM": 3,
    "SEARCH_MAX_CLAIMS": 10,
    "TAVILY_TOPIC": "general",
    "TAVILY_SEARCH_DEPTH": "basic",
    "FACT_CHECK_PROVIDER": FactCheckProvider.GOOGLE,
    "FACT_CHECK_TIMEOUT_SECONDS": 20.0,
    "FACT_CHECK_ATTEMPTS": 3,
    "FACT_CHECK_MAX_RESULTS": 10,
    "FACT_CHECK_LANGUAGE": "",
    "FACT_CHECK_MAX_AGE_DAYS": 0,
    "FACT_CHECK_CONCURRENCY": 2,
    "FACT_CHECK_MIN_MATCH": 0.15,
    "MAX_TEXT_CHARS": 100_000,
    "CLAIM_EXTRACTOR": ClaimExtractorProvider.SPACY,
    "SPACY_MODEL": "en_core_web_sm",
    "CLAIM_MIN_TOKENS": 4,
    "CLAIM_MAX_KEYWORDS": 10,
    "CLAIM_MAX_SENTENCES": 400,
    "CREDIBILITY_ENABLED": True,
    "CREDIBILITY_FRESH_DAYS": 365,
    "CREDIBILITY_STALE_DAYS": 3650,
    "ENVIRONMENT": Environment.LOCAL,
    "VERIFICATION_STORE": StoreBackend.MEMORY,
    "LLM_PROVIDER": LLMProvider.OPENAI,
    "VECTOR_STORE_PROVIDER": VectorStoreProvider.MEMORY,
    "EMBEDDING_PROVIDER": LLMProvider.HASHING,
    "IMAGE_READER": VisionProvider.TESSERACT,
    "OBJECT_DETECTOR": VisionProvider.YOLO,
    "TRANSCRIBER": SpeechProvider.WHISPER,
}


class Settings:
    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_env_file", None)
        for key in (
            "TAVILY_API_KEY",
            "SERPER_API_KEY",
            "BRAVE_API_KEY",
            "GOOGLE_FACT_CHECK_API_KEY",
        ):
            setattr(self, key, _secret(kwargs.pop(key, None)))
        self.SEARCH_PROVIDERS = list(
            kwargs.pop(
                "SEARCH_PROVIDERS",
                [SearchProvider.TAVILY, SearchProvider.BRAVE, SearchProvider.SERPER],
            )
        )
        for key, default in _DEFAULTS.items():
            setattr(self, key, kwargs.pop(key, default))
        for key, value in kwargs.items():
            setattr(self, key, value)

    def search_secrets(self) -> tuple[str, ...]:
        keys = (self.TAVILY_API_KEY, self.SERPER_API_KEY, self.BRAVE_API_KEY)
        return tuple(k.get_secret_value() for k in keys if k is not None)

    def fact_check_secrets(self) -> tuple[str, ...]:
        keys = (self.GOOGLE_FACT_CHECK_API_KEY,)
        return tuple(k.get_secret_value() for k in keys if k is not None)

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT is Environment.PRODUCTION

    @property
    def is_local(self) -> bool:
        return self.ENVIRONMENT is Environment.LOCAL


#: Carries the real ``lru_cache`` so that ``get_settings.cache_clear()`` — which the
#: committed tests call to swap in a different instance — exists here too.
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


for _name, _obj in {
    "ClaimExtractorProvider": ClaimExtractorProvider,
    "Environment": Environment,
    "FactCheckProvider": FactCheckProvider,
    "LLMProvider": LLMProvider,
    "SearchProvider": SearchProvider,
    "SecretStr": SecretStr,
    "Settings": Settings,
    "SpeechProvider": SpeechProvider,
    "StoreBackend": StoreBackend,
    "VectorStoreProvider": VectorStoreProvider,
    "VisionProvider": VisionProvider,
    "get_settings": get_settings,
}.items():
    setattr(config, _name, _obj)
sys.modules["app.core.config"] = config


# ================================================== shim: app.services pkg ==
#
# ``app/services/__init__.py`` re-exports ``VerificationService`` beside the two
# services under test, and importing it therefore pulls in the desks and the SQL
# repositories — whisper, OpenCV, sqlalchemy, none of which are installed and none
# of which these tests touch. Registering the package with a ``__path__`` and no
# body means ``from app.services.claims import ...`` finds the real submodule while
# the re-export list is skipped.
#
# This fakes the package shim, not the code: ``claims.py`` and ``research.py`` are
# imported and executed in full, and nothing outside ``app/services`` imports the
# package's re-exports, so there is nothing else for this to hide.

services = types.ModuleType("app.services")
_services_dir = str(Path(BACKEND) / "app" / "services")
services.__path__ = [_services_dir]  # type: ignore[attr-defined]
sys.modules["app.services"] = services


# =========================================================== stub: pytest ====

pytest = types.ModuleType("pytest")


@dataclass
class _Param:
    values: tuple[Any, ...]
    id: str | None = None


def _param(*values: Any, id: str | None = None) -> _Param:
    return _Param(values, id)


class _Approx:
    def __init__(self, expected: float, tol: float = 1e-9) -> None:
        self.expected = expected
        self.tol = tol

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, int | float):
            return NotImplemented
        return abs(float(other) - self.expected) <= self.tol

    def __repr__(self) -> str:
        return f"approx({self.expected})"


class _Raises:
    def __init__(self, expected: type[BaseException], match: str | None) -> None:
        self.expected = expected
        self.match = match
        self.value: BaseException | None = None

    def __enter__(self) -> _Raises:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is None:
            raise AssertionError(f"DID NOT RAISE {self.expected.__name__}")
        if not issubclass(exc_type, self.expected):
            return False
        if self.match is not None and not re.search(self.match, str(exc)):
            raise AssertionError(
                f"{self.expected.__name__} raised but {self.match!r} not in {str(exc)!r}"
            )
        self.value = exc
        return True


def _raises(expected: type[BaseException], *, match: str | None = None) -> _Raises:
    return _Raises(expected, match)


def _fixture(fn: Any = None, **_kwargs: Any) -> Any:
    def wrap(func: Any) -> Any:
        func._is_fixture = True
        return func

    return wrap(fn) if fn is not None else wrap


def _parametrize(argnames: str, argvalues: list[Any], **_kwargs: Any) -> Any:
    def wrap(func: Any) -> Any:
        cases = getattr(func, "_parametrize", [])
        func._parametrize = [*cases, (argnames, argvalues)]
        return func

    return wrap


_mark = types.SimpleNamespace(
    parametrize=_parametrize,
    asyncio=lambda fn: fn,
)


class _MonkeyPatch:
    """Just enough of pytest's, with an explicit undo."""

    def __init__(self) -> None:
        self._undo: list[tuple[Any, str, Any, bool]] = []

    def setattr(self, target: Any, name: str, value: Any) -> None:
        had = hasattr(target, name)
        self._undo.append((target, name, getattr(target, name, None), had))
        setattr(target, name, value)

    def setenv(self, name: str, value: str) -> None:
        import os

        self._undo.append((os.environ, name, os.environ.get(name), name in os.environ))
        os.environ[name] = value

    def undo(self) -> None:
        for target, name, old, had in reversed(self._undo):
            if had:
                if isinstance(target, dict):
                    target[name] = old
                else:
                    setattr(target, name, old)
            elif isinstance(target, dict):
                target.pop(name, None)
            else:
                delattr(target, name)
        self._undo.clear()


pytest.approx = lambda expected, **_kw: _Approx(expected)  # type: ignore[attr-defined]
pytest.fixture = _fixture  # type: ignore[attr-defined]
pytest.mark = _mark  # type: ignore[attr-defined]
pytest.param = _param  # type: ignore[attr-defined]
pytest.raises = _raises  # type: ignore[attr-defined]
pytest.MonkeyPatch = _MonkeyPatch  # type: ignore[attr-defined]
sys.modules["pytest"] = pytest


# ============================================================== the runner ====


def _cases(fn: Any) -> list[dict[str, Any]]:
    """Expand stacked ``parametrize`` marks into one kwargs dict per case."""
    marks = getattr(fn, "_parametrize", [])
    combos: list[dict[str, Any]] = [{}]
    for argnames, argvalues in marks:
        # Real pytest accepts a comma-separated string or a sequence of names.
        names = (
            [n.strip() for n in argnames.split(",")]
            if isinstance(argnames, str)
            else list(argnames)
        )
        expanded: list[dict[str, Any]] = []
        for base in combos:
            for value in argvalues:
                raw = value.values if isinstance(value, _Param) else value
                if len(names) == 1:
                    row = {names[0]: raw[0] if isinstance(value, _Param) else raw}
                else:
                    row = dict(zip(names, raw, strict=True))
                expanded.append({**base, **row})
        combos = expanded
    return combos


def _label(fn: Any, case: dict[str, Any]) -> str:
    if not case:
        return fn.__name__
    ids = "-".join(str(v)[:24] for v in case.values())
    return f"{fn.__name__}[{ids}]"


def _resolve(
    fn: Any,
    fixtures: dict[str, Any],
    known: dict[str, Any],
    patches: list[_MonkeyPatch],
) -> dict[str, Any]:
    """Build kwargs for ``fn``, instantiating fixtures (and their fixtures) as needed."""
    kwargs = dict(known)
    for name in inspect.signature(fn).parameters:
        if name in kwargs:
            continue
        if name == "monkeypatch":
            patch = _MonkeyPatch()
            patches.append(patch)
            kwargs[name] = patch
        elif name in fixtures:
            fixture = fixtures[name]
            inner = _resolve(fixture, fixtures, {}, patches)
            kwargs[name] = fixture(**inner)
    return kwargs


def run(module_names: list[str]) -> int:
    passed = failed = 0
    failures: list[tuple[str, str]] = []

    for module_name in module_names:
        module = __import__(module_name, fromlist=["*"])
        fixtures = {
            name: obj
            for name, obj in vars(module).items()
            if getattr(obj, "_is_fixture", False)
        }
        tests = [
            (name, obj)
            for name, obj in vars(module).items()
            if name.startswith("test_") and inspect.isfunction(obj)
        ]
        tests.sort(key=lambda pair: pair[1].__code__.co_firstlineno)

        print(f"\n\033[1m{module_name}\033[0m  ({len(tests)} tests)")
        for name, fn in tests:
            for case in _cases(fn):
                label = _label(fn, case)
                patches: list[_MonkeyPatch] = []
                try:
                    kwargs = _resolve(fn, fixtures, case, patches)
                    result = fn(**kwargs)
                    if inspect.isawaitable(result):
                        asyncio.run(result)
                except Exception:
                    failed += 1
                    failures.append((f"{module_name}::{label}", traceback.format_exc()))
                    print(f"  \033[31mFAIL\033[0m {label}")
                else:
                    passed += 1
                    print(f"  \033[32mok\033[0m   {label}")
                finally:
                    for patch in patches:
                        patch.undo()

    print(f"\n\033[1m{passed} passed, {failed} failed\033[0m")
    for where, tb in failures:
        print(f"\n\033[31m{'=' * 70}\n{where}\033[0m\n{tb}")
    return 1 if failed else 0


#: Every committed test module that runs without ``pydantic``. ``test_research_api``
#: is absent on purpose: it drives the endpoint, which needs FastAPI.
DEFAULT_MODULES = [
    "tests.test_search_parse",
    "tests.test_provider_http",
    "tests.test_search_fanout",
    "tests.test_factcheck_google",
    "tests.test_factcheck_lookup",
    "tests.test_research_imports",
    "tests.test_research_urls",
    "tests.test_research_queries",
    "tests.test_research_evidence",
    "tests.test_research_reviews",
    "tests.test_research_dedupe",
    "tests.test_research_dossier",
    "tests.test_research_service",
]


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:] or DEFAULT_MODULES))
