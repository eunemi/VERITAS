import React from "react";
import Link from "next/link";
import { Band, Slug, Spread } from "@/components/agents/shared/layout";
import { DESK_ISSUE } from "@/lib/desks";

/**
 * A statement of the paper: the privacy note and the terms.
 *
 * Both are set the same way — masthead, standfirst, numbered clauses, colophon —
 * because both are documents a reader may need to cite. The clause numbers are the
 * one place numbering earns itself on this site: a clause is referred to by its
 * number, so the figure carries information rather than decorating a list.
 */

export interface Clause {
  heading: string;
  body: React.ReactNode;
}

export function StatementPage({
  kicker,
  titleLines,
  standfirst,
  clauses,
  foot,
}: {
  /** Small label above the masthead, e.g. "Privacy". */
  kicker: string;
  /** One array entry per printed line. The second line is set in italic. */
  titleLines: [string, string];
  standfirst: string;
  clauses: Clause[];
  /** The closing paragraph, in the colophon's small type. */
  foot: React.ReactNode;
}) {
  return (
    <main className="min-h-screen bg-background">
      <Band
        className="bg-ink-black text-parchment"
        inner="flex h-9 items-center justify-between gap-gutter"
      >
        <span className="flex items-center gap-3">
          <Slug className="font-bold">{kicker}</Slug>
          <span aria-hidden className="h-3 w-px bg-parchment/25" />
          <Slug className="text-parchment/50">A statement of the paper</Slug>
        </span>
        <Slug className="tabular hidden text-parchment/40 md:inline">Issue {DESK_ISSUE}</Slug>
      </Band>

      <Spread className="pt-stack-xl pb-stack-lg">
        <Slug className="text-secondary">
          {clauses.length < 10 ? `0${clauses.length}` : clauses.length} clauses · In force{" "}
          {DESK_ISSUE}
        </Slug>
        <h1 className="font-masthead mt-stack-sm max-w-[16ch] text-[clamp(40px,7vw,88px)] leading-[0.94] font-black tracking-[-0.025em] text-ink-black">
          <span className="block">{titleLines[0]}</span>
          <span className="block pl-[0.05em] font-normal italic">{titleLines[1]}</span>
        </h1>
        <p className="font-headline-md mt-stack-md max-w-[48ch] text-[22px] leading-[1.35] font-normal text-ink-black/70 italic">
          {standfirst}
        </p>
      </Spread>

      <Spread className="pb-stack-xl">
        <ol className="border-t-2 border-ink-black">
          {clauses.map((clause, index) => (
            <li
              key={clause.heading}
              className="grid gap-stack-sm border-b border-ink-black/12 py-stack-md lg:grid-cols-12 lg:gap-gutter"
            >
              <div className="lg:col-span-3">
                <span className="font-masthead tabular block text-[30px] leading-none font-black tracking-[-0.03em] text-ink-black/20">
                  {index < 9 ? `0${index + 1}` : index + 1}
                </span>
                <h2 className="font-headline-md mt-2.5 text-[22px] leading-tight font-bold text-ink-black">
                  {clause.heading}
                </h2>
              </div>
              <div className="font-body-md text-body-md max-w-[68ch] text-ink-black/70 lg:col-span-8 lg:col-start-4">
                {clause.body}
              </div>
            </li>
          ))}
        </ol>

        <div className="pt-stack-md">
          <Slug className="text-ink-black/40">Colophon</Slug>
          <p className="font-body-sm mt-2.5 max-w-[86ch] text-[13px] leading-[21px] text-ink-black/50">
            {foot}
          </p>
          <p className="mt-stack-md">
            <Link
              href="/intel"
              className="inline-flex items-center gap-2 border-b-2 border-secondary pb-1 transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              <Slug className="text-ink-black">See how the desks read</Slug>
              <span aria-hidden className="text-[13px] leading-none text-secondary">
                &rarr;
              </span>
            </Link>
          </p>
        </div>
      </Spread>
    </main>
  );
}
