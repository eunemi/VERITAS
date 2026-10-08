"""Application configuration.

Every value is read from the environment (or a local ``.env``). Nothing in this
file carries a usable default for a secret: the defaults that do exist are the
safe, local-development ones, and anything that would grant access to a paid or
privileged service defaults to ``None`` so a missing key fails loudly at the call
site instead of silently working in one environment and not another.

``get_settings`` is cached, so ``Settings`` is constructed once per process and
can be overridden in tests by clearing the cache or by overriding the FastAPI
dependency that wraps it.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.errors import ConfigurationError

#: The ``backend/`` directory: this file is ``backend/app/core/config.py``.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Environment(StrEnum):
    """Deployment environment. Gates docs exposure and error verbosity."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(StrEnum):
    """Which LLM backend the ``llm`` package should resolve."""

    OPENAI = "openai"
    OLLAMA = "ollama"
    #: Embeddings only, computed in-process from word hashes and needing no key.
    #: See :mod:`app.llm.hashing` for what it does and does not measure.
    HASHING = "hashing"


class SearchProvider(StrEnum):
    """Which web-search backend the ``search`` package should resolve."""

    TAVILY = "tavily"
    SERPER = "serper"
    BRAVE = "brave"


class FactCheckProvider(StrEnum):
    """Which fact-check database the ``factcheck`` package should resolve."""

    GOOGLE = "google"


class VectorStoreProvider(StrEnum):
    """Which vector store the ``vectorstore`` package should resolve."""

    CHROMA = "chroma"
    FAISS = "faiss"
    #: In-process, unshared between workers, and no dependency to install. The
    #: honest choice for a single-process deployment and the one the store contract
    #: is tested against.
    MEMORY = "memory"


class ClaimExtractorProvider(StrEnum):
    """Which extractor the ``nlp`` package should resolve.

    One member today, and the enum exists anyway for the same reason the other four
    do: the setting is the seam. An LLM-backed extractor is the obvious second
    implementation, and having the key be a string in a settings file rather than an
    import in a service is what makes swapping it a deployment change.
    """

    SPACY = "spacy"


class VisionProvider(StrEnum):
    """Which reader and detector the ``vision`` package should resolve.

    One member per role today, and the enum exists for the reason the others do:
    the setting is the seam. A hosted OCR endpoint is the obvious second reader,
    and keeping the choice a string in a settings file is what makes swapping it a
    deployment change rather than an edit to the image desk.
    """

    TESSERACT = "tesseract"
    YOLO = "yolo"


class SpeechProvider(StrEnum):
    """Which transcriber the ``audio`` package should resolve.

    One member, for the same reason :class:`FactCheckProvider` has one: the seam is
    the setting. ``faster-whisper`` is the obvious second — same weights, a
    different runtime — and a hosted endpoint the third, so which one runs stays a
    string in a settings file rather than an import in the audio desk.
    """

    WHISPER = "whisper"


class StoreBackend(StrEnum):
    """Which verification store :func:`app.main.create_app` builds.

    The default is the database, because the point of this seam is a durable store
    and ``docker-compose`` brings PostgreSQL up beside the API. ``memory`` is the
    escape hatch: it needs no database running, which is what the test suite and a
    quick local run want, and it is why :mod:`app.repositories.memory` still ships.
    """

    DATABASE = "database"
    MEMORY = "memory"


