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
      "Paste the copy. The desk returns it marked up: every assertion specific enough to check underlined, and every one it set aside told you why in the margin.",
    file: "VT–0114",
    method: [
      { key: "Reads", value: "Articles, captions, statements" },
      { key: "Looks for", value: "Assertions specific enough to check" },
      { key: "Returns", value: "An annotated galley proof" },
      { key: "Does not", value: "Rule on whether they are true" },
    ],
    prompt: "Submit copy for examination",
    stages: [
      "Ingesting copy",
      "Splitting sentences",
      "Finding assertions",
      "Resolving named entities",
      "Reading subject terms",
      "Setting aside the uncheckable",
      "Marking what remains",
    ],
  },
  image: {
    id: "image",
    number: "02",
    name: "Image",
    titleLines: ["Image", "Forensics"],
    eyebrow: "Agent 02 — Visual desk",
    standfirst:
      "The frame goes on the plate. The desk recovers the text printed in it, checks what that text asserts, and rules each claim at the place on the frame it was read from.",
    file: "VT–0115",
    method: [
      { key: "Reads", value: "Photographs, screenshots, stills" },
      { key: "Looks for", value: "Text printed in the frame" },
      { key: "Returns", value: "A ruled plate and its readings" },
      { key: "Does not", value: "Say whether the picture is real" },
    ],
    prompt: "Give the address of the frame",
    stages: [
      "Fetching the frame",
      "Reading the page",
      "Recovering text",
      "Extracting claims",
      "Searching the record",
      "Checking what it says",
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
      "The desk transcribes the recording, takes the claims out of what was said, and checks those against the record — timecoded, so every line can be found again.",
    file: "VT–0116",
    method: [
      { key: "Reads", value: "Interviews, calls, voice notes" },
      { key: "Looks for", value: "Claims made aloud" },
      { key: "Returns", value: "A timecoded transcript and slate" },
      { key: "Does not", value: "Tell one voice from another" },
    ],
    prompt: "Give the address of the recording",
    stages: [
      "Fetching the recording",
      "Measuring the waveform",
      "Detecting speech",
      "Transcribing",
      "Discarding what the waveform will not carry",
      "Checking what was said",
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
      "The footage goes on the plate. The desk recovers the text printed in its frames, checks what that text asserts, and rules each claim at the place on the frame it was read from. A clip's sound goes to the speech desk.",
    file: "VT–0117",
    method: [
      { key: "Reads", value: "Video footage frames" },
      { key: "Looks for", value: "Text printed in the frames" },
      { key: "Returns", value: "A ruled plate and its readings" },
      { key: "Does not", value: "Say whether the video is real" },
    ],
    prompt: "Give the address of the footage",
    stages: [
      "Fetching the footage",
      "Pulling frames",
      "Reading the page",
      "Recovering text",
      "Extracting claims",
      "Searching the record",
      "Checking what it says",
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
      "The desks that read the artifact report here. The core publishes the gravest determination any of them filed, at the confidence of the desks that filed it, and never averages a finding away.",
    file: "VT–0119",
    method: [
      { key: "Reads", value: "The desk records, not the artifact" },
      { key: "Looks for", value: "The gravest determination filed" },
      { key: "Returns", value: "A signed determination" },
      { key: "Does not", value: "Re-examine the artifact itself" },
    ],
    prompt: "Convene the desks",
    stages: [
      "Collecting the filed records",
      "Ranking the determinations",
      "Taking the gravest of them",
      "Averaging the desks that filed it",
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
