# Live text, document, image and URL verification

The homepage cards open `/intel/text`, `/intel/image`, `/intel/docx`, `/intel/pdf` and
`/intel/url`. Each submits a verification to FastAPI and polls the real job status; the
pages do not render demo verdicts.

## Configuration

Set these in `backend/.env` locally, or in your backend host's environment:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your-provider-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
CLAIM_EXTRACTION_LLM=true
VISION_MODEL=gpt-4o-mini
SEARCH_PROVIDERS=tavily
TAVILY_API_KEY=your-search-key
GOOGLE_VISION_API_KEY=your-google-cloud-vision-key
PUBLIC_API_URL=http://localhost:8000
```

Model IDs must exist on the selected provider. `OPENAI_BASE_URL` also supports
OpenAI-compatible services. A vision model must accept image inputs and JSON output;
a text-only model cannot inspect a photograph. Optional `VISION_API_KEY` and
`VISION_BASE_URL` let vision use a different provider. When unset they reuse the
OpenAI-compatible configuration. No keys belong in the frontend.

`GOOGLE_VISION_API_KEY` is for Google Cloud Vision **Web Detection**, not the Google
Fact Check API. Enable Cloud Vision and billing on its project. Missing/rejected
keys are reported as unavailable lookup, never as “no matching image exists”.

Set `frontend/.env.local` to `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`.
For deployment use the public backend URL, set `PUBLIC_API_URL` to that backend
origin and allow the frontend origin in `CORS_ORIGINS`. Restart the backend and
rebuild the frontend after environment changes.

Use `VERIFICATION_STORE=memory` for a single-process local run, or the existing
PostgreSQL setup for durable records. Uploaded images live in `UPLOAD_DIRECTORY`;
deploy this on persistent shared storage when running multiple instances. The API
reads its own uploads directly, so verification does not depend on making an HTTP
request back through the deployment's public address.

## What is checked

- **Text:** extracts multilingual claims (including Hindi/Hinglish and short
  headlines), retrieves live search evidence, and assesses meaning rather than
  treating shared keywords/numbers as corroboration. The model selects numbered
  evidence passages; the server supplies the literal excerpts and source URLs.
- **Verdicts:** supported, contradicted, contested or insufficient evidence.
  A decisive result needs two independent cited sources. Repeated domains and
  syndicated stories do not count twice. Confidence is a model estimate, not a
  calibrated probability. A model outage cannot produce a decisive verdict.
- **Images:** upload/drop a file or paste a public image URL; add the claimed event,
  location or date if known. The report includes visible observations, recovered
  text, file metadata, checks on the text/caption, related web search results and
  Cloud Vision matching pages when configured.
- **Documents:** DOCX and text-based PDF uploads are extracted through the multipart
  file endpoint and then sent through the same text claim/evidence pipeline. Scanned
  PDFs without an embedded text layer need OCR before they can be checked.
- **URLs:** the backend fetches the public page, strips non-readable markup, extracts
  its claims and checks them against independent sources. Public redirects are
  followed for up to three hops, with the same public-host check applied at each hop;
  redirects to private hosts are refused.
- **Scope:** related search pages are labelled separately from actual image
  matches. Matching pages can show reuse but do not by themselves establish the
  original capture date, publisher, pixel authenticity or AI generation. The claim
  verdict does not certify the photograph. Missing evidence remains unverified.

Text-only deployments without a model can retain spaCy extraction by setting
`CLAIM_EXTRACTION_LLM=false` and installing its model. Semantic verdicts still need
the configured language model. OCR falls back to Tesseract when visual analysis is
unavailable. The online vision path does not require Tesseract or YOLO.

If the configured language-model key expires or the provider is unavailable, text
claim extraction automatically falls back to the installed spaCy extractor. The
verification still completes and publishes the live sources it found; the semantic
verdict is reported as insufficient until a working language-model key is configured.

## Checks

```bash
pytest tests/test_live_verification.py tests/test_desk_image.py \
  tests/test_desk_factcheck.py tests/test_graph_workflow.py \
  tests/test_verification_api.py tests/test_verification_service.py \
  tests/test_pipeline_contracts.py tests/test_llm_clients.py tests/test_media_fetch.py
```

Provider fixtures test grounding, nonexistent citations, same-publisher/reprint
deduplication, outages, reverse lookup parsing, uploaded-image validation and
schema/persistence round trips. Live provider checks require the keys above.
