"use client";

import { useState } from "react";
import { ForensicPlate } from "@/components/agents/instruments/ForensicPlate";
import { Determination } from "@/components/agents/shared/Determination";
import { DeskFailure } from "@/components/agents/shared/DeskFailure";
import { DeskPage } from "@/components/agents/shared/DeskPage";
import { FindingLedger, SignalTable } from "@/components/agents/shared/FindingLedger";
import { LedgerBand } from "@/components/agents/shared/LedgerBand";
import {
  isFetchableUrl,
  LinkField,
  SubmissionBench,
} from "@/components/agents/shared/SubmissionBench";
import { useExamination } from "@/components/agents/shared/useExamination";
import { MarkedSpread, Spread } from "@/components/agents/shared/layout";
import { DESKS } from "@/lib/desks";
import { DESK_PACE_MS, examineImage } from "@/lib/services/agentServices";
import type { ImageRecord } from "@/lib/types/agents";

const desk = DESKS.image;

export default function ImageDesk() {
  const [url, setUrl] = useState("");
  const { status, record, error, open, reopen, working } = useExamination<ImageRecord>();

  const ready = isFetchableUrl(url);

  return (
    <DeskPage
      desk={desk}
      status={status}
      latencyMs={DESK_PACE_MS}
      onReopen={reopen}
      bench={
        <SubmissionBench
          prompt={desk.prompt}
          note="One still image at a time"
          hint="Regions the desk read are ruled onto the frame itself, at the place they were found — not listed away from it."
          actionLines={["Examine", "frame"]}
          onSubmit={() => open(() => examineImage(url.trim()))}
          disabled={!ready || working}
        >
          <LinkField
            value={url}
            onChange={setUrl}
            kind="image"
            formats="JPG · PNG · WEBP · AVIF"
            scanning={working}
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
                    <SignalTable signals={record.signals} title="Readings" />
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
