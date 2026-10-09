/**
 * Transport to the examination API.
 *
 * Everything in here mirrors the wire, not the page: field names are the backend's
 * snake_case, `Determination` and friends are its exact enum strings, and nothing is
 * reshaped for a component. The translation into the record shapes the desks render
 * lives one layer up, in `@/lib/services/agentServices`, so that a change to the
 * contract lands in one file and a change to a plate lands in another.
 */

import type {
  Determination,
  Relevance,
  Reliability,
} from "@/lib/types/agents";

/**
 * `NEXT_PUBLIC_*` is substituted at build time by matching the literal text
 * `process.env.NEXT_PUBLIC_API_URL`, so this expression cannot be built up from a
 * variable or read off a destructured `process.env` — either spelling survives into
 * the bundle as an undefined lookup. The trailing slash is trimmed because every
 * path below leads with one.
 */
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/+$/, "");

function requireApiBaseUrl(): string {
  if (!API_BASE_URL) {
    throw new ApiError(
      "configuration_error",
      "The application is missing its API endpoint configuration.",
    );
  }
  return API_BASE_URL;
}

// ================================================================== wire ====

export type Desk =
  | "text"
  | "image"
  | "audio"
  | "video"
  | "fact-check"
  | "decision";

export type ArtifactKind = "text" | "claim" | "url" | "image" | "audio" | "video";

export type Status = "pending" | "running" | "completed" | "failed";

export interface VerdictOut {
  determination: Determination;
  headline: string;
  rationale: string;
  /** Printed form, e.g. `"92%"`. */
  confidence: string;
  /** The same reading as a number, for anything that thresholds or weighs. */
  confidence_value: number;
}

export interface AnnotationOut {
  ref: number;
  /** Verbatim from the artifact, which is how a marker finds its span. */
  quote: string;
  note: string;
  determination: Determination;
}

export interface SignalOut {
  label: string;
  reading: string;
  weight: number;
}

export interface LedgerEntryOut {
  key: string;
  value: string;
}

export interface ExhibitOut {
  ref: number;
  source: string;
  published: string;
  relevance: Relevance;
  reliability: Reliability;
  determination: Determination;
  extract: string;
}

/** Percentages of the frame. `ref` is 0 for a region that produced no claim. */
export interface PlateRegionOut {
  ref: number;
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
}

export interface ImageDetailOut {
  width: number;
  height: number;
  text: string;
  regions: PlateRegionOut[];
}

export interface TranscriptCueOut {
  ref: number;
  start: number;
  end: number;
  timecode: string;
  text: string;
}

export interface AudioDetailOut {
  duration: number;
  runtime: string;
  language: string;
  text: string;
  envelope: number[];
  /** `[start, end]` fractions of the duration where the recording is voiced. */
  spans: number[][];
  cues: TranscriptCueOut[];
}

export type DeskDetailOut = ImageDetailOut | AudioDetailOut;

export interface DeskReportOut {
  desk: Desk;
  verdict: VerdictOut;
  ledger: LedgerEntryOut[];
  annotations: AnnotationOut[];
  signals: SignalOut[];
  exhibits: ExhibitOut[];
  /** The union is open: a desk added later may bring a shape not named here. */
  detail: DeskDetailOut | null;
}

export interface DeskProgressOut {
  desk: Desk;
  status: Status;
  started_at: string | null;
  completed_at: string | null;
}

export interface ArtifactOut {
  kind: ArtifactKind;
  content: string | null;
  url: string | null;
  filename: string | null;
}

/**
 * Named `failure` on the record because `error` is the top-level key of every
 * non-2xx body this API returns, and the two are different things: a failed
 * examination is a 200 with a `failure`.
 */
export interface FailureOut {
  code: string;
  message: string;
  desk: Desk | null;
}

export interface VerificationAccepted {
  id: string;
  status: Status;
  /** The full roster, adjudicator included. */
  desks: Desk[];
  created_at: string;
}

