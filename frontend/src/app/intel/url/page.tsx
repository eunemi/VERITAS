"use client";

import { useState } from "react";
import { ExhibitLedger } from "@/components/agents/instruments/ExhibitLedger";
import { Determination } from "@/components/agents/shared/Determination";
import { DeskFailure } from "@/components/agents/shared/DeskFailure";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { FindingLedger } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import { isFetchableUrl, SubmissionBench } from "@/components/agents/shared/SubmissionBench";
import { useExamination } from "@/components/agents/shared/useExamination";
import { MarkedSpread, Spread } from "@/components/agents/shared/layout";
import type { VerificationOut } from "@/lib/api/client";
import { DESKS } from "@/lib/desks";
import { DESK_PACE_MS, examineUrl } from "@/lib/services/agentServices";
import type { FactCheckRecord } from "@/lib/types/agents";

const desk = DESKS.url;

function urlHost(value: string): string {
  try {
    return new URL(value).hostname;
  } catch {
    return value;
  }
}

function deskLabel(deskId: string): string {
  return deskId === "fact-check" ? "Fact-check" : deskId.charAt(0).toUpperCase() + deskId.slice(1);
}

function UrlCheckingField({
  value,
  onChange,
  onSubmit,
  working,
  progress,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  working: boolean;
  progress: VerificationOut | null;
}) {
  const trimmed = value.trim();
  const currentDesk = progress?.desks.find((candidate) => candidate.status === "running");
  const filed = progress?.desks.filter((candidate) => candidate.status === "completed").length ?? 0;
  const total = progress?.desks.length ?? 0;
  const completion = total ? Math.round((filed / total) * 100) : 0;

  return (
    <div
      className={`ticked relative overflow-hidden bg-parchment p-5 transition-colors duration-300 sm:p-6 ${working ? "ring-1 ring-gold-ink/45" : ""}`}
    >
      {working ? (
        <span
          aria-hidden
          className="animate-proof-scan pointer-events-none absolute inset-x-0 top-0 z-10 h-px bg-secondary"
        />
      ) : null}
      <div aria-busy={working}>
        <div className="flex items-center justify-between gap-4">
          <label htmlFor="url-to-check" className="font-body-sm text-body-sm text-ink-black/75">
            Public article or page URL
          </label>
          <span className="font-mono-label text-label text-ink-black/45 uppercase">
            {working ? "Live check" : "HTTP / HTTPS"}
          </span>
        </div>
        <div className="relative mt-3 flex items-center gap-3 border-b border-ink-black/30 focus-within:border-secondary">
          <span aria-hidden className="font-mono-label text-label text-secondary">↗</span>
          <input
            id="url-to-check"
            type="url"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onSubmit();
              }
            }}
            disabled={working}
            placeholder="https://example.com/article"
            aria-invalid={!!trimmed && !isFetchableUrl(trimmed)}
            className="min-w-0 flex-1 bg-transparent py-3 text-ink-black placeholder:text-ink-black/35 focus:outline-none"
          />
        </div>
      </div>

      {working ? (
        <div role="status" aria-live="polite" className="mt-4 border-t border-ink-black/12 pt-4">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span
              aria-hidden
              className="motion-safe:animate-spin h-3.5 w-3.5 rounded-full border-2 border-ink-black/15 border-t-secondary"
            />
            <span className="font-mono-label text-label text-secondary uppercase">
              {currentDesk ? `${deskLabel(currentDesk.desk)} desk is checking` : "Opening page"}
            </span>
            {trimmed ? (
              <span className="min-w-0 truncate text-sm text-ink-black/55">{urlHost(trimmed)}</span>
            ) : null}
            {total ? (
              <span className="ml-auto font-mono-label text-label tabular text-ink-black/55">
                {filed}/{total} filed
              </span>
            ) : null}
          </div>
          <div className="mt-3 h-1.5 overflow-hidden bg-ink-black/10" aria-hidden>
            <div
              className={`h-full bg-gold-ink transition-[width] duration-500 ease-out ${total ? "" : "w-1/3 motion-safe:animate-pulse"}`}
              style={total ? { width: `${completion}%` } : undefined}
            />
          </div>
          <p className="mt-2 text-sm text-ink-black/55">
            {currentDesk
              ? "Reading the page and comparing its claims with independent sources."
              : "Connecting to the live examination desk…"}
          </p>
        </div>
      ) : (
        <p className={`mt-3 text-sm ${trimmed && !isFetchableUrl(trimmed) ? "text-secondary" : "text-ink-black/50"}`}>
          {trimmed && !isFetchableUrl(trimmed)
            ? "That does not look like a complete web link."
            : "We only fetch publicly accessible pages."}
        </p>
      )}
    </div>
  );
}

export default function UrlDesk() {
  const [url, setUrl] = useState("");
  const { status, record, error, open, reopen, working, progress } = useExamination<FactCheckRecord>();
  const ready = isFetchableUrl(url);
  const submit = () => {
    if (!ready || working) return;
    void open((options) => examineUrl(url.trim(), options));
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
          note="One public page link at a time"
          hint={ready ? "The page must be publicly reachable. Its claims will be checked against other sources." : "Paste a complete link beginning with https:// or http://."}
          actionLines={["Check", "page"]}
          onSubmit={submit}
          disabled={!ready || working}
        >
          <UrlCheckingField
            value={url}
            onChange={setUrl}
            onSubmit={submit}
            working={working}
            progress={progress}
          />
        </SubmissionBench>
      }
      failure={<DeskFailure error={error} onRetry={reopen} />}
      record={
        record ? (
          <>
            <LedgerBand entries={record.ledger} />
            <Spread className="pt-stack-xl">
              <MarkedSpread
                artifact={<ExhibitLedger claim={record.claim} exhibits={record.exhibits} />}
                margin={<FindingLedger annotations={record.annotations} title="Where they conflict" />}
              />
            </Spread>
            <div className="pt-stack-xl">
              <Determination verdict={record.verdict} annotations={record.annotations} signedBy="URL source desk" exhibits={record.exhibits} />
            </div>
          </>
        ) : null
      }
    />
  );
}
