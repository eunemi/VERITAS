"use client";

import Link from "next/link";
import { useState } from "react";
import { ContributionBand } from "@/components/agents/instruments/ContributionBand";
import { Determination } from "@/components/agents/shared/Determination";
import { DeskFailure } from "@/components/agents/shared/DeskFailure";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { FindingLedger, SignalTable } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import { CopyField, SubmissionBench } from "@/components/agents/shared/SubmissionBench";
import { useExamination } from "@/components/agents/shared/useExamination";
import { MarkedSpread, SectionHead, Slug, Spread } from "@/components/agents/shared/layout";
import { DESKS } from "@/lib/desks";
import { DECISION_PACE_MS, deliberate } from "@/lib/services/agentServices";
import type { DecisionRecord } from "@/lib/types/agents";

const desk = DESKS.decision;

/** Enough copy for the desks below to have something to file on. */
const MINIMUM = 80;

/**
 * Which desks a paragraph of copy actually opens.
 *
 * Not the whole roster: the desks that open depend on what was submitted, and copy
 * goes to these two. A frame or a recording opens different ones and is signed the
 * same way, from its own desk's bench.
 */
const REPORTING = ["text", "fact-check"].map((id) => DESKS[id]);

export default function DecisionDesk() {
  const [copy, setCopy] = useState("");
  const { status, record, error, open, reopen, working } = useExamination<DecisionRecord>();

  const tooShort = copy.trim().length < MINIMUM;

  return (
    <DeskPage
      desk={desk}
      status={status}
      latencyMs={DECISION_PACE_MS}
      onReopen={reopen}
      bench={
        <SubmissionBench
          prompt={desk.prompt}
          note="Plain text · a paragraph or more"
          hint={
            tooShort
              ? "The core needs something for the desks below it to file on first."
              : "The core does not read the artifact. It reads what the desks filed about it, takes the gravest determination among them, and signs that."
          }
          actionLines={["Convene", "desks"]}
          onSubmit={() => open(async () => (await deliberate(copy)).decision)}
          disabled={tooShort || working}
        >
          <CopyField
            value={copy}
            onChange={setCopy}
            rows={7}
            scanning={working}
            placeholder="Paste the copy the desks should be convened on."
          />

          <div className="mt-stack-lg">
            <SectionHead title="Who reports on copy" note="Two desks · in filing order" />
            <ol className="mt-stack-sm">
              {REPORTING.map((reporting) => (
                <li key={reporting.id} className="border-b border-ink-black/12">
                  <Link
                    href={`/intel/${reporting.id}`}
                    className="group grid grid-cols-[56px_1fr] items-baseline gap-x-4 gap-y-1 py-stack-md transition-colors hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black sm:grid-cols-[56px_1fr_1.4fr]"
                  >
                    <Slug className="tabular text-ink-black/40">{reporting.number}</Slug>
                    <span className="font-headline-md text-[24px] leading-tight font-normal text-ink-black italic group-hover:text-secondary">
                      {reporting.titleLines.join(" ")}
                    </span>
                    <span className="font-body-sm text-body-sm col-start-2 text-ink-black/55 sm:col-start-3">
                      Looks for {reporting.method[1].value.toLowerCase()}
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
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
                artifact={
                  <div className="flex flex-col gap-stack-xl">
                    <ContributionBand contributions={record.contributions} />
                    {record.signals.length ? (
                      <SignalTable signals={record.signals} title="How the ruling was tested" />
                    ) : null}
                  </div>
                }
                margin={
                  <FindingLedger annotations={record.annotations} title="What decided it" />
                }
              />
            </Spread>
            <div className="pt-stack-xl">
              <Determination verdict={record.verdict} signedBy="decision core" />
            </div>
          </>
        ) : null
      }
    />
  );
}
