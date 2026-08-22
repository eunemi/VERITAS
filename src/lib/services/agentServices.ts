/**
 * Stand-in examination desks.
 *
 * There is no model behind these yet. What they do provide is a record in the
 * real shape, built from the artifact that was actually submitted — the copy you
 * pasted is the copy that gets marked up, the image you chose is the image on the
 * plate — so the desks behave like the finished thing while the backend is wired.
 */

import { seededEnvelope, hashString, seededRandom } from "@/lib/deterministic";
import type {
  Annotation,
  AudioRecord,
  DecisionRecord,
  Determination,
  Exhibit,
  FactCheckRecord,
  ImageRecord,
  TextRecord,
  TranscriptSegment,
  VideoFrame,
  VideoRecord,
} from "@/lib/types/agents";

/** How long a desk pretends to work. Exported so the ticker paces to the wait. */
export const DESK_LATENCY = 4200;

/** The core waits on five desks, so it takes longer. */
export const DECISION_LATENCY = 5400;

function settle<T>(value: T, ms: number = DESK_LATENCY): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

/** Two-digit count, the way a printed ledger sets small figures. */
function figure(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function timecode(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${figure(m)}:${figure(s)}`;
}

/* ---------------------------------------------------------------- text ---- */

/** Split copy into sentences long enough to be worth quoting. */
function sentencesOf(copy: string): string[] {
  return copy
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 24);
}

const TEXT_NOTES: { note: string; determination: Annotation["determination"] }[] = [
  {
    note: "States a figure without naming where it came from. No primary source is reachable from the text.",
    determination: "REQUIRES VERIFICATION",
  },
  {
    note: "Matches three independent records already in the ledger. Wording is close to the original release.",
    determination: "SUPPORTED",
  },
  {
    note: "Attributes intent to a named party. The cited quote does not appear in any transcript on file.",
    determination: "CONTESTED",
  },
  {
    note: "Presents a contested timeline as settled. Two records on file place the event a week later.",
    determination: "CONTRADICTED",
  },
];

export async function examineText(copy: string): Promise<TextRecord> {
  const trimmed = copy.trim();
  const sentences = sentencesOf(trimmed);
  const words = trimmed.split(/\s+/).filter(Boolean).length;

  // Quote real spans of the submitted copy so the proof marks up what you sent.
  const annotations: Annotation[] = sentences.slice(0, 4).map((quote, i) => ({
    ref: i + 1,
    quote,
    note: TEXT_NOTES[i % TEXT_NOTES.length].note,
    determination: TEXT_NOTES[i % TEXT_NOTES.length].determination,
  }));

  const rng = seededRandom(hashString(trimmed || "empty"));
  const emotive = 0.35 + rng() * 0.5;

  return settle<TextRecord>({
    kind: "text",
    copy: trimmed,
    annotations,
    signals: [
      {
        label: "Emotive language",
        reading: emotive > 0.65 ? "HIGH" : emotive > 0.45 ? "ELEVATED" : "LOW",
        weight: emotive,
      },
      {
        label: "Unsourced assertions",
        reading: figure(annotations.filter((a) => a.determination !== "SUPPORTED").length),
        weight: Math.min(1, annotations.length / 4),
      },
      { label: "Source attribution", reading: "SPARSE", weight: 0.28 },
      { label: "Narrative shift", reading: figure(Math.max(1, Math.round(rng() * 3))), weight: 0.45 },
      { label: "Register consistency", reading: "STABLE", weight: 0.82 },
    ],
    ledger: [
      { key: "Language", value: "English" },
      { key: "Words", value: String(words) },
      { key: "Claims", value: figure(annotations.length) },
      { key: "Entities", value: figure(12) },
      { key: "Signals", value: figure(5) },
      { key: "Confidence", value: "92%" },
    ],
    verdict: {
      determination: "REQUIRES VERIFICATION",
      headline: "Two claims cannot be sourced",
      rationale:
        "The copy carries four checkable claims. One matches records already on file. The remaining three rest on attribution the text never supplies, and one contradicts a timeline the ledger holds. The piece is not false — it is unsupported, and it should not run until the missing sources are produced.",
      confidence: "92%",
    },
  });
}

/* --------------------------------------------------------------- image ---- */

export async function examineImage(
  file: File | null,
  previewUrl: string | null,
): Promise<ImageRecord> {
  const name = file?.name ?? "untitled";
  const rng = seededRandom(hashString(name));

  return settle<ImageRecord>({
    kind: "image",
    previewUrl,
    fileName: name,
    regions: [
      { ref: 1, x: 18, y: 22, w: 26, h: 30, label: "Edge discontinuity" },
      { ref: 2, x: 58, y: 14, w: 22, h: 22, label: "Lighting mismatch" },
      { ref: 3, x: 40, y: 62, w: 34, h: 24, label: "Texture regularity" },
    ],
    channels: [
      { label: "Red residual", reading: "0.41", weight: 0.41 },
      { label: "Green residual", reading: "0.36", weight: 0.36 },
      { label: "Blue residual", reading: "0.78", weight: 0.78 },
      { label: "Luminance noise", reading: "UNEVEN", weight: 0.66 },
    ],
    annotations: [
      {
        ref: 1,
        quote: "Region 1 · upper left",
        note: "Boundary pixels resolve harder than the surrounding plane. Consistent with a composited edge.",
        determination: "ANOMALOUS",
      },
      {
        ref: 2,
        quote: "Region 2 · upper right",
        note: "Cast shadows fall away from the dominant light source present everywhere else in the frame.",
        determination: "CONTESTED",
      },
      {
        ref: 3,
        quote: "Region 3 · lower centre",
        note: "Texture repeats on a fixed period. Photographic grain does not repeat.",
        determination: "SYNTHETIC",
      },
    ],
    ledger: [
      { key: "File", value: name.length > 22 ? `${name.slice(0, 20)}…` : name },
      { key: "Generative signal", value: "87%" },
      { key: "Regions flagged", value: figure(3) },
      { key: "Text recovered", value: "14 lines" },
      { key: "Metadata", value: rng() > 0.5 ? "Present" : "Stripped" },
      { key: "Confidence", value: "87%" },
    ],
    verdict: {
      determination: "SYNTHETIC",
      headline: "The frame was generated, not photographed",
      rationale:
        "Three separate readings point the same way. The flagged edge resolves too cleanly for a lens, the shadows in region 2 contradict the frame's own light source, and region 3 carries a repeating texture period no sensor produces. Taken together the plate is a generated image, not a photograph of an event.",
      confidence: "87%",
    },
  });
}

/* --------------------------------------------------------------- audio ---- */

const TRANSCRIPT: Omit<TranscriptSegment, "timecode">[] = [
  {
    ref: null,
    speaker: "Speaker 01",
    line: "The timeline of events is exactly as I set it out in the previous briefing.",
    flagged: false,
  },
  {
    ref: null,
    speaker: "Speaker 02",
    line: "Can you confirm the precise location of the secondary meeting?",
    flagged: false,
  },
  {
    ref: 1,
    speaker: "Speaker 01",
    line: "I cannot comment on the secondary location at this time.",
    flagged: true,
  },
  {
    ref: 2,
    speaker: "Speaker 01",
    line: "That figure was never part of the agreement as it was signed.",
    flagged: true,
  },
];

export async function examineAudio(file: File | null): Promise<AudioRecord> {
  const name = file?.name ?? "untitled";
  const totalSeconds = 168;

  return settle<AudioRecord>({
    kind: "audio",
    fileName: name,
    duration: timecode(totalSeconds),
    envelope: seededEnvelope(name, 160),
    flaggedSpans: [
      { start: 0.52, end: 0.63, ref: 1 },
      { start: 0.78, end: 0.86, ref: 2 },
    ],
    transcript: TRANSCRIPT.map((segment, i) => ({
      ...segment,
      timecode: timecode((totalSeconds / TRANSCRIPT.length) * i),
    })),
    annotations: [
      {
        ref: 1,
        quote: "01:27 – 01:45",
        note: "Formant transitions are smoother than the same speaker's earlier passages. The join is machine-clean.",
        determination: "SYNTHETIC",
      },
      {
        ref: 2,
        quote: "02:11 – 02:24",
        note: "Room tone drops out for 40 ms at the sentence boundary. The line was cut in from another take.",
        determination: "ANOMALOUS",
      },
      {
        ref: 3,
        quote: "Full recording",
        note: "Background noise floor is otherwise continuous, and the two voices remain separable throughout.",
        determination: "CONSISTENT",
      },
    ],
    ledger: [
      { key: "File", value: name.length > 22 ? `${name.slice(0, 20)}…` : name },
      { key: "Duration", value: timecode(totalSeconds) },
      { key: "Words", value: "421" },
      { key: "Speakers", value: figure(2) },
      { key: "Spans flagged", value: figure(2) },
      { key: "Confidence", value: "91%" },
    ],
    verdict: {
      determination: "SYNTHETIC",
      headline: "Two passages were not spoken in the room",
      rationale:
        "The recording is largely authentic — one continuous noise floor, two consistently separable voices. Two stretches are not. Both sit at sentence boundaries, both lose room tone at the join, and both show formant transitions cleaner than the same speaker produces elsewhere. The quotes drawn from those two stretches should not be attributed.",
      confidence: "91%",
    },
  });
}

/* --------------------------------------------------------------- video ---- */

export async function examineVideo(file: File | null): Promise<VideoRecord> {
  const name = file?.name ?? "untitled";
  const runtimeSeconds = 105;
  const frameCount = 12;
  const flaggedFrames = new Map<number, number>([
    [6, 1],
    [9, 2],
  ]);

  const frames: VideoFrame[] = Array.from({ length: frameCount }, (_, i) => ({
    index: i,
    timecode: timecode((runtimeSeconds / frameCount) * i),
    ref: flaggedFrames.get(i) ?? null,
  }));

  return settle<VideoRecord>({
    kind: "video",
    fileName: name,
    runtime: timecode(runtimeSeconds),
    frames,
    scenes: [
      { label: "Interior, podium", span: 0.34, determination: "CONSISTENT" },
      { label: "Cutaway, crowd", span: 0.22, determination: "CONSISTENT" },
      { label: "Interior, close", span: 0.29, determination: "ANOMALOUS" },
      { label: "Exterior, wide", span: 0.15, determination: "CONSISTENT" },
    ],
    annotations: [
      {
        ref: 1,
        quote: "Frame 07 · 01:02",
        note: "The face re-registers between frames while the head does not move. A swap boundary sits here.",
        determination: "SYNTHETIC",
      },
      {
        ref: 2,
        quote: "Frame 10 · 01:27",
        note: "A cast shadow crosses the podium in the opposite direction to the one before and after it.",
        determination: "ANOMALOUS",
      },
      {
        ref: 3,
        quote: "Audio bed, throughout",
        note: "Speech stays locked to lip movement across all four scenes, including the flagged ones.",
        determination: "CONSISTENT",
      },
    ],
    ledger: [
      { key: "File", value: name.length > 22 ? `${name.slice(0, 20)}…` : name },
      { key: "Runtime", value: timecode(runtimeSeconds) },
      { key: "Frames read", value: "128" },
      { key: "Scenes", value: figure(4) },
      { key: "Frames flagged", value: figure(2) },
      { key: "Confidence", value: "88%" },
    ],
    verdict: {
      determination: "SYNTHETIC",
      headline: "One scene carries a face substitution",
      rationale:
        "Three of four scenes hold up, and the audio stays locked to lip movement throughout — whoever prepared this did not touch the sound. The third scene does not hold up. A face re-registers across a static head at frame 7, and a shadow reverses direction at frame 10. That scene was rebuilt.",
      confidence: "88%",
    },
  });
}

/* ---------------------------------------------------------- fact-check ---- */

const EXHIBITS: Omit<Exhibit, "ref">[] = [
  {
    source: "Global Ledger DB",
    published: "12 May 2024",
    relevance: "HIGH",
    reliability: "VERIFIED",
    determination: "CONTRADICTED",
    extract: "Records the figure as 1.4 million, not the 4.1 million the claim asserts.",
  },
  {
    source: "Primary Source Archives",
    published: "10 May 2024",
    relevance: "MEDIUM",
    reliability: "HIGH",
    determination: "INSUFFICIENT",
    extract: "Covers the same period but does not break the total down by region.",
  },
  {
    source: "Historical Event Record",
    published: "20 Nov 2023",
    relevance: "HIGH",
    reliability: "VERIFIED",
    determination: "CONTESTED",
    extract: "Places the decision one week after the date the claim gives.",
  },
  {
    source: "Verified Witness Statements",
    published: "14 May 2024",
    relevance: "LOW",
    reliability: "MEDIUM",
    determination: "SUPPORTED",
    extract: "Two statements independently confirm the meeting took place.",
  },
  {
    source: "Official Register, Second Series",
    published: "03 Jun 2024",
    relevance: "MEDIUM",
    reliability: "VERIFIED",
    determination: "CONTRADICTED",
    extract: "The named party is not listed as a signatory on any instrument that day.",
  },
];

export async function examineClaim(claim: string): Promise<FactCheckRecord> {
  const exhibits: Exhibit[] = EXHIBITS.map((exhibit, i) => ({ ...exhibit, ref: i + 1 }));
  const contradicting = exhibits.filter((e) => e.determination === "CONTRADICTED").length;
  const supporting = exhibits.filter((e) => e.determination === "SUPPORTED").length;

  return settle<FactCheckRecord>({
    kind: "fact-check",
    claim: claim.trim(),
    exhibits,
    annotations: exhibits.slice(0, 3).map((exhibit) => ({
      ref: exhibit.ref,
      quote: exhibit.source,
      note: exhibit.extract,
      determination: exhibit.determination,
    })),
    ledger: [
      { key: "Sources searched", value: "17" },
      { key: "Exhibits returned", value: figure(exhibits.length) },
      { key: "Supporting", value: figure(supporting) },
      { key: "Contradicting", value: figure(contradicting) },
      { key: "Strongest reliability", value: "Verified" },
      { key: "Evidence strength", value: "94%" },
    ],
    verdict: {
      determination: "CONTRADICTED",
      headline: "The central figure is wrong by a factor of three",
      rationale:
        "Five exhibits came back. The two carrying verified reliability both contradict the claim — one on the figure itself, one on who signed. A third puts the date a week out. Only one supports any part of it, and only the part nobody disputed: that the meeting happened. The claim as written should not be repeated.",
      confidence: "94%",
    },
  });
}

/* ------------------------------------------------------------ decision ---- */

/** What one desk filed, and the weight the core gives it. */
interface Filing {
  /** Desk id, matching `@/lib/desks`. */
  id: string;
  /** Printed in the contribution band. */
  label: string;
  /** Relative weight. Normalised across whoever actually reported. */
  weight: number;
  determination: Determination;
  /** The core's note on this filing. Printed only when the desk reported. */
  quote: string;
  note: string;
}

/** The five reporting desks, in filing order. */
const FILINGS: Filing[] = [
  {
    id: "text",
    label: "Text",
    weight: 24,
    determination: "REQUIRES VERIFICATION",
    quote: "Text, attribution",
    note: "The copy's claims are unsupported rather than false. They stay open until a source is produced.",
  },
  {
    id: "image",
    label: "Image",
    weight: 16,
    determination: "SYNTHETIC",
    quote: "Image, residual structure",
    note: "Noise residual is regular where a camera sensor leaves it uneven. Read without sight of the other desks.",
  },
  {
    id: "audio",
    label: "Audio",
    weight: 18,
    determination: "SYNTHETIC",
    quote: "Audio, phase continuity",
    note: "Phase runs continuously across a splice a microphone could not have recorded in one take.",
  },
  {
    id: "video",
    label: "Video",
    weight: 21,
    determination: "SYNTHETIC",
    quote: "Video, frame cadence",
    note: "Frame-to-frame motion is smoother than the stated capture rate allows across two scenes.",
  },
  {
    id: "fact-check",
    label: "Fact-check",
    weight: 21,
    determination: "CONTRADICTED",
    quote: "Fact-check, verified sources",
    note: "The two most reliable exhibits contradict the central claim outright.",
  },
];

/**
 * Which determination the core carries forward. First match wins, so a single
 * contradicted claim is never averaged away by four quieter findings.
 */
const PRECEDENCE: Determination[] = [
  "CONTRADICTED",
  "SYNTHETIC",
  "ANOMALOUS",
  "CONTESTED",
  "REQUIRES VERIFICATION",
  "INSUFFICIENT",
  "CONSISTENT",
  "SUPPORTED",
  "CLEAR",
];

const HEADLINES: Partial<Record<Determination, string>> = {
  CONTRADICTED: "Fabricated, and assembled deliberately",
  SYNTHETIC: "Machine-made, and presented as a record",
  ANOMALOUS: "Altered somewhere between capture and here",
  CONTESTED: "Contested exactly where it matters",
  "REQUIRES VERIFICATION": "Unsupported, and not yet publishable",
  INSUFFICIENT: "Too little to rule on either way",
};

const COUNT_WORDS = ["No", "One", "Two", "Three", "Four", "Five"];

/**
 * The core's record.
 *
 * `reporting` names the desks that actually filed on the artifact — the
 * investigation bench may only have opened two of them. Shares are normalised
 * over whoever reported, and every figure is counted from that set, so the record
 * cannot claim a desk that never read the thing. Called with no argument (the
 * decision desk's own bench) it convenes all five.
 */
export async function renderDecision(reporting?: string[]): Promise<DecisionRecord> {
  const named = reporting ? FILINGS.filter((filing) => reporting.includes(filing.id)) : FILINGS;
  /* An empty or unrecognised list would divide by zero below, and a core that
     ruled on nothing is not a state this record can represent. */
  const filed = named.length > 0 ? named : FILINGS;
  const count = filed.length;

  const total = filed.reduce((sum, filing) => sum + filing.weight, 0);
  const shares = filed.map((filing) => Math.round((filing.weight / total) * 100) / 100);
  /* Rounding to hundredths leaves a stray point; the largest share absorbs it so
     the shares still sum to 1 and the contribution band's rule reaches the end. */
  const drift = Math.round((1 - shares.reduce((sum, share) => sum + share, 0)) * 100) / 100;
  shares[shares.indexOf(Math.max(...shares))] += drift;

  const ruling = PRECEDENCE.find((d) => filed.some((f) => f.determination === d)) ?? "INSUFFICIENT";
  const synthetic = filed.filter((filing) => filing.determination === "SYNTHETIC").length;

  /* A fixture, but a monotone one: the core is least sure when only one desk
     could read the artifact, and most sure when all five did. */
  const confidence = `${89 + count}%`;

  const rationale = [
    count === 1
      ? `${filed[0].label} was the only desk that could read this artifact, so the ruling rests on one reading.`
      : `${COUNT_WORDS[count]} desks reported and none dissented.`,
    synthetic >= 2
      ? `${COUNT_WORDS[synthetic]} found synthetic media in ${COUNT_WORDS[synthetic].toLowerCase()} different modalities, which is not what accidental compression or re-encoding looks like.`
      : null,
    filed.some((filing) => filing.id === "fact-check")
      ? "The fact-check desk found the central claim contradicted by the two most reliable records on file."
      : null,
    ruling === "REQUIRES VERIFICATION"
      ? "Nothing here shows the item was made, only that it has not been shown to be true. Hold it until the sources are produced."
      : "The item was built to be believed, and it should be published only as a fabrication.",
  ]
    .filter(Boolean)
    .join(" ");

  return settle<DecisionRecord>(
    {
      kind: "decision",
      contributions: filed.map((filing, index) => ({
        desk: filing.label,
        share: shares[index],
        determination: filing.determination,
      })),
      signals: [
        {
          label: "Desks in agreement",
          reading: `${figure(count)} of ${figure(count)}`,
          weight: 1,
        },
        { label: "Evidence strength", reading: "91%", weight: 0.91 },
        { label: "Signal consistency", reading: "89%", weight: 0.89 },
        { label: "Model confidence", reading: confidence, weight: (89 + count) / 100 },
      ],
      annotations: filed.map((filing, index) => ({
        ref: index + 1,
        quote: filing.quote,
        note: filing.note,
        determination: filing.determination,
      })),
      ledger: [
        { key: "Desks reporting", value: figure(count) },
        { key: "Dissenting desks", value: figure(0) },
        { key: "Findings weighed", value: figure(count) },
        { key: "Evidence strength", value: "91%" },
        { key: "Signal consistency", value: "89%" },
        { key: "Confidence", value: confidence },
      ],
      verdict: {
        determination: ruling,
        headline: HEADLINES[ruling] ?? "The record stands as filed",
        rationale,
        confidence,
      },
    },
    DECISION_LATENCY,
  );
}
