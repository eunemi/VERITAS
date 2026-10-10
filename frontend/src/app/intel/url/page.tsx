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
import { DESKS } from "@/lib/desks";
import { DESK_PACE_MS, examineUrl } from "@/lib/services/agentServices";
import type { FactCheckRecord } from "@/lib/types/agents";

const desk = DESKS.url;

export default function UrlDesk() {
  const [url, setUrl] = useState("");
  const { status, record, error, open, reopen, working, progress } = useExamination<FactCheckRecord>();
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
          note="One public page link at a time"
          hint={ready ? "The page must be publicly reachable. Its claims will be checked against other sources." : "Paste a complete link beginning with https:// or http://."}
          actionLines={["Check", "page"]}
          onSubmit={() => open((options) => examineUrl(url.trim(), options))}
          disabled={!ready || working}
        >
          <div className="ticked bg-parchment p-5 sm:p-6">
            <label htmlFor="url-to-check" className="font-body-sm text-body-sm block text-ink-black/75">Public article or page URL</label>
            <input
              id="url-to-check"
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              disabled={working}
              placeholder="https://example.com/article"
              aria-invalid={!!url.trim() && !ready}
              className="mt-3 w-full border-b border-ink-black/30 bg-transparent py-3 text-ink-black placeholder:text-ink-black/35 focus:border-secondary focus:outline-none"
            />
            <p className={`mt-3 text-sm ${url.trim() && !ready ? "text-secondary" : "text-ink-black/50"}`}>
              {url.trim() && !ready ? "That does not look like a complete web link." : "We only fetch publicly accessible pages."}
            </p>
          </div>
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
              <Determination verdict={record.verdict} signedBy="URL source desk" exhibits={record.exhibits} />
            </div>
          </>
        ) : null
      }
    />
  );
}
