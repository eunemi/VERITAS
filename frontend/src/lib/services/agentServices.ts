/**
 * The examination desks.
 *
 * One submission opens a record on the backend; this module waits for that record to
 * close and translates it into the shapes the desks render. Two things about that
 * translation are worth knowing before reading it:
 *
 * A single submission can open several desks — a text artifact goes to the text desk
 * and the fact-check desk by default — so one record carries several reports and a
 * page pulls out the one it is about. And the decision desk is always added: it is
 * never requested and cannot be, because it reads the other desks' reports rather
 * than the artifact.
 *
 * Nothing here invents a figure. Every number on a record comes off the wire; where
 * the backend does not measure something, the page does not show it.
 */

import {
  ApiError,
  readVerification,
  readVerificationHistory,
  verify,
  type ArtifactIn,
  type ArtifactKind,
  type ArtifactOut,
  type CallOptions,
  type Desk,
  type DeskReportOut,
  type FailureOut,
  type Status,
  type VerdictOut,
  type VerificationOut,
  type VerificationSummaryOut,
} from "@/lib/api/client";
import {
  toneOf,
  type AgentRecord,

  type Contribution,
  type DecisionRecord,
  type Determination,
  type FactCheckRecord,
  type ImageRecord,
  type TextRecord,

  type Verdict,
} from "@/lib/types/agents";

/**
 * Display cadence for the ticker, not a measurement.
 *
 * Real examinations take as long as the search and the models take, which is not
 * known when the stage list starts moving. These pace the stages so they read at
 * walking speed; the ticker is unmounted the moment the record arrives, however long
 * that turns out to be.
 */
export const DESK_PACE_MS = 9000;
export const DECISION_PACE_MS = 6000;

// ================================================================ results ===

export interface Filing {
  desk: Desk;
  record: AgentRecord;
}

/** A closed record, as the pages read it. */
export interface Examination {
  id: string;
  status: Status;
  artifact: ArtifactOut;
  /** The examining desks that filed, in the order the record lists them. */
  filings: Filing[];
  decision: DecisionRecord | null;
  /** Set when a desk stopped the run. Reports filed before it are still above. */
  failure: FailureOut | null;
}

/**
 * The examination itself failed, or filed nothing for the desk that was asked.
 *
 * Extends `ApiError` so that a page rendering a failure reads one shape whether the
 * service was unreachable, refused the submission, or ran and could not finish.
 */
export class ExaminationError extends ApiError {
  readonly desk: Desk | null;
  /** What did come back, so a partial record can still be shown. */
  readonly examination: Examination | null;

  constructor(
    code: string,
    message: string,
    desk: Desk | null = null,
    examination: Examination | null = null,
  ) {
    super(code, message, 200);
    this.name = "ExaminationError";
    this.desk = desk;
    this.examination = examination;
  }
}

// ============================================================== mapping =====

function verdictOf(verdict: VerdictOut): Verdict {
  return {
    determination: verdict.determination,
    headline: verdict.headline,
    rationale: verdict.rationale,
    confidence: verdict.confidence,
    confidenceValue: verdict.confidence_value,
  };
}

/**
 * Whether an artifact location the desk annotated should be ruled in the margin.
 *
 * A note the desk was satisfied by is still a note, and marking it adverse would
 * turn agreement into an accusation, so only unresolved and adverse findings rule.
 */
function ruled(refs: Map<number, Determination>, ref: number): boolean {
  const determination = refs.get(ref);
  return determination !== undefined && toneOf(determination) !== "clear";
}

function annotationRefs(report: DeskReportOut): Map<number, Determination> {
  return new Map(report.annotations.map((a) => [a.ref, a.determination]));
}

/** A readable name for a media artifact the desk was pointed at. */
function nameFrom(url: string, filename?: string | null): string {
  if (filename) return filename;
  try {
    const path = new URL(url).pathname;
    const last = decodeURIComponent(path.split("/").filter(Boolean).pop() ?? "");
    return last || new URL(url).hostname;
  } catch {
    return url;
  }
}

function textRecordOf(report: DeskReportOut, artifact: ArtifactOut): TextRecord {
  return {
    kind: "text",
    // The copy the backend echoes back, not the copy in the form: the galley proof
    // finds each annotation by searching for its quote, so it has to mark the exact
    // string the desk read.
    copy: artifact.content ?? "",
    ledger: report.ledger,
    annotations: report.annotations,
    signals: report.signals,
    exhibits: report.exhibits,
    verdict: verdictOf(report.verdict),
  };
}

function factCheckRecordOf(
  report: DeskReportOut,
  artifact: ArtifactOut,
): FactCheckRecord {
  return {
    kind: "fact-check",
    claim: artifact.content ?? artifact.url ?? "",
    ledger: report.ledger,
    annotations: report.annotations,
    exhibits: report.exhibits,
    signals: report.signals,
    verdict: verdictOf(report.verdict),
  };
}

