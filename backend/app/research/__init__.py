"""Turning search results into a dossier, without adding anything to them.

Everything in this package sits *above* :mod:`app.search`. That package talks to
Tavily, Brave and Serper and normalises their three response shapes into
:class:`~app.domain.research.Retrieval` objects. This one decides what those
retrievals mean: which of them are the same page, which are the same story, which
publisher each belongs to, which sentence of a snippet actually bears on the claim,
and what date — if any — can be honestly attached.

The modules, in the order the request path uses them:

* :mod:`~app.research.terms` — words and figures, tokenised once so the other
  modules cannot disagree about what a claim contains.
* :mod:`~app.research.queries` — one claim into the small ladder of queries that
  will be sent for it, adding no word the claim did not contain.
* :mod:`~app.research.urls` and :mod:`~app.research.suffixes` — one identity per
  document, and the registrable domain that identifies a publisher.
* :mod:`~app.research.dedupe` — page identity (merged) and story identity (marked).
* :mod:`~app.research.evidence` — verbatim passage selection, recorded as offsets.
* :mod:`~app.research.dossier` — assembly, dating and ordering.
* :mod:`~app.research.reviews` — what a fact-check publisher's rating means, and
  whether the claim they rated is the caller's.
* :mod:`~app.research.credibility` — grading a source *as a source*, on six axes and
  never on whose domain it is.

**The import rule.** Nothing here imports :mod:`app.search`, :mod:`app.factcheck`,
:mod:`app.providers`, :mod:`app.llm` or :mod:`app.nlp`, and ``test_research_imports``
fails the build if it ever does. The first three are the seams this package must be
testable without: a function that takes retrievals and returns sources needs no network
and no model, and keeping it that way is what makes the honesty properties — a quote is
a slice, a cluster is a label — cheap to test exhaustively. :mod:`app.llm` is the ban
that says nothing here may summarise. The last is subtler and matters more in
production: :mod:`app.nlp` brings spaCy and scikit-learn, everything here runs on the
request path, and a deployment that can search but cannot load a language model must
still produce a dossier. So :mod:`~app.research.terms` is a deliberate second, smaller
tokeniser rather than a shortcut to the good one.

Import from the modules rather than from this package. The names here are
domain-general — ``terms``, ``queries``, ``evidence`` — and would collide with local
variables at almost every call site if they were re-exported flat.
"""

from __future__ import annotations
