/**
 * The desk register.
 *
 * One entry per examination desk. Pages read their masthead, method note, stage
 * list and neighbours from here, so the six desks stay in step and the ordering
 * lives in a single place.
 */

export interface MethodRow {
  key: string;
  value: string;
}

export interface DeskDefinition {
  /** Route segment under /intel. */
  id: string;
  /** Printed as AGENT 01, AGENT 02 … */
  number: string;
  /** Short name for the slug bar and neighbour links. */
  name: string;
  /** Masthead title, one array entry per printed line. */
  titleLines: string[];
  /** Mono eyebrow above the title. */
  eyebrow: string;
  /** Italic standfirst. One or two sentences, plain. */
  standfirst: string;
  /** File number in the slug bar. */
  file: string;
  /** Hanging key/value rows in the method note. */
  method: MethodRow[];
  /** What the submission bench asks for. */
  prompt: string;
  /** Ordered operations shown in the ticker while the desk works. */
  stages: string[];
}

export const DESK_ISSUE = "22 Aug 2026";

export const DESKS: Record<string, DeskDefinition> = {
  text: {
    id: "text",
    number: "01",
    name: "Text",
    titleLines: ["Text", "Examination"],
    eyebrow: "Agent 01 — Linguistic desk",
    standfirst:
      "Paste the copy. The desk returns it marked up: every checkable claim underlined, every claim answered in the margin.",
    file: "VT–0114",
    method: [
      { key: "Reads", value: "Articles, captions, statements" },
      { key: "Looks for", value: "Unsourced claims, register shifts" },
      { key: "Returns", value: "An annotated galley proof" },
      { key: "Does not", value: "Judge opinion or style" },
    ],
    prompt: "Submit copy for examination",
    stages: [
      "Ingesting copy",
      "Detecting language",
      "Extracting claims",
      "Resolving entities",
      "Reading register",
      "Weighing signals",
      "Drawing determination",
    ],
  },
  image: {
    id: "image",
    number: "02",
    name: "Image",
    titleLines: ["Image", "Forensics"],
    eyebrow: "Agent 02 — Visual desk",
    standfirst:
      "The submitted frame goes on the plate. The desk marks the regions that do not behave like photography and says why.",
    file: "VT–0115",
    method: [
      { key: "Reads", value: "Photographs, screenshots, stills" },
      { key: "Looks for", value: "Composite edges, light conflicts" },
      { key: "Returns", value: "A marked plate and channel strip" },
      { key: "Does not", value: "Identify people in the frame" },
    ],
    prompt: "Submit a frame for the plate",
    stages: [
      "Ingesting frame",
      "Reading metadata",
      "Recovering text",
      "Measuring residuals",
      "Testing light sources",
      "Checking texture period",
      "Drawing determination",
    ],
  },
  audio: {
    id: "audio",
    number: "03",
    name: "Audio",
    titleLines: ["Audio", "Forensics"],
    eyebrow: "Agent 03 — Speech desk",
    standfirst:
      "The desk transcribes the recording, then marks the stretches where the voice stops behaving like a voice in a room.",
    file: "VT–0116",
    method: [
      { key: "Reads", value: "Interviews, calls, voice notes" },
      { key: "Looks for", value: "Clone joins, room-tone drops" },
      { key: "Returns", value: "A timecoded transcript and slate" },
      { key: "Does not", value: "Match voices to named people" },
    ],
    prompt: "Submit a recording for the slate",
    stages: [
      "Ingesting recording",
      "Detecting speech",
      "Transcribing",
      "Separating speakers",
      "Reading spectrum",
      "Testing for clone joins",
      "Drawing determination",
    ],
  },
  video: {
    id: "video",
    number: "04",
    name: "Video",
    titleLines: ["Video", "Forensics"],
    eyebrow: "Agent 04 — Temporal desk",
    standfirst:
      "The desk pulls the footage into a contact sheet and reads it across time, where substitutions and impossible shadows show up.",
    file: "VT–0117",
    method: [
      { key: "Reads", value: "Clips, broadcast feeds, uploads" },
      { key: "Looks for", value: "Face swaps, shadow reversals" },
      { key: "Returns", value: "A filmstrip and scene timeline" },
      { key: "Does not", value: "Re-encode or alter the source" },
    ],
    prompt: "Submit footage for the strip",
    stages: [
      "Ingesting footage",
      "Pulling frames",
      "Cutting scenes",
      "Reading frames",
      "Lifting audio bed",
      "Testing continuity",
      "Drawing determination",
    ],
  },
  "fact-check": {
    id: "fact-check",
    number: "05",
    name: "Fact-check",
    titleLines: ["Fact-check", "Desk"],
    eyebrow: "Agent 05 — Evidence & sources",
    standfirst:
      "State the claim. The desk searches the record and returns every exhibit it found, ruled and rated, including the ones that disagree.",
    file: "VT–0118",
    method: [
      { key: "Reads", value: "A single checkable claim" },
      { key: "Looks for", value: "Primary records, first reports" },
      { key: "Returns", value: "A ruled exhibit table" },
      { key: "Does not", value: "Weigh sources it cannot cite" },
    ],
    prompt: "State the claim to be checked",
    stages: [
      "Isolating the claim",
      "Searching the record",
      "Retrieving exhibits",
      "Rating reliability",
      "Comparing accounts",
      "Drawing determination",
    ],
  },
  decision: {
    id: "decision",
    number: "06",
    name: "Decision",
    titleLines: ["Decision", "Core"],
    eyebrow: "Agent 06 — Adjudication",
    standfirst:
      "The five desks report here. The core weighs what they found against how reliably they found it, and signs the record.",
    file: "VT–0119",
    method: [
      { key: "Reads", value: "The five desk records" },
      { key: "Looks for", value: "Agreement, and dissent" },
      { key: "Returns", value: "A signed determination" },
      { key: "Does not", value: "Re-examine the artifact itself" },
    ],
    prompt: "Convene the desks",
    stages: [
      "Collecting records",
      "Weighting by reliability",
      "Testing agreement",
      "Resolving dissent",
      "Signing the record",
    ],
  },
};

export const DESK_ORDER = ["text", "image", "audio", "video", "fact-check", "decision"];

export function neighboursOf(id: string): {
  previous: DeskDefinition | null;
  next: DeskDefinition | null;
} {
  const at = DESK_ORDER.indexOf(id);
  return {
    previous: at > 0 ? DESKS[DESK_ORDER[at - 1]] : null,
    next: at >= 0 && at < DESK_ORDER.length - 1 ? DESKS[DESK_ORDER[at + 1]] : null,
  };
}
