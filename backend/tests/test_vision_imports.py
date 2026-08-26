"""The lazy-import discipline in :mod:`app.vision`, enforced rather than documented.

No module in the package may import OpenCV, pytesseract, ultralytics or torch at
module scope. Every one of those imports sits inside a function body, which is what
lets ``import app.main`` answer ``/health`` — and lets the text desk work — on a
machine with none of the vision stack installed. It matters more here than in
:mod:`app.nlp`: ultralytics pulls in torch, and a container that has to carry
several hundred megabytes to serve a text verification is a build nobody wants.

The break is invisible on a developer machine that happens to have the libraries,
so this reads the source with :mod:`ast` rather than importing anything, and holds
wherever it runs.

``anyio`` is exempt: it is a hard runtime dependency of the application already,
imported at module scope by ``app/nlp/pipeline.py``. Adding it to the forbidden set
would assert something this package does not claim. ``httpx`` is a different case —
fetching a submitted URL moved to :mod:`app.media`, so no module here should reach
the network at all, and :func:`test_no_module_here_fetches_anything` says so.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: The package under inspection, located from this file rather than by importing it.
VISION = Path(__file__).resolve().parent.parent / "app" / "vision"

#: Top-level distributions that must never be imported at module scope: the three
#: the package uses, plus the heavy transitive dependencies they bring, so that
#: reaching for ``numpy`` or ``torch`` directly is caught by the same rule.
FORBIDDEN = frozenset(
    {"cv2", "pytesseract", "ultralytics", "torch", "torchvision", "numpy", "PIL"}
)

#: Modules that must stay free of *any* third party, so the types the desk, the
#: schemas and these tests read are available with nothing installed.
PLAIN_PYTHON = ("base.py", "relevance.py")

def modules() -> list[Path]:
    """Every source file in the package, ``__init__`` included."""
    return sorted(VISION.glob("*.py"))


def test_the_package_is_where_this_thinks_it_is() -> None:
    """Guards the guard: a moved package would make every check below vacuous."""
    assert VISION.is_dir()
    assert {path.name for path in modules()} == {
        "__init__.py",
        "base.py",
        "detect.py",
        "ocr.py",
        "prepare.py",
        "relevance.py",
    }


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


@pytest.mark.parametrize("name", PLAIN_PYTHON)
def test_the_shared_types_and_the_gate_need_nothing_installed(name: str) -> None:
    """``base`` and ``relevance`` import only the standard library and ``app``.

    ``base`` holds the dataclasses the image desk and the API schemas read, and
    ``relevance`` decides whether to load a detector at all — a decision that has
    to be reachable *before* the several hundred megabytes are paid for. A third
    party import in either would make both of those claims false.
    """
    path = VISION / name
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    outside = sorted(
        {
            _root(module)
            for module in _eager_imports(tree.body)
            if _root(module) != "app" and _root(module) not in _STDLIB
        }
    )

    assert not outside, f"{name} imports {', '.join(outside)}"


def test_no_module_here_fetches_anything() -> None:
    """Reading an image and getting hold of one are separate concerns.

    ``app/media/fetch.py`` owns every outbound request, including the guard that
    stops a submitted URL reaching this deployment's own network. A second HTTP
    client in this package would be a second copy of that guard to keep correct.
    """
    for path in modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = {_root(module) for module in _eager_imports(tree.body)}
        assert "httpx" not in found, f"{path.name} should not import httpx"


def test_the_libraries_are_imported_somewhere() -> None:
    """Otherwise the check above passes for a package that reads no images at all.

    Not a style rule — it distinguishes "the imports are lazy" from "there are no
    imports", and only the first is the thing being asserted.
    """
    found: set[str] = set()
    for path in modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(_root(alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                found.add(_root(node.module))

    assert {"cv2", "pytesseract", "ultralytics"} <= found


@pytest.mark.parametrize("name", ("image.py", "audio.py", "graph.py"))
def test_the_desks_keep_langgraph_lazy(name: str) -> None:
    """``app.desks`` is imported at startup, and it imports every desk.

    Which means an eager ``app.graph.workflow`` import in any of these would make
    langgraph a startup dependency of the whole application — the exact thing
    ``tests/test_graph_imports.py`` keeps confined to one module. ``app.desks.graph``
    is included because it is where that import now lives, inside a function body.
    """
    path = VISION.parent / "desks" / name
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    eager = set(_eager_imports(tree.body))

    assert "app.graph.workflow" not in eager


def test_the_plain_python_half_of_the_verdict_stays_a_normal_import() -> None:
    """Distinguishes "lazy where it must be" from "lazy everywhere".

    ``app.graph.verdict`` holds dataclasses and an enum mapping, costs nothing, and
    both desks read it to file a report. Deferring it too would be cargo cult.
    """
    for name in ("image.py", "audio.py"):
        path = VISION.parent / "desks" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert "app.graph.verdict" in set(_eager_imports(tree.body)), name


# ------------------------------------------------------------------------ ast ----

#: Standard-library roots the two plain-Python modules legitimately use. A short
#: allow-list rather than a check against ``sys.stdlib_module_names``, because the
#: point is that this list stays short.
_STDLIB = frozenset(
    {
        "__future__",
        "collections",
        "dataclasses",
        "enum",
        "math",
        "re",
        "typing",
        "unicodedata",
    }
)


def _root(module: str) -> str:
    """``ultralytics.models.yolo`` -> ``ultralytics``."""
    return module.split(".")[0]


def _eager_imports(body: list[ast.stmt]) -> list[str]:
    """Modules imported by running ``body``, at any nesting that still executes.

    Function bodies are skipped, since they run on call rather than on import —
    that being the whole point. ``if TYPE_CHECKING:`` blocks are skipped because
    they never run at all. Everything else is descended into: a ``try``/``except
    ImportError`` around an import executes, and so does a class body.
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
