"use client";

import { useEffect, useRef, useState } from "react";
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

const MAX_DOCUMENT_BYTES = 50 * 1024 * 1024;

function isAbortError(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === "AbortError";
}

/** The DOCX and PDF desks share the text examination after extraction. */
export function DocumentDesk({ kind }: { kind: "docx" | "pdf" }) {
  const desk = DESKS[kind];
  const setting = SETTINGS[kind];
  const [copy, setCopy] = useState("");
  const [fileName, setFileName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const extractionController = useRef<AbortController | null>(null);
  const { status, record, error, open, reopen, working, progress } = useExamination<TextRecord>();
  const tooShort = copy.trim().length < 8;

  useEffect(
    () => () => {
      extractionController.current?.abort();
      extractionController.current = null;
    },
    [],
  );

  const clearDocument = () => {
    extractionController.current?.abort();
    extractionController.current = null;
    setUploading(false);
    setCopy("");
    setFileName("");
    setUploadError(null);
  };

  const handleFileUpload = async (file: File) => {
    if (!file || uploading || working) return;

    // A replacement is a new submission, even when it is invalid. Clear the old
    // extracted copy before validating so it cannot be submitted by accident.
    setCopy("");
    setFileName("");
    setUploadError(null);
    if (!file.name.toLowerCase().endsWith(setting.accept)) {
      setUploadError(`Choose a ${setting.format} file.`);
      return;
    }
    if (file.size === 0) {
      setUploadError(`This ${setting.format} file is empty. Choose a file with readable text.`);
      return;
    }
    if (file.size > MAX_DOCUMENT_BYTES) {
      setUploadError(`This ${setting.format} file must be 50 MB or smaller.`);
      return;
    }

    extractionController.current?.abort();
    const controller = new AbortController();
    extractionController.current = controller;
    setUploading(true);
    try {
      const extracted = await extractTextFromFile(file, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (!extracted.trim()) {
        setUploadError(`This ${setting.format} file contains no readable text.`);
        return;
      }
      setCopy(extracted);
      setFileName(file.name);
    } catch (cause) {
      if (controller.signal.aborted || isAbortError(cause)) return;
      setUploadError(cause instanceof Error ? cause.message : `Unable to read this ${setting.format} file.`);
    } finally {
      if (extractionController.current === controller) {
        extractionController.current = null;
        setUploading(false);
      }
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
              {uploading ? (
                <button
                  type="button"
                  onClick={clearDocument}
                  className="mt-3 cursor-pointer border-b border-ink-black/40 pb-0.5 text-sm text-ink-black/65 hover:border-secondary hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black"
                >
                  Cancel reading
                </button>
              ) : fileName ? (
                <div className="mt-3 flex flex-wrap items-baseline justify-center gap-3">
                  <p className="max-w-[34ch] break-words text-sm text-ink-black/65">{fileName}</p>
                  <button
                    type="button"
                    onClick={clearDocument}
                    className="cursor-pointer border-b border-ink-black/40 pb-0.5 text-sm text-ink-black/65 hover:border-secondary hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black"
                  >
                    Clear the bench
                  </button>
                </div>
              ) : null}
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
            <div className="pt-stack-xl"><Determination verdict={record.verdict} annotations={record.annotations} signedBy={`${setting.format} text desk`} /></div>
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
