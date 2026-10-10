"use client";

import { useState } from "react";
import { GalleyProof } from "@/components/agents/instruments/GalleyProof";
import { ExhibitLedger } from "@/components/agents/instruments/ExhibitLedger";
import { Determination } from "@/components/agents/shared/Determination";
import { DeskFailure } from "@/components/agents/shared/DeskFailure";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { FindingLedger, SignalTable } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import { SubmissionBench } from "@/components/agents/shared/SubmissionBench";
import { useExamination } from "@/components/agents/shared/useExamination";
import { MarkedSpread, Spread } from "@/components/agents/shared/layout";
import { extractTextFromFile } from "@/lib/api/client";
import { DESKS } from "@/lib/desks";
import { DESK_PACE_MS, examineText } from "@/lib/services/agentServices";
import type { TextRecord } from "@/lib/types/agents";

const SETTINGS = {
  docx: {
    accept: ".docx",
    format: "DOCX",
  },
  pdf: {
    accept: ".pdf",
    format: "PDF",
  },
} as const;

/** The DOCX and PDF desks share the text examination after extraction. */
export function DocumentDesk({ kind }: { kind: "docx" | "pdf" }) {
  const desk = DESKS[kind];
  const setting = SETTINGS[kind];
  const [copy, setCopy] = useState("");
  const [fileName, setFileName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const { status, record, error, open, reopen, working, progress } = useExamination<TextRecord>();
  const tooShort = copy.trim().length < 8;

  const handleFileUpload = async (file: File) => {
    if (!file || uploading || working) return;
    if (!file.name.toLowerCase().endsWith(setting.accept)) {
      setUploadError(`Choose a ${setting.format} file.`);
      setFileName("");
      return;
    }
    setUploading(true);
    setUploadError(null);
    setFileName(file.name);
    try {
      setCopy(await extractTextFromFile(file));
    } catch (cause) {
      setCopy("");
      setFileName("");
      setUploadError(cause instanceof Error ? cause.message : `Unable to read this ${setting.format} file.`);
    } finally {
      setUploading(false);
    }
  };

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
          note={`${setting.format} upload only`}
          hint={uploading ? `Reading your ${setting.format} file…` : tooShort ? `Choose a ${setting.format} file to begin.` : "File ready. Start the verification when you are ready."}
          actionLines={["Verify", setting.format]}
          onSubmit={() => open((options) => examineText(copy, options))}
          disabled={tooShort || working || uploading}
        >
          <div className="ticked relative flex min-h-48 items-center justify-center overflow-hidden bg-parchment p-6">
            <input
              id={`${kind}-file-upload`}
              type="file"
              accept={setting.accept}
              className="sr-only"
              disabled={uploading || working}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleFileUpload(file);
                event.target.value = "";
              }}
            />
            <div className="text-center">
              <label htmlFor={`${kind}-file-upload`} className="inline-flex min-h-12 cursor-pointer items-center justify-center border border-ink-black px-6 py-3 font-mono-label text-mono-label text-ink-black transition-colors hover:bg-ink-black hover:text-parchment focus-within:outline-2 focus-within:outline-offset-4 focus-within:outline-ink-black">
                {uploading ? `Reading ${setting.format}…` : fileName ? `Replace ${setting.format} file` : `Choose ${setting.format} file`}
              </label>
              {fileName ? <p className="mt-3 max-w-[34ch] break-words text-sm text-ink-black/65">{fileName}</p> : null}
              {uploadError ? <p role="alert" className="mt-3 max-w-[42ch] text-sm leading-6 text-secondary">{uploadError}</p> : null}
            </div>
          </div>
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
