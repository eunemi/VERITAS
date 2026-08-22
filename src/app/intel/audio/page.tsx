"use client";

import { useState } from "react";
import { AudioSlate } from "@/components/agents/instruments/AudioSlate";
import { Determination } from "@/components/agents/shared/Determination";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { FindingLedger } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import {
  FileField,
  SubmissionBench,
  useArtifact,
} from "@/components/agents/shared/SubmissionBench";
import { MarkedSpread, Spread } from "@/components/agents/shared/layout";
import type { DeskStatus } from "@/components/agents/shared/SlugBar";
import { DESKS } from "@/lib/desks";
import { DESK_LATENCY, examineAudio } from "@/lib/services/agentServices";
import type { AudioRecord } from "@/lib/types/agents";

const desk = DESKS.audio;

export default function AudioDesk() {
  const { artifact, pick } = useArtifact();
  const [status, setStatus] = useState<DeskStatus>("bench");
  const [record, setRecord] = useState<AudioRecord | null>(null);

  async function examine() {
    if (!artifact.file || status === "working") return;
    setStatus("working");
    const result = await examineAudio(artifact.file);
    setRecord(result);
    setStatus("record");
  }

  return (
    <DeskPage
      desk={desk}
      status={status}
      latencyMs={DESK_LATENCY}
      onReopen={() => {
        setRecord(null);
        setStatus("bench");
      }}
      bench={
        <SubmissionBench
          prompt={desk.prompt}
          note="One recording at a time"
          hint="The desk brackets the suspect stretches on the trace, then sets the same numbers against the lines spoken there."
          actionLines={["Examine", "audio"]}
          onSubmit={examine}
          disabled={!artifact.file || status === "working"}
        >
          <FileField
            artifact={artifact}
            onPick={(file) => pick(file)}
            accept="audio/*"
            formats="MP3 · WAV · M4A · OGG"
            kind="audio"
            scanning={status === "working"}
          />
        </SubmissionBench>
      }
      record={
        record ? (
          <>
            <LedgerBand entries={record.ledger} />
            <Spread className="pt-stack-xl">
              <MarkedSpread
                artifact={<AudioSlate record={record} />}
                margin={<FindingLedger annotations={record.annotations} />}
              />
            </Spread>
            <div className="pt-stack-xl">
              <Determination verdict={record.verdict} signedBy="speech forensics desk" />
            </div>
          </>
        ) : null
      }
    />
  );
}
