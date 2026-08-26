"""The seven agents, one module each.

Each module holds one agent and its ``NAME``, which is both the graph's node name and
the label the agent signs its trace notes with — one string, so a note can never name a
node that does not exist.

Every agent is a callable object rather than a function: dependencies arrive in
``__init__`` and the state arrives in ``__call__``, which is what lets
:mod:`app.graph.workflow` inject settings and a claim extractor without any agent
reaching for a global.

No agent imports another. Everything one agent tells the next travels through a channel
on :class:`~app.graph.state.GraphState`, which is what lets the graph reorder them, run
two at once, or drop one without the rest noticing.

Nothing is re-exported here either, and that is deliberate. Three of these agents —
:mod:`~app.graph.agents.evidence`, :mod:`~app.graph.agents.contradiction` and
:mod:`~app.graph.agents.judge` — need nothing but :mod:`app.domain` and
:mod:`app.research`, and re-exporting the flat names would make importing any one of
them pull the four that read :class:`~app.core.config.Settings` as well. Import from the
modules.
"""

from __future__ import annotations
