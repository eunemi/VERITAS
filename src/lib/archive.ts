/**
 * The published record index.
 *
 * Every entry is a record that was signed at one of the desks. The shape is what
 * the backend will fill — one row per signed record, keyed by its file number —
 * so the index can be swapped for a query without the page changing. The rows
 * below are fixtures, and the archive page says so.
 */

import type { Determination } from "@/lib/types/agents";

/** What was handed over. Matches the kinds the commission bench accepts. */
export type ArchiveArtifact = "Copy" | "Claim" | "Frame" | "Recording" | "Footage";

export interface ArchiveRecord {
  /** File number, as printed on the record. */
  id: string;
  headline: string;
  /** One sentence on what the examination turned on. */
  standfirst: string;
  /** ISO date the record was signed. Sorted and grouped by this. */
  filed: string;
  /** Desk that led the examination. A key of `DESKS`. */
  desk: string;
  artifact: ArchiveArtifact;
  /** Where the artifact came to us from. */
  source: string;
  region: string;
  determination: Determination;
  confidence: string;
}

/** Newest first. The index is printed in filing order and never re-sorted. */
export const ARCHIVE: ArchiveRecord[] = [
  {
    id: "VT–0113",
    headline: "Authentication of the August diplomatic cables",
    standfirst:
      "Six pages of correspondence, submitted as a leak. The copy desk found the register consistent with the named ministry throughout.",
    filed: "2026-08-15",
    desk: "text",
    artifact: "Copy",
    source: "Internal leak",
    region: "Europe",
    determination: "SUPPORTED",
    confidence: "96%",
  },
  {
    id: "VT–0111",
    headline: "The viral market-panic call was never recorded",
    standfirst:
      "Phase ran continuously across a splice no microphone could have captured in one take.",
    filed: "2026-07-02",
    desk: "audio",
    artifact: "Recording",
    source: "Social platform",
    region: "North America",
    determination: "SYNTHETIC",
    confidence: "97%",
  },
  {
    id: "VT–0109",
    headline: "Deep-sea sabotage footage: too little to rule on",
    standfirst:
      "Nine seconds at 240p. The video desk could not separate compression from tampering and declined to guess.",
    filed: "2026-06-14",
    desk: "video",
    artifact: "Footage",
    source: "Anonymous submission",
    region: "Baltic",
    determination: "INSUFFICIENT",
    confidence: "41%",
  },
  {
    id: "VT–0106",
    headline: "The flood photograph was taken four years earlier",
    standfirst:
      "The frame is real. The caption is not — the same image sits in a 2022 wire archive under a different river.",
    filed: "2026-05-28",
    desk: "image",
    artifact: "Frame",
    source: "Messaging forward",
    region: "South Asia",
    determination: "CONTRADICTED",
    confidence: "99%",
  },
  {
    id: "VT–0104",
    headline: "Grain export figures cannot be traced to a source",
    standfirst:
      "Three of four claims rest on attribution the copy never supplies. Unsupported rather than false.",
    filed: "2026-04-09",
    desk: "fact-check",
    artifact: "Claim",
    source: "Newsletter",
    region: "East Africa",
    determination: "REQUIRES VERIFICATION",
    confidence: "88%",
  },
  {
    id: "VT–0101",
    headline: "Composite of a rally that did not happen at that scale",
    standfirst:
      "Two crowds, one horizon line. The plate shows the seam the retouching left along the treeline.",
    filed: "2026-03-21",
    desk: "image",
    artifact: "Frame",
    source: "Campaign account",
    region: "South America",
    determination: "SYNTHETIC",
    confidence: "94%",
  },
  {
    id: "VT–0097",
    headline: "Hospital capacity claim holds, with one figure corrected",
    standfirst:
      "The central claim is supported by ministry records. A bed count in the third paragraph was overstated by a factor of ten.",
    filed: "2026-02-02",
    desk: "fact-check",
    artifact: "Copy",
    source: "Regional daily",
    region: "Southeast Asia",
    determination: "SUPPORTED",
    confidence: "93%",
  },
  {
    id: "VT–0094",
    headline: "Ministerial resignation clip cut from two separate answers",
    standfirst:
      "The edit is real footage in a false order. Frame cadence changes at the join, and the room tone does not.",
    filed: "2025-12-11",
    desk: "video",
    artifact: "Footage",
    source: "Broadcast rip",
    region: "West Africa",
    determination: "ANOMALOUS",
    confidence: "91%",
  },
  {
    id: "VT–0090",
    headline: "Two desks disagreed on the same recording, and both were printed",
    standfirst:
      "The audio desk read the splice as an edit; the core weighed the transcript against it and left the disagreement standing.",
    filed: "2025-11-04",
    desk: "decision",
    artifact: "Recording",
    source: "Whistleblower",
    region: "Middle East",
    determination: "CONTESTED",
    confidence: "72%",
  },
  {
    id: "VT–0086",
    headline: "The quoted memo exists; the quote does not",
    standfirst:
      "Four words were added to a sentence that is otherwise verbatim. The addition carries the whole story.",
    filed: "2025-09-17",
    desk: "text",
    artifact: "Copy",
    source: "Trade publication",
    region: "North America",
    determination: "CONTRADICTED",
    confidence: "98%",
  },
  {
    id: "VT–0081",
    headline: "Earthquake damage frame is consistent with the stated location",
    standfirst:
      "Shadow direction, sensor noise and the two visible signs all agree with the time and place claimed.",
    filed: "2025-07-30",
    desk: "image",
    artifact: "Frame",
    source: "Field reporter",
    region: "Central Asia",
    determination: "CONSISTENT",
    confidence: "95%",
  },
  {
    id: "VT–0075",
    headline: "Machine-read speech attributed to a governor who never gave it",
    standfirst:
      "The voice is a model of a real one. The desk marked the six places where breathing does not track the sentence.",
    filed: "2025-05-08",
    desk: "audio",
    artifact: "Recording",
    source: "Video platform",
    region: "South Asia",
    determination: "SYNTHETIC",
    confidence: "96%",
  },
];

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/**
 * `2026-08-15` → `15 Aug 2026`. Formatted by hand rather than with
 * `toLocaleDateString`, which resolves differently on the server and in the
 * browser and would print two different dates into the same markup.
 */
export function filedOn(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day} ${MONTHS[Number(month) - 1]} ${year}`;
}

export function yearOf(iso: string): string {
  return iso.slice(0, 4);
}

/** Facet values, taken from the records themselves so a filter cannot go stale. */
export function facetsOf(records: ArchiveRecord[]) {
  const unique = (values: string[]) => Array.from(new Set(values));
  return {
    years: unique(records.map((record) => yearOf(record.filed))).sort().reverse(),
    desks: unique(records.map((record) => record.desk)),
    determinations: unique(records.map((record) => record.determination)).sort(),
  };
}
