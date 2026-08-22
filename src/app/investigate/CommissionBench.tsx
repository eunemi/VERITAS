"use client";

import Link from "next/link";
import { useState } from "react";
import { ContributionBand } from "@/components/agents/instruments/ContributionBand";
import { Determination } from "@/components/agents/shared/Determination";
import { ExaminationTicker } from "@/components/agents/shared/ExaminationTicker";
import { FindingLedger, SignalTable } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import type { DeskStatus } from "@/components/agents/shared/SlugBar";
import {
  CopyField,
  FileField,
  SubmissionBench,
  useArtifact,
} from "@/components/agents/shared/SubmissionBench";
import { Band, MarkedSpread, SectionHead, Slug, Spread } from "@/components/agents/shared/layout";
import { DESKS, DESK_ISSUE, type DeskDefinition } from "@/lib/desks";
import {
  DECISION_LATENCY,
  DESK_LATENCY,
  examineAudio,
  examineClaim,
  examineImage,
  examineText,
  examineVideo,
  renderDecision,
} from "@/lib/services/agentServices";
import {
  TONE_RULE,
  TONE_TEXT,
  toneOf,
  type AgentRecord,
  type DecisionRecord,
  type LedgerEntry,
} from "@/lib/types/agents";

/**
 * The commission bench: one artifact, every desk that can read it, one signed
 * record.
 *
 * The routing is the honest part of this page. An artifact opens only the desks
 * that can actually read it — copy goes to the copy and fact-check desks, footage
 * goes to the video desk and the audio desk underneath it — so no desk on the
 * page reports on something it never saw, and the core weighs only what was
 * filed. The old version of this page ran a four-second timer and printed the
 * same verdict every time, whatever you handed it.
 */

/** The five desks that can read an artifact. The core is not one of them. */
type ReportingDesk = "text" | "image" | "audio" | "video" | "fact-check";

interface Submission {
  copy: string;
  file: File | null;
  url: string | null;
}

/** Which service reads for which desk. Keyed so the map cannot miss a desk. */
const READERS: Record<ReportingDesk, (submission: Submission) => Promise<AgentRecord>> = {
  text: ({ copy }) => examineText(copy),
  "fact-check": ({ copy }) => examineClaim(copy),
  image: ({ file, url }) => examineImage(file, url),
  audio: ({ file }) => examineAudio(file),
  video: ({ file }) => examineVideo(file),
};

interface Kind {
  id: string;
  /** Printed on the chooser. */
  label: string;
  /** What this kind is, in the reader's words. */
  note: string;
  desks: ReportingDesk[];
  /** Absent for copy, which is typed rather than filed. */
  file?: {
    accept: string;
    formats: string;
    kind: "image" | "audio" | "video";
    /** Only the image desk shows the artifact back, so only it needs an object URL. */
    preview: boolean;
  };
  prompt: string;
  hint: string;
}

const KINDS: Kind[] = [
  {
    id: "copy",
    label: "Copy",
    note: "An article, a post, or a single claim",
    desks: ["text", "fact-check"],
    prompt: "Paste the copy you want read.",
    hint: "Two desks open on copy: one reads how it is written, the other checks what it asserts against the records on file. Neither sees the other's working.",
  },
  {
    id: "frame",
    label: "Frame",
    note: "A photograph or a still",
    desks: ["image"],
    file: { accept: "image/*", formats: "JPG · PNG · WEBP", kind: "image", preview: true },
    prompt: "Choose the frame to put on the plate.",
    hint: "The image desk reads the frame itself — residual noise, edge continuity, the direction the light falls — and marks what it finds by exhibit number.",
  },
  {
    id: "recording",
    label: "Recording",
    note: "Speech, a call, a clip",
    desks: ["audio"],
    file: { accept: "audio/*", formats: "MP3 · WAV · M4A", kind: "audio", preview: false },
    prompt: "Choose the recording to be slated.",
    hint: "The audio desk reads the waveform and the transcript together, and flags the stretches where the two disagree with each other.",
  },
  {
    id: "footage",
    label: "Footage",
    note: "Video, with the sound it carries",
    desks: ["video", "audio"],
    file: { accept: "video/*", formats: "MP4 · MOV · WEBM", kind: "video", preview: false },
    prompt: "Choose the footage to be examined.",
    hint: "Footage is two artifacts in one file, so two desks open on it: the video desk reads the frames, the audio desk reads the track underneath them.",
  },
];

