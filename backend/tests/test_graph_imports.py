"""Where LangGraph is allowed to appear, enforced rather than documented.

One module imports it: ``app/graph/workflow.py``. Everything else — the state, the
verdict types, all seven agents — is plain Python, and that boundary buys two things
this suite depends on.

**The agents are testable without the runtime.** Every test in
``test_graph_judge``, ``test_graph_state`` and ``test_graph_contradiction`` calls an
agent with a dict. If any of them imported ``langgraph``, none of those files could run
in a deployment that had not installed it, and the sufficiency gate — the property most
worth testing exhaustively — would be the part hardest to reach.

**A missing dependency fails in one place.** ``pip install`` without ``langgraph``
should be an ``ImportError`` on ``app.graph.workflow`` and nothing else, so a service
that never compiles the graph still imports ``app.graph.verdict`` to read a
:class:`~app.graph.verdict.Ruling`.

The other rule here is that **no agent imports another**. Agents communicate through
channels on :class:`~app.graph.state.GraphState`, which is what lets the workflow run
search and fact-check in the same superstep; a direct import between two of them would
be a call ordering the graph does not know about and cannot schedule.

Read with :mod:`ast` rather than by importing, so it holds in this sandbox too — where
``langgraph`` is not installed and an import-based check could not load the one module it
most needs to inspect.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: The package under inspection, located from this file rather than by importing it.
GRAPH = Path(__file__).resolve().parent.parent / "app" / "graph"

#: The one module allowed to import the graph runtime.
RUNTIME_HOST = "workflow.py"

#: Distributions no module here may import, ``workflow.py`` included.
#:
#: ``langchain`` and its siblings are the ones worth naming. This package uses the graph
#: runtime only — ``StateGraph``, channels, supersteps — and constructs no chain, prompt
#: template or model client, so the seam to a language model stays :mod:`app.llm`'s. A
#: ``langchain_core`` import here would be the first step to two of them.
FORBIDDEN_THIRD_PARTY = frozenset(
    {
        "langchain",
        "langchain_core",
        "langchain_community",
        "langchain_anthropic",
        "langsmith",
        "httpx",
        "requests",
        "spacy",
        "sklearn",
    }
)

#: What the state, the verdict types and the scoring engine are allowed to reach for:
#: the standard library, :mod:`app.domain` and each other. All three are imported by the
#: judge and the API layer, so a dependency added to any of them is added to all.
PLAIN_PYTHON = ("state.py", "verdict.py", "scoring.py")


def modules() -> list[Path]:
    """Every source file in the package and its ``agents`` subpackage."""
    return sorted(GRAPH.rglob("*.py"))


def agents() -> list[Path]:
    """The seven agent modules, without the subpackage's ``__init__``."""
    return [
        path
        for path in sorted((GRAPH / "agents").glob("*.py"))
        if path.name != "__init__.py"
    ]


def test_the_package_is_where_this_thinks_it_is() -> None:
    """Guards the guard: a moved module makes every check below vacuous.

    Naming the agents rather than counting them, so deleting one fails here instead of
    quietly reducing the parametrised cases to the ones that still pass.
    """
    assert GRAPH.is_dir()
    assert {path.name for path in agents()} == {
        "claim.py",
        "search.py",
        "factcheck.py",
        "evidence.py",
        "source.py",
        "contradiction.py",
        "judge.py",
    }
    assert (GRAPH / RUNTIME_HOST).is_file()


def test_langgraph_is_imported_in_exactly_one_module() -> None:
    """The central rule, stated in both directions.

    The negative half alone would pass for a package that had stopped using LangGraph
    altogether, which is a different bug with the same symptom here.
    """
    hosts = sorted(
        path.name
        for path in modules()
        if any(_root(name) == "langgraph" for name in _imports(path))
    )
    assert hosts == [RUNTIME_HOST], (
        f"langgraph is imported in {', '.join(hosts) or 'no module'}. Exactly "
        f"{RUNTIME_HOST} may import it — see the import rule in app/graph/__init__.py."
    )


@pytest.mark.parametrize("path", agents(), ids=lambda path: path.name)
def test_no_agent_imports_the_graph_runtime(path: Path) -> None:
    """One case per agent, so a failure names the file that would stop being testable."""
    assert not any(_root(name) == "langgraph" for name in _imports(path)), (
        f"{path.name} imports langgraph, so it can no longer be called with a dict and "
        f"its tests now require the runtime to be installed."
    )


@pytest.mark.parametrize("path", agents(), ids=lambda path: path.name)
def test_no_agent_imports_another_agent(path: Path) -> None:
    """Agents talk through the state, never to each other."""
    reached = sorted(
        name
        for name in _imports(path)
        if name.startswith("app.graph.agents") and name != f"app.graph.agents.{path.stem}"
    )
    assert not reached, (
        f"{path.name} imports {', '.join(reached)}. Pass it through a channel on "
        f"GraphState instead — a direct call is an ordering the graph cannot schedule."
    )


@pytest.mark.parametrize("name", PLAIN_PYTHON)
def test_the_state_and_the_verdict_types_reach_for_nothing(name: str) -> None:
    """Both are imported by every agent, so anything they need, everything needs.

    Note the third: ``scoring.py`` is where every 0–100 comes from, and it stays plain
    for the same reason — a deployment reading a :class:`~app.graph.verdict.Score` off a
    stored ruling must not need the graph runtime to do it.

    ``state.py`` is the one that looks like it should import the runtime: its
    accumulating channel is an ``Annotated`` reducer, and LangGraph reads that
    reflectively rather than through a base class, which is what makes the file's
    independence possible at all.
    """
    reached = sorted(
        name_
        for name_ in _imports(GRAPH / name)
        if name_.startswith("app.") and not name_.startswith(("app.domain", "app.graph"))
    )
    assert not reached, f"{name} imports {', '.join(reached)}"
    assert not any(
        _root(name_) in FORBIDDEN_THIRD_PARTY for name_ in _imports(GRAPH / name)
    )


@pytest.mark.parametrize("path", modules(), ids=lambda path: path.name)
def test_no_module_reaches_for_a_chain_framework(path: Path) -> None:
    offending = sorted(
        {name for name in _imports(path) if _root(name) in FORBIDDEN_THIRD_PARTY}
    )
    assert not offending, f"{path.name} imports {', '.join(offending)}"


def test_the_agents_package_imports_no_agent() -> None:
    """``__init__`` stays empty so importing one agent does not pull the other six.

    :mod:`~app.graph.agents.judge` needs neither :class:`~app.core.config.Settings` nor a
    vendor client, and a re-export here would give it both transitively — enough to make
    ``test_graph_judge`` unrunnable in an environment without pydantic installed.
    """
    reached = sorted(
        name for name in _imports(GRAPH / "agents" / "__init__.py") if name != "__future__"
    )
    assert not reached, f"app/graph/agents/__init__.py imports {', '.join(reached)}"


# ------------------------------------------------------------------------ ast ----


def _root(module: str) -> str:
    """``langgraph.graph.state`` -> ``langgraph``."""
    return module.split(".")[0]


def _imports(path: Path) -> set[str]:
    """Every absolute module name ``path`` imports, at any scope.

    Includes ``TYPE_CHECKING`` blocks deliberately. ``workflow.py`` imports
    ``CompiledStateGraph`` under one, and a rule about where a dependency may appear
    should count an import that only a type checker follows — it is still the place a
    reader learns which module owns the runtime.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
    return found
