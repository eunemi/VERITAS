"use client";

import { Colophon } from "./Colophon";
import { DeskMasthead } from "./DeskMasthead";
import { DeskNavigation } from "./DeskNavigation";
import { ExaminationTicker } from "./ExaminationTicker";
import { SlugBar, type DeskStatus } from "./SlugBar";
import { Slug, Spread } from "./layout";
import type { DeskDefinition } from "@/lib/desks";

/**
 * The shape every desk shares: slug, masthead, then the bench, the record or the
 * reason there is no record, then the colophon and the way through to the next desk.
 * Holding this in one place is what makes the six desks feel like six pages of one
 * publication.
 */
export function DeskPage({
  desk,
  status,
  bench,
  record,
  failure,
  onReopen,
  latencyMs,
}: {
  desk: DeskDefinition;
  status: DeskStatus;
  /** The submission bench. Shown until the record is closed. */
  bench: React.ReactNode;
  /** The closed record. Shown only when there is one. */
  record?: React.ReactNode;
  /** Why no record was filed. Shown in its place, never alongside it. */
  failure?: React.ReactNode;
  onReopen: () => void;
  /** Pacing for the ticker's stages while the desks work. */
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

      {status === "record" ? record : null}
      {status === "failed" ? <Spread>{failure}</Spread> : null}
      {status === "bench" || status === "working" ? (
        <Spread className={status === "working" ? "pt-stack-xl" : ""}>{bench}</Spread>
      ) : null}

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
        {/* A desk with no bench is a desk that is not open, and the colophon should
            not tell a reader what submitting does. */}
        <Colophon desk={desk} open={bench !== null} />
      </Spread>

      <DeskNavigation desk={desk} />
    </main>
  );
}
