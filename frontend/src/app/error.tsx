"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Band, Slug, Spread } from "@/components/agents/shared/layout";
import { DESK_ISSUE } from "@/lib/desks";

/**
 * The route error boundary.
 *
 * The app had none, so a throw anywhere below the root layout fell through to the
 * framework's own screen. Next 16 passes `retry`, which re-fetches and re-renders
 * the segment — `reset` only clears the boundary without re-fetching, and is the
 * wrong call here (see node_modules/next/dist/docs/01-app/03-api-reference/
 * 03-file-conventions/error.md).
 *
 * The digest is printed because it is the only thing that ties what the reader saw
 * to the line in the server log — a paper that asks for traceability should give a
 * reader the reference number.
 */
export default function DeskError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="min-h-screen bg-background">
      <Band
        className="bg-ink-black text-parchment"
        inner="flex h-9 items-center justify-between gap-gutter"
      >
        <span className="flex items-center gap-3">
          <Slug className="font-bold">Stop press</Slug>
          <span aria-hidden className="h-3 w-px bg-parchment/25" />
          <Slug className="text-parchment/50">The page failed to set</Slug>
        </span>
        <Slug className="tabular hidden text-parchment/40 md:inline">Issue {DESK_ISSUE}</Slug>
      </Band>

      <Spread className="pt-stack-xl pb-stack-lg">
        <Slug className="text-alert-crimson">Press halted</Slug>
        <h1 className="font-masthead mt-stack-sm max-w-[15ch] text-[clamp(44px,8vw,96px)] leading-[0.92] font-black tracking-[-0.025em] text-ink-black">
          <span className="block">This page</span>
          <span className="block pl-[0.05em] font-normal italic">did not come off.</span>
        </h1>
        <p className="font-headline-md mt-stack-md max-w-[46ch] text-[22px] leading-[1.35] font-normal text-ink-black/70 italic">
          Something failed while the page was being rendered. Nothing you submitted was sent
          anywhere, and running it again is safe.
        </p>
      </Spread>

      <Spread className="pb-stack-xl">
        <dl className="border-t-2 border-ink-black">
          <div className="grid gap-2 border-b border-ink-black/12 py-stack-sm sm:grid-cols-12 sm:items-baseline sm:gap-gutter">
            <dt className="sm:col-span-3">
              <Slug className="text-ink-black/40">Reported as</Slug>
            </dt>
            <dd className="font-body-sm text-body-sm text-ink-black/70 sm:col-span-9">
              {error.message || "An unspecified rendering error"}
            </dd>
          </div>
          {error.digest ? (
            <div className="grid gap-2 border-b border-ink-black/12 py-stack-sm sm:grid-cols-12 sm:items-baseline sm:gap-gutter">
              <dt className="sm:col-span-3">
                <Slug className="text-ink-black/40">Log reference</Slug>
              </dt>
              <dd className="tabular font-mono-label text-[13px] leading-none text-ink-black/70 sm:col-span-9">
                {error.digest}
              </dd>
            </div>
          ) : null}
        </dl>

        <div className="mt-stack-lg flex flex-wrap items-center gap-x-stack-lg gap-y-stack-sm">
          <button
            type="button"
            onClick={() => retry()}
            className="cursor-pointer bg-ink-black px-6 py-3.5 transition-colors hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            <Slug className="text-parchment">Set the page again</Slug>
          </button>
          <Link
            href="/"
            className="border-b-2 border-secondary pb-1 transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            <Slug className="text-ink-black">Back to the front page</Slug>
          </Link>
        </div>
      </Spread>
    </main>
  );
}
