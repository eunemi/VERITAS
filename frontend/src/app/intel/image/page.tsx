"use client";

import { useState } from "react";
import { ForensicPlate } from "@/components/agents/instruments/ForensicPlate";
import { ExhibitLedger } from "@/components/agents/instruments/ExhibitLedger";
import { Determination } from "@/components/agents/shared/Determination";
import { DeskFailure } from "@/components/agents/shared/DeskFailure";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { FindingLedger, SignalTable } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import {
  isFetchableUrl,
  LinkField,
  SubmissionBench,
} from "@/components/agents/shared/SubmissionBench";
import { useExamination } from "@/components/agents/shared/useExamination";
import { MarkedSpread, Spread, SectionHead } from "@/components/agents/shared/layout";
import { DESKS } from "@/lib/desks";
import { DESK_PACE_MS, examineImage } from "@/lib/services/agentServices";
import type { ImageRecord } from "@/lib/types/agents";

const desk = DESKS.image;

export default function ImageDesk() {
  const [url, setUrl] = useState("");
  const [caption, setCaption] = useState("");
  const [uploading, setUploading] = useState(false);
  const { status, record, error, open, reopen, working, progress } = useExamination<ImageRecord>();

  const ready = isFetchableUrl(url);

  return (
    <DeskPage
      desk={desk}
      status={status}
      progress={progress}
      latencyMs={DESK_PACE_MS}
      onReopen={reopen}
      bench={
        <SubmissionBench
          prompt={desk.prompt}
          note="One still image at a time"
          hint="The desk inspects visible details, checks readable text and your caption, and searches for web context and image matches."
          actionLines={["Examine", "frame"]}
          onSubmit={() => open((options) => examineImage(url.trim(), null, options, caption.trim()))}
          disabled={!ready || working || uploading}
        >
          <LinkField
            value={url}
            onChange={setUrl}
            kind="image"
            formats="JPG · PNG · WEBP · GIF · AVIF · up to 50 MB"
            scanning={working}
            onBusy={setUploading}
          />
          <label className="mt-6 block text-ink-black/70">What is claimed about this image? (optional)
            <textarea value={caption} onChange={(event) => setCaption(event.target.value)} maxLength={5000} rows={3} disabled={working || uploading} placeholder="For example: This photo shows flooding in Delhi today. Include the caption, date or location you want checked." className="mt-2 w-full border border-ink-black/20 bg-parchment p-4 text-ink-black" />
          </label>
        </SubmissionBench>
      }
      failure={<DeskFailure error={error} onRetry={reopen} />}
      record={
        record ? (
          <>
            <LedgerBand entries={record.ledger} />
            <div className="pt-stack-xl"><Determination verdict={record.verdict} signedBy="image context & claim check" scope="Text / caption verdict" /></div>
            <Spread className="pt-stack-xl">
              <MarkedSpread
                artifact={
                  <ForensicPlate
                    previewUrl={record.previewUrl}
                    fileName={record.fileName}
                    regions={record.regions}
                    annotations={record.annotations}
                  />
                }
                margin={
                  <div className="flex flex-col gap-stack-lg">
                    <FindingLedger annotations={record.annotations} />
                    <SignalTable title="Image readings" signals={record.signals} />
                  </div>
                }
              />
            </Spread>
            <Spread className="py-stack-xl">
              <div className="grid gap-8 md:grid-cols-2">
                <section><SectionHead title="What the image shows" note="Model observations" />
                  <p className="mt-4 leading-relaxed">{record.description || "Visual description was not available for this image."}</p>
                  <ul className="mt-4 list-disc space-y-2 pl-5">{record.observations.map((item, i) => <li key={i}>{item}</li>)}</ul>
                </section>
                <section><SectionHead title="Origin & authenticity" note={`Reverse lookup: ${record.webStatus.replaceAll("_", " ")}`} />
                  <p className="mt-4 leading-relaxed">{record.provenance}</p>
                  <p className="mt-3 text-sm text-ink-black/65">The claim verdict above concerns the recovered text/caption. It does not certify the photograph itself.</p>
                  <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-ink-black/65">{record.limitations.map((item, i) => <li key={i}>{item}</li>)}</ul>
                </section>
              </div>
              <section className="mt-8"><SectionHead title="Text recovered from the image" note="Check against the original" />
                <p className="mt-4 whitespace-pre-wrap font-proof leading-relaxed">{record.extractedText || "No readable text was recovered."}</p>
              </section>
              {record.metadata.length ? <div className="mt-8"><SectionHead title="File details" note="Metadata can be edited" /><dl className="mt-4 grid gap-3 sm:grid-cols-2">{record.metadata.map((item) => <div key={item.key}><dt className="text-sm text-ink-black/50">{item.key}</dt><dd>{item.value}</dd></div>)}</dl></div> : null}
              <div className="mt-10"><ExhibitLedger exhibits={record.exhibits} /></div>
            </Spread>
          </>
        ) : null
      }
    />
  );
}