function imageRecordOf(report: DeskReportOut, artifact: ArtifactOut): ImageRecord {
  const detail = report.detail && "regions" in report.detail ? report.detail : null;
  return {
    kind: "image",
    previewUrl: artifact.url,
    fileName: nameFrom(artifact.url ?? "", artifact.filename),
    regions: detail?.regions ?? [],
    ledger: report.ledger,
    annotations: report.annotations,
    signals: report.signals,
    verdict: verdictOf(report.verdict),
    extractedText: detail?.text ?? "",
    exhibits: report.exhibits,
    description: detail?.description ?? "",
    observations: detail?.observations ?? [],
    provenance: detail?.provenance ?? "Image authenticity has not been established.",
    webStatus: detail?.web_status ?? "not_searched",
    limitations: detail?.limitations ?? [],
    metadata: detail?.metadata ?? [],
  };
}



/**
 * The signed record.
 *
 * The contributions are read off the examining desks' own reports rather than off
 * the decision desk's signals, which carry the same readings behind a label that
 * would have to be parsed back into a desk id to link anywhere.
 */
function decisionRecordOf(
  report: DeskReportOut,
  examining: DeskReportOut[],
): DecisionRecord {
  const contributions: Contribution[] = examining.map((filed) => ({
    desk: filed.desk,
    confidence: filed.verdict.confidence_value,
    determination: filed.verdict.determination,
  }));

  return {
    kind: "decision",
    contributions,
    // The decision desk's own signals restate the contributions above, so the record
    // shows them once. Anything it measures beyond a per-desk reading appears here.
    signals: report.signals.filter(
      (signal) => !/ desk$/i.test(signal.label),
    ),
    ledger: report.ledger,
    annotations: report.annotations,
    verdict: verdictOf(report.verdict),
  };
}

/** A desk with no record shape of its own yet still has a verdict and a ledger. */
function recordOf(report: DeskReportOut, artifact: ArtifactOut): AgentRecord | null {
  switch (report.desk) {
    case "text":
      return textRecordOf(report, artifact);
    case "fact-check":
      return factCheckRecordOf(report, artifact);
    case "image":
      return imageRecordOf(report, artifact);

    default:
      return null;
  }
}

function examinationOf(record: VerificationOut): Examination {
  const examining = record.reports.filter((report) => report.desk !== "decision");
  const adjudication = record.reports.find((report) => report.desk === "decision");

  const filings: Filing[] = [];
  for (const report of examining) {
    const mapped = recordOf(report, record.artifact);
    if (mapped) filings.push({ desk: report.desk, record: mapped });
  }

  return {
    id: record.id,
    status: record.status,
    artifact: record.artifact,
    filings,
    decision: adjudication ? decisionRecordOf(adjudication, examining) : null,
    failure: record.failure,
  };
}

// ============================================================ submission ====

export interface ExamineOptions {
  signal?: AbortSignal;
  /** Called with each reading of the open record, so a page can follow progress. */
  onReading?: (record: VerificationOut) => void;
}

/**
 * Submit an artifact, wait for the record to close, and return it.
 *
 * A failed record comes back rather than throwing: the desks that filed before the
 * failure are on it, and a page that can show a partial record should. Only the
 * transport raises from here.
 */
export async function commission(
  artifact: ArtifactIn,
  desks: Desk[] | null = null,
  options: ExamineOptions = {},
): Promise<Examination> {
  const record = await verify(
    { artifact, desks },
    { signal: options.signal, onReading: options.onReading },
  );
  return examinationOf(record);
}

/** Pull the one desk a page is about, or explain why it is not there. */
function filed<T extends AgentRecord>(
  examination: Examination,
  desk: Desk,
  kind: T["kind"],
): T {
  const filing = examination.filings.find((candidate) => candidate.desk === desk);
  if (filing && filing.record.kind === kind) return filing.record as T;

  const failure = examination.failure;
  if (failure) {
    throw new ExaminationError(
      failure.code,
      failure.message,
      failure.desk,
      examination,
    );
  }
  throw new ExaminationError(
    "no_report",
    `The examination closed without a report from the ${desk} desk.`,
    desk,
    examination,
  );
}

export async function examineText(
  copy: string,
  options: ExamineOptions = {},
): Promise<TextRecord> {
  const examination = await commission(
    { kind: "text", content: copy },
    ["fact-check"],
    options,
  );
  const checked = filed<FactCheckRecord>(examination, "fact-check", "fact-check");
  return { ...checked, kind: "text", copy };
}

export async function examineClaim(
  claim: string,
  options: ExamineOptions = {},
): Promise<FactCheckRecord> {
  const examination = await commission(
    { kind: "claim", content: claim },
    ["fact-check"],
    options,
  );
  return filed<FactCheckRecord>(examination, "fact-check", "fact-check");
}