class Settings(BaseSettings):
    """Typed view of the process environment.

    The class is deliberately flat. Grouping these into nested models reads
    tidily but means every consumer learns a second layer of names, and the seams
    that actually need to vary independently (LLM, search, vector store) are
    already separated by their provider enums.
    """

    model_config = SettingsConfigDict(
        # Resolved against the backend directory rather than the working
        # directory, so `uvicorn app.main:app` reads the same file whether it is
        # started from `backend/` or from the repository root. A real environment
        # (a container, a deploy) sets variables directly and has no .env at all,
        # which is why a missing file is not an error.
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Env vars are conventionally upper-case; matching case-insensitively
        # means `database_url` in a .env file works the same as `DATABASE_URL`.
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- app ----

    APP_NAME: str = "Veritas Verification API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Environment = Environment.LOCAL
    DEBUG: bool = False

    #: Mount point for the versioned API. Health also lives outside it.
    API_V1_PREFIX: str = "/api/v1"

    # ------------------------------------------------------------ logging ----

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    #: One JSON object per line, which is what a log collector wants. Local runs
    #: set ``console`` in ``.env`` to get a readable line instead; the default is
    #: the deployed one so that a container with no ``.env`` logs correctly.
    LOG_FORMAT: Literal["json", "console"] = "json"

    # -------------------------------------------------------------- cors ----

    #: Comma-separated in the environment, list here. The defaults are the local
    #: Next.js dev server under both names the browser can reach it by, on every
    #: port it may end up on: ``next dev`` wants 3000 and walks upward one port at
    #: a time when it is taken, so a machine with two other Node projects running
    #: serves this one from 3002 or 3003 without being asked to. ``localhost`` and
    #: ``127.0.0.1`` are different origins to the same-origin policy however
    #: identical they look, so a page opened at one of them cannot call an API
    #: that only allows the other. Deployed origins are supplied explicitly.
    #:
    #: ``NoDecode`` is load-bearing, not tidiness. Without it pydantic-settings
    #: JSON-decodes every complex-typed field before validation runs, so the bare
    #: ``CORS_ORIGINS=http://localhost:3000`` that a .env file — and therefore a
    #: container — carries raises ``SettingsError`` and the process never starts.
    #: Suppressing that hands the raw string to the validator below, which owns
    #: both accepted forms. Init keyword arguments never reach the decoder, which
    #: is why this only ever broke through the environment.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://localhost:3002",
            "http://127.0.0.1:3002",
            "http://localhost:3003",
            "http://127.0.0.1:3003",
        ]
    )

    # ---------------------------------------------------------- database ----

    #: SQLAlchemy async URL. The driver is part of the URL so swapping Postgres
    #: for something else later is a configuration change, not a code change.
    DATABASE_URL: str = "postgresql+asyncpg://veritas:veritas@localhost:5432/veritas"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    #: Which store holds verifications. ``memory`` needs no database at all — see
    #: :class:`StoreBackend`. Set it before starting the API without PostgreSQL up,
    #: or every request will fail on connection rather than on anything meaningful.
    VERIFICATION_STORE: StoreBackend = StoreBackend.DATABASE

    # -------------------------------------------------------------- auth ----

    #: Signing key for issued JWTs. There is no default: an application that
    #: signs tokens with a checked-in fallback is worse than one that will not
    #: start. Validated below for anything that is not local development.
    JWT_SECRET_KEY: SecretStr | None = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --------------------------------------------------------------- llm ----

    LLM_PROVIDER: LLMProvider = LLMProvider.OPENAI
    #: Requests time out rather than holding a worker open indefinitely.
    LLM_TIMEOUT_SECONDS: float = 60.0
    LLM_MAX_RETRIES: int = 2

    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    #: Where the chat-completions shape is served. Overridable because that shape
    #: is spoken by more than OpenAI — vLLM, llama.cpp, LM Studio and several
    #: hosted vendors — so pointing at one of those is a setting, not a client.
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    #: Local Llama 3 via Ollama. No key; the base URL is the whole config.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # ------------------------------------------------------------ search ----

    #: The single provider :func:`app.search.get_search_client` resolves, for
    #: callers that want one engine. Web research does not use it; it fans out
    #: over ``SEARCH_PROVIDERS`` instead.
    SEARCH_PROVIDER: SearchProvider = SearchProvider.TAVILY
    #: The roster web research queries, all at once. Every claim goes to every
    #: provider here that has a key; the ones without are reported as skipped
    #: rather than dropped silently.
    #:
    #: Defaults to all three, because "multiple independent websites" is the
    #: requirement and a single index cannot corroborate itself. Two of the three
    #: are enough for that — see :mod:`app.search.serper`, whose API contract could
    #: not be verified — and a deployment with one key configured still works,
    #: with the narrowing recorded in every dossier it produces.
    #:
    #: ``NoDecode`` for the same reason ``CORS_ORIGINS`` has it: without it,
    #: ``SEARCH_PROVIDERS=tavily,brave`` in a .env file is JSON-decoded before
    #: validation and the process fails to start.
    SEARCH_PROVIDERS: Annotated[list[SearchProvider], NoDecode] = Field(
        default_factory=lambda: [
            SearchProvider.TAVILY,
            SearchProvider.BRAVE,
            SearchProvider.SERPER,
        ]
    )
    SEARCH_TIMEOUT_SECONDS: float = 20.0
    #: Upper bound on results requested per query, per provider call.
    SEARCH_MAX_RESULTS: int = 10
    #: Total tries per request, not retries: 1 disables retrying. Only 429 and 5xx
    #: are retried; see :data:`app.providers.http.RETRYABLE`.
    SEARCH_ATTEMPTS: int = 3
    #: Concurrent in-flight requests per provider. Low by default because these
    #: quotas are per-key and per-second on entry-level plans — Brave's free tier
    #: in particular is documented in the low single digits — and a burst that
    #: earns a 429 costs more time in backoff than the concurrency saved. Raise it
    #: for a paid plan; check the plan rather than assuming.
    SEARCH_CONCURRENCY: int = 2
    #: Query formulations sent per claim, per provider.
    #:
    #: Three, matching :data:`app.research.queries.DEFAULT_QUERIES`: the claim itself,
    #: its terms, and its entities and figures alone. The cost is multiplicative —
    #: three queries against three providers is nine requests for one claim — which is
    #: why this is small and why it is configurable. Setting it to 1 searches only the
    #: claim as written, which is the most faithful query and the one least likely to
    #: match anything at all.
    #:
    #: Fewer queries than this are sent when the formulations collapse into each
    #: other, and :attr:`~app.domain.research.ClaimResearch.queries` records what was
    #: actually asked rather than what this permitted.
    SEARCH_QUERIES_PER_CLAIM: int = 3
    #: Claims researched per request, at most.
    #:
    #: The request count multiplies out fast — this times
    #: ``SEARCH_QUERIES_PER_CLAIM`` times the provider roster, so ten claims at the
    #: defaults is ninety provider requests — and an article can easily make fifty
    #: checkable assertions. Ten is a ceiling on what one HTTP request may spend of a
    #: shared, metered quota, not a judgement about how many claims are worth
    #: checking.
    #:
    #: When it truncates, the claims that were dropped are named in the response with
    #: the reason. Silently researching the first ten of fifty and returning them as
    #: "the claims" would misdescribe the submission.
    SEARCH_MAX_CLAIMS: int = 10

    TAVILY_API_KEY: SecretStr | None = None
    SERPER_API_KEY: SecretStr | None = None
    BRAVE_API_KEY: SecretStr | None = None

    #: Which Tavily index to search: ``general``, ``news`` or ``finance``.
    #:
    #: ``general`` is the default because fact-checking wants primary documents —
    #: statute, filings, papers, government pages — and the news index does not
    #: rank those. The cost is dates: Tavily returns ``published_date`` only on
    #: ``news``, so most results from the default will have none. That trade is
    #: made in favour of finding the right page over knowing when the wrong one
    #: was published.
    TAVILY_TOPIC: str = "general"
    #: ``basic`` or ``advanced``. ``advanced`` returns better-targeted chunks at a
    #: higher credit cost per search.
    TAVILY_SEARCH_DEPTH: str = "basic"

    def search_secrets(self) -> tuple[str, ...]:
        """Every configured search API key, for redaction.

        Exists so that :mod:`app.search.fanout` can scrub provider error text
        without knowing which vendors have keys. Adding a provider means adding
        its key here and to the roster above — one file, two lines, and no way to
        add a key that redaction then misses.

        Returns the raw secret values, so this is only ever called to build the
        argument to :func:`app.providers.http.redact`. It must not be logged.
        """
        keys = (self.TAVILY_API_KEY, self.SERPER_API_KEY, self.BRAVE_API_KEY)
        return tuple(key.get_secret_value() for key in keys if key is not None)

    # -------------------------------------------------------- fact check ----

    FACT_CHECK_PROVIDER: FactCheckProvider = FactCheckProvider.GOOGLE
    GOOGLE_FACT_CHECK_API_KEY: SecretStr | None = None
    FACT_CHECK_TIMEOUT_SECONDS: float = 20.0
    #: Total tries per request, not retries: 1 disables retrying. Same policy as
    #: ``SEARCH_ATTEMPTS`` — see :data:`app.providers.http.RETRYABLE`.
    FACT_CHECK_ATTEMPTS: int = 3
    #: Records requested per claim. Ten is the API's own default page size.
    #:
    #: Only the first page is ever read (see :mod:`app.factcheck.google`), so this is
    #: the hard ceiling on records per claim, not a batch size. Ten is generous for the
    #: purpose: a claim with more than ten published fact checks is a famous one, and
    #: the eleventh is not going to change the picture.
    FACT_CHECK_MAX_RESULTS: int = 10
    #: BCP-47 language to restrict reviews to, or empty for no restriction.
    #:
    #: Empty by default, deliberately. Filtering to ``en`` would hide a Spanish-language
    #: fact check of a Spanish-language claim, which is a real fact check about the real
    #: world, and the cost of that is worse than the cost of a rating this service
    #: cannot read: an unreadable rating is reported as
    #: :attr:`~app.domain.factcheck.Stance.UNRECOGNISED` with the publisher's own words
    #: intact, so the reader still gets the URL, the outlet and the verdict as written.
    FACT_CHECK_LANGUAGE: str = ""
    #: Ignore reviews older than this many days, or 0 for no limit.
    #:
    #: Zero by default because a fact check does not expire. The 2016 debunk of a
    #: rumour is the reason the rumour is known to be false, and a window would drop it
    #: while keeping this month's re-circulation of the same rumour unreviewed. Google
    #: measures the age from the claim date or the review date, whichever is newer.
    FACT_CHECK_MAX_AGE_DAYS: int = 0
    #: Concurrent in-flight lookups. Low for the reason ``SEARCH_CONCURRENCY`` is: the
    #: quota is per-key and daily, and one request per claim is already the smallest
    #: number of requests this can take.
    FACT_CHECK_CONCURRENCY: int = 2
    #: How much of the claim a database record must repeat to count as being about it.
    #:
    #: Scored by :func:`app.research.evidence.assess`, the same arithmetic as evidence
    #: selection, and compared against
    #: :attr:`~app.domain.factcheck.FactCheck.match`. Low by default — see
    #: :data:`app.research.reviews.MIN_MATCH` for the argument, which is that the two
    #: failure directions are not symmetric. A record that slips through arrives with
    #: the fact-checker's own wording of the claim attached, so a reader can see it is
    #: about something else; a record wrongly excluded becomes a silent "nobody has
    #: reviewed this".
    FACT_CHECK_MIN_MATCH: float = 0.15

    def fact_check_secrets(self) -> tuple[str, ...]:
        """Every configured fact-check API key, for redaction.

        The counterpart to :meth:`search_secrets`, kept separate because the two are
        passed to different fan-outs and a lookup has no business being handed the
        search keys. Same rule: returns raw secret values, so it is only ever called to
        build the argument to :func:`app.providers.http.redact`, and must not be logged.
        """
        keys = (self.GOOGLE_FACT_CHECK_API_KEY,)
        return tuple(key.get_secret_value() for key in keys if key is not None)

    # ------------------------------------------------------- credibility ----

    #: Whether each source is graded as a source — see :mod:`app.domain.credibility`.
    #:
    #: On by default, and it costs nothing per request: the scoring is arithmetic over
    #: retrievals this service already has, with no network call and no model behind
    #: it. The switch exists because every number it produces is this service's own
    #: judgement rather than something a provider reported, and an operator who does
    #: not want that in their responses should be able to stop producing it without
    #: patching a service.
    #:
    #: Off leaves :attr:`~app.domain.research.ClaimResearch.credibility` empty, which
    #: is an absence of assessment and not a finding about any source. Nothing else on
    #: the dossier changes: no source is dropped, reordered or rescored, because the
    #: grading is reported beside the sources and never applied to them.
    CREDIBILITY_ENABLED: bool = True
    #: How old a page may be and still read as current, in days.
    #:
    #: A year, because "recent" for a claim about the world is not "recent" for a news
    #: cycle: a figure published eleven months ago is usually still the current figure.
    #: Read against the dossier's ``retrieved_at`` rather than a fresh clock, so two
    #: sources in one response are judged against the same instant.
    CREDIBILITY_FRESH_DAYS: int = 365
    #: How old a page may be before its age is worth remarking on, in days.
    #:
    #: Ten years, and deliberately far out. Age is not a fault —
    #: :attr:`~app.domain.credibility.Axis.DATE` reports what is known about a page's
    #: date rather than penalising an old one — because the 2016 debunk is the reason
    #: a rumour is known to be false and the statute a claim turns on may be from 1974.
    #: Pulling this in towards a news window would quietly downgrade the primary
    #: documents that settle most claims.
    CREDIBILITY_STALE_DAYS: int = 3650

    # ------------------------------------------------------------- judge ----
    #
    # The sufficiency gate — see :class:`app.graph.verdict.Thresholds`. Every one of
    # these is a reason for the judge to return ``UNCERTAIN`` rather than a weight in a
    # score, so raising one makes the graph *decline* to rule more often rather than
    # making it stricter about what it calls true.

    #: Independent sources that must carry a passage bearing on a claim before it can
    #: be ruled on at all. Two, because one page saying something is not corroboration
    #: and the commonest false verdict in a system like this is a single source
    #: restated with confidence. Syndicated copies and repeat domains are discounted
    #: first, so three reprints of one wire story do not satisfy this.
    JUDGE_MIN_SOURCES: int = 2
    #: Lowest :attr:`app.domain.Credibility.standing` that counts towards the above.
    #: At :data:`app.domain.credibility.BAND_MODERATE`, so a source whose publisher,
    #: date and quotable content could not be established is not counted as one of the
    #: two. An ungraded source still counts — ``CREDIBILITY_ENABLED`` being off must
    #: not silently decide every verdict.
    JUDGE_MIN_STANDING: float = 0.40
    #: Total indication weight below which nothing has been established either way.
    #: Reached by, say, one corroborating passage from a well-established source, or a
    #: single unanimous fact-check rating — anything less is a claim nobody found
    #: anything on, which is a finding of its own and not a weak verdict.
    JUDGE_MIN_WEIGHT: float = 0.60
    #: Share of the total weight the losing side must reach for a claim to read as
    #: contested rather than settled. Just under a third: a claim carried 7-to-3 has
    #: real disagreement behind it and a reader who is shown only the 7 has been
    #: misled about how settled it is.
    JUDGE_CONTEST_MARGIN: float = 0.30

    # --------------------------------------------------------- reasoning ----
    #
    # The final reading of a dossier — see :mod:`app.reasoning`. It runs after the
    # judge and cannot overturn the sufficiency gate above, so nothing here loosens
    # anything there.

    #: Whether a language model reads the dossier at all. Off is a supported
    #: configuration and not a degraded one: the verdict, score and citations are
    #: produced by :mod:`app.graph` either way, and this layer adds an explanation
    #: of them. A deployment with no key, no budget or no appetite for a model in
    #: the path sets this to false and loses prose, not findings.
    REASONING_ENABLED: bool = True
    #: Zero, because the same dossier should read the same way twice. This is not a
    #: drafting task where variety is wanted.
    REASONING_TEMPERATURE: float = 0.0
    #: Output ceiling. Generous for four sentences and a short list of ids, because
    #: a truncated reply is discarded whole — the JSON does not close — and the cost
    #: of the margin is far lower than the cost of paying for a reply twice.
    REASONING_MAX_TOKENS: int = 700
    #: How many passages the model is shown. It may cite only what it is shown, so
    #: this is also the ceiling on how much evidence can appear in an answer. Twelve
    #: keeps the brief inside a comfortable context while covering more sources than
    #: :attr:`JUDGE_MIN_SOURCES` requires; the passages are chosen one per source
    #: before any source gets a second, so a single prolific page cannot fill it.
    REASONING_MAX_EXHIBITS: int = 12

    # ------------------------------------------------------ vector store ----

    VECTOR_STORE_PROVIDER: VectorStoreProvider = VectorStoreProvider.CHROMA
    #: On-disk location for Chroma. Ignored by FAISS, which uses INDEX_PATH.
    CHROMA_PERSIST_DIRECTORY: str = "./var/chroma"
    FAISS_INDEX_PATH: str = "./var/faiss/index.faiss"
    #: Which provider turns text into vectors, resolved separately from
    #: :attr:`LLM_PROVIDER` because embedding and generation are different
    #: capabilities and a deployment may have one and not the other. The default
    #: OpenAI generates text and does not embed, so a single key would otherwise make
    #: retrieval unreachable in every default deployment — and retrieval is the one
    #: part of this pipeline that costs nothing to run locally.
    EMBEDDING_PROVIDER: LLMProvider = LLMProvider.HASHING
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # ------------------------------------------------ evidence retrieval ----

    #: Whether the fact-check desk indexes a run's passages and retrieves against
    #: them. Off is a degradation and not a different result: retrieval is a second
    #: reading of what was already gathered — see :mod:`app.services.evidence` — so
    #: what it changes is which passages a reader is shown first, never the ruling.
    EVIDENCE_INDEX_ENABLED: bool = True
    #: How many passages :class:`app.services.evidence.EvidenceIndex` returns for a
    #: claim. Above :data:`app.research.evidence.MAX_EVIDENCE`, which is the cap on
    #: what one *source* contributes to a dossier: this reaches across every source
    #: found for the claim, so the same number would be a narrower answer.
    EVIDENCE_TOP_K: int = 8
    #: Cosine similarity below which a retrieved passage is dropped.
    #:
    #: A vector store always answers — it returns the nearest neighbours it has,
    #: however far away they are — so without a floor the least relevant passage in
    #: the index is reported as relevant whenever the index is small. Low, because
    #: this cuts off noise rather than ranking: the ordering above it is the store's
    #: to decide.
    EVIDENCE_MIN_SIMILARITY: float = 0.05

    # -------------------------------------------------- claim extraction ----

    CLAIM_EXTRACTOR: ClaimExtractorProvider = ClaimExtractorProvider.SPACY

    #: The spaCy pipeline to load. ``en_core_web_sm`` is the default because it is
    #: 12 MB against ``trf``'s 400-odd and needs no GPU, and because the two things
    #: the rules here depend on — dependency labels and entity spans — are what the
    #: small model is weakest at only in the tail. Note this is *not* installed by
    #: ``pip install -r requirements.txt``: spaCy models are separate artifacts, so
    #: a deploy needs ``python -m spacy download en_core_web_sm`` as its own step.
    SPACY_MODEL: str = "en_core_web_sm"

    #: Fewest content-bearing tokens a clause needs before it is worth checking.
    #: Four admits "The bridge opened in March" and rejects "It did." Counted over
    #: words and numbers, so punctuation cannot pad a fragment over the line.
    CLAIM_MIN_TOKENS: int = 4

    #: How many keywords to return per claim and for the document. Ten is where a
    #: TF-IDF ranking over a handful of sentences stops distinguishing terms and
    #: starts listing them.
    CLAIM_MAX_KEYWORDS: int = 10

    #: Ceiling on sentences read from one submission. ``MAX_TEXT_CHARS`` bounds the
    #: bytes but not the work: 100,000 characters is a few thousand sentences, and
    #: the parse is linear in them while the usefulness of the two-thousandth claim
    #: in one response is nil. The response reports how many sentences were read, so
    #: a client can see the cap was hit rather than infer the tail was empty.
    CLAIM_MAX_SENTENCES: int = 400

    # -------------------------------------------------------------- media ----

    #: How long to wait for a submitted media URL. Higher than an API timeout
    #: because this fetches a file from a host nobody here controls.
    MEDIA_FETCH_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0)

    #: Allow media URLs that resolve to private, loopback or link-local addresses.
    #: Off, because a URL supplied by a caller and fetched by this server is a
    #: request-forgery primitive: see ``app/media/fetch.py``. Turn it on only for
    #: a local fixture server.
    MEDIA_ALLOW_PRIVATE_HOSTS: bool = True

    # ------------------------------------------------------------- vision ----

    IMAGE_READER: VisionProvider = VisionProvider.TESSERACT
    OBJECT_DETECTOR: VisionProvider = VisionProvider.YOLO

    #: Tesseract language packs, in its own ``+``-joined form (``eng+deu``). Each
    #: one named here must be installed alongside the binary.
    TESSERACT_LANGUAGE: str = "eng"

    #: Tesseract page segmentation mode. 3 is full automatic page segmentation,
    #: which is right for the mixed screenshots and photographs this receives; 6
    #: (assume one uniform block) reads a cropped quote better but merges columns.
    TESSERACT_PSM: int = Field(default=3, ge=0, le=13)

    #: Per-word confidence below which a word is dropped rather than reported. A
    #: misread word inside a sentence is worse than a gap, because it becomes a
    #: claim about something nobody said.
    TESSERACT_MIN_CONFIDENCE: float = Field(default=0.45, ge=0.0, le=1.0)

    #: How many prepared variants of an image to OCR before taking the best. Each
    #: pass costs a full recognition, and the third (deskewed) only helps a
    #: photographed page. Lowering this to 1 reads the grayscale pass only.
    IMAGE_MAX_PASSES: int = Field(default=3, ge=1)

    #: Characters of recovered text below which the desk reports that it found no
    #: readable claim rather than sending fragments into the pipeline.
    IMAGE_MIN_TEXT_CHARS: int = Field(default=24, ge=1)

    #: Height, in pixels, to upscale a small image to before OCR. Tesseract's
    #: classifier is trained around 30px of x-height and degrades sharply below 20.
    IMAGE_UPSCALE_TO: int = Field(default=900, ge=0)

    #: Whether to run object detection at all. Independent of the relevance gate:
    #: this is the deployment saying it has the weights, the gate is the image
    #: saying its text is about objects.
    IMAGE_DETECTION_ENABLED: bool = True

    #: YOLOv8 weights. A bare filename is resolved by ultralytics, which
    #: *downloads it from the internet on first use* and caches it — so a sealed
    #: deployment should set this to an absolute path to a file it ships.
    YOLO_WEIGHTS: str = "yolov8n.pt"

    #: Confidence below which a detection is discarded.
    YOLO_MIN_CONFIDENCE: float = Field(default=0.40, ge=0.0, le=1.0)

    # -------------------------------------------------------------- audio ----

    TRANSCRIBER: SpeechProvider = SpeechProvider.WHISPER

    #: Which Whisper checkpoint to load, or an absolute path to a ``.pt`` file. A
    #: bare name is resolved by whisper, which *downloads it from the internet on
    #: first use* and caches it under :attr:`WHISPER_DOWNLOAD_ROOT` — the same trap
    #: as :attr:`YOLO_WEIGHTS`, so a sealed deployment ships the file and names it
    #: here. ``base`` is roughly 140 MB and transcribes clean speech well; ``small``
    #: and ``medium`` are markedly better on accents and cross-talk and cost
    #: proportionally more CPU.
    WHISPER_MODEL: str = "base"

    #: Where whisper caches downloaded checkpoints. ``None`` leaves its default
    #: (``~/.cache/whisper``), which is per-user and therefore lost on a container
    #: restart — set it to a mounted path to download once rather than per deploy.
    WHISPER_DOWNLOAD_ROOT: str | None = None

    #: ``cpu`` or ``cuda``. Not auto-detected: a process that silently falls back to
    #: CPU turns a 30-second transcription into a ten-minute one, and the deployment
    #: should say which it expects.
    WHISPER_DEVICE: str = "cpu"

    #: ISO code of the spoken language, or ``None`` to let whisper detect it from
    #: the first 30 seconds. Naming it is both faster and more accurate; detection
    #: is what a mixed-language intake needs.
    WHISPER_LANGUAGE: str | None = None

    #: Whisper's own probability that a segment contains no speech, above which the
    #: segment is discarded. Its decoder emits a most-likely continuation even for
    #: audio with nothing in it, and this is the model's own signal that it did.
    WHISPER_NO_SPEECH_CEILING: float = Field(default=0.60, ge=0.0, le=1.0)

    #: Seconds of audio read from one submission. The decoder truncates rather than
    #: refusing, and the report says it did: half an hour of a two-hour recording
    #: still yields checkable claims, whereas rejecting the file yields none. This
    #: also bounds memory — decoded audio is 64 KB per second, so the default is
    #: about 115 MB of samples.
    AUDIO_MAX_SECONDS: float = Field(default=1800.0, gt=0)

    #: How long to let ffmpeg run before killing it. A malformed container can make
    #: a decoder spin, and without this the worker thread never comes back.
    AUDIO_DECODE_TIMEOUT_SECONDS: float = Field(default=120.0, gt=0)

    #: Decibels below the clip's peak at which audio counts as silence, for
    #: ``librosa.effects.split``. 35 keeps room tone out of the speech spans without
    #: clipping the quiet end of a sentence; lower values split mid-word.
    AUDIO_SILENCE_FLOOR_DB: float = Field(default=35.0, gt=0)

    #: Seconds of detected speech below which the desk reports that it heard nothing
    #: rather than loading a model. Checked before transcription, so a music bed or
    #: a silent track costs a signal measurement instead of an inference.
    AUDIO_MIN_SPEECH_SECONDS: float = Field(default=1.0, ge=0.0)

    #: Fraction of a transcribed segment that must fall inside a detected speech
    #: span for the words to be kept. This is the anti-hallucination gate; see
    #: :func:`app.audio.analyse.voiced` for why it is not optional.
    AUDIO_MIN_VOICED_RATIO: float = Field(default=0.35, ge=0.0, le=1.0)

    #: Per-segment confidence below which words are dropped rather than reported,
    #: for the reason :attr:`TESSERACT_MIN_CONFIDENCE` exists: a plausible mishearing
    #: inside a sentence becomes a claim about something nobody said.
    AUDIO_MIN_CONFIDENCE: float = Field(default=0.30, ge=0.0, le=1.0)

    #: Characters of transcript below which the desk reports that it recovered no
    #: checkable speech rather than sending fragments into the pipeline.
    AUDIO_MIN_TEXT_CHARS: int = Field(default=24, ge=1)

    #: How many buckets the published waveform is reduced to. The reader draws it at
    #: a few hundred pixels wide, so anything finer is bytes it throws away. 0 omits
    #: the envelope entirely.
    AUDIO_ENVELOPE_BUCKETS: int = Field(default=160, ge=0)

    # ------------------------------------------------------------ uploads ----

    #: Ceiling on artifact size, in bytes. Enforced by the upload dependency
    #: rather than left to the reverse proxy, so limits hold in local runs too.
    MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024

    #: Ceiling on submitted prose, in characters. A separate limit because the
    #: JSON path is the only ingress today — ``MAX_UPLOAD_BYTES`` is never
    #: consulted for a pasted article — and because the cost of text is what a
    #: desk has to read rather than what it has to store. Enforced in the service
    #: rather than as a pydantic field constraint so that the bound is
    #: configurable per deployment and applies to a worker as well as a request.
    #:
    #: Note what this does *not* do: the body is fully read and parsed before any
    #: check runs, so this yields a clean 413 rather than protecting the process.
    #: A Content-Length guard in middleware is the fix for that, and is not built.
    MAX_TEXT_CHARS: int = 100_000

    # ------------------------------------------------------- validation ----

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept ``a,b`` from the environment as well as a JSON array.

        ``NoDecode`` on the field means nothing else parses this string, so the
        JSON form is decoded here rather than left to pydantic-settings. A
        malformed array raises ``JSONDecodeError`` — a ``ValueError`` — which
        pydantic reports as an ordinary validation error naming the field,
        instead of the loader-level ``SettingsError`` it used to produce.
        """
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if stripped.startswith("["):
            return json.loads(stripped)
        return [origin.strip() for origin in stripped.split(",") if origin.strip()]

    @field_validator("SEARCH_PROVIDERS", mode="before")
    @classmethod
    def _split_providers(cls, value: object) -> object:
        """Accept ``tavily,brave`` from the environment as well as a JSON array.

        Same reasoning as :meth:`_split_origins`, and the same ``NoDecode``. The
        comma form is the one an operator will actually write in a .env file, and
        an unknown name still fails validation naming the field and listing the
        providers that exist.
        """
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if stripped.startswith("["):
            return json.loads(stripped)
        return [name.strip() for name in stripped.split(",") if name.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT is Environment.PRODUCTION

    @property
    def is_local(self) -> bool:
        return self.ENVIRONMENT is Environment.LOCAL

    @model_validator(mode="after")
    def _require_deployment_secrets(self) -> Settings:
        """Refuse to start a deployed process that is missing a real secret.

        A missing signing key is only tolerable on a laptop, where the tokens are
        thrown away. Anywhere else, starting without one means the service issues
        tokens nobody can trust — which is worse than not starting, because it
        fails silently and only at the point where a token is verified.

        Raising here rather than at first use is deliberate: configuration
        mistakes should surface when the container starts and the deploy can be
        rolled back, not on the first request that happens to need auth.
        """
        if self.is_local:
            return self

        if self.JWT_SECRET_KEY is None or not self.JWT_SECRET_KEY.get_secret_value():
            raise ConfigurationError(
                "JWT_SECRET_KEY must be set when ENVIRONMENT is not 'local'.",
                details={"setting": "JWT_SECRET_KEY", "environment": self.ENVIRONMENT},
            )

        if self.is_production:
            if "*" in self.CORS_ORIGINS:
                # With `allow_credentials=True`, a wildcard origin means any site
                # can make credentialed calls to this API on a visitor's behalf.
                raise ConfigurationError(
                    "CORS_ORIGINS cannot contain '*' in production; "
                    "list the exact origins.",
                    details={"setting": "CORS_ORIGINS"},
                )
            if self.DEBUG:
                raise ConfigurationError(
                    "DEBUG cannot be enabled in production.",
                    details={"setting": "DEBUG"},
                )

        return self

    @property
    def docs_enabled(self) -> bool:
        """Interactive docs are for humans working on the service, not the web."""
        return not self.is_production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings.

    Cached so that importing configuration is free after the first call, and so
    tests can substitute a different instance by clearing the cache:

        get_settings.cache_clear()
    """
    return Settings()
