"use client";

import { useState } from "react";
import { AudioSlate } from "@/components/agents/instruments/AudioSlate";
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
import { DESK_PACE_MS, examineAudio } from "@/lib/services/agentServices";
import type { AudioRecord } from "@/lib/types/agents";

const desk = DESKS.audio;

export default function AudioDesk() {
  const [url, setUrl] = useState("");
  const { status, record, error, open, reopen, working } = useExamination<AudioRecord>();

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
          note="One recording at a time"
          hint="The desk marks where the recording carries speech, then sets the transcript against it line by line."
          actionLines={["Examine", "audio"]}
          onSubmit={() => open(() => examineAudio(url.trim()))}
          disabled={!ready || working}
        >
          <LinkField
            value={url}
            onChange={setUrl}
            kind="audio"
            formats="MP3 · WAV · M4A · OGG"
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
                artifact={<AudioSlate record={record} />}
                margin={
                  <div className="flex flex-col gap-stack-lg">
                    <FindingLedger annotations={record.annotations} />
                  </div>
                }
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
