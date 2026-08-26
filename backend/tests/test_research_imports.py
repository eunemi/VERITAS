"""The purity of :mod:`app.research`, enforced rather than documented.

Five packages are off limits to every module under ``app/research``, and each ban buys
something specific:

:mod:`app.search` is the network. A function that takes retrievals and returns sources
needs no HTTP client, and keeping it that way is what makes the honesty properties —
a quote is a slice of a snippet, a syndication cluster is a label and not a deletion —
cheap enough to test exhaustively that they actually are tested.

:mod:`app.factcheck` is the same ban for the same reason, and it is the one most likely
to be broken by a plausible-looking refactor. :mod:`app.research.reviews` decides what a
publisher's rating means and whether their claim is the caller's; the clients under
``app/factcheck`` are forbidden from deciding either. Letting the judgement import the
vendor would put a Google-shaped assumption inside the only code that reads a verdict,
and the 45-case vocabulary round-trip would then be testing a client's parse rather than
this service's reading.

:mod:`app.providers` is the shared transport — retries, backoff, redaction, provider
date strings. Nothing here makes a request, so nothing here needs a retry policy, and
the package imports ``httpx`` at module scope.

:mod:`app.llm` is a language model. Nothing in this package may summarise, and the
surest way to guarantee that is for the thing that could summarise to be unreachable.

:mod:`app.nlp` is spaCy and scikit-learn, and this is the ban that matters in
production. Everything in ``app.research`` runs on the request path, and a deployment
with search keys but no language model must still produce a dossier — that is exactly
what ``POST /research`` with a ``claims`` body does. It is also the easiest of the three
to break by accident, because :mod:`app.nlp` has a better tokeniser and a better
stopword list than :mod:`app.research.terms` and importing them would look like a
cleanup.

Read with :mod:`ast` rather than by importing, so it holds wherever it runs — including
here, where spaCy is not installed and an import-based check could not even load the
module it was trying to inspect.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: The package under inspection, located from this file rather than by importing it.
RESEARCH = Path(__file__).resolve().parent.parent / "app" / "research"

#: Application packages no module here may import, at any scope.
#:
#: Unlike ``test_nlp_imports``, a lazy import inside a function body is forbidden too.
#: There it was the mechanism — the imports are meant to happen, just late. Here the
#: dependency is meant not to exist, and a function-scoped ``import app.nlp`` would
#: fail at request time in exactly the deployment this rule protects.
FORBIDDEN = frozenset(
    {"app.search", "app.factcheck", "app.providers", "app.llm", "app.nlp"}
)

#: Third-party distributions that must not appear either.
#:
#: ``app.research`` is stdlib-only, and these are the specific temptations: an
#: HTTP client, a public-suffix library that ``app/research/suffixes.py`` exists
#: because it cannot rely on, and the NLP stack's transitive heavyweights.
FORBIDDEN_THIRD_PARTY = frozenset(
    {
        "httpx",
        "requests",
        "aiohttp",
        "tldextract",
        "publicsuffix2",
        "publicsuffixlist",
        "tld",
        "spacy",
        "nltk",
        "sklearn",
        "numpy",
        "scipy",
        "pydantic",
    }
)


def modules() -> list[Path]:
    """Every source file in the package, ``__init__`` included."""
    return sorted(RESEARCH.glob("*.py"))


def test_the_package_is_where_this_thinks_it_is() -> None:
    """Guards the guard: a moved package makes every check below vacuous.

    Naming the modules rather than counting them, so deleting ``dedupe.py`` fails here
    instead of quietly reducing the parametrised cases to the ones that still pass.
    """
    assert RESEARCH.is_dir()
    assert {path.name for path in modules()} >= {
        "__init__.py",
        "dedupe.py",
        "dossier.py",
        "evidence.py",
        "queries.py",
        "reviews.py",
        "suffixes.py",
        "terms.py",
        "urls.py",
    }


@pytest.mark.parametrize("path", modules(), ids=lambda path: path.name)
def test_no_forbidden_application_package_is_imported(path: Path) -> None:
    """The central rule. One case per module, so a failure names the file."""
    offending = sorted(
        {
            name
            for name in _imports(path)
            if any(name == banned or name.startswith(f"{banned}.") for banned in FORBIDDEN)
        }
    )
    assert not offending, (
        f"{path.name} imports {', '.join(offending)}. Everything in app.research runs "
        f"on the request path deciding things, with no vendor client, no transport and "
        f"none of the NLP extras installed — move whatever needs them into a service."
    )


@pytest.mark.parametrize("path", modules(), ids=lambda path: path.name)
def test_nothing_outside_the_standard_library_is_imported(path: Path) -> None:
    """No third-party dependency either, which is what makes the package portable."""
    offending = sorted(
        {name for name in _imports(path) if _root(name) in FORBIDDEN_THIRD_PARTY}
    )
    assert not offending, f"{path.name} imports {', '.join(offending)}"


def test_only_the_domain_is_imported_from_the_application() -> None:
    """The positive form: ``app.domain`` and ``app.research`` itself, nothing else.

    The two checks above are deny lists and would miss a new package added later. This
    one fails on anything unexpected, which is the version that keeps working without
    being edited.
    """
    reached: set[str] = set()
    for path in modules():
        reached.update(
            name
            for name in _imports(path)
            if name.startswith("app.")
            and not name.startswith(("app.domain", "app.research"))
        )
    assert not reached, (
        f"app.research reached into {', '.join(sorted(reached))}. Only app.domain is "
        f"allowed — see the import rule in app/research/__init__.py."
    )


def test_the_domain_is_imported_somewhere() -> None:
    """Otherwise every check above passes for a package that imports nothing at all."""
    reached: set[str] = set()
    for path in modules():
        reached.update(name for name in _imports(path) if name.startswith("app."))
    assert any(name.startswith("app.domain") for name in reached)


# ------------------------------------------------------------------------ ast ----


def _root(module: str) -> str:
    """``xml.etree.ElementTree`` -> ``xml``."""
    return module.split(".")[0]


def _imports(path: Path) -> set[str]:
    """Every absolute module name ``path`` imports, at any scope.

    Relative imports are skipped: ``from . import terms`` cannot reach outside the
    package, so it is not something these rules are about.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
    return found
