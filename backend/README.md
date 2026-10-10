# Veritas backend

**Live Text/Image desks:** see [LIVE_VERIFICATION.md](LIVE_VERIFICATION.md) for
current provider setup, capabilities, limits and checks. The historical API design
notes below predate the implemented desks.

FastAPI service behind the Veritas frontend. The HTTP surface is complete —
four endpoints, their schemas, validation, error handling, the domain model and the
service layer that orchestrates a verification. **Claim extraction is implemented**:
`POST /api/v1/extract-claim` reads real prose with spaCy, NLTK and scikit-learn.
**Web research is implemented**: `POST /api/v1/research` fans a claim out across
Tavily, Brave and Serper at once, deduplicates what comes back at two levels, and
quotes evidence verbatim or not at all.
**Fact-check lookup is implemented**: the same endpoint searches Google's Fact Check
Tools index for reviews already published on each claim, and returns each one's
verdict, publisher, URL and date as evidence beside the web sources — never folded
into them, never summed into a rating.
**Text and image verification are implemented:** live evidence is assessed by a
semantic reader, with validated citations and uncertainty when evidence is missing.
Images include visual description, OCR, caption checking and configured web matching.

## Requirements

- Python 3.12 or newer
- PostgreSQL 16 (or Docker, which brings its own)
- A spaCy English model and NLTK's punkt data — two downloads `pip` does not
  perform, described under [Running it](#on-the-host)

## Running it

### With Docker

```bash
docker compose up --build
```

The API is on <http://localhost:8000>, Postgres on 5432. Source is bind-mounted
and uvicorn runs with `--reload`, so edits take effect without a rebuild. The image
fetches both NLP data sets during the build, so extraction works out of the box.

### On the host

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt
```

Two data sets are not Python packages and so are not in `requirements.txt`:

```bash
python -m spacy download en_core_web_sm
```

```bash
python -m nltk.downloader punkt_tab stopwords
```

The two are not equally required, and the difference is deliberate. Without the spaCy
model `/api/v1/extract-claim` answers `500` with the exact command above in
`error.details.install` — there is no sensible degraded parse. Without the NLTK data
the extractor logs a warning once and falls back to spaCy's own sentence boundaries,
because losing punkt costs some segmentation accuracy and nothing else.

```bash
cp .env.example .env
```

Start Postgres (`docker compose up postgres`) or point `DATABASE_URL` at your own,
then:

```bash
uvicorn app.main:app --reload
```

Nothing connects to the database at startup, so the service comes up and answers
`/health` whether or not Postgres is running.

## Checking it works

```bash
curl -s localhost:8000/health | python -m json.tool
```

```json
{
  "status": "ok",
  "service": "Veritas Verification API",
  "version": "0.1.0",
  "environment": "local",
  "timestamp": "2026-08-23T11:04:07.512901+00:00"
}
```

Interactive docs are at `/docs` and `/redoc` in every environment except
production, where they and `/openapi.json` are closed.

## The API

Eight endpoints under `/api/v1`, plus `/health`.

Authentication is a bearer token and is optional almost everywhere. `POST /verify` and
`GET /verification/{id}` work with or without one; `GET /verifications` and
`GET /auth/me` require one. What signing in buys is ownership — see
[Accounts and ownership](#accounts-and-ownership).

### `POST /api/v1/verify`

Submits an artifact and returns `202` immediately with an id to poll. The
examination runs after the response is sent.

```bash
curl -si localhost:8000/api/v1/verify -H 'content-type: application/json' -d '{
  "artifact": {"kind": "text", "content": "The bridge opened in March 2026."}
}'
```

```json
{
  "id": "8f14e45f-ceea-467a-9c4d-1b1e1a3f7c02",
  "status": "pending",
  "desks": ["text", "fact-check", "decision"],
  "created_at": "2026-08-23T11:04:07.512901+00:00"
}
```

The response also carries
`Location: /api/v1/verification/8f14e45f-ceea-467a-9c4d-1b1e1a3f7c02`.

Send `Authorization: Bearer <token>` to attach the record to that account, which makes
it private to it and puts it in `GET /verifications`. Send nothing and the submission
is anonymous, in which case the id in the response is the only handle on the record
that exists. A token that is *present but rejected* is a `401` rather than a silent
fallback to anonymous — otherwise an expired session would go on submitting records
its owner could never list.

`artifact` is a union discriminated on `kind`. `text` and `claim` carry `content`;
`url` carries `url`; `image` carries `url` and an optional
`filename`. Anything else in the object is rejected rather than ignored.

URL submissions are fetched by the text and fact-check desks with the same public-host,
redirect and byte-limit protections used for media. HTML is reduced to readable page
copy before claims are extracted, so a URL result checks the claims actually published
on that page rather than the address string itself.

`desks` is optional. Omitted, the roster follows the artifact's kind — copy opens
the text and fact-check desks, for instance. Supplied, it is checked against that table and
normalised, so `["fact-check", "text"]` and `["text", "fact-check"]` produce the same
record. The `decision` desk cannot be named: it reads the other desks' records and is
appended to every verification.

### `GET /api/v1/verification/{id}`

Returns the record as it stands, in the same shape at every stage — a pending record
has an empty `reports` list, a failed one keeps whatever was filed before the failure
and adds `failure`. While the record is not terminal the response carries
`Retry-After: 1`; when it is, the header is absent and `terminal` is `true`. A client
can poll on either signal and needs no table of which statuses are final.

A record with an owner is readable only by that owner. Everyone else — including an
anonymous caller and including a signed-in caller who is not the owner — gets `404`,
not `403`, with the same body a genuinely unknown id produces. A `403` would confirm
the id exists, which turns this endpoint into an oracle for anyone walking the id
space. A record with no owner stays readable by id, which is what lets the client that
submitted it poll without signing in.

There is no top-level `verdict`. The `decision` desk's report carries the signed
determination, so there is one source for it rather than two.

A verification that stopped reports `failure`, never `error` — `error` is the
top-level key of every non-2xx body, and a `200` using it would leave a client unable
to tell a failed verification from a failed request by shape.

### `GET /api/v1/verifications`

The caller's own verifications, newest first. Requires a token.

```bash
curl -s localhost:8000/api/v1/verifications?limit=20 \
  -H "authorization: Bearer $TOKEN"
