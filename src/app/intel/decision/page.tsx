"use client";

import Link from "next/link";
import { useState } from "react";
import { ContributionBand } from "@/components/agents/instruments/ContributionBand";
import { Determination } from "@/components/agents/shared/Determination";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { FindingLedger, SignalTable } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import { SubmissionBench } from "@/components/agents/shared/SubmissionBench";
import { MarkedSpread, SectionHead, Slug, Spread } from "@/components/agents/shared/layout";
import type { DeskStatus } from "@/components/agents/shared/SlugBar";
import { DESKS, DESK_ORDER } from "@/lib/desks";
import { DECISION_LATENCY, renderDecision } from "@/lib/services/agentServices";
import type { DecisionRecord } from "@/lib/types/agents";

const desk = DESKS.decision;

/** The five desks that report to the core, in the order they file. */
const REPORTING = DESK_ORDER.slice(0, 5).map((id) => DESKS[id]);

export default function DecisionDesk() {
  const [status, setStatus] = useState<DeskStatus>("bench");
  const [record, setRecord] = useState<DecisionRecord | null>(null);

  async function convene() {
    if (status === "working") return;
    setStatus("working");
    const result = await renderDecision();
    setRecord(result);
    setStatus("record");
  }

  return (
    <DeskPage
      desk={desk}
      status={status}
      latencyMs={DECISION_LATENCY}
      onReopen={() => {
        setRecord(null);
        setStatus("bench");
      }}
      bench={
        <SubmissionBench
          prompt={desk.prompt}
          note="Nothing to submit here"
          hint="The core does not read the artifact. It reads what the five desks filed about it, and weighs each by how much of the artifact that desk could see."
          actionLines={["Convene", "desks"]}
          onSubmit={convene}
          disabled={status === "working"}
        >
          <SectionHead title="Who reports" note="Five desks · in filing order" />
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
        </SubmissionBench>
      }
      record={
        record ? (
          <>
            <LedgerBand entries={record.ledger} />
            <Spread className="pt-stack-xl">
              <MarkedSpread
                artifact={
                  <div className="flex flex-col gap-stack-xl">
                    <ContributionBand contributions={record.contributions} />
                    <SignalTable signals={record.signals} title="How the ruling was tested" />
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
