"""Loading the models, once per process.

Three resources, three failure modes, one place that knows about any of them.

**Every import of spaCy, NLTK and scikit-learn in this package happens inside a
function body, never at module scope.** That is not a style preference. If
``app/nlp/pipeline.py`` imported spaCy at the top, ``app.nlp.__init__`` importing it
to register the extractor would make ``import app.main`` fail on a machine without
spaCy — so the health endpoint, the verification endpoints and their entire test
suite would depend on a 500 MB NLP stack being installed to answer a request that
never touches it. Deferring the import moves that failure to the one call that
actually needs the parser, where it belongs, and it is what lets
:mod:`tests.test_claims_api` run against a stub extractor with none of these
libraries present.

**The parser is required; the segmenter and the stopword list are not.** Sentence
splitting has two good implementations here, so falling back from one to the other
is honest. The dependency parse has exactly one, and the screening and splitting
rules are meaningless without it — so a missing model is a hard, loud
:class:`~app.core.errors.ConfigurationError` naming the command that fixes it,
rather than a degraded mode that returns plausible nonsense.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from app.core.errors import ConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Guards :data:`_CACHE` only.
_CACHE_LOCK = threading.Lock()

#: Guards every parse. A different lock from the one above, and deliberately so:
#: they protect different things — the dictionary, and the model's interned string
#: store — and sharing one would deadlock the moment a parse needed to load a
#: model, because :class:`threading.Lock` is not reentrant. Nothing in this package
#: holds both. See :func:`parse_lock`.
_PARSE_LOCK = threading.Lock()

#: Loaded pipelines, keyed by spaCy model name. Never evicted: a process serves one
#: configured model, and the key exists only so a test can load a second one
#: without the first hiding it.
_CACHE: dict[str, Resources] = {}


@dataclass(frozen=True, slots=True)
class Resources:
    """Everything the pipeline needs, loaded and ready.

    ``Any`` on the two library objects rather than real types: annotating them
    properly would mean importing ``spacy`` at module scope, which is the one thing
    this module exists to avoid. The types are documented instead —
    ``nlp`` is a ``spacy.language.Language`` and ``segmenter`` is an
    ``nltk.tokenize.punkt.PunktSentenceTokenizer``.
    """

    #: The loaded spaCy pipeline. Tagger, parser, lemmatiser and NER.
    nlp: Any
    #: NLTK's trained sentence tokeniser, or ``None`` when its data is not
    #: downloaded — in which case the pipeline uses spaCy's own boundaries.
    segmenter: Any | None
    #: Lower-cased stopwords, NLTK's list union spaCy's, for the TF-IDF vectoriser.
    stopwords: frozenset[str]
    #: The model name this was loaded from, for log lines and error details.
    model: str


def load(model: str) -> Resources:
    """Return the loaded resources for ``model``, loading them on first use.

    Double-checked so that the common case — every call after the first — does not
    contend on the lock, while two requests arriving before the first load finishes
    cannot both pay for it.

    Raises :class:`ConfigurationError` when spaCy or the model is absent.
    """
    cached = _CACHE.get(model)
    if cached is not None:
        return cached
    with _CACHE_LOCK:
        cached = _CACHE.get(model)
        if cached is None:
            cached = _build(model)
            _CACHE[model] = cached
        return cached


def parse_lock() -> threading.Lock:
    """The lock every parse must hold.

    A loaded spaCy ``Language`` is not safe to call from two threads at once. The
    pipeline components themselves are stateless, but the shared ``Vocab``'s
    ``StringStore`` is written to whenever the model meets a string it has not
    interned before — which is most documents — and that write is unsynchronised. A
    torn ``StringStore`` does not raise; it yields wrong token text under load and
    nowhere else, which is the worst failure profile available.

    The alternatives were a pipeline per thread and a pipeline per process.
    Per-thread costs a full model load and its memory for every worker in anyio's
    thread pool, to buy parallelism inside one container that this deployment does
    not want anyway — ``Dockerfile`` runs a single uvicorn process on purpose and
    says so: "Concurrency comes from running more replicas". So: one parse at a
    time per process, off the event loop, and horizontal scaling for throughput.
    """
    return _PARSE_LOCK


def warm(model: str) -> None:
    """Load ``model`` now, so the first request does not pay for it.

    Deliberately *not* called from application startup. Loading en_core_web_sm takes
    the better part of a second and raises when the model is missing, so calling it
    in a lifespan hook would turn "one endpoint returns 500" into "the container
    never becomes healthy and the orchestrator restarts it forever" — including for
    a deployment that only serves ``/health`` and the verification endpoints. A
    worker process that does nothing but extract claims should call this at startup;
    the web process should not.
    """
    load(model)


# ----------------------------------------------------------------- loading ----


def _build(model: str) -> Resources:
    """Import the libraries and load everything. Called under ``_CACHE_LOCK``."""
    nlp = _load_spacy(model)
    segmenter = _load_segmenter()
    stopwords = _load_stopwords(nlp)
    logger.info(
        "nlp resources loaded",
        extra={
            "model": model,
            "segmenter": "punkt" if segmenter is not None else "spacy",
            "stopwords": len(stopwords),
        },
    )
    return Resources(nlp=nlp, segmenter=segmenter, stopwords=stopwords, model=model)


def _load_spacy(model: str) -> Any:
    """Load the spaCy pipeline, or explain exactly what to install.

    Two distinct failures with two distinct fixes, which is why they are two
    branches: the library missing means the requirements were not installed, and the
    model missing means they were, because the model is not a PyPI dependency of
    spaCy — it is a separate artefact fetched by ``spacy download``. Reporting both
    as "spaCy is broken" is what makes this a twenty-minute problem instead of a
    one-line one.
    """
    try:
        import spacy
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ConfigurationError(
            "spaCy is not installed, so claim extraction cannot run. "
            "Install the runtime dependencies: pip install -r requirements.txt",
            details={"missing": "spacy", "install": "pip install -r requirements.txt"},
        ) from exc

    try:
        return spacy.load(model)
    except OSError as exc:  # pragma: no cover - depends on the environment
        # spaCy raises OSError (E050) for an unknown model name. The model is a
        # separate download and forgetting it is the single most common way to
        # deploy this service broken, so the message is the command, verbatim.
        raise ConfigurationError(
            f"The spaCy model {model!r} is not installed. "
            f"Download it: python -m spacy download {model}",
            details={
                "missing": model,
                "install": f"python -m spacy download {model}",
            },
        ) from exc


def _load_segmenter() -> Any | None:
    """Return NLTK's trained sentence tokeniser, or ``None`` if unavailable.

    Punkt is used in preference to spaCy's boundaries because it is the better tool
    for this specific job on this specific kind of text. It is an unsupervised
    abbreviation detector: it learns from the corpus which full stops end sentences
    and which end "Dr.", "Rep.", "Inc.", "U.S.", and it exposes character offsets
    for the spans it finds. spaCy's boundaries come from the dependency parse, which
    is excellent syntax and only incidentally a segmenter — on a sentence it parses
    badly it can put a boundary mid-clause, and news copy full of abbreviations and
    quoted speech is exactly where that happens.

    Returning ``None`` rather than raising: the data is a separate download like the
    spaCy model, but unlike the model there is a good second implementation already
    in the process, so the honest response to its absence is a logged warning and a
    slightly worse segmenter — not a 500 on an endpoint that can still do its job.

    The two-branch load is NLTK 3.9's doing. It replaced the pickled ``punkt``
    tokeniser with a ``punkt_tab`` data format, because loading a trained tokeniser
    meant unpickling a file from the internet. The resource names differ, so a
    service pinned to either side of that release needs both paths.
    """
    try:
        import nltk
    except ImportError:  # pragma: no cover - depends on the environment
        logger.warning(
            "nltk is not installed; falling back to spaCy sentence boundaries",
            extra={"missing": "nltk"},
        )
        return None

    try:  # NLTK >= 3.9: a class that loads the `punkt_tab` data itself.
        from nltk.tokenize.punkt import PunktTokenizer

        return PunktTokenizer("english")
    except ImportError:
        pass  # Older NLTK. Fall through to the pickle.
    except LookupError:
        logger.warning(
            "NLTK punkt_tab data is not downloaded; falling back to spaCy "
            "sentence boundaries. Fix: python -m nltk.downloader punkt_tab stopwords",
            extra={"missing": "punkt_tab"},
        )
        return None

    try:  # NLTK < 3.9: the trained tokeniser is a pickle in the data directory.
        return nltk.data.load("tokenizers/punkt/english.pickle")
    except LookupError:
        logger.warning(
            "NLTK punkt data is not downloaded; falling back to spaCy sentence "
            "boundaries. Fix: python -m nltk.downloader punkt stopwords",
            extra={"missing": "punkt"},
        )
        return None


def _load_stopwords(nlp: Any) -> frozenset[str]:
    """Lower-cased stopwords for the vectoriser: NLTK's list, union spaCy's.

    Both, rather than either. They disagree — spaCy's list is roughly twice the size
    and carries words NLTK's does not ("various", "several", "moreover"), while
    NLTK's carries inflected forms and contractions spaCy handles by lemma. For
    keyword extraction a false positive costs one dropped term and a false negative
    puts "would" at the top of the keyword list, so the union is the right side to
    err on.

    Lower-cased because ``TfidfVectorizer`` lower-cases its input before consulting
    ``stop_words``, so a capitalised entry in the list would never match anything.
    """
    spacy_words = {word.lower() for word in nlp.Defaults.stop_words}
    try:
        from nltk.corpus import stopwords

        nltk_words = {word.lower() for word in stopwords.words("english")}
    except (ImportError, LookupError):
        logger.warning(
            "NLTK stopwords are unavailable; using spaCy's list alone. "
            "Fix: python -m nltk.downloader stopwords",
            extra={"missing": "stopwords"},
        )
        nltk_words = set()
    return frozenset(spacy_words | nltk_words)


def reset() -> None:
    """Drop the cache. For tests that load a second model; not used in serving."""
    with _CACHE_LOCK:
        _CACHE.clear()