```

```json
{
  "items": [
    {
      "id": "8f14e45f-ceea-467a-9c4d-1b1e1a3f7c02",
      "status": "completed",
      "terminal": true,
      "artifact": {"kind": "text", "content": "The bridge opened in March 2026."},
      "verdict": {"determination": "CONTESTED", "confidence": "75%"},
      "created_at": "2026-08-23T11:04:07.512901+00:00"
    }
  ],
  "count": 1
}
```

Rows are summaries: status, artifact, the signed verdict once there is one, and the
timestamps. The desk reports are not included, because each carries its annotations,
signals and exhibits and twenty of those is a large response to render a list of
twenty lines — a row's `id` fetches the full record.

`limit` is `1`–`100`, default `20`. There is no `user` parameter and no path segment
naming an account: the owner comes from the token, so there is no version of this
request that asks for somebody else's records. `count` counts the rows returned, not
the rows that exist; paging will add fields to this object, which is why it is an
object rather than a bare array.

Authentication is required rather than optional here, because there is no such thing
as an anonymous caller's history — an anonymous submission has no owner to match on.

### Accounts and ownership

Three endpoints, and `POST /api/v1/auth/login` is the only one that issues a token.

```bash
curl -s localhost:8000/api/v1/auth/register -H 'content-type: application/json' \
  -d '{"email": "reader@example.com", "password": "correct horse battery staple"}'
```

`POST /api/v1/auth/register` → `201` with the account and **no token**. Registration
creates and login authenticates, so exactly one endpoint mints tokens; the client pays
one extra round trip for that. Addresses are stored trimmed and lower-cased, so case
alone cannot make a second account. Passwords are 8–128 characters and length is the
only rule — no composition requirements, per NIST SP 800-63B. The upper bound is not
cosmetic: Argon2 hashes its whole input, so an unbounded field lets one request occupy
a worker for as long as it likes.

`POST /api/v1/auth/login` → `200` with `access_token`, `token_type`, `expires_in` and
the account, so a client need not follow with `/auth/me`.

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {"id": "…", "email": "reader@example.com", "display_name": "reader"}
}
```

Every rejection is the same `401` with the same message — `Email or password is
incorrect.` — whether the address is unknown, the password is wrong, or the account has
been closed. The unknown-address path hashes against a throwaway decoy first, so it
costs what a known address costs; three distinct messages, or one fast path and one
slow one, are both answers to "does this address have an account here". A malformed
address is that same `401` rather than a `422`, for the same reason.

`GET /api/v1/auth/me` → the account the token identifies. The token is verified **and
the account re-read** on every authenticated request, so deactivating an account takes
effect immediately rather than whenever its outstanding tokens happen to expire.

