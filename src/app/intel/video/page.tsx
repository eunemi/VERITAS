"use client";

import { useState } from "react";
import { Filmstrip } from "@/components/agents/instruments/Filmstrip";
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
import { DESK_LATENCY, examineVideo } from "@/lib/services/agentServices";
import type { VideoRecord } from "@/lib/types/agents";

const desk = DESKS.video;

export default function VideoDesk() {
  const { artifact, pick } = useArtifact();
  const [status, setStatus] = useState<DeskStatus>("bench");
  const [record, setRecord] = useState<VideoRecord | null>(null);

  async function examine() {
    if (!artifact.file || status === "working") return;
    setStatus("working");
    const result = await examineVideo(artifact.file);
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
          note="One clip at a time"
          hint="The desk reads the footage across time. Frames that break continuity are ruled on the strip and set at their true place in the running order."
          actionLines={["Examine", "footage"]}
          onSubmit={examine}
          disabled={!artifact.file || status === "working"}
        >
          <FileField
            artifact={artifact}
            onPick={(file) => pick(file)}
            accept="video/*"
            formats="MP4 · MOV · WEBM · MKV"
            kind="video"
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
                artifact={<Filmstrip record={record} />}
                margin={<FindingLedger annotations={record.annotations} />}
              />
            </Spread>
            <div className="pt-stack-xl">
              <Determination verdict={record.verdict} signedBy="temporal forensics desk" />
            </div>
          </>
        ) : null
      }
    />
  );
}
