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
import { MarkedSpread, Spread } from "@/components/agents/shared/layout";
import { DESKS } from "@/lib/desks";
import { DESK_PACE_MS, examineText } from "@/lib/services/agentServices";
import type { TextRecord } from "@/lib/types/agents";

const SETTINGS = {
  docx: {
    accept: ".docx",
    format: "DOCX",
    placeholder: "Your extracted document text will appear here.",
  },
  pdf: {
    accept: ".pdf",
    format: "PDF",
    placeholder: "Your extracted document text will appear here.",
  },
} as const;

/** The DOCX and PDF desks share the text examination after extraction. */
export function DocumentDesk({ kind }: { kind: "docx" | "pdf" }) {
  const desk = DESKS[kind];
  const setting = SETTINGS[kind];
  const [copy, setCopy] = useState("");
  const [uploading, setUploading] = useState(false);
  const { status, record, error, open, reopen, working, progress } = useExamination<TextRecord>();
  const tooShort = copy.trim().length < 8;

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
          note={`${setting.format} only · text is extracted before checking`}
          hint={tooShort ? `Choose a ${setting.format} file to begin.` : "The extracted text is checked against live web evidence."}
          actionLines={["Verify", setting.format]}
          onSubmit={() => open((options) => examineText(copy, options))}
          disabled={tooShort || working || uploading}
        >
          <CopyField
            value={copy}
            onChange={setCopy}
            scanning={working}
            onBusy={setUploading}
            accept={setting.accept}
            uploadLabel={`[ UPLOAD ${setting.format} ]`}
            placeholder={setting.placeholder}
          />
        </SubmissionBench>
      }
      failure={<DeskFailure error={error} onRetry={reopen} />}
      record={
        record ? (
          <>
            <LedgerBand entries={record.ledger} />
            <div className="pt-stack-xl"><Determination verdict={record.verdict} signedBy={`${setting.format} text desk`} /></div>
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