Passwords are hashed with Argon2id (`argon2-cffi`, at the library's own defaults —
OWASP's first choice, and raised by the library when the guidance moves). Tokens are
HS256 JWTs signed with `JWT_SECRET_KEY`, which has no default and no
generated-per-process fallback: a checked-in default would let any copy of this
repository forge a token for any deployment of it, and a generated one would
invalidate every session on restart. `Settings` refuses to build without a key outside
`ENVIRONMENT=local`.

Verification is deliberately narrow. The accepted algorithm is the configured one and
never the token's own `alg` header, which is what closes the `alg: none` and
HMAC-signed-with-the-RSA-public-key forgeries. `sub`, `type`, `exp`, `iat` and `jti`
are *required* claims rather than merely read ones — a token with no `exp` is a token
that never expires. And `type` is checked against what the caller expected, because
both kinds are signed with one key, so without it a long-lived refresh token would
authenticate a request as well as an access token does.

**Two things this does not have yet, and the order to add them in.** There is no rate
limit, and `POST /auth/login` is the first endpoint that needs one, with
`POST /auth/register` second — registration is the one place the API confirms an
account exists, because the alternative is either locking out the first holder of an
address or silently signing the caller in as them. There is also no
`POST /auth/refresh`: `create_refresh_token` and `REFRESH_TOKEN_EXPIRE_DAYS` exist and
are unused, so the access-token lifetime is the session length today. Adding the
endpoint means deciding on rotation and storage first, which is a larger change than
signing a second token.

### `POST /api/v1/extract-claim`

Returns the separately checkable claims in a piece of prose, plus the named entities
and the ranked keywords.

```bash
curl -s localhost:8000/api/v1/extract-claim \
  -H 'content-type: application/json' \
  -d '{"text":"The Queensferry Crossing opened in 2017 and cost £1.35bn. It is magnificent."}'
```

```json
{
  "claims": [
    {
      "ref": 1,
      "text": "The Queensferry Crossing opened in 2017.",
      "quote": "The Queensferry Crossing opened in 2017",
      "start": 0,
      "end": 39,
      "checkable": true,
      "reason": "",
      "entities": [
        {"text": "Queensferry Crossing", "label": "FAC", "start": 4, "end": 24},
        {"text": "2017", "label": "DATE", "start": 35, "end": 39}
      ],
      "keywords": [
        {"term": "queensferry crossing", "score": 1.0},
        {"term": "open 2017", "score": 1.0}
      ]
    },
    {
      "ref": 2,
      "text": "The Queensferry Crossing cost £1.35bn.",
      "quote": "cost £1.35bn",
      "start": 44,
      "end": 56,
      "checkable": true,
      "reason": "",
      "entities": [
        {"text": "£1.35bn", "label": "MONEY", "start": 49, "end": 56}
      ],
      "keywords": [
        {"term": "cost 1.35bn", "score": 1.0},
        {"term": "queensferry crossing", "score": 1.0}
      ]
    },
    {
      "ref": 3,
      "text": "It is magnificent.",
      "quote": "It is magnificent",
      "start": 58,
      "end": 75,
      "checkable": false,
      "reason": "opinion",
      "entities": [],
      "keywords": [{"term": "magnificent", "score": 1.0}]
    }
  ],
  "count": 3,
  "checkable_count": 2,
  "sentences": 2,
  "entities": [
    {"text": "Queensferry Crossing", "label": "FAC", "start": 4, "end": 24},
    {"text": "2017", "label": "DATE", "start": 35, "end": 39},
    {"text": "£1.35bn", "label": "MONEY", "start": 49, "end": 56}
  ],
  "keywords": [
    {"term": "magnificent", "score": 1.0},
    {"term": "1.35bn", "score": 0.302},
    {"term": "2017", "score": 0.302}
  ]
}
```

Four things in that response are the whole design:

**One sentence can be several claims.** "opened in 2017 and cost £1.35bn" asserts two
things and a desk can only rule on one at a time, so the second clause is lifted out
with its subject carried in — `text` is rewritten to stand alone, because "and cost
£1.35bn" is not something evidence bears on. `count` and `checkable_count` are both
reported so a UI cannot say "3 claims found" over a list of two.

**`quote` is verbatim, always.** It is a slice of the submitted string, so
`text[start:end] == quote` holds for every claim and a client can highlight in place
without searching for the string and finding the wrong occurrence of it. A rewrite is
never quoted: claim 2's `text` supplies the subject that "and cost £1.35bn" lacked,
while its `quote` stays the twelve characters the source actually spends on that
assertion. It goes the other way too. Cut a parenthetical out of the middle of a
sentence and the main clause's quote is *wider* than its rewrite — "The bridge, which
cost £4bn, opened in March." gives a `text` of "The bridge opened in March." against a
`quote` that still contains the clause that was removed, because the quote's job is to
be what was written.

**Unfit sentences are marked, not dropped.** Claim 3 comes back with
`checkable: false` and `reason: "opinion"`, because "the extractor skipped your last
sentence" and "the extractor thinks your last sentence is opinion" are different
messages and only one is useful. The reasons are the stable strings in
[`Unfit`](app/domain/claims.py): `fragment`, `too_short`, `question`, `imperative`,
`opinion`, `prediction`, `hypothetical`, `attribution_only`, `no_content`.

**Checkable is not true.** "The Moon is made of cheese" passes every screening rule.
The screen decides whether evidence *bears* on a sentence; the verdict is the
fact-check desk's job, and conflating the two would let a heuristic veto claims it
merely found implausible.

Entity labels and boundaries are the model's rather than this endpoint's — it is
`en_core_web_sm` that decides "Queensferry Crossing" is a `FAC` and where it begins.
What the endpoint guarantees is the arithmetic: `text[start:end]` is the string
reported, for an entity exactly as for a claim.

The keyword lists above are abridged and their scores rounded. Two things about them
are worth knowing before reading a real one.

A term is a lemma, not a span. "opened" ranks as `open`, `£` is dropped as a symbol
before anything is counted, and scikit-learn removes stop words *before* it forms
bigrams — so "the prime minister of Canada" yields the term "minister canada", which
appears nowhere in the source. That is why `Keyword` carries no offsets, and it is also
why the lemmas go to the vectoriser whitespace-split rather than through its default
`\b\w\w+\b`: that pattern would re-tokenise them and turn `1.35bn` into `35bn`,
`covid-19` into two terms, and `3.5` into nothing at all.

A score is a TF-IDF weight taken against the other sentences of *this* submission, so
it ranks terms within one response and means nothing across two. In a passage as short
as the one above there is nothing to rank: every content term occurs once, in one
sentence, so every weight is equal, all of them normalise to 1.0, and the alphabetical
tie-break settles the order — deterministic, which is what matters when the same text is
submitted twice. The document-level list is a sum over sentences and so leans towards
terms from short ones, which is why a three-word sentence puts "magnificent" at the top
of it here.

Oversized input gets a `413` before the model is loaded; a missing spaCy model gets a
`500` naming the install command in `error.details.install`.

### `POST /api/v1/research`

Searches every configured provider for each claim and reports what came back. Takes
either `text` — extract the claims first, then research the checkable ones — or
`claims`, which researches strings exactly as given and needs no spaCy model.

```bash
curl -s localhost:8000/api/v1/research \
  -H 'content-type: application/json' \
  -d '{"claims":["The Bank of England held its benchmark rate at 4.75% in March 2026."]}'
```

```json
{
  "claims": [
    {
      "claim": "The Bank of England held its benchmark rate at 4.75% in March 2026.",
      "queries": [
        "The Bank of England held its benchmark rate at 4.75% in March 2026."
      ],
      "sources": [
        {
          "ref": 1,
          "url": "https://reuters.com/markets/boe-holds-2026-03-12",
          "urls": [
            "https://reuters.com/markets/boe-holds-2026-03-12",
            "https://www.reuters.com/markets/boe-holds-2026-03-12/?utm_source=twitter"
          ],
          "title": "Bank of England holds rate at 4.75% as services inflation persists",
          "domain": "reuters.com",
          "host": "reuters.com",
          "evidence": [
            {
              "quote": "held its benchmark rate at 4.75%",
              "provider": "tavily",
              "start": 18,
              "end": 50,
              "score": 0.83,
              "matched_entities": ["Bank of England"],
              "matched_terms": ["benchmark", "rate"],
              "matched_numbers": ["4.75%"]
            }
          ],
          "retrievals": [
            {
              "provider": "tavily",
              "query": "The Bank of England held its benchmark rate at 4.75% in March 2026.",
              "rank": 1,
              "url": "https://www.reuters.com/markets/boe-holds-2026-03-12/?utm_source=twitter",
              "title": "Bank of England holds rate at 4.75% as services inflation persists",
              "snippet": "The Bank of England held its benchmark rate at 4.75% on Thursday …",
              "score": 0.94,
              "published_at": "2026-03-12T18:00:00Z",
              "date_basis": "provider",
              "date_text": "2026-03-12T18:00:00Z"
            },
            {
              "provider": "brave",
              "query": "The Bank of England held its benchmark rate at 4.75% in March 2026.",
              "rank": 2,
              "url": "https://reuters.com/markets/boe-holds-2026-03-12",
              "title": "BoE holds at 4.75%",
              "snippet": "The Bank of England held its benchmark rate at 4.75% …",
              "score": null,
              "published_at": "2026-03-12T00:00:00Z",
              "date_basis": "provider_relative",
              "date_text": "2 days ago"
            }
          ],
          "published_at": "2026-03-12T18:00:00Z",
          "date_basis": "provider",
          "date_text": "2026-03-12T18:00:00Z",
          "cluster": 1,
          "providers": ["tavily", "brave"]
        }
      ],
      "fact_checks": [
        {
          "source": "google",
          "claim": {
            "text": "The Bank of England held its benchmark rate at 4.75% in March 2026.",
            "reviews": [
              {
                "publisher": "Full Fact",
                "site": "fullfact.org",
                "url": "https://fullfact.org/economy/boe-rate-march-2026/",
                "rating": "Mostly false",
                "title": "The Bank cut in March, it did not hold",
                "language": "en",
                "reviewed_at": "2026-03-13T11:00:00Z",
                "date_text": "2026-03-13T11:00:00Z",
                "stance": "mostly_false",
                "stance_from": "mostly false"
              }
            ],
            "claimant": "A Member of Parliament",
            "claimed_at": "2026-03-12T00:00:00Z",
            "date_text": "2026-03-12"
          },
          "match": 0.9231,
          "matched_entities": ["Bank of England", "March 2026"],
          "matched_terms": ["benchmark rate"],
          "matched_numbers": ["4.75%", "2026"],
          "publishers": ["Full Fact"],
          "agreement": "mostly_false"
        }
      ],
      "domains": ["reuters.com", "apnews.com", "ft.com"],
      "stories": 2
    }
  ],
  "skipped": [],
  "providers": [
    {"provider": "brave", "status": "searched", "queries": ["…"], "results": 8,
     "code": "", "detail": ""},
    {"provider": "serper", "status": "skipped", "queries": [], "results": 0,
     "code": "configuration_error", "detail": "SERPER_API_KEY is not set."},
    {"provider": "tavily", "status": "searched", "queries": ["…"], "results": 10,
     "code": "", "detail": ""}
  ],
  "fact_checkers": [
    {"provider": "google", "status": "searched", "queries": ["…"], "results": 1,
     "code": "", "detail": ""}
  ],
  "retrieved_at": "2026-03-14T09:30:00Z",
  "searched": true,
  "fact_checked": true
}
```

Abridged — `sources` above shows one of several, and the `queries` on each provider
outcome are elided. Seven things in that response are the design.

**`searched` is the field to read first.** It is `false` when no provider actually
answered, and when it is `false` every empty `sources` list in the body means "not
looked for", not "not found". An expired API key produces exactly the same empty list
as a claim nobody has ever written about, and this flag is the only thing separating
them. The endpoint is a `200` even with every provider dead, for the same reason: a
`502` for "Tavily timed out" would discard the results Brave returned in the same
request, and a `500` for "no keys are configured" would be indistinguishable, to a
client, from "the web contains nothing about this". Provider trouble is data, on
`providers[]`; the status code is reserved for the request being wrong.

`fact_checked` is the same flag for the fact-check lookup, and it is a second flag rather
than a wider reading of the first because the two fail separately: the fact-check key is
free and independent of the search keys, so complete web research with no fact-check
coverage is the common deployment and not a fault. Read it before reading an empty
`fact_checks` list, which otherwise says *no fact-checker has ruled on this* — a
statement about the world, and an inviting one for a reader to treat as licence. The
lookup's outcomes are on `fact_checkers[]`, beside `providers[]` and never mixed into it,
so that a missing key cannot make the search look broken and a dead database cannot cost
the search its results.

**`stories` sits beside `domains` because they answer different questions.**
Deduplication happens at two levels and they are not the same operation. One page
returned by three engines under four URL spellings is **merged** into a single source
that lists all four in `urls` and all three in `providers` — a page counted twice is a
source invented. Several publishers carrying one wire story are **marked** with a shared
`cluster` and *never* merged: every publisher stays in `sources` and stays counted in
`domains`, because dropping one would delete a result a provider really returned. Read
the two together. Three domains and one story is a single report reprinted, not three
confirmations; the response gives you both numbers rather than choosing which one you
meant.

**Every quote is verbatim and checkable.** `evidence[].quote` is a slice of one
provider's snippet, and `start`, `end` and `provider` are given so a client can
re-derive it: find that provider in `retrievals`, take `snippet[start:end]`, and it
equals `quote`. Nothing is summarised, nothing is paraphrased, no quote spans a
snippet's `[...]` elision, and a source whose snippets say nothing about the claim comes
back with `evidence: []` rather than a plausible-looking first sentence. It keeps its
place in `sources` — that three engines returned a page which turns out to be irrelevant
is information, and dropping it would make the search look better targeted than it was.

**A date says what kind of date it is.** `date_basis` is one of `provider` (the engine
stated a publication date), `provider_modified` (a date it would not commit to),
`provider_relative` (`"2 days ago"`, resolved against `retrieved_at`) or `url_path` (read
out of the URL by this service, the weakest basis and the only one it derives itself).
The strongest basis available wins, `date_text` carries the provider's own string so a
parse can be checked against it, and all three fields are absent together when nothing
stated a date — there is no fallback to the retrieval time, because that would be a
fabricated publication date indistinguishable from a real one.

**`queries` is the verbatim record of what was sent.** Nothing is appended to a query —
no "fact check", no "debunked", no "true or false" — because a query this service steered
would return evidence this service had chosen the shape of. Up to
`SEARCH_QUERIES_PER_CLAIM` formulations go out per claim: the claim as written, its terms,
then its entities and figures alone. The `claims` input has no entities or keywords to
work from, so it produces only the first, and the narrower search is visible in the
response rather than hidden. The fact-check lookup sends one query per claim and never
widens it, because the widening is the wrong instrument there: the formulations exist to
surface *documents*, and an index keyed on claim wording answers a reworded variant with a
different record. Its `queries`, on `fact_checkers[]`, are the claims themselves.

**A fact check is evidence in the body, never the answer.** `fact_checks` sits beside
`sources` and is never merged into it — a published review is not a search result, and a
fact-checker's own page that the engines also returned is counted once in each rather than
twice in either. Everything a publisher said nests under `fact_checks[].claim`; everything
this service derived sits beside it, which is what keeps the two distinguishable at a
glance. `rating` is the publisher's string verbatim, `stance` is this service's reading of
it, and `stance_from` names the phrase that produced the reading, so an audit needs no
access to the table. A rating the table cannot read is `unrecognised` with
`stance_from: ""` and reaches the client with the publisher's own words intact — which
says exactly as much as the publisher did, and strictly more than a confident wrong answer
would. `agreement` is a stance only when every reviewer of that claim read the same way
and `null` otherwise, never a majority, because two syndicated copies of one wire story
would outvote the newsroom that did the reporting. And no field, at any level of the
response, is a verdict on what the client sent.

**`claim.text` is the database's wording, not the claim you submitted.** Google's index is
keyed on claim wording, so a lookup for one claim returns reviews of neighbouring ones —
the same figure and the same month, attributed to a different central bank. Those are kept
rather than dropped, because reporting no fact checks where fact checks exist is a false
statement about the world that looks identical to the true one. `match` (0–1, the same
scale as evidence relevance) and the three `matched_*` lists say how much of the claim the
reviewed one actually repeats, and `FACT_CHECK_MIN_MATCH` is the floor they are measured
against. Read `claim.text` before citing a rating: it is the field that separates "a
fact-checker ruled on this" from "a fact-checker ruled on something adjacent".

A claim that was submitted or extracted but not searched appears in `skipped` with a
reason — the extractor found it unfit to check, or the `SEARCH_MAX_CLAIMS` ceiling cut it
off. The `claims` input is never judged unfit, but the ceiling applies to it too. A body
listing three claims for prose that made twelve would misdescribe the prose even though
every claim shown is real.

Oversized input gets a `413` naming `text` or `claims` in `error.details.field`. A
missing spaCy model gets a `500` naming the install command — reachable only through
`text`; `claims` needs no model.

### What currently happens end to end

`POST /api/v1/extract-claim` works: it loads the model, reads the prose and answers with
claims, entities and keywords. `POST /api/v1/research` works: it searches the providers
that have keys, looks each claim up in Google's fact-check index if that key is set, and
returns the dossier; with no keys at all it still returns one — `searched: false`,
`fact_checked: false`, every claim listed, every provider and the fact-checker accounted
for. `POST /api/v1/verify`
does not get that far. No desk is
implemented, so a submitted verification runs to `failed` with
`failure.code = "not_implemented"` naming the desk that is missing, in the same
request cycle. That is the intended behaviour until the desks exist — the point of
building the surface first is that the wiring, the validation and the failure
recording are all exercised by it.

Nothing yet connects the two halves that do work: `/research` gathers evidence — web
sources and published reviews both — and no desk reads it. Wiring the fact-check desk
to it is the next step, and it needs no change to either side: the service takes claims
and returns a `Dossier`, which is a domain type. What the desk must not do is
short-circuit on a `FactCheck` whose `agreement` looks decisive. A review is one source
among several, and a desk that returned somebody else's rating as its own verdict would
be laundering it — which is the failure mode `fact_checks` is kept out of `sources` to
make visible rather than convenient.

## Tests, types, lint

```bash
pytest
```

```bash
ruff check . && ruff format --check . && mypy app
```

The tests never touch the network. `tests/search_bench.py` registers a fake client over
each provider in `app.search`'s registry and puts the real factory back afterwards;
`tests/factcheck_bench.py` does the same for `app.factcheck` and can also stand in for a
database whose *construction* fails, which is a different outcome from one that answers
badly; `tests/research_bench.py` holds a corpus of one wire story as several publishers
actually ran it, which is what the deduplication is measured against.

Three modules cover the fact-check path and they divide along the same line the code does.
`tests/test_factcheck_google.py` is the wire: Google's response shape, its error envelopes,
and the fact that the key travels in a header rather than a query parameter.
`tests/test_research_reviews.py` is the judgement, with no network in it — 45 of its cases
are a round-trip over the whole rating vocabulary, which exists because the table is the
one place here where adding an entry silently changes how an existing rating reads.
`tests/test_factcheck_lookup.py` is the isolation: that one rate-limited claim costs that
claim's records and nothing else, and that zero records with a healthy database is never
the same value as zero records with a dead one.

`tests/test_security.py` and `tests/test_auth_api.py` skip as a pair when `argon2-cffi`
or `PyJWT` is missing. That is a real skip and not a masked failure: neither library has
a degraded mode — there is no weaker hash and no unsigned token — so without them the
code under test raises `ConfigurationError` by design and there is nothing to assert.
The security module forges tokens with the application's own key, which is the only way
to reach the checks that run *after* a signature verifies: a missing `exp`, a swapped
`alg`, a refresh token offered where an access token belongs.

[offline_search_tests.py](offline_search_tests.py) is a second runner, for a machine
where nothing can be installed. It stubs `httpx`, `anyio`, `pytest` and `Settings` in
`sys.modules` and then executes the real, committed test functions against the real
application code — so parsing, retry, fan-out, query building, evidence selection,
deduplication, assembly, rating vocabulary, fact-check lookup and the service are all
exercised with no dependencies present:

```bash
python3 offline_search_tests.py
```

It cannot cover anything that needs pydantic, which means every schema and every route.
`tests/test_research_api.py` is the module that asserts the HTTP contract and it runs
under `pytest` only.

## Configuration

Every setting is a field on `Settings` in [app/core/config.py](app/core/config.py)
and is documented in [.env.example](.env.example). Values come from the process
environment, falling back to `backend/.env`, falling back to the defaults in that
file. `.env` is resolved relative to this directory, not the working directory, so
`uvicorn` works from either.

Two guards run at startup rather than at first use, so a bad deploy fails while it
can still be rolled back:

- `JWT_SECRET_KEY` is required whenever `ENVIRONMENT` is not `local`.
- In `production`, `DEBUG` must be off and `CORS_ORIGINS` must not contain `*`.

`MAX_TEXT_CHARS` (default 100,000) bounds submitted prose on the JSON path, which
`MAX_UPLOAD_BYTES` does not cover. It is enforced in the service rather than as a
field constraint, so the bound is configurable per deployment and applies to a worker
as well as to a request. Note what it does not do: the body is fully read and parsed
before the check runs, so it yields a clean `413` rather than protecting the process.

Five settings belong to claim extraction:

| Setting | Default | What it does |
| --- | --- | --- |
| `CLAIM_EXTRACTOR` | `spacy` | Which implementation the registry hands to the service. One entry today. |
| `SPACY_MODEL` | `en_core_web_sm` | The pipeline to load. Not installed by `pip`; see [Running it](#on-the-host). |
| `CLAIM_MIN_TOKENS` | `4` | Fewest content tokens a clause needs to be worth checking. Admits "The bridge opened in March", rejects "It did." |
| `CLAIM_MAX_KEYWORDS` | `10` | Keywords per claim and for the document. |
| `CLAIM_MAX_SENTENCES` | `400` | Ceiling on sentences read from one submission. |

`CLAIM_MAX_SENTENCES` is the one worth a second look, because `MAX_TEXT_CHARS` bounds
the bytes but not the work: 100,000 characters is a few thousand sentences, each of
which is parsed. Hitting the ceiling truncates rather than fails, and `sentences` in the
response reports how many were actually read — so a client can tell a capped submission
from one that simply ended, which it could not do if the tail were silently dropped.

Eight belong to web research:

| Setting | Default | What it does |
| --- | --- | --- |
| `SEARCH_PROVIDERS` | `tavily,brave,serper` | The roster `/research` fans out over, all at once. Providers without a key are reported as `skipped` in every dossier, not dropped. |
| `SEARCH_QUERIES_PER_CLAIM` | `3` | Formulations per claim, per provider: the claim, its terms, its entities and figures. `1` searches only the claim as written. |
| `SEARCH_MAX_CLAIMS` | `10` | Claims researched per request. What the ceiling cuts is named in `skipped`. |
| `SEARCH_MAX_RESULTS` | `10` | Results requested per query, per provider. |
| `SEARCH_ATTEMPTS` | `3` | Total tries per request, not retries — `1` disables retrying. Only 429 and 5xx are retried. |
| `SEARCH_CONCURRENCY` | `2` | Concurrent in-flight requests per provider. |
| `SEARCH_TIMEOUT_SECONDS` | `20` | Per-request timeout. |
| `TAVILY_TOPIC` / `TAVILY_SEARCH_DEPTH` | `general` / `basic` | Which Tavily index, and how hard it looks. |

The request count multiplies out: `SEARCH_MAX_CLAIMS × SEARCH_QUERIES_PER_CLAIM ×`
providers is ninety provider requests at the defaults, against quotas that are per-key
and metered. That is what the two ceilings are for, and why both of them report what
they cut instead of trimming silently. `SEARCH_CONCURRENCY` is low for a related reason —
these limits are often per-second on entry-level plans, and a burst that earns a 429
costs more in backoff than the concurrency saved. Check the plan before raising it.

`SEARCH_PROVIDER`, singular, is a different setting: it selects the one client
`get_search_client()` resolves, for a caller that wants a single engine. Web research
ignores it.

Two of the three providers is enough to corroborate. `app/search/serper.py` is written
against Serper's documentation and **has not been verified against a live response** —
if a field name there is wrong, that provider fails and the other two carry the request,
which is the failure mode the fan-out is built for.

Nine belong to the fact-check lookup:

| Setting | Default | What it does |
| --- | --- | --- |
| `FACT_CHECK_PROVIDER` | `google` | Which database the registry hands to the lookup. One entry today. |
| `GOOGLE_FACT_CHECK_API_KEY` | *unset* | Free, and separate from the search keys. Unset, the lookup is `skipped` on `fact_checkers`, `fact_checked` is `false`, and the web search is untouched. |
| `FACT_CHECK_MAX_RESULTS` | `10` | Records requested per claim. Only the first page is read, so this is the hard ceiling per claim, not a batch size. |
| `FACT_CHECK_MIN_MATCH` | `0.15` | How much of the claim a record must repeat to be reported, on the same 0–1 scale as evidence relevance. |
| `FACT_CHECK_LANGUAGE` | *empty* | BCP-47 restriction. Empty means none, so a Spanish review of a Spanish claim is not filtered away. |
| `FACT_CHECK_MAX_AGE_DAYS` | `0` | Ignore reviews older than this. `0` means no limit — a fact check does not expire. |
| `FACT_CHECK_ATTEMPTS` | `3` | Total tries per request, not retries. Same policy as `SEARCH_ATTEMPTS`. |
| `FACT_CHECK_CONCURRENCY` | `2` | Concurrent in-flight lookups. |
| `FACT_CHECK_TIMEOUT_SECONDS` | `20` | Per-request timeout. |

`FACT_CHECK_MIN_MATCH` is the one to think about before changing, because its two failure
directions are not symmetric. A record that slips through arrives with the fact-checker's
own wording under `claim.text`, so a reader can see for themselves that it is about
something adjacent. A record wrongly excluded becomes a silent "nobody has reviewed this
claim", which is indistinguishable from the truth. Hence the low floor: over-report and
label, rather than under-report and look clean.

The other two defaults are `0` and empty on purpose, and both would be tempting to
tighten. `FACT_CHECK_MAX_AGE_DAYS=0` keeps the 2016 debunk that is the whole reason a
rumour is known to be false; a window would drop it while keeping this month's
recirculation unreviewed. `FACT_CHECK_LANGUAGE=""` keeps reviews this service cannot read
the rating of — the reading vocabulary in `app/research/reviews.py` is English-only, so a
Spanish `"Falso"` arrives as `unrecognised` with `rating: "Falso"`, the publisher and the
URL all intact. That is a worse stance and a real fact check, which beats no fact check.

## Layout

```
app/
  main.py              application factory and ASGI entry point
  api/
    deps.py            shared request dependencies (Annotated aliases)
    responses.py       shared OpenAPI response entries; the Retry-After hint
    v1/router.py       the only router main.py mounts under /api/v1
    v1/routes/         one module per resource, each exposing `router`
  core/
    config.py          Settings; every environment variable in one typed place
    errors.py          VeritasError hierarchy — code, message, HTTP status
    exception_handlers.py  exceptions to JSON, including the 500 catch-all
    logging.py         JSON and console formatters, one handler on root
    middleware.py      correlation id and the per-request access line
    context.py         the request-id context variable
    registry.py        generic provider registry used by the five seams
  domain/
    enums.py           the closed vocabularies, and the desk-routing table
    verification.py    the Verification aggregate and its value types
    claims.py          ExtractedClaim
    research.py        Source, Evidence, Retrieval, ProviderOutcome, Dossier
    factcheck.py       Review, ReviewedClaim, FactCheck, Stance
  desks/base.py        seam: ArtifactDesk and Adjudicator Protocols
  nlp/
    base.py            seam: the ClaimExtractor Protocol and its registry
    resources.py       loads and caches the spaCy model, punkt, stopwords
    segment.py         sentence boundaries as character offsets
    split.py           one sentence into its separately checkable clauses
    screen.py          whether a clause is checkable, and why not
    keywords.py        TF-IDF over the sentences of one submission
    pipeline.py        the extractor: segment, parse, split, screen, rank
  providers/           what every outbound vendor client shares
    http.py            shared transport: retry, backoff, error mapping, redaction
    dates.py           provider date strings to instants, with the basis kept
    outcomes.py        how many requests survived → searched / partial / failed
  search/              the network half of web research
    base.py            seam: the SearchClient Protocol and its registry
    tavily.py          Tavily
    brave.py           Brave, whose dates are relative
    serper.py          Serper — written to the docs, unverified against live
    fanout.py          every provider × every query, failures isolated
  factcheck/           the network half of the fact-check lookup
    base.py            seam: the FactCheckClient Protocol and its registry
    google.py          Google's Fact Check Tools API; reads no rating
    lookup.py          every claim at once, one failure costing one claim
  research/            the judgement half: no network, no model, stdlib only
    urls.py            page identity, publisher identity, dates in a path
    suffixes.py        the registry-suffix table urls.py reads
    terms.py           tokens, numbers, entities — the shared vocabulary
    queries.py         a claim to the query ladder that will be sent
    evidence.py        which passage of a snippet bears on the claim, verbatim
    reviews.py         what a rating means, and whose claim was reviewed
    dedupe.py          one page from many URLs; one story from many publishers
    dossier.py         assembly: dates, ordering, reference numbers
  repositories/        the store seams and both implementations
    base.py            Protocols: verifications, accounts, research
    memory.py          in-memory stores, per process, bounded where it matters
    sql/               the SQLAlchemy stores; one module per aggregate
  security/            passwords and tokens — the only crypto in the codebase
    passwords.py       Argon2id hashing, at the library's own defaults
    tokens.py          JWT signing, and the narrow verification it insists on
  services/
    verification.py    submit, run, read — all orchestration and guards
    auth.py            register, sign in, token to account
    claims.py          claim extraction: guards, then the registered extractor
    research.py        the seam: queries, fan-out, lookup, dossier assembly
    evidence.py        the evidence index over the vector store
    limits.py          the text size guard, shared by all three
  database/
    base.py            declarative base with Alembic-safe naming convention
    session.py         lazy engine, session factory, FastAPI session dependency
  schemas/             pydantic request and response models
  models/              SQLAlchemy tables, one module per aggregate
  llm/                 the reasoning seam: OpenAI, Ollama
  vectorstore/         the embedding seam: Chroma, in-memory
  utils/               clock and id helpers, no internal dependencies
alembic/
  env.py               reads DATABASE_URL from Settings, not alembic.ini
  versions/            0001 is the whole schema: seven tables, written by hand
tests/
  stubs.py             desk and extractor test doubles
  search_bench.py      a fake search provider and the registry swap for it
  factcheck_bench.py   a fake fact-check database, and record/review builders
  research_bench.py    a wire-copy corpus: one story as several publishers ran it
  test_nlp_*.py        the four NLP modules; the parser-backed cases skip
                       themselves when no spaCy model is installed
  test_provider_http.py  transport: retry, backoff, error mapping, redaction
  test_search_*.py     parsing, fan-out
  test_factcheck_*.py  Google's wire format; per-claim isolation in the lookup
  test_research_*.py   urls, queries, evidence, reviews, dedupe, dossier,
                       service, api
  test_security.py     hashing and token verification; skips without the libraries
  test_auth_api.py     the three endpoints, and the ownership rules they switch on
```

Dependencies point one way: `api` → `services` → `repositories`, `desks` and the
seams, with `domain` at the bottom of the application proper and `core`/`utils`
depending on nothing inside `app`. Five rules are worth stating because they are easy
to break by accident:

- **`domain` does not import `desks`.** The report types the desk seam returns are
  defined in `domain`, which is what keeps the two from importing each other.
- **`services` does not import `schemas`.** Services exchange domain objects; the
  routes own the conversion, and that is what keeps the wire format in one layer.
- **No module in `app/nlp` imports spaCy, NLTK or scikit-learn at module scope.**
  Every one of those imports sits inside a function body. That is what lets
  `import app.main` answer `/health` on a machine with none of the stack installed,
  and what turns a missing model into a `500` on the one request that asked for a
  parse instead of a crash at startup. Adding a top-level `import spacy` anywhere
  under `app/nlp` undoes it silently — the suite still passes on a developer machine
  that has the model.
- **`app/research` imports nothing but the standard library and `app/domain`.** Not
  `app/search`, not `app/factcheck`, not `app/llm`, not `app/nlp`, at any scope. All the
  judgement in web research lives there — which URLs are one page, which passage of a
  snippet bears on the claim, which publishers are running one story, what a
  fact-checker's rating means and whether their claim is yours — and keeping it free of
  the network is what makes every one of those decisions testable without a key, a model
  or a socket. `app/search` and `app/factcheck` are the mirror image: they own the wire
  and decide nothing, which is why `app/factcheck/google.py` returns every rating as the
  publisher's string with `stance` left at `unrecognised` and lets
  `app/research/reviews.py` read it. Neither side imports the other;
  `app/services/research.py` is the only place they meet, which is also why
  `queries.build` returns bare strings rather than the `Task` objects the fan-out
  consumes.
- **`app/providers` is shared by both wire packages and depends on neither.** Timeouts,
  retries, backoff, redaction, provider date strings and the searched/partial/failed
  split live there because "be honest about a partial answer" is not search-specific.
  `http.py` and `dates.py` used to sit in `app/search`; a Google fact-check GET and a
  Tavily POST have nothing in common as APIs and everything in common as dependencies.

Only `app.main`, `app.api.*`, and the two HTTP adapters in `core` import the web
framework — everything below them is usable from a worker or a script.

## Conventions worth knowing before adding code

**Errors.** Raise from `app.core.errors`, never `HTTPException`. The handlers turn
any `VeritasError` into the standard envelope using its `code` and `status`:

```json
{
  "error": {
    "code": "provider_timeout",
    "message": "Upstream took too long.",
    "details": {"provider": "tavily"},
    "request_id": "a1b2c3d4e5f6"
  }
}
```

`code` is the contract and never gets reworded; `message` is for a person and may
change.

**Logging.** `get_logger(__name__)`, and pass structured fields as `extra=`:

```python
logger.info("verdict recorded", extra={"claim_id": claim.id, "confidence": 0.91})
```

Both formatters emit those fields, and every line carries the request id without
it being threaded through any signature.

**Adding an endpoint.** Add a module under `app/api/v1/routes/`, then one import
and one `include_router` line in `app/api/v1/router.py`. Routes do not reach
`app/main.py`.

**What a route may contain.** Convert the request, call one service method, convert
the result. Every existing handler is those three lines, and if a route grows a branch
the branch belongs in the service — that is what makes the same logic reachable from a
worker, and what keeps a test of the rules from needing an HTTP client.

**Dependencies.** Take the `Annotated` aliases from `app/api/deps.py`
(`VerificationServiceDep`, `SettingsDep`, …) rather than writing `Depends` in a
signature. Each collaborator is its own hop, so a test can override the store alone and
still exercise the real service, or override the service and replace the lot; a service
that reached for its own collaborators would leave only the second option.

**Two response rules.** Set a header on an injected `Response` — never return
`JSONResponse(headers=...)`, because returning a `Response` subclass makes FastAPI skip
`response_model` while the generated document goes on advertising it. And if the header
is not one of CORS's seven safelisted response headers, add it to `expose_headers` in
`app/main.py`, or a browser reads `null` where curl shows the value. Both of these fail
only in a browser, which is why they are written down here.

**Implementing a provider.** Add a module to the seam package, implement the
Protocol in its `base.py`, and register it:

```python
# app/llm/openai_client.py
llm_clients.register(LLMProvider.OPENAI, OpenAIClient)
```

Import that module from the package's `__init__.py` so the registration runs. Add
the SDK to `requirements.txt` at the same time — not before.

## Where this meets the frontend

The wire vocabulary was taken from `src/lib/types/agents.ts` rather than invented
here. `Determination` is the same nine strings, space in `REQUIRES VERIFICATION`
included, and `Annotation`, `Signal` and `LedgerEntry` are field-for-field identical,
so those three need no translation in either direction.

Three differences are real and will need a line of adapter code on the frontend side
when it stops using `agentServices.ts`:

- **Casing.** Every field on the wire is snake_case (`created_at`, `confidence_value`)
  where the frontend uses camelCase (`previewUrl`, `flaggedSpans`, `fileName`). No
  model sets an `alias_generator`; the reasoning is in
  [app/schemas/\_\_init\_\_.py](app/schemas/__init__.py), and it comes down to one
  spelling per field being worth more than matching the convention of the other side.
  Note `filename`, which is one word here and `fileName` there.
- **`copy` is `content`.** `TextRecord.copy` holds the submitted prose; on the wire
  that is `artifact.content`, and it lives on the artifact rather than on each desk's
  report, because one artifact is what all the desks read.
- **`confidence` gained a sibling.** The frontend's `Verdict.confidence` is the printed
  string, and the wire still carries it under that name. `confidence_value` is the same
  number unrounded, for anything that has to threshold or sort rather than print.

Structurally, the frontend has one interface per desk (`TextRecord`, `ImageRecord`, …)
discriminated on `kind`; the API returns one `DeskReportOut` shape per desk,
discriminated on `desk`, with the desk-specific collections — `signals`, `exhibits`,
`annotations` — present and empty where a desk does not fill them. A record is
therefore rendered by reading the fields a view needs, not by narrowing a union first.

## Not built yet

- **The desks.** `app/desks/base.py` defines the two Protocols and the registries are
  wired, but nothing is registered. This is the next piece of work and the only one
  the endpoints are waiting on. `/research` already gathers the evidence a fact-check
  desk would read — web sources and published reviews both; nothing consumes it yet.
- **Serper, verified.** `app/search/serper.py` is written against Serper's published
  documentation and has never been run against a live response. Tavily, Brave and
  Google's Fact Check Tools API were checked against their references; this one was not,
  and if a field name in it is wrong the provider fails and reports itself as failed
  while the other two carry the request.
- **The second page of fact checks.** The lookup reads one page per claim and never
  follows `nextPageToken`, so `FACT_CHECK_MAX_RESULTS` is a hard ceiling on records per
  claim rather than a batch size. A claim with more than ten published reviews is a
  famous one, and the eleventh does not change the picture — but the ceiling is a real
  limit and not a sampling strategy, so it is written down rather than hidden behind a
  default that looks like pagination.
- **Ratings in other languages.** The vocabulary in `app/research/reviews.py` is English.
  `FACT_CHECK_LANGUAGE` is unset by default so a Spanish review of a Spanish claim is
  still returned, but its `"Falso"` arrives as `stance: "unrecognised"` with the
  publisher, the URL, the date and the rating string intact. That is deliberate — a
  guessed reading can invert a verdict, and `unrecognised` costs a stance without ever
  inverting one — but it does mean the `stance` field is less useful outside English than
  the rest of the record is.
- **Fact-checkers beyond Google's index.** One database is registered. It indexes the
  `ClaimReview` markup publishers put on their own pages, which means a newsroom that
  publishes fact checks without that markup is invisible to it, and `fact_checks: []` for
  a claim says only that *this index* holds nothing.
- **Page fetching.** Research reads provider *snippets* — a sentence or two per result —
  and never fetches the page. That bounds what evidence can be: a claim answered in the
  fourth paragraph of an article will not be quotable from a snippet that stops at the
  first. Fetching would give better evidence and needs its own robots, rate-limit,
  content-type and extraction handling, which is a separate piece of work.
- **Media by upload.** Image, audio and video artifacts are submitted as URLs.
  Multipart upload is a separate path: it needs `MAX_UPLOAD_BYTES` enforced against a
  stream rather than a parsed body, and somewhere to put the bytes.
- **Durable storage under `VERIFICATION_STORE=memory`.** The default is `database`,
  and both stores are real. Left on `memory`, records live in an `OrderedDict` on
  `app.state`, bounded at `MAX_RECORDS` and evicting oldest-first, and accounts live in
  a second dict beside it — per-process, so two workers do not share either, and a
  client can poll a different worker than the one that accepted its submission and get
  a 404. That is what `memory` means and why it is not the default.
- **A queue.** `background.add_task` runs the examination in the same process that
  accepted the submission. `service.run(id)` already takes nothing but an id, so
  becoming a queue enqueue is a one-line change at the one call site.
- **Auth: rate limiting and refresh.** Register, login and `/auth/me` work, and
  ownership is enforced. Nothing is rate-limited yet — `POST /auth/login` first, then
  `POST /auth/register` — and there is no `POST /auth/refresh`, so the access-token
  lifetime is the session length. See [Accounts and ownership](#accounts-and-ownership).
- **Readiness.** `/health` is liveness only — it answers "is this process up",
  which is the question an orchestrator restarts on. A check that also pinged
  Postgres and the LLM provider would make an unrelated outage look like a dead
  container and get it killed during the outage. Readiness, when something needs
  it, is a separate endpoint with a separate meaning.