export async function examineImage(
  url: string,
  filename: string | null = null,
  options: ExamineOptions = {},
  caption = "",
): Promise<ImageRecord> {
  const examination = await commission(
    { kind: "image", url, filename, content: caption || null },
    ["image"],
    options,
  );
  return filed<ImageRecord>(examination, "image", "image");
}

/** Examine a public page URL using the same source-checking record as a claim. */
export async function examineUrl(
  url: string,
  options: ExamineOptions = {},
): Promise<FactCheckRecord> {
  const examination = await commission(
    { kind: "url", url },
    ["fact-check"],
    options,
  );
  return filed<FactCheckRecord>(examination, "fact-check", "fact-check");
}



/** What a submission that ran to a signed record comes back as. */
export interface Adjudication {
  decision: DecisionRecord;
  examination: Examination;
}

/**
 * Open every desk an artifact calls for and return the signed record with them.
 *
 * The decision desk cannot be commissioned by itself — it reads what the examining
 * desks filed, so there has to be something for them to file on first. Naming no
 * roster opens the desks the artifact's kind calls for and adds the adjudicator over
 * the top of them.
 *
 * Unlike `commission`, this raises when nothing was signed: a caller asking for a
 * determination has no record without one, and the reports that were filed before the
 * run stopped travel on the error for a page that can still show them.
 */
export async function convene(
  artifact: ArtifactIn,
  options: ExamineOptions = {},
): Promise<Adjudication> {
  const examination = await commission(artifact, null, options);

  if (!examination.decision) {
    const failure = examination.failure;
    throw new ExaminationError(
      failure?.code ?? "no_report",
      failure?.message ??
        "The examination closed without a signed record from the decision desk.",
      failure?.desk ?? "decision",
      examination,
    );
  }

  return { decision: examination.decision, examination };
}

/** The decision desk's own bench, which is convened on copy. */
export function deliberate(
  copy: string,
  options: ExamineOptions = {},
): Promise<Adjudication> {
  return convene({ kind: "text", content: copy }, options);
}

// =============================================================== the file ===

/**
 * The archive's own vocabulary for what was handed over. The wire's `kind` is a
 * transport word; these are the words the index and the commission slip print.
 */
const HANDED_OVER: Record<ArtifactKind, string> = {
  text: "Copy",
  claim: "Claim",
  url: "Address",
  image: "Frame",

};

const TITLE_LENGTH = 120;

/** One line naming the artifact: its opening words, or the address it was fetched from. */
function titleOf(artifact: ArtifactOut): string {
  if (artifact.content) {
    const collapsed = artifact.content.replace(/\s+/g, " ").trim();
    return collapsed.length > TITLE_LENGTH
      ? `${collapsed.slice(0, TITLE_LENGTH).trimEnd()}…`
      : collapsed;
  }
  if (artifact.url) {
    return artifact.kind === "url"
      ? artifact.url
      : nameFrom(artifact.url, artifact.filename);
  }
  return artifact.filename ?? "Nothing was attached";
}

/**
 * One row of the reader's file.
 *
 * A row, not a record: the history endpoint sends no desk reports, so nothing here is
 * a finding beyond the determination the decision desk signed. `id` is what fetches
 * the record itself.
 */
export interface FiledRecord {
  id: string;
  status: Status;
  terminal: boolean;
  /** `Copy`, `Claim`, `Frame`, `Recording`, `Footage` or `Address`. */
  handedOver: string;
  title: string;
  /** ISO stamp, formatted by the page that prints it. */
  filed: string;
  /** Null until the decision desk has signed, and on a record that failed. */
  verdict: Verdict | null;
  failure: FailureOut | null;
}

function filedRecordOf(row: VerificationSummaryOut): FiledRecord {
  return {
    id: row.id,
    status: row.status,
    terminal: row.terminal,
    handedOver: HANDED_OVER[row.artifact.kind],
    title: titleOf(row.artifact),
    filed: row.created_at,
    verdict: row.verdict ? verdictOf(row.verdict) : null,
    failure: row.failure,
  };
}

/**
 * `GET /verifications` — the signed-in account's own records, newest first.
 *
 * Raises when nobody is signed in, because there is no anonymous history to fall back
 * to: a record filed without a token has no owner to match on. The caller has the
 * session and should not be asking without one.
 */
export async function history(
  limit?: number,
  options: CallOptions = {},
): Promise<FiledRecord[]> {
  const { items } = await readVerificationHistory({
    limit,
    signal: options.signal,
  });
  return items.map(filedRecordOf);
}

/**
 * `GET /verification/{id}` — one record as it stands, in the shape the desks render.
 *
 * The same translation a submission goes through, so a row of the file expands into
 * exactly the record the desk printed when it was signed. An owned record answers 404
 * to anyone but its owner, which arrives here as an `ApiError` with `not_found`.
 */
export async function retrieve(
  id: string,
  options: CallOptions = {},
): Promise<Examination> {
  const { record } = await readVerification(id, { signal: options.signal });
  return examinationOf(record);
}
