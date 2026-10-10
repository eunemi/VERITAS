/**
 * Shapes returned by the examination desks.
 *
 * Every desk produces the same three-part record — a ledger of counted facts, a
 * set of annotations anchored to the artifact, and a determination — plus one
 * desk-specific exhibit (the proof, the plate, the slate, the strip, the table).
 */

/** How the desk came down on a single annotation. Drives colour, nothing else. */
export type Determination =
  | "SUPPORTED"
  | "CONSISTENT"
  | "CLEAR"
  | "REQUIRES VERIFICATION"
  | "INSUFFICIENT"
  | "CONTESTED"
  | "CONTRADICTED"
  | "ANOMALOUS"
  | "SYNTHETIC";

/**
 * A marginal note anchored to a location in the artifact.
 * `ref` is the exhibit number printed both in the margin and on the artifact —
 * it is a pointer, which is why the numbering is meaningful here.
 */
export interface Annotation {
  ref: number;
  /** The exact span of the artifact this note refers to. */
  quote: string;
  /** The examiner's note. One sentence, plain. */
  note: string;
  determination: Determination;
}

/** A measured reading. `weight` (0–1) sets the bar length, `reading` is the label. */
export interface Signal {
  label: string;
  reading: string;
  weight: number;
}

/** One cell of the ledger band. */
export interface LedgerEntry {
  key: string;
  value: string;
}

/**
 * The closing verdict of a record.
 *
 * Both forms of the confidence are carried because they are read by different
 * things: `confidence` is the printed string a record sets inline, and
 * `confidenceValue` is the 0–1 reading the decision desk's shares are computed
 * from. Deriving one from the other means parsing a display string, which is how a
 * rounding decision made for a reader ends up inside an arithmetic.
 */
export interface Verdict {
  determination: Determination;
  headline: string;
  rationale: string;
  /** Printed form, e.g. `"92%"`. */
  confidence: string;
  /** The same reading, 0–1. */
  confidenceValue: number;
}

interface RecordBase {
  ledger: LedgerEntry[];
  annotations: Annotation[];
  verdict: Verdict;
}

/* ---------------------------------------------------------------- text ---- */

export interface TextRecord extends RecordBase {
  kind: "text";
  /** The copy as submitted. Annotated in place by the galley proof. */
  copy: string;
  signals: Signal[];
  exhibits: Exhibit[];
}

/* --------------------------------------------------------------- image ---- */

/**
 * A callout box drawn over the plate, in percentages of the image box.
 *
 * `ref` is 0 for a region the desk read but drew no conclusion about — a line of
 * recovered text that made no claim. Those are labelled and boxed, not numbered,
 * so nothing in the margin points at them.
 */
export interface PlateRegion {
  ref: number;
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
}

export interface ImageRecord extends RecordBase {
  kind: "image";
  /** The image the desk read, so the plate shows the artifact and not a stand-in. */
  previewUrl: string | null;
  fileName: string;
  regions: PlateRegion[];
  /** What the desk measured on the frame: recovered text, detections. */
  signals: Signal[];
  extractedText: string;
  exhibits: Exhibit[];
  description: string;
  observations: string[];
  provenance: string;
  webStatus: string;
  limitations: string[];
  metadata: LedgerEntry[];
}



/* ---------------------------------------------------------- fact-check ---- */

/** How closely a source bears on the claim. */
export type Relevance = "HIGH" | "MEDIUM" | "LOW";

/** How much weight the source itself carries. */
export type Reliability = "VERIFIED" | "HIGH" | "MEDIUM" | "LOW";

export interface Exhibit {
  ref: number;
  source: string;
  published: string;
  relevance: Relevance;
  reliability: Reliability;
  determination: Determination;
  extract: string;
  url?: string;
  claim_ref?: number | null;
}

export interface FactCheckRecord extends RecordBase {
  kind: "fact-check";
  claim: string;
  exhibits: Exhibit[];
  /** Counted ratios behind the ruling: claims settled, sources graded, evidence found. */
  signals: Signal[];
}

/* ------------------------------------------------------------ decision ---- */

/**
 * One examining desk's standing in the final ruling.
 *
 * `confidence` is that desk's own confidence in its own finding, not a share of a
 * total. The decision desk does not average the desks or apportion weight between
 * them: it takes the gravest determination filed and reports the mean confidence of
 * the desks that filed it, so there is no share to show and inventing one would
 * describe an arithmetic that never ran.
 */
export interface Contribution {
  /** The desk's id, as the routes and the roster spell it. */
  desk: string;
  confidence: number;
  determination: Determination;
}

export interface DecisionRecord extends RecordBase {
  kind: "decision";
  contributions: Contribution[];
  signals: Signal[];
}

export type AgentRecord =
  | TextRecord
  | ImageRecord

  | FactCheckRecord
  | DecisionRecord;

/* ---------------------------------------------------------------------- */

/** Determinations that read as a clean result. */
const CLEAR_SET: ReadonlySet<Determination> = new Set<Determination>([
  "SUPPORTED",
  "CONSISTENT",
  "CLEAR",
]);

/** Determinations that read as unresolved rather than adverse. */
const OPEN_SET: ReadonlySet<Determination> = new Set<Determination>([
  "REQUIRES VERIFICATION",
  "INSUFFICIENT",
]);

export type DeterminationTone = "clear" | "open" | "adverse";

export function toneOf(determination: Determination): DeterminationTone {
  if (CLEAR_SET.has(determination)) return "clear";
  if (OPEN_SET.has(determination)) return "open";
  return "adverse";
}

/**
 * Text colour per tone. Kept in one place so every desk agrees.
 *
 * `open` was `text-gold-foil`, which measures 2.0:1 on the #fef9f0 ground — the
 * determination, the most important word in a record, was the least readable
 * thing on the page wherever a desk could not settle. Foil fills a rule; it does
 * not set a word. Every call site of this map is on paper, so one value fixes it.
 */
export const TONE_TEXT: Record<DeterminationTone, string> = {
  clear: "text-trust-green",
  open: "text-gold-ink",
  adverse: "text-secondary",
};

/** Rule/underline colour per tone. */
export const TONE_RULE: Record<DeterminationTone, string> = {
  clear: "bg-trust-green",
  open: "bg-gold-foil",
  adverse: "bg-secondary",
};

/** Border colour per tone. */
export const TONE_BORDER: Record<DeterminationTone, string> = {
  clear: "border-trust-green",
  open: "border-gold-foil",
  adverse: "border-secondary",
};
