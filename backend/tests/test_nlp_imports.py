"""The lazy-import discipline in :mod:`app.nlp`, enforced rather than documented.

No module in the package may import spaCy, NLTK or scikit-learn at module scope; every
one of those imports sits inside a function body. That is what lets ``import app.main``
answer ``/health`` on a machine with none of the stack installed, and what turns a
missing model into a ``500`` on the one request that asked for a parse rather than a
crash at startup.

It is also the easiest invariant in the codebase to break by accident, and the break is
invisible: a developer machine with spaCy installed passes the whole suite either way,
and the failure surfaces in a container that was built without the model. So this reads
the source with :mod:`ast` instead of importing anything — which means it holds wherever
it runs, including here, where none of the three libraries is installed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: The package under inspection, located from this file rather than by importing it —
#: ``import app.nlp`` would pull in the settings and defeat the point of a check that
#: needs nothing installed.
NLP = Path(__file__).resolve().parent.parent / "app" / "nlp"

#: Top-level distributions that must never be imported at module scope. The three the
#: package actually uses, plus the two heavy transitive dependencies they pull in, so
#: that reaching for ``numpy`` directly is caught by the same rule.
FORBIDDEN = frozenset({"spacy", "nltk", "sklearn", "numpy", "scipy"})


def modules() -> list[Path]:
    """Every source file in the package, ``__init__`` included."""
    return sorted(NLP.glob("*.py"))


def test_the_package_is_where_this_thinks_it_is() -> None:
    """Guards the guard: a moved package would make every check below vacuous."""
    assert NLP.is_dir()
    assert {path.name for path in modules()} >= {"__init__.py", "pipeline.py"}


@pytest.mark.parametrize("path", modules(), ids=lambda path: path.name)
def test_no_library_is_imported_at_module_scope(path: Path) -> None:
    """The invariant. One case per module, so a failure names the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    offending = sorted(
        {name for name in _eager_imports(tree.body) if _root(name) in FORBIDDEN}
    )

    assert not offending, (
        f"{path.name} imports {', '.join(offending)} when it is imported. Move the "
        f"import inside the function that needs it."
    )


def test_the_libraries_are_imported_somewhere() -> None:
    """Otherwise the check above passes for a package that dropped spaCy entirely.

    Not a style rule — it is what distinguishes "the imports are lazy" from "there are
    no imports", and only the first of those is the thing being asserted.
    """
    found: set[str] = set()
    for path in modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(_root(alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                found.add(_root(node.module))

    assert {"spacy", "nltk", "sklearn"} <= found


# ------------------------------------------------------------------------ ast ----


def _root(module: str) -> str:
    """``sklearn.feature_extraction.text`` -> ``sklearn``."""
    return module.split(".")[0]


def _eager_imports(body: list[ast.stmt]) -> list[str]:
    """Modules imported by running ``body``, at any nesting that still executes.

    Function bodies are skipped, since they run on call rather than on import — that
    being the whole point. ``if TYPE_CHECKING:`` blocks are skipped because they never
    run at all, which is how :mod:`app.nlp.split` can annotate a ``Token`` it will not
    import. Everything else is descended into: a ``try``/``except ImportError`` around
    an import executes, and so does a class body, so both are still eager.
    """
    found: list[str] = []
    for node in body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            continue
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.append(node.module)
        for field in ("body", "orelse", "finalbody"):
            found.extend(_eager_imports(getattr(node, field, None) or []))
        for handler in getattr(node, "handlers", None) or []:
            found.extend(_eager_imports(handler.body))
    return found


def _is_type_checking(test: ast.expr) -> bool:
    """``TYPE_CHECKING`` or ``typing.TYPE_CHECKING``, however it was spelled."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False