export interface VerificationOut {
  id: string;
  status: Status;
  terminal: boolean;
  artifact: ArtifactOut;
  desks: DeskProgressOut[];
  reports: DeskReportOut[];
  failure: FailureOut | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

/**
 * One row of `GET /verifications`: a record without its desk reports.
 *
 * The signed verdict is here because it is what a list is read for. The reports are
 * not — each carries its own annotations, signals and exhibits, and twenty of those
 * is a large response to print twenty lines from. A row's `id` fetches the record.
 */
export interface VerificationSummaryOut {
  id: string;
  status: Status;
  terminal: boolean;
  artifact: ArtifactOut;
  /** Null until the decision desk has signed. */
  verdict: VerdictOut | null;
  failure: FailureOut | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface VerificationHistoryOut {
  items: VerificationSummaryOut[];
  /** The length of `items`, not a total: nothing counts rows the query left out. */
  count: number;
}

export interface TextArtifactIn {
  kind: "text";
  content: string;
}

export interface ClaimArtifactIn {
  kind: "claim";
  content: string;
}

export interface UrlArtifactIn {
  kind: "url";
  url: string;
}

/**
 * Media is fetched by the backend from a URL. There is no upload endpoint: that
 * needs multipart with a byte ceiling enforced against a stream, and it is not
 * built, so a file sitting on the reader's disk cannot be examined yet.
 */
export interface MediaArtifactIn {
  kind: "image" | "audio" | "video";
  url: string;
  filename?: string | null;
}

export type ArtifactIn =
  | TextArtifactIn
  | ClaimArtifactIn
  | UrlArtifactIn
  | MediaArtifactIn;

export interface VerifyRequest {
  artifact: ArtifactIn;
  /** Omitted or null takes the default roster for the artifact's kind. */
  desks?: Desk[] | null;
}

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown> | null;
    request_id?: string | null;
  };
}

// ================================================================ errors ====

/** Codes this client raises itself, alongside whatever the API sends. */
export const UNREACHABLE = "service_unreachable";
export const POLL_TIMEOUT = "poll_timeout";
export const MALFORMED = "malformed_response";

/**
 * One error type for both halves of a failed call, distinguished by `status`.
 *
 * `code` is the branchable part — the API documents it as a stable snake_case
 * vocabulary, while `message` is written for people and may be reworded at any
 * time. Anything deciding what to render reads `code`; anything showing the reader
 * a sentence prints `message`.
 */
export class ApiError extends Error {
  readonly code: string;
  /** 0 when the request never reached the API at all. */
  readonly status: number;
  readonly details: Record<string, unknown> | null;
  readonly requestId: string | null;

  constructor(
    code: string,
    message: string,
    status = 0,
    details: Record<string, unknown> | null = null,
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
  }

  /** No response came back: wrong host, nothing listening, or CORS refused it. */
  get unreachable(): boolean {
    return this.status === 0 && this.code === UNREACHABLE;
  }

  /** The desk exists in the roster but is not implemented on the server. */
  get notImplemented(): boolean {
    return this.code === "not_implemented";
  }
}

// =============================================================== session ====

/**
 * The bearer token sent with every request, or null when nobody is signed in.
 *
 * Held here rather than threaded through each call because it is a property of the
 * session and not of any one request: submitting with a token attaches the record to
 * that account, and `GET /verifications` cannot be read without one. `AuthProvider`
 * is the only writer — it owns where the token is kept and when it is dropped.
 */
let bearer: string | null = null;

export function setAuthToken(token: string | null): void {
  bearer = token;
}

// =============================================================== requests ===

const REQUEST_ID_HEADER = "x-request-id";

export interface CallOptions {
  signal?: AbortSignal;
}

/**
 * The one place a request is made and a response is read.
 *
 * Exported because the auth endpoints in `./auth` are the same API over the same
 * error envelope, and a second `fetch` wrapper would be a second place for the
 * bearer token, the error shape and the unreachable case to be handled differently.
 */
export async function request<T>(
  path: string,
  init: RequestInit & CallOptions,
): Promise<{ body: T; response: Response }> {
  const apiBaseUrl = requireApiBaseUrl();
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      // Caller headers land last so an explicit one wins; the token is spread in
      // before them and never overwrites a header a call site set on purpose.
      headers: {
        Accept: "application/json",
        ...(bearer === null ? null : { Authorization: `Bearer ${bearer}` }),
        ...init.headers,
      },
    });
  } catch (cause) {
    // A rejected fetch carries no status and, for a cross-origin refusal, no
    // detail either — the browser withholds it. Everything actionable is on our
    // side of the wire, so name the address rather than guess at the reason.
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(
      UNREACHABLE,
      `Could not reach the examination service at ${apiBaseUrl}.`,
      0,
      { cause: String(cause) },
    );
  }

  const requestId = response.headers.get(REQUEST_ID_HEADER);
  const text = await response.text();

  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    const envelope = (parsed ?? {}) as ErrorEnvelope;
    const error = envelope.error ?? {};
    throw new ApiError(
      error.code ?? `http_${response.status}`,
      error.message ?? `The service answered ${response.status}.`,
      response.status,
      error.details ?? null,
      error.request_id ?? requestId,
    );
  }

  if (parsed === null) {
    throw new ApiError(
      MALFORMED,
      "The service answered without a readable body.",
      response.status,
      null,
      requestId,
    );
  }

  return { body: parsed as T, response };
}

