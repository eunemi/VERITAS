"use client";

import { useState } from "react";
import { GalleyProof } from "@/components/agents/instruments/GalleyProof";
import { Determination } from "@/components/agents/shared/Determination";
import { DeskFailure } from "@/components/agents/shared/DeskFailure";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { FindingLedger } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import { CopyField, SubmissionBench } from "@/components/agents/shared/SubmissionBench";
import { useExamination } from "@/components/agents/shared/useExamination";
import { MarkedSpread, Slug, Spread } from "@/components/agents/shared/layout";
import { DESKS } from "@/lib/desks";
import { DESK_PACE_MS, examineText } from "@/lib/services/agentServices";
import type { TextRecord } from "@/lib/types/agents";

const desk = DESKS.text;

/** Enough copy for the desk to have something to mark. */
const MINIMUM = 80;

const SAMPLE = `Officials confirmed on Tuesday that the relief fund has already reached 4.1 million households across the northern districts. The figure was first published by the state disaster authority and has since been repeated by three national outlets. A senior official said the transfers were completed within nine days of the announcement, calling the rollout the fastest in the programme's history. Independent auditors have not yet been given access to the disbursement records.`;

export default function TextDesk() {
  const [copy, setCopy] = useState("");
  const { status, record, error, open, reopen, working } = useExamination<TextRecord>();

  const tooShort = copy.trim().length < MINIMUM;

  return (
    <DeskPage
      desk={desk}
      status={status}
      latencyMs={DESK_PACE_MS}
      onReopen={reopen}
      bench={
        <SubmissionBench
          prompt={desk.prompt}
          note="Plain text · a paragraph or more"
          hint={
            tooShort
              ? "The desk needs a paragraph or two to find claims worth checking."
              : "The desk marks the copy in place and answers each mark in the margin."
          }
          actionLines={["Examine", "copy"]}
          onSubmit={() => open(() => examineText(copy))}
          disabled={tooShort || working}
        >
          <CopyField
            value={copy}
            onChange={setCopy}
            scanning={working}
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
            <Spread className="pt-stack-xl">
              <MarkedSpread
                artifact={<GalleyProof copy={record.copy} annotations={record.annotations} />}
                margin={
                  <div className="flex flex-col gap-stack-lg">
                    <FindingLedger annotations={record.annotations} />
                  </div>
                }
              />
            </Spread>
            <div className="pt-stack-xl">
              <Determination verdict={record.verdict} signedBy="linguistic desk" />
            </div>
          </>
        ) : null
      }
    />
  );
}
