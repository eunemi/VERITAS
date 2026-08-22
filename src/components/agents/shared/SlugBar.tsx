"use client";

import Link from "next/link";
import { Band, Slug } from "./layout";
import { DESK_ISSUE, type DeskDefinition } from "@/lib/desks";

/** Where the desk is in its work. Drives the slug bar and the page's body. */
export type DeskStatus = "bench" | "working" | "record";

const STATUS_COPY: Record<DeskStatus, string> = {
  bench: "Awaiting submission",
  working: "Examination open",
  record: "Record closed",
};

const STATUS_MARK: Record<DeskStatus, string> = {
  bench: "bg-parchment/30",
  working: "bg-gold-foil animate-pulse",
  record: "bg-secondary",
};

/**
 * The wire slug that runs above every desk — where you are, which file, which
 * issue, and whether the desk is still working. Same strip on all six pages, so
 * moving between desks feels like turning a page rather than loading a new app.
 */
export function SlugBar({ desk, status }: { desk: DeskDefinition; status: DeskStatus }) {
  const divider = <span aria-hidden className="h-3 w-px shrink-0 bg-parchment/25" />;

  return (
    <Band
      className="bg-ink-black text-parchment"
      inner="flex h-9 items-center justify-between gap-gutter"
    >
      <div className="flex min-w-0 items-center gap-3">
        <Link
          href="/intel"
          className="shrink-0 transition-opacity hover:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-foil"
        >
          <Slug>Intelligence Desk</Slug>
        </Link>
        {divider}
        <Slug className="shrink-0 text-parchment/50">Agent {desk.number}</Slug>
        {divider}
        <Slug className="shrink-0 text-parchment/50">{desk.name}</Slug>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <Slug className="tabular hidden text-parchment/40 md:inline">File {desk.file}</Slug>
        <span aria-hidden className="hidden h-3 w-px bg-parchment/25 md:inline-block" />
        <Slug className="tabular hidden text-parchment/40 lg:inline">{DESK_ISSUE}</Slug>
        <span aria-hidden className="hidden h-3 w-px bg-parchment/25 lg:inline-block" />
        <span className="flex items-center gap-2">
          <span aria-hidden className={`h-1.5 w-1.5 ${STATUS_MARK[status]}`} />
          <Slug>{STATUS_COPY[status]}</Slug>
        </span>
      </div>
    </Band>
  );
}
