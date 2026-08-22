"use client";

import { useState } from "react";
import { ForensicPlate } from "@/components/agents/instruments/ForensicPlate";
import { Determination } from "@/components/agents/shared/Determination";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { FindingLedger, SignalTable } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import {
  FileField,
  SubmissionBench,
  useArtifact,
} from "@/components/agents/shared/SubmissionBench";
import { MarkedSpread, Spread } from "@/components/agents/shared/layout";
import type { DeskStatus } from "@/components/agents/shared/SlugBar";
import { DESKS } from "@/lib/desks";
import { DESK_LATENCY, examineImage } from "@/lib/services/agentServices";
import type { ImageRecord } from "@/lib/types/agents";

const desk = DESKS.image;

export default function ImageDesk() {
  const { artifact, pick } = useArtifact();
  const [status, setStatus] = useState<DeskStatus>("bench");
  const [record, setRecord] = useState<ImageRecord | null>(null);

  async function examine() {
    if (!artifact.file || status === "working") return;
    setStatus("working");
    const result = await examineImage(artifact.file, artifact.url);
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
          note="One still image at a time"
          hint="Flagged regions are ruled onto the frame itself, at the place they were found — not listed away from it."
          actionLines={["Examine", "frame"]}
          onSubmit={examine}
          disabled={!artifact.file || status === "working"}
        >
          <FileField
            artifact={artifact}
            onPick={(file) => pick(file, true)}
            accept="image/*"
            formats="JPG · PNG · WEBP · AVIF"
            kind="image"
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
                artifact={
                  <ForensicPlate
                    previewUrl={record.previewUrl}
                    fileName={record.fileName}
                    regions={record.regions}
                    annotations={record.annotations}
                  />
                }
                margin={
                  <div className="flex flex-col gap-stack-lg">
                    <FindingLedger annotations={record.annotations} />
                    <SignalTable signals={record.channels} title="Channel residuals" />
                  </div>
                }
              />
            </Spread>
            <div className="pt-stack-xl">
              <Determination verdict={record.verdict} signedBy="visual forensics desk" />
            </div>
          </>
        ) : null
      }
    />
  );
}
