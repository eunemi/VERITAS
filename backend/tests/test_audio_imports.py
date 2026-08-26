"""The lazy-import discipline in :mod:`app.audio`, enforced rather than documented.

No module in the package may import librosa, soundfile, numpy or whisper at module
scope. Every one of those imports sits inside a function body, which is what lets
``import app.main`` answer ``/health`` — and lets every other desk work — on a
machine with none of the audio stack installed. It matters as much as it does in
:mod:`app.vision`: openai-whisper pulls in torch, and numba arrives with librosa, so
a container that has to carry both to serve a text verification is a build nobody
wants.

The break is invisible on a developer machine that happens to have the libraries,
so this reads the source with :mod:`ast` rather than importing anything, and holds
wherever it runs.

``anyio`` is exempt: it is a hard runtime dependency imported at module scope by
``app/nlp/pipeline.py`` already. ``httpx`` is absent by design — fetching a
submitted URL belongs to :mod:`app.media`, and a second client here would be a
second copy of its request-forgery guard.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: The package under inspection, located from this file rather than by importing it.
AUDIO = Path(__file__).resolve().parent.parent / "app" / "audio"

#: Top-level distributions that must never be imported at module scope: the ones the
#: package uses, plus the heavy transitive dependencies they bring, so that reaching
#: for ``torch`` or ``numba`` directly is caught by the same rule.
FORBIDDEN = frozenset(
    {
        "librosa",
        "soundfile",
        "numpy",
        "whisper",
        "torch",
        "torchaudio",
        "numba",
        "scipy",
        "audioread",
    }
)

#: The module that must stay free of *any* third party, so the types the desk, the
#: schemas and these tests read are available with nothing installed.
PLAIN_PYTHON = ("base.py",)


def modules() -> list[Path]:
    """Every source file in the package, ``__init__`` included."""
    return sorted(AUDIO.glob("*.py"))


def test_the_package_is_where_this_thinks_it_is() -> None:
    """Guards the guard: a moved package would make every check below vacuous."""
    assert AUDIO.is_dir()
    assert {path.name for path in modules()} == {
        "__init__.py",
        "analyse.py",
        "base.py",
        "decode.py",
        "transcribe.py",
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
def test_the_shared_types_need_nothing_installed(name: str) -> None:
    """``base`` imports only the standard library.

    It holds the dataclasses the audio desk and the API schemas read, which is why
    ``Clip.samples`` is annotated ``Any`` rather than ``numpy.ndarray``: naming that
    type would put numpy into the one module that must not need it.
    """
    path = AUDIO / name
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
    """Decoding a recording and getting hold of one are separate concerns."""
    for path in modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = {_root(module) for module in _eager_imports(tree.body)}
        assert "httpx" not in found, f"{path.name} should not import httpx"


def test_the_libraries_are_imported_somewhere() -> None:
    """Otherwise the check above passes for a package that hears nothing at all.

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

    assert {"librosa", "numpy", "whisper"} <= found


def test_only_the_decoder_starts_a_process() -> None:
    """ffmpeg is spawned in one place, so the argument vector has one author.

    A second caller is a second chance to interpolate something a submitter wrote
    into an argument list.
    """
    for path in modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = {_root(module) for module in ast_imports(tree)}
        if path.name == "decode.py":
            assert "subprocess" in found
        else:
            assert "subprocess" not in found, f"{path.name} spawns a process"


def ast_imports(tree: ast.Module) -> set[str]:
    """Every module named by an import anywhere in ``tree``, lazy ones included."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
    return found


# ------------------------------------------------------------------------ ast ----

#: Standard-library roots the plain-Python module legitimately uses. A short
#: allow-list rather than a check against ``sys.stdlib_module_names``, because the
#: point is that this list stays short.
_STDLIB = frozenset({"__future__", "dataclasses", "typing"})


def _root(module: str) -> str:
    """``librosa.effects.split`` -> ``librosa``."""
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
