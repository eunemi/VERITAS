"use client";

import { useState } from "react";
import { GalleyProof } from "@/components/agents/instruments/GalleyProof";
import { ExhibitLedger } from "@/components/agents/instruments/ExhibitLedger";
import { Determination } from "@/components/agents/shared/Determination";
import { DeskFailure } from "@/components/agents/shared/DeskFailure";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { FindingLedger, SignalTable } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import { CopyField, SubmissionBench } from "@/components/agents/shared/SubmissionBench";
import { useExamination } from "@/components/agents/shared/useExamination";
import { MarkedSpread, Slug, Spread } from "@/components/agents/shared/layout";
import { DESKS } from "@/lib/desks";
import { DESK_PACE_MS, examineText } from "@/lib/services/agentServices";
import type { TextRecord } from "@/lib/types/agents";

const desk = DESKS.text;

/** Enough copy for the desk to have something to mark. */
const MINIMUM = 8;

const SAMPLE = "Chandrayaan-3 successfully landed on the Moon on 23 August 2023.";

export default function TextDesk() {
  const [copy, setCopy] = useState("");
  const [uploading, setUploading] = useState(false);
  const { status, record, error, open, reopen, working, progress } = useExamination<TextRecord>();

  const tooShort = copy.trim().length < MINIMUM;

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
          note="Headlines · news · Hindi, English & Hinglish"
          hint={
            tooShort
              ? "Enter a claim or news report with at least 8 characters."
              : "Claims are checked against live web evidence. Include dates and locations when available."
          }
          actionLines={["Verify", "news"]}
          onSubmit={() => open((options) => examineText(copy, options))}
          disabled={tooShort || working || uploading}
        >
          <CopyField
            value={copy}
            onChange={setCopy}
            scanning={working}
            onBusy={setUploading}
            allowUpload
            accept=".pdf,.docx,.md,.txt"
            uploadLabel="[ UPLOAD TEXT / DOC ]"
            placeholder="Paste the article, statement or caption to be examined."
          />
          {status === "bench" && !copy ? (
            <button
              type="button"
              onClick={() => setCopy(SAMPLE)}
              className="mt-stack-md cursor-pointer border-b border-ink-black/30 pb-1 transition-colors hover:border-secondary hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              <Slug className="text-ink-black/50">Or set a sample dispatch on the bench</Slug>
            </button>
          ) : null}
        </SubmissionBench>
      }
      failure={<DeskFailure error={error} onRetry={reopen} />}
      record={
        record ? (
          <>
            <LedgerBand entries={record.ledger} />
            <div className="pt-stack-xl"><Determination verdict={record.verdict} signedBy="live fact-check desk" /></div>
            <Spread className="pt-stack-xl">
              <MarkedSpread
                artifact={<GalleyProof copy={record.copy} annotations={record.annotations} />}
                margin={
                  <div className="flex flex-col gap-stack-lg">
                    <FindingLedger annotations={record.annotations} />
                    <SignalTable title="Verification coverage" signals={record.signals} />
                  </div>
                }
              />
            </Spread>
            <Spread className="py-stack-xl"><ExhibitLedger exhibits={record.exhibits} /></Spread>
          </>
        ) : null
      }
    />
  );
}
