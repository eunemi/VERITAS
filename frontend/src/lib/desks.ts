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

const d = new Date();
const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const DESK_ISSUE = `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;

export const DESKS: Record<string, DeskDefinition> = {
  text: {
    id: "text",
    number: "01",
    name: "Text",
    titleLines: ["Text", "Examination"],
    eyebrow: "Agent 01 — Linguistic desk",
    standfirst:
      "Paste a headline, article or forwarded message. The desk checks its claims against live web sources and returns a verdict, an explanation and the evidence you can open yourself.",
    file: "VT–0114",
    method: [
      { key: "Reads", value: "Articles, captions, statements" },
      { key: "Looks for", value: "Evidence supporting or contradicting each claim" },
      { key: "Returns", value: "Verdicts, explanations and linked sources" },
      { key: "Unclear evidence", value: "Reported as unverified" },
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
      "Upload a photograph or screenshot. The desk reads its details and text, checks the caption against live sources, and looks for web context and matching images.",
    file: "VT–0115",
    method: [
      { key: "Reads", value: "Photographs, screenshots, stills" },
      { key: "Looks for", value: "Visible details, claims and web context" },
      { key: "Returns", value: "Image report, evidence and match status" },
      { key: "Authenticity", value: "Unverified unless supported by provenance" },
    ],
    prompt: "Upload an image or paste its address",
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
  docx: {
    id: "docx",
    number: "03",
    name: "DOCX",
    titleLines: ["DOCX", "Examination"],
    eyebrow: "Agent 03 — Document desk",
    standfirst:
      "Upload a Word document. The desk extracts its readable text, checks the claims against live sources, and returns the evidence with the original copy preserved.",
    file: "VT–0116",
    method: [
      { key: "Reads", value: "Word documents and their readable text" },
      { key: "Looks for", value: "Checkable claims, names, dates and figures" },
      { key: "Returns", value: "Extracted copy, verdicts and linked sources" },
      { key: "Unclear evidence", value: "Reported as unverified" },
    ],
    prompt: "Upload a DOCX document for examination",
    stages: [
      "Receiving document",
      "Extracting readable text",
      "Finding assertions",
      "Resolving named entities",
      "Searching live sources",
      "Comparing the evidence",
      "Marking what remains",
    ],
  },
  pdf: {
    id: "pdf",
    number: "04",
    name: "PDF",
    titleLines: ["PDF", "Examination"],
    eyebrow: "Agent 04 — Document desk",
    standfirst:
      "Upload a PDF report, notice or article. The desk reads its text, checks the claims it can verify, and shows you where the evidence came from.",
    file: "VT–0117",
    method: [
      { key: "Reads", value: "PDF reports, notices and articles" },
      { key: "Looks for", value: "Claims supported or contradicted by sources" },
      { key: "Returns", value: "Extracted copy, findings and exhibits" },
      { key: "Unclear evidence", value: "Reported as unverified" },
    ],
    prompt: "Upload a PDF for examination",
    stages: [
      "Receiving document",
      "Extracting readable text",
      "Finding assertions",
      "Resolving named entities",
      "Searching live sources",
      "Comparing the evidence",
      "Marking what remains",
    ],
  },
  url: {
    id: "url",
    number: "05",
    name: "URL Link",
    titleLines: ["URL", "Link Check"],
    eyebrow: "Agent 05 — Web desk",
    standfirst:
      "Paste a public article or page link. The desk reads the page, checks its claims against other sources, and reports what the wider record supports.",
    file: "VT–0118",
    method: [
      { key: "Reads", value: "Public article and page links" },
      { key: "Looks for", value: "Claims, dates, sources and page context" },
      { key: "Returns", value: "A verdict with linked web evidence" },
      { key: "Access", value: "The page must be publicly reachable" },
    ],
    prompt: "Paste a URL link for examination",
    stages: [
      "Opening the page",
      "Reading the article",
      "Extracting claims",
      "Resolving named entities",
      "Searching the record",
      "Comparing accounts",
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

/** The five public tools shown on the intelligence cards. */
export const DESK_ORDER = ["text", "image", "docx", "pdf", "url"];

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