/** `POST /verify` — accepted, not finished. Poll the id it hands back. */
export async function submitVerification(
  submission: VerifyRequest,
  options: CallOptions = {},
): Promise<VerificationAccepted> {
  const { body } = await request<VerificationAccepted>("/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submission),
    signal: options.signal,
  });
  return body;
}

interface Read {
  record: VerificationOut;
  /** Seconds the server asks a poller to wait. Absent once the record is terminal. */
  retryAfter: number | null;
}

/** `GET /verification/{id}` — one reading of the record as it stands. */
export async function readVerification(
  id: string,
  options: CallOptions = {},
): Promise<Read> {
  const { body, response } = await request<VerificationOut>(
    `/verification/${encodeURIComponent(id)}`,
    { method: "GET", signal: options.signal },
  );
  const header = response.headers.get("retry-after");
  const seconds = header === null ? NaN : Number(header);
  return {
    record: body,
    retryAfter: Number.isFinite(seconds) ? seconds : null,
  };
}

/** The server's own ceiling, so a caller is refused here rather than with a 422. */
export const MAX_HISTORY_LIMIT = 100;

/**
 * `GET /verifications` — the signed-in account's own records, newest first.
 *
 * Requires a token. There is no such thing as an anonymous history: a record
 * submitted without one has no owner to match on, and its id is the only handle on
 * it that exists.
 */
export async function readVerificationHistory(
  options: CallOptions & { limit?: number } = {},
): Promise<VerificationHistoryOut> {
  const query =
    options.limit === undefined
      ? ""
      : `?limit=${Math.min(Math.max(Math.trunc(options.limit), 1), MAX_HISTORY_LIMIT)}`;
  const { body } = await request<VerificationHistoryOut>(`/verifications${query}`, {
    method: "GET",
    signal: options.signal,
  });
  return body;
}

// ================================================================ polling ===

const FIRST_POLL_MS = 600;
const MAX_POLL_MS = 2_500;
const DEFAULT_DEADLINE_MS = 180_000;

export interface PollOptions extends CallOptions {
  /** Called with every reading, terminal one included. */
  onReading?: (record: VerificationOut) => void;
  /** Give up after this long and raise `poll_timeout`. */
  timeoutMs?: number;
}

const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });

/**
 * Read the record until `terminal` is true, then return it.
 *
 * `Retry-After` is the server's own answer to how long to wait and is sent only
 * while the record is still open, so honouring it means never asking twice about a
 * finished examination. Between readings the interval grows to `MAX_POLL_MS`: a
 * submission that runs several desks against live search can take minutes, and a
 * fixed one-second poll would spend most of them asking.
 *
 * A terminal record is returned, not thrown — `status: "failed"` with a `failure`
 * attached is an outcome the record was designed to carry, and the reports filed
 * before the failure are still on it. Only the transport raises.
 */
export async function pollVerification(
  id: string,
  options: PollOptions = {},
): Promise<VerificationOut> {
  const { signal, onReading, timeoutMs = DEFAULT_DEADLINE_MS } = options;
  const started = performance.now();
  let backoff = FIRST_POLL_MS;

  for (;;) {
    const { record, retryAfter } = await readVerification(id, { signal });
    onReading?.(record);
    if (record.terminal) return record;

    if (performance.now() - started > timeoutMs) {
      throw new ApiError(
        POLL_TIMEOUT,
        `The examination was still running after ${Math.round(timeoutMs / 1000)}s.`,
        0,
        { id, status: record.status },
      );
    }

    const hinted = retryAfter === null ? 0 : retryAfter * 1000;
    await wait(Math.min(MAX_POLL_MS, Math.max(hinted, backoff)), signal);
    backoff = Math.min(MAX_POLL_MS, Math.round(backoff * 1.4));
  }
}

/** Submit, then poll to a terminal record. The whole round trip. */
export async function verify(
  submission: VerifyRequest,
  options: PollOptions = {},
): Promise<VerificationOut> {
  const accepted = await submitVerification(submission, { signal: options.signal });
  return pollVerification(accepted.id, options);
}

/** Upload a document and return its extracted text. */
export async function extractTextFromFile(file: File, options: CallOptions = {}): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);
  const { body } = await request<{ text: string }>("/files/extract-text", {
    method: "POST", body: formData, signal: options.signal,
  });
  return body.text;
}

/** Upload media and return the API URL the examination service can read. */
export async function uploadMediaFile(file: File, options: CallOptions = {}): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);
  const { body } = await request<{ url: string }>("/files/upload-media", {
    method: "POST", body: formData, signal: options.signal,
  });
  return body.url;
}
