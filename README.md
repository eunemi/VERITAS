<a id="top"></a>

<div align="center">

<img src="docs/assets/veritas-hero.svg" alt="Veritas — The truth behind the story. Five tools, one evidence trail." width="100%" />

<br />

**An evidence-first workspace for checking the stories we read, receive, and share.**

Text, images, documents, and public pages — examined against live sources,<br />
with citations, reasoning, and uncertainty kept in view.

<br />

[![Open Veritas](https://img.shields.io/badge/OPEN_VERITAS-D6BD84?style=for-the-badge&logo=vercel&logoColor=151C18)](https://veritasreal.vercel.app)
[![Explore the tools](https://img.shields.io/badge/EXPLORE_THE_TOOLS-243C30?style=for-the-badge&logo=readthedocs&logoColor=F1E9D8)](https://veritasreal.vercel.app/intel)
[![API health](https://img.shields.io/badge/API_HEALTH-18231D?style=for-the-badge&logo=fastapi&logoColor=D6BD84)](https://veritas-ojg4.onrender.com/health)

<br />

![Next.js 16](https://img.shields.io/badge/Next.js-16-151C18?style=flat-square&logo=nextdotjs&logoColor=white&labelColor=293A30)
![React 19](https://img.shields.io/badge/React-19-151C18?style=flat-square&logo=react&logoColor=DDD0AA&labelColor=293A30)
![TypeScript](https://img.shields.io/badge/TypeScript-5-151C18?style=flat-square&logo=typescript&logoColor=DDD0AA&labelColor=293A30)
![Python 3.12](https://img.shields.io/badge/Python-3.12+-151C18?style=flat-square&logo=python&logoColor=DDD0AA&labelColor=293A30)
![FastAPI](https://img.shields.io/badge/FastAPI-async-151C18?style=flat-square&logo=fastapi&logoColor=DDD0AA&labelColor=293A30)
![LangGraph](https://img.shields.io/badge/LangGraph-workflows-151C18?style=flat-square&logo=langgraph&logoColor=DDD0AA&labelColor=293A30)

<br />

[The experience](#the-experience) · [Five tools](#five-tools-one-method) · [URL flow](#url-checks-are-live-jobs) · [Architecture](#inside-the-engine) · [Quickstart](#run-it-locally) · [Deployment](#ship-it) · [API](#the-api) · [Contributing](#contributing)

</div>

<br />

## The experience

### Question the story. Follow the evidence.

Veritas turns an artifact into an inspectable record. Submit a headline, a forwarded message, a screenshot, a document, or an article link. The system extracts checkable claims, gathers evidence, assesses what the sources actually support, and returns a report you can read source by source.

The interface takes its cues from an editorial desk: a masthead, an examination bench, annotated copy, an exhibit ledger, and a final determination. Serif headlines, warm paper, dark ink, and restrained motion give the evidence room to breathe.

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>01 &nbsp; Bring the artifact</h3>
      <p>Paste, upload, or link. Five focused tools share a single verification workflow.</p>
      <sub>TEXT · IMAGE · DOCX · PDF · URL</sub>
    </td>
    <td width="33%" valign="top">
      <h3>02 &nbsp; Watch the examination</h3>
      <p>A submission opens a record. Live polling follows the desks as their reports arrive.</p>
      <sub>SUBMIT → EXAMINE → ADJUDICATE</sub>
    </td>
    <td width="33%" valign="top">
      <h3>03 &nbsp; Read the evidence</h3>
      <p>Inspect claim annotations, source excerpts, provider outcomes, and the reasoning behind the finding.</p>
      <sub>CITATIONS · CONTEXT · UNCERTAINTY</sub>
    </td>
  </tr>
</table>

> **The principle:** a confident-looking answer is not enough. The record should show what was checked, what was found, and what remains unresolved.

<br />

## Five tools, one method

| Desk | Bring | What the tool does | Open |
| :--- | :--- | :--- | :---: |
| **01 / Text** | Headlines, articles, statements, forwarded messages | Extracts claims, searches live sources, and returns an annotated evidence report. LLM-assisted extraction supports multilingual input, including Hindi and Hinglish. | [↗](https://veritasreal.vercel.app/intel/text) |
| **02 / Image** | Photographs, screenshots, captions, public image URLs | Describes visible details, recovers text, inspects metadata, and checks caption claims. Google Cloud Vision can add matching pages when configured. | [↗](https://veritasreal.vercel.app/intel/image) |
| **03 / DOCX** | Word documents | Extracts readable paragraph text and routes it through the same claim-and-evidence pipeline as pasted prose. | [↗](https://veritasreal.vercel.app/intel/docx) |
| **04 / PDF** | Text-based reports, notices, articles | Extracts embedded text and checks its claims. Scanned PDFs need OCR before submission. | [↗](https://veritasreal.vercel.app/intel/pdf) |
| **05 / URL** | Public article and page links | Fetches readable page content, follows permitted public redirects, and checks the page's claims against other sources with live progress shown inside the URL field. | [↗](https://veritasreal.vercel.app/intel/url) |

The **fact-check desk** gathers and evaluates evidence. The **decision desk** combines the filed reports into the final determination and is appended automatically. DOCX and PDF are frontend intake tools, not separate backend verification desk IDs.

<details>
<summary><strong>Inside a report</strong> — the details behind the determination</summary>

- **Verdict:** a determination, headline, rationale, and confidence estimate.
- **Annotations:** the original quoted claim, an explanation, and a finding.
- **Exhibits:** source URLs, literal evidence excerpts, relevance, and reliability labels.
- **Ledger:** examination metadata, source counts, and provider availability.
- **Signals:** readings used to explain the report.
- **Image detail:** observations, recovered text, metadata, web context, and limitations when available.

Common claim outcomes are `SUPPORTED`, `CONTRADICTED`, `CONTESTED`, and `INSUFFICIENT`. A decisive semantic finding needs independent cited evidence. Confidence is a model estimate, not a calibrated probability.

Image context and caption checking do not certify pixel authenticity, original capture date, or AI generation. Related search results are distinguished from actual image matches.

</details>

<br />

## URL checks are live jobs

The URL desk does not pretend to verify a page instantly in the browser. It opens the
same server-side verification record used by the other desks and keeps the reader
informed while the page is being fetched and examined:

1. The browser validates that the input is a complete `http://` or `https://` URL.
2. `POST /api/v1/verify` accepts the URL and returns `202 Accepted` with a record id.
3. The backend checks the host, follows up to three public redirects, fetches the page,
   removes scripts and non-readable markup, and keeps the original URL as provenance.
4. The text and fact-check desks extract claims, search independent sources, compare the
   evidence, and file their reports. The decision desk signs the final record.
5. The frontend polls `GET /api/v1/verification/{id}` and honors the server's
   `Retry-After` hint. The URL field shows a scan line, spinner, hostname, active desk,
   filed-desk count, and progress bar while this happens.
6. The page renders the completed exhibits and determination, or a clear service/page
   failure when the public URL cannot be read.

Only publicly reachable pages can be fetched. Private, loopback, link-local, and other
non-public destinations are refused on every redirect hop. A valid URL can still finish
with `INSUFFICIENT` when it returns no readable prose, requires browser JavaScript to
render its content, blocks the fetcher, or has no claims that can be checked.

<br />

## Built around evidence

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>↗ &nbsp; Live source discovery</h3>
      <p>Tavily, Brave, and Serper adapters support concurrent research. Google Fact Check lookup adds published reviews alongside web evidence.</p>
    </td>
    <td width="50%" valign="top">
      <h3>⌁ &nbsp; Grounded assessment</h3>
      <p>The semantic judge selects numbered evidence passages. The server validates citations and supplies the excerpts and source URLs.</p>
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h3>◇ &nbsp; Independent corroboration</h3>
      <p>URL normalization and story clustering distinguish independent reporting from repeated domains and syndicated copies.</p>
    </td>
    <td valign="top">
      <h3>◎ &nbsp; Visible uncertainty</h3>
      <p>Missing keys, unavailable providers, and insufficient evidence remain visible in the result instead of becoming invented certainty.</p>
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h3>▤ &nbsp; A personal record</h3>
      <p>Bearer-token authentication attaches submissions to an account. Owned records and their history are available only to that account.</p>
    </td>
    <td valign="top">
      <h3>↔ &nbsp; Replaceable providers</h3>
      <p>OpenAI-compatible endpoints, Groq configuration, and Ollama support sit behind provider interfaces, with separate vision settings when needed.</p>
    </td>
  </tr>
</table>

<br />

## Inside the engine

<img src="docs/assets/veritas-system.svg" alt="Three system layers: the Next.js workspace, the FastAPI and LangGraph examination engine, and the persistent evidence record." width="100%" />

### From artifact to finding

```mermaid
flowchart LR
    A["Artifact"] --> B["Claim extraction"]
    B --> C["Live web search"]
    B --> D["Published fact checks"]
    C --> E["Evidence selection"]
    D --> E
    E --> F["Source assessment"]
    F --> G["Contradiction analysis"]
    G --> H["Semantic judge"]
    H --> I["Desk reports"]
    I --> J["Decision record"]

    classDef intake fill:#F2E9D5,stroke:#AC9159,color:#24372E
    classDef research fill:#284B3B,stroke:#8DA98B,color:#F5EFDF
    classDef record fill:#18231D,stroke:#C7AC72,color:#E8D8B3
    class A,B intake
    class C,D,E,F,G research
    class H,I,J record
```

Search and published fact-check lookup run as parallel branches. When extraction finds no checkable claims, the graph skips research and goes directly to the judge. Document text and image-derived claims join the text/evidence workflow; visual inspection adds image-specific context.

<details>
<summary><strong>Request lifecycle &amp; deployment topology</strong></summary>

```mermaid
sequenceDiagram
    actor Reader
    participant Web as Next.js · Vercel
    participant API as FastAPI · Render
    participant DB as PostgreSQL · Neon
    participant Work as Examination task
    participant Sources as Search / LLM / Vision
    Reader->>Web: Submit an artifact
    Web->>API: POST /api/v1/verify
    API->>DB: Persist pending record
    API-->>Web: 202 Accepted + record ID
    API->>Work: Start background examination
    Work->>Sources: Gather and assess evidence
    loop Until terminal
        Web->>API: GET /api/v1/verification/{id}
        API->>DB: Read status and reports
        API-->>Web: Record + polling hint
    end
    Work->>DB: File reports and final status
    Web-->>Reader: Render the completed record
```

The current execution model uses a bounded in-process verification runner inside the
API process. PostgreSQL persists records and the runner can recover open records after
an API restart, but PostgreSQL is not a durable job queue. Keep one API process per
container unless a real external worker queue is added. In-memory stores are available
for quick local development and lose accounts and records when the process restarts.
The Chroma evidence index uses hashing-based embeddings for passage retrieval, rather
than a separate semantic embedding API.

</details>

### The stack

| Layer | Technologies |
| :--- | :--- |
| **Editorial frontend** | Next.js 16 · React 19 · TypeScript · Tailwind CSS 4 · Framer Motion |
| **API & contracts** | Python 3.12+ · FastAPI · Uvicorn · Pydantic v2 · HTTPX |
| **Verification workflow** | LangGraph · claim extraction · source assessment · semantic judging |
| **Text & documents** | spaCy · NLTK · scikit-learn · python-docx · pypdf |
| **Models & research** | OpenAI-compatible APIs / Groq · Ollama · Tavily · Brave · Serper |
| **Image context** | Multimodal model · Pillow · Google Cloud Vision Web Detection · optional local OCR/detection |
| **Persistence** | PostgreSQL · SQLAlchemy async · asyncpg · Alembic · Chroma |
| **Identity** | Argon2id password hashes · PyJWT bearer tokens · record ownership checks |
| **Delivery & tooling** | Vercel · Render · Neon · Docker · pytest · Ruff · mypy · ESLint |

<br />

## Run it locally

**You will need:** Node.js **20.9+**, Python **3.12+**, and credentials for a
language-model provider and at least one search provider for live verification.
PostgreSQL is optional for the in-memory quickstart below and required for durable
accounts and verification records.

### 1 / Get the project

```bash
git clone https://github.com/eunemi/VERITAS.git
cd VERITAS
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

### 2 / Configure the desks

Edit the matching entries in `backend/.env`:

```dotenv
ENVIRONMENT=local
DEBUG=false
VERIFICATION_STORE=memory
VECTOR_STORE_PROVIDER=memory
CORS_ORIGINS=http://localhost:3000
PUBLIC_API_URL=http://localhost:8000

LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
OPENAI_API_KEY=your-provider-key
CLAIM_EXTRACTION_LLM=true
VISION_MODEL=gpt-4o-mini

SEARCH_PROVIDERS=tavily
TAVILY_API_KEY=your-search-key
JWT_SECRET_KEY=your-generated-secret
```

Generate the value for `JWT_SECRET_KEY` with `openssl rand -hex 32`. Replace the key placeholders with your own credentials. In-memory accounts and records reset when the process restarts.

`VERIFICATION_STORE=memory` is the fastest local path and does not need PostgreSQL.
For a durable local run, use `VERIFICATION_STORE=database`, start PostgreSQL, and set
`DATABASE_URL` to the database you want the API to use. The verification store also
controls the account store: memory mode loses both accounts and records on restart.

The frontend's `frontend/.env.local` should contain:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

`NEXT_PUBLIC_API_URL` is embedded into the browser bundle at build time. Restart
`npm run dev` after changing it locally, and redeploy/rebuild the frontend after
changing it in Vercel.

### 3 / Start the API

From the repository root:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m spacy download en_core_web_sm
python -m nltk.downloader punkt_tab stopwords
uvicorn app.main:app --reload --port 8000
```

### 4 / Start the workspace

In a **second terminal**, from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

| Open | Address |
| :--- | :--- |
| **Workspace** | http://localhost:3000 |
| **Interactive API docs** | http://localhost:8000/docs |
| **API health** | http://localhost:8000/health |
| **Public API health** | http://localhost:8000/api/health |

To run the already-built frontend instead of the development server:

```bash
cd frontend
npm run build
npm run start
```

The workspace is then served on the port printed by Next.js. The API still needs to be
running separately.

<details>
<summary><strong>Use PostgreSQL and Docker Compose instead</strong></summary>

Compose runs **the API and PostgreSQL**. The frontend still runs in its own terminal.

1. In `backend/.env`, set `VERIFICATION_STORE=database` and `VECTOR_STORE_PROVIDER=chroma`. Keep the provider credentials and JWT secret configured above.
2. From `backend/`, with the Python environment active, start the database and apply migrations:

```bash
docker compose up -d postgres
DATABASE_URL=postgresql+asyncpg://veritas:veritas@localhost:5432/veritas alembic upgrade head
docker compose up --build api
```

Wait for PostgreSQL to be ready before running Alembic. The Compose configuration overrides the API's database hostname to `postgres` inside the container. Local named volumes keep database and `/app/var` data across rebuilds. The Docker build includes the spaCy model and NLTK data.

The compose file is a local development stack. It runs one reloading API process and
PostgreSQL; the frontend still runs from its own `frontend/` terminal. For a quick
frontend-only pass, memory mode is enough, but URL verification still needs the backend
and its configured provider credentials.

</details>

<details>
<summary><strong>Provider options</strong> — text, search, image matching, and fallbacks</summary>

| Capability | Configuration |
| :--- | :--- |
| **OpenAI-compatible text** | `LLM_PROVIDER=openai`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY` |
| **Groq** | Use `OPENAI_BASE_URL=https://api.groq.com/openai/v1`, a supported `OPENAI_MODEL`, and `GROQ_API_KEY` |
| **Ollama text** | `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |
| **Visual description** | `VISION_MODEL`; optionally separate `VISION_BASE_URL` and `VISION_API_KEY`. The model must support image inputs and JSON output. |
| **Web research** | `SEARCH_PROVIDERS=tavily,brave,serper` and the keys for the providers you enable |
| **Published fact checks** | `GOOGLE_FACT_CHECK_API_KEY` |
| **Reverse-image context** | `GOOGLE_VISION_API_KEY`, with Cloud Vision Web Detection enabled |

Search providers without credentials report their unavailability. Model failures can fall back to installed spaCy extraction, but semantic verdicts remain insufficient without a working model. Local Tesseract OCR requires the Tesseract system binary; hosted vision does not require Tesseract or YOLO.

See [live verification configuration](backend/LIVE_VERIFICATION.md) and the [complete environment template](backend/.env.example).

</details>

<br />

## Ship it

### Vercel × Render × Neon

| Service | Responsibility | Setup |
| :--- | :--- | :--- |
| **Vercel** | Frontend | Root directory: `frontend`. Build: `npm run build`. |
| **Render** | FastAPI backend | Docker Web Service. Root directory: `backend`. Dockerfile: `./Dockerfile`. Health check: `/health`. |
| **Neon** | Persistent records and accounts | PostgreSQL connection string using the `postgresql+asyncpg://` driver. |

#### Vercel · public build-time configuration

```dotenv
NEXT_PUBLIC_API_URL=https://veritas-ojg4.onrender.com/api/v1
```

Set this in the **Production** environment and rebuild after changing it. For a fork, replace the hostname with your own API service.

#### Render · server-side configuration

| Variable | Value |
| :--- | :--- |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `CORS_ORIGINS` | `https://veritasreal.vercel.app` — your exact frontend origin, without a trailing slash |
| `PUBLIC_API_URL` | `https://veritas-ojg4.onrender.com` — backend origin, without `/api/v1` |
| `JWT_SECRET_KEY` | A generated secret, stored in Render |
| `DATABASE_URL` | Your Neon pooled URL, using `postgresql+asyncpg://` |
| `VERIFICATION_STORE` | `database` |
| `UPLOAD_DIRECTORY` | A persistent/shared path for uploaded images, such as `/app/var/uploads` |
| **Provider configuration** | The model, search, and optional vision settings from the provider table above |

Keep one entry per variable. Multiple permitted frontend origins go in one comma-separated `CORS_ORIGINS` value. Vercel preview URLs and additional custom domains need their own explicit entries.

Run `alembic upgrade head` once against the target database using its direct connection URL, from `backend/` with dependencies installed. The runtime Docker image contains the app, not the Alembic migration directory. Configure persistent storage for uploads and the Chroma index if those files must survive deployments; multiple API instances need shared upload storage. The shipped container runs one Uvicorn process, and the verification runner is in-process rather than a separate queue worker.

#### Verify the connection

```bash
curl -fsS https://veritas-ojg4.onrender.com/api/v1/health

curl -i -X OPTIONS https://veritas-ojg4.onrender.com/api/v1/verify \
  -H 'Origin: https://veritasreal.vercel.app' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
```

Expect health to report `status: "ok"` and `environment: "production"`. The preflight should return `200` with `access-control-allow-origin` matching the frontend origin. Health is a liveness check; it does not validate the database or provider credentials.

<details>
<summary><strong>Deployment troubleshooting</strong></summary>

| Symptom | Check |
| :--- | :--- |
| `service_unreachable` | Test `/health`, then preflight with the **exact address-bar origin**. A rejected browser request can mean networking, timeout, or CORS; it does not prove the API is down. |
| `Disallowed CORS origin` | Update Render's `CORS_ORIGINS`, save, and redeploy the API. Domain aliases and preview URLs are distinct origins. |
| Old API URL after editing Vercel settings | Rebuild the frontend. `NEXT_PUBLIC_API_URL` is embedded at build time. |
| `GET /` returns `404` on Render | Expected: the backend has no homepage. Configure the health check to use `/health`. |
| Health works, verification fails | Check database connectivity, migrations, and the API logs using the returned request ID. |
| `No verification with id ...` | Use `VERIFICATION_STORE=database` for deployed environments. Memory mode loses records when the API restarts; an owned record also returns `404` when read without its owner's token. |
| URL check says the page could not be read | Confirm the page is public, returns readable HTML/text, does not require browser-only JavaScript, and does not redirect to a private host. The fetcher allows at most three redirects. |
| Record completes with no sources | Inspect the provider ledger. Add working search credentials; a healthy server alone cannot retrieve evidence. |
| Images upload but previews fail | Check `PUBLIC_API_URL`, persistent upload storage, and the generated media URL. |
| Scanned PDF produces no text | Run OCR first; PDF intake reads the embedded text layer. |

</details>

<br />

## The API

**Base path:** `/api/v1` · **Format:** JSON, except multipart file uploads · **Identity:** optional bearer auth for submission; required for account history.

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `GET` | `/health` | Versioned liveness check; also available at root `/health` and public `/api/health` |
| `POST` | `/verify` | Accept an artifact and return a record ID (`202`) |
| `GET` | `/verification/{id}` | Read progress, reports, final status, or failure |
| `GET` | `/verifications?limit=20` | Read the signed-in account's history |
| `POST` | `/extract-claim` | Extract checkable claims from text |
| `POST` | `/research` | Gather web sources and published fact checks |
| `POST` | `/files/extract-text` | Extract text from TXT, Markdown, DOCX, or PDF |
| `POST` | `/files/upload-media` | Store a supported image and return its API URL |
| `GET` | `/files/media/{filename}` | Retrieve an uploaded image by its generated filename |
| `POST` | `/auth/register` | Create an account |
| `POST` | `/auth/login` | Issue an access token |
| `GET` | `/auth/me` | Read the authenticated account |

### Open a record

```bash
curl -sS http://localhost:8000/api/v1/verify \
  -H 'Content-Type: application/json' \
  -d '{
    "artifact": {
      "kind": "claim",
      "content": "The Eiffel Tower was completed in 1889."
    },
    "desks": ["fact-check"]
  }'
```

Illustrative acceptance response — this is a job receipt, not a verdict:

```json
{
  "id": "8f14e45f-ceea-467a-9c4d-1b1e1a3f7c02",
  "status": "pending",
  "desks": ["fact-check", "decision"],
  "created_at": "2026-10-11T09:00:00Z"
}
```

For the URL desk, submit a URL artifact instead of text or claim content:

```bash
curl -sS http://localhost:8000/api/v1/verify \
  -H 'Content-Type: application/json' \
  -d '{"artifact":{"kind":"url","url":"https://example.com/article"}}'
```

The URL submission opens the text and fact-check desks by default, followed by the
decision desk. The backend keeps the submitted address on the record while the desks
work on the readable page content fetched from it.

Read `/api/v1/verification/{id}` using the returned ID until `terminal` is `true`. Nonterminal responses include a `Retry-After` hint. A completed record carries `reports`; a failed examination carries `failure` and preserves reports already filed. Request-level errors use an `error` envelope with a stable `code`, `message`, and request ID.

Anonymous records are readable by ID. Sending `Authorization: Bearer <token>` attaches ownership; subsequent reads need that account's token. Local interactive docs are at `/docs`; `/docs`, `/redoc`, and `/openapi.json` are disabled in production.

<br />

## Project map

```text
VERITAS/
├── frontend/
│   ├── src/app/                 Pages, examination tools, archive, error states
│   ├── src/components/          Editorial UI, submission benches, report instruments
│   ├── src/context/             Account and session state
│   ├── src/lib/api/             Typed fetch client, auth, submission, polling
│   └── src/lib/services/        API records → presentation models
├── backend/
│   ├── app/api/v1/              Versioned HTTP routes
│   ├── app/core/                Settings, middleware, errors, structured logging
│   ├── app/domain/              Artifact, claim, evidence, and verdict vocabulary
│   ├── app/desks/               Text, image, fact-check, and decision desks
│   ├── app/graph/               LangGraph nodes, state, workflow, and judging
│   ├── app/nlp/                 Claim extraction, segmentation, keyword ranking
│   ├── app/search/              Tavily, Brave, Serper, and concurrent fan-out
│   ├── app/factcheck/           Published fact-check lookup
│   ├── app/research/            Evidence selection, deduplication, source assessment
│   ├── app/llm/                 Model clients and hashing embeddings
│   ├── app/vision/              Visual context, OCR, and image preparation
│   ├── app/repositories/        SQL and in-memory storage implementations
│   ├── app/security/            Password hashing and token verification
│   ├── app/services/            Verification and research orchestration
│   ├── app/vectorstore/         Evidence indexing and retrieval
│   ├── alembic/                 Database migrations
│   └── tests/                   API, workflow, provider, and persistence tests
├── docs/assets/                 Original README illustrations
├── scripts/                     Maintenance utilities
└── claude-skills/               Vendored agent workflow resources
```

## Quality & engineering

### Frontend

Run from `frontend/`:

```bash
npm ci
npm run lint
npm run typecheck
npm run build
```

### Backend

Run from `backend/` with the Python environment active:

```bash
python -m pip install -r requirements-dev.txt
ruff check app
mypy app
pytest
```

Provider fixtures cover citation grounding, source deduplication, timeouts, outages, image validation, and API contracts without calling paid services. Parser-backed tests need the installed NLP models; live provider checks need real credentials. A dependency-light search check is also available with `python offline_search_tests.py`.

**Implementation highlights:**

- Argon2id password hashing and constrained JWT validation.
- Account-scoped history and ownership checks on individual records.
- Exact-origin CORS, request IDs, structured logs, and consistent API errors.
- Public-host and redirect checks for server-side media and page fetching.
- File-type validation, byte limits, and generated upload filenames.
- Startup validation for production secrets and incompatible settings.

## Contributing

Useful contributions include provider integrations, citation-quality improvements, multilingual extraction, accessibility refinements, and reproducible bug reports.

1. Open an [issue](https://github.com/eunemi/VERITAS/issues) describing the problem or proposed change.
2. Keep the change focused and follow the surrounding frontend or backend conventions.
3. Add meaningful regression coverage for behavior changes and run the relevant checks above.
4. Open a pull request with the problem, solution, and verification steps.

For a provider integration, keep HTTP behavior in the provider adapter and evidence assessment in the research or graph layer. For a UI change, preserve the typed API contract and the distinction between evidence, findings, and service failures.

### Further reading

- [Live verification guide](backend/LIVE_VERIFICATION.md) — current capabilities, provider setup, and limitations.
- [Backend reference](backend/README.md) — detailed contracts and architectural notes, including historical design context.
- [Configuration reference](backend/app/core/config.py) — the source of truth for environment settings.
- [API schemas](backend/app/schemas/verification.py) — request and response models.
- [Graph implementation](backend/app/graph/workflow.py) — nodes, branching, and execution.

<br />

<div align="center">

<img src="docs/assets/veritas-signature.svg" alt="The last word belongs to the evidence. Veritas — question the story." width="100%" />

<br />

Built by [Arya Yadav](https://github.com/eunemi) · [Open Veritas](https://veritasreal.vercel.app) · [Report an issue](https://github.com/eunemi/VERITAS/issues) · [Back to top ↑](#top)

</div>