const STATUS_COPY: Record<DeskStatus, string> = {
  bench: "Awaiting an artifact",
  working: "Desks reading",
  record: "Record signed",
};

const STATUS_MARK: Record<DeskStatus, string> = {
  bench: "bg-parchment/30",
  working: "bg-gold-foil animate-pulse",
  record: "bg-secondary",
};

/** Two-digit count, the way a printed ledger sets small figures. */
function figure(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/** One desk's filing, kept with the desk that filed it. */
interface Filing {
  desk: DeskDefinition;
  record: AgentRecord;
}

/** A filed record, summarised: who read it, what they ruled, how sure they were. */
function FilingRow({ desk, record }: Filing) {
  const tone = toneOf(record.verdict.determination);

  return (
    <li className="border-t border-ink-black/12 py-stack-lg first:border-t-0 first:pt-0">
      <div className="grid gap-stack-md lg:grid-cols-12 lg:gap-gutter">
        <div className="lg:col-span-3">
          <Slug className="tabular text-ink-black/40">Agent {desk.number}</Slug>
          <p className="font-headline-md mt-2 text-[26px] leading-tight font-normal text-ink-black italic">
            {desk.name} desk
          </p>
          <span className="mt-3.5 flex items-center gap-2.5">
            <span aria-hidden className={`h-[2px] w-6 shrink-0 ${TONE_RULE[tone]}`} />
            <Slug className={TONE_TEXT[tone]}>{record.verdict.determination}</Slug>
          </span>
        </div>

        <div className="lg:col-span-6">
          <h3 className="font-headline-md text-[23px] leading-snug font-bold text-ink-black">
            {record.verdict.headline}
          </h3>
          <p className="font-body-sm text-body-sm mt-2.5 max-w-[62ch] text-ink-black/65">
            {record.verdict.rationale}
          </p>
        </div>

        <div className="lg:col-span-3 lg:text-right">
          <Slug className="text-ink-black/40">Confidence</Slug>
          <p className="tabular font-headline-md mt-2 text-[30px] leading-none font-semibold text-ink-black">
            {record.verdict.confidence}
          </p>
          <p className="mt-2">
            <Slug className="tabular text-ink-black/40">
              {figure(record.annotations.length)} marked
            </Slug>
          </p>
          <Link
            href={`/intel/${desk.id}`}
            className="mt-stack-sm inline-flex items-center gap-2 border-b-2 border-secondary pb-1 transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            <Slug className="text-ink-black">Open the desk</Slug>
            <span aria-hidden className="text-[13px] leading-none text-secondary">
              &rarr;
            </span>
          </Link>
        </div>
      </div>
    </li>
  );
}

export function CommissionBench() {
  const [kindId, setKindId] = useState(KINDS[0].id);
  const [status, setStatus] = useState<DeskStatus>("bench");
  const [copy, setCopy] = useState("");
  const { artifact, pick } = useArtifact();
  const [filings, setFilings] = useState<Filing[]>([]);
  const [decision, setDecision] = useState<DecisionRecord | null>(null);

  const kind = KINDS.find((option) => option.id === kindId) ?? KINDS[0];
  const working = status === "working";
  const ready = kind.file ? artifact.file !== null : copy.trim().length > 0;

  const stages = [
    "Typing the artifact",
    ...kind.desks.map((id) => `${DESKS[id].name} desk is reading it`),
    "Collecting the filed records",
    "Weighting each desk by what it could read",
    "Signing one determination",
  ];

  function choose(id: string) {
    if (working) return;
    setKindId(id);
    /* A frame is not footage: whatever is on the bench cannot be read by the
       desks the new kind opens, so it comes off. */
    pick(null);
  }

  async function commission() {
    if (working || !ready) return;
    setStatus("working");

    const roster = kind.desks;
    const records = await Promise.all(
      roster.map((id) => READERS[id]({ copy, file: artifact.file, url: artifact.url })),
    );
    setFilings(roster.map((id, index) => ({ desk: DESKS[id], record: records[index] })));

    /* The core is told who actually reported, so it cannot weigh a desk that
       never opened a file on this artifact. */
    setDecision(await renderDecision(roster));
    setStatus("record");
  }

  function reopen() {
    setFilings([]);
    setDecision(null);
    setStatus("bench");
  }

  const marked = filings.reduce((sum, filing) => sum + filing.record.annotations.length, 0);
  const adverse = filings.reduce(
    (sum, filing) =>
      sum +
      filing.record.annotations.filter((note) => toneOf(note.determination) === "adverse").length,
    0,
  );

  const ledger: LedgerEntry[] = decision
    ? [
        { key: "Artifact", value: kind.label },
        { key: "Desks opened", value: figure(filings.length) },
        { key: "Findings marked", value: figure(marked) },
        { key: "Adverse findings", value: figure(adverse) },
        { key: "Filed", value: DESK_ISSUE },
        { key: "Confidence", value: decision.verdict.confidence },
      ]
    : [];

  const divider = <span aria-hidden className="h-3 w-px shrink-0 bg-parchment/25" />;

  return (
    <main className="min-h-screen bg-background">
      <Band
        className="bg-ink-black text-parchment"
        inner="flex h-9 items-center justify-between gap-gutter"
      >
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/intel"
            className="shrink-0 transition-opacity hover:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-foil"
          >
            <Slug>Intelligence Desk</Slug>
          </Link>
          {divider}
          <Slug className="shrink-0 text-parchment/50">Commission</Slug>
          <span aria-hidden className="hidden h-3 w-px bg-parchment/25 md:inline-block" />
          <Slug className="hidden shrink-0 text-parchment/50 md:inline">{kind.label}</Slug>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <Slug className="tabular hidden text-parchment/40 lg:inline">{DESK_ISSUE}</Slug>
          <span aria-hidden className="hidden h-3 w-px bg-parchment/25 lg:inline-block" />
          <span className="flex items-center gap-2">
            <span aria-hidden className={`h-1.5 w-1.5 ${STATUS_MARK[status]}`} />
            <Slug>{STATUS_COPY[status]}</Slug>
          </span>
        </div>
      </Band>

      <Spread className="pt-stack-xl pb-stack-lg">
        <Slug className="text-secondary">One artifact, every desk that can read it</Slug>
        <h1 className="font-masthead mt-stack-sm max-w-[15ch] text-[clamp(44px,8vw,104px)] leading-[0.92] font-black tracking-[-0.025em] text-ink-black">
          <span className="block">Open a file</span>
          <span className="block pl-[0.05em] font-normal italic">on one thing.</span>
        </h1>
        <p className="font-headline-md mt-stack-md max-w-[46ch] text-[23px] leading-[1.35] font-normal text-ink-black/70 italic">
          Hand over what you have. The desks that can read it each file separately, and the core
          signs one record over the top of them.
        </p>
      </Spread>

      {working ? (
        <ExaminationTicker stages={stages} durationMs={DESK_LATENCY + DECISION_LATENCY} />
      ) : null}

      {status === "record" && decision ? (
        <>
          <LedgerBand entries={ledger} />

          <Spread className="pt-stack-xl pb-stack-xl">
            <SectionHead
              title="What each desk filed"
              note={`${figure(filings.length)} reporting · read independently`}
            />
            <ol className="mt-stack-md">
              {filings.map((filing) => (
                <FilingRow key={filing.desk.id} desk={filing.desk} record={filing.record} />
              ))}
            </ol>
          </Spread>

          <Spread className="pb-stack-xl">
            <MarkedSpread
              artifact={
                <div className="flex flex-col gap-stack-xl">
                  <ContributionBand contributions={decision.contributions} />
                  <SignalTable signals={decision.signals} title="How the ruling was tested" />
                </div>
              }
              margin={<FindingLedger annotations={decision.annotations} title="What decided it" />}
            />
          </Spread>

          <Determination verdict={decision.verdict} signedBy="decision core" />

          <Spread>
            <div className="flex flex-wrap items-baseline justify-between gap-4 border-t border-ink-black/15 py-stack-lg">
              <p className="font-body-sm text-body-sm max-w-[52ch] text-ink-black/55">
                The record stands as filed. Commissioning another artifact opens a new file and
                leaves this one behind.
              </p>
              <button
                type="button"
                onClick={reopen}
                className="cursor-pointer border-b-2 border-secondary pb-1 transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
              >
                <Slug className="text-secondary">Commission another</Slug>
              </button>
            </div>
          </Spread>
        </>
      ) : (
        <Spread className={working ? "pt-stack-xl" : ""}>
          <section className="pb-stack-xl">
            <SectionHead title="What are you handing over?" note="Sets which desks open" />
            <fieldset className="mt-stack-md" disabled={working}>
              <legend className="sr-only">What are you handing over?</legend>
              <div className="grid gap-px bg-ink-black/15 sm:grid-cols-2 lg:grid-cols-4">
                {KINDS.map((option) => (
                  <label
                    key={option.id}
                    className="block cursor-pointer bg-background"
                  >
                    <input
                      type="radio"
                      name="artifact-kind"
                      value={option.id}
                      checked={option.id === kindId}
                      onChange={() => choose(option.id)}
                      className="peer sr-only"
                    />
                    <span className="block h-full px-5 py-stack-md text-ink-black transition-colors peer-checked:bg-ink-black peer-checked:text-parchment peer-focus-visible:outline-2 peer-focus-visible:-outline-offset-2 peer-focus-visible:outline-secondary peer-disabled:opacity-60">
                      <span className="font-headline-md block text-[26px] leading-tight font-normal italic">
                        {option.label}
                      </span>
                      <span className="font-body-sm text-body-sm mt-1.5 block opacity-60">
                        {option.note}
                      </span>
                      <span className="mt-3.5 block">
                        <Slug className="opacity-45">
                          {option.desks.length === 1
                            ? "One desk opens"
                            : `${option.desks.length} desks open`}
                        </Slug>
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          </section>

          <SubmissionBench
            prompt={kind.prompt}
            note={kind.file ? `Accepts ${kind.file.formats}` : "Plain text"}
            hint={kind.hint}
            actionLines={["Open", "the file"]}
            onSubmit={commission}
            disabled={working || !ready}
          >
            {kind.file ? (
              <FileField
                artifact={artifact}
                onPick={(file) => pick(file, kind.file?.preview ?? false)}
                accept={kind.file.accept}
                formats={kind.file.formats}
                kind={kind.file.kind}
                scanning={working}
              />
            ) : (
              <CopyField
                value={copy}
                onChange={setCopy}
                placeholder="Paste the article, the post, or the one sentence you want checked…"
                scanning={working}
              />
            )}

            <div className="mt-stack-lg">
              <SectionHead
                title="Who will read it"
                note={`${figure(kind.desks.length)} desks · then the core signs`}
              />
              <ol className="mt-stack-sm">
                {kind.desks.map((id) => {
                  const desk = DESKS[id];
                  return (
                    <li key={id} className="border-b border-ink-black/12">
                      <Link
                        href={`/intel/${desk.id}`}
                        className="group grid grid-cols-[64px_1fr] items-baseline gap-x-4 gap-y-1 py-stack-md transition-colors hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black sm:grid-cols-[64px_1fr_1.4fr]"
                      >
                        <Slug className="tabular text-ink-black/40">{desk.number}</Slug>
                        <span className="font-headline-md text-[24px] leading-tight font-normal text-ink-black italic group-hover:text-secondary">
                          {desk.titleLines.join(" ")}
                        </span>
                        <span className="font-body-sm text-body-sm col-start-2 text-ink-black/55 sm:col-start-3">
                          Looks for {desk.method[1].value.toLowerCase()}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ol>
            </div>
          </SubmissionBench>
        </Spread>
      )}

      <Spread>
        <div className="border-t border-ink-black/15 pt-stack-md pb-stack-lg">
          <Slug className="text-ink-black/40">Colophon</Slug>
          <p className="font-body-sm mt-2.5 max-w-[86ch] text-[13px] leading-[21px] text-ink-black/50">
            Set at the Veritas investigations bench · Issue{" "}
            <span className="tabular">{DESK_ISSUE}</span>. The examination model is not attached
            yet: the findings, figures and determination on this record are fixtures, held in the
            shape the real record will take. Nothing you hand over is uploaded — the copy stays in
            this browser, and the file never leaves your disk.
          </p>
        </div>
      </Spread>

      <Band className="bg-ink-black text-parchment" inner="py-stack-xl">
        <div className="flex flex-wrap items-end justify-between gap-stack-md">
          <div>
            <Slug className="text-parchment/45">Before you commission</Slug>
            <p className="font-headline-md mt-3 max-w-[28ch] text-[30px] leading-[1.1] font-normal italic">
              Read what each desk looks for, and what it will not tell you.
            </p>
          </div>
          <Link
            href="/intel"
            className="font-mono-label text-mono-label border border-parchment px-6 py-3 uppercase transition-colors hover:bg-parchment hover:text-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-foil"
          >
            The register of desks
          </Link>
        </div>
      </Band>
    </main>
  );
}
