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

/** The closing verdict of a record. */
export interface Verdict {
  determination: Determination;
  headline: string;
  rationale: string;
  confidence: string;
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
}

/* --------------------------------------------------------------- image ---- */

/** A callout box drawn over the plate, in percentages of the image box. */
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
  /** Object URL of the submitted image, so the plate shows the real artifact. */
  previewUrl: string | null;
  fileName: string;
  regions: PlateRegion[];
  /** Per-channel residual readings, shown as the plate's channel strip. */
  channels: Signal[];
}

/* --------------------------------------------------------------- audio ---- */

export interface TranscriptSegment {
  ref: number | null;
  timecode: string;
  speaker: string;
  line: string;
  flagged: boolean;
}

export interface AudioRecord extends RecordBase {
  kind: "audio";
  fileName: string;
  duration: string;
  /** Deterministic envelope, 0–1 per sample. Generated from the file name. */
  envelope: number[];
  /** Flagged stretches, as fractions of total duration. */
  flaggedSpans: { start: number; end: number; ref: number }[];
  transcript: TranscriptSegment[];
}

/* --------------------------------------------------------------- video ---- */

export interface VideoFrame {
  index: number;
  timecode: string;
  /** Set when this cell carries an annotation. */
  ref: number | null;
}

export interface VideoScene {
  label: string;
  /** Fraction of the running time this scene occupies. */
  span: number;
  determination: Determination;
}

export interface VideoRecord extends RecordBase {
  kind: "video";
  fileName: string;
  runtime: string;
  frames: VideoFrame[];
  scenes: VideoScene[];
}

/* ---------------------------------------------------------- fact-check ---- */

export interface Exhibit {
  ref: number;
  source: string;
  published: string;
  relevance: "HIGH" | "MEDIUM" | "LOW";
  reliability: "VERIFIED" | "HIGH" | "MEDIUM" | "LOW";
  determination: Determination;
  extract: string;
}

export interface FactCheckRecord extends RecordBase {
  kind: "fact-check";
  claim: string;
  exhibits: Exhibit[];
}

/* ------------------------------------------------------------ decision ---- */

export interface Contribution {
  desk: string;
  /** Share of the final weighting, 0–1. Shares sum to 1. */
  share: number;
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
  | AudioRecord
  | VideoRecord
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
