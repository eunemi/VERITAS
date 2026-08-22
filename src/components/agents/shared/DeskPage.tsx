"use client";

import { Colophon } from "./Colophon";
import { DeskMasthead } from "./DeskMasthead";
import { DeskNavigation } from "./DeskNavigation";
import { ExaminationTicker } from "./ExaminationTicker";
import { SlugBar, type DeskStatus } from "./SlugBar";
import { Slug, Spread } from "./layout";
import type { DeskDefinition } from "@/lib/desks";

/**
 * The shape every desk shares: slug, masthead, then either the bench or the
 * record, then the colophon and the way through to the next desk. Holding this in
 * one place is what makes the six desks feel like six pages of one publication.
 */
export function DeskPage({
  desk,
  status,
  bench,
  record,
  onReopen,
  latencyMs,
}: {
  desk: DeskDefinition;
  status: DeskStatus;
  /** The submission bench. Shown until the record is closed. */
  bench: React.ReactNode;
  /** The closed record. Shown only when there is one. */
  record?: React.ReactNode;
  onReopen: () => void;
  /** How long the desk takes, so the ticker paces itself to the real wait. */
  latencyMs?: number;
}) {
  return (
    <main className="min-h-screen bg-background">
      <SlugBar desk={desk} status={status} />

      <Spread>
        <DeskMasthead desk={desk} />
      </Spread>

      {status === "working" ? (
        <ExaminationTicker stages={desk.stages} durationMs={latencyMs} />
      ) : null}

      {status === "record" ? (
        record
      ) : (
        <Spread className={status === "working" ? "pt-stack-xl" : ""}>{bench}</Spread>
      )}

      {status === "record" ? (
        <Spread>
          <div className="flex flex-wrap items-baseline justify-between gap-4 border-t border-ink-black/15 py-stack-lg">
            <p className="font-body-sm text-body-sm max-w-[52ch] text-ink-black/55">
              The record stands as filed. Sending another artifact opens a new file at this
              desk and leaves this one behind.
            </p>
            <button
              type="button"
              onClick={onReopen}
              className="cursor-pointer border-b-2 border-secondary pb-1 transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              <Slug className="text-secondary">Send another artifact</Slug>
            </button>
          </div>
        </Spread>
      ) : null}

      <Spread>
        <Colophon desk={desk} />
      </Spread>

      <DeskNavigation desk={desk} />
    </main>
  );
}
