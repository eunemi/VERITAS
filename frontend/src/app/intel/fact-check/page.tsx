"use client";

import { useState } from "react";
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
import { DESK_PACE_MS, examineClaim } from "@/lib/services/agentServices";
import type { FactCheckRecord } from "@/lib/types/agents";

const desk = DESKS["fact-check"];

/** A claim needs to be a sentence before it can be checked. */
const MINIMUM = 24;

const SAMPLE =
  "The relief fund reached 4.1 million households within nine days of the announcement.";

export default function FactCheckDesk() {
  const [claim, setClaim] = useState("");
  const { status, record, error, open, reopen, working } =
    useExamination<FactCheckRecord>();

  const tooShort = claim.trim().length < MINIMUM;

  return (
    <DeskPage
      desk={desk}
      status={status}
      latencyMs={DESK_PACE_MS}
      onReopen={reopen}
      bench={
        <SubmissionBench
          prompt={desk.prompt}
          note="One claim · checkable as written"
          hint={
            tooShort
              ? "State it as a single sentence that could be shown right or wrong."
              : "Every exhibit the desk finds is listed, including the ones that disagree."
          }
          actionLines={["Check", "claim"]}
          onSubmit={() => open(() => examineClaim(claim))}
          disabled={tooShort || working}
        >
          <CopyField
            value={claim}
            onChange={setClaim}
            rows={3}
            scanning={working}
            placeholder="One claim, stated plainly. Names, figures and dates help."
          />
          {status === "bench" && !claim ? (
            <button
              type="button"
              onClick={() => setClaim(SAMPLE)}
              className="mt-stack-md cursor-pointer border-b border-ink-black/30 pb-1 transition-colors hover:border-secondary hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              <Slug className="text-ink-black/50">Or set a sample claim on the bench</Slug>
            </button>
          ) : null}
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
                margin={
                  <div className="flex flex-col gap-stack-lg">
                    <FindingLedger annotations={record.annotations} title="Where they conflict" />
                  </div>
                }
              />
            </Spread>
            <div className="pt-stack-xl">
              <Determination verdict={record.verdict} signedBy="source desk" exhibits={record.exhibits} />
            </div>
          </>
        ) : null
      }
    />
  );
}
