"use client";

import { useEffect, useState } from "react";
import { Band, Slug } from "./layout";

/** A ruled tick track. Inline so the gradient can read `currentColor`. */
const TICK_TRACK: React.CSSProperties = {
  backgroundImage: "repeating-linear-gradient(to right, currentColor 0 1px, transparent 1px 9px)",
};

/**
 * The desk at work: one line, moving. This replaces a checklist of seven rows
 * with what a wire actually shows — the operation currently running, its place
 * in the sequence, and how far along the pass is on the tick track below.
 */
export function ExaminationTicker({
  stages,
  durationMs = 4200,
}: {
  stages: string[];
  durationMs?: number;
}) {
  const [step, setStep] = useState(0);
  const count = stages.length;

  useEffect(() => {
    const per = Math.max(340, Math.floor(durationMs / count));
    const id = setInterval(() => {
      setStep((current) => (current < count - 1 ? current + 1 : current));
    }, per);
    return () => clearInterval(id);
  }, [count, durationMs]);

  const progress = ((step + 1) / count) * 100;

  return (
    <Band className="bg-ink-black text-parchment" inner="py-stack-md">
      <div
        className="flex flex-wrap items-baseline gap-x-5 gap-y-2"
        aria-live="polite"
        aria-atomic="true"
      >
        <span className="flex items-center gap-2.5">
          <span aria-hidden className="h-1.5 w-1.5 animate-pulse bg-gold-foil" />
          <Slug className="text-gold-foil">Examining</Slug>
        </span>
        <Slug className="tabular text-parchment/40">
          {String(step + 1).padStart(2, "0")} / {String(count).padStart(2, "0")}
        </Slug>
        <p className="font-headline-md text-[22px] leading-none font-normal text-parchment italic">
          {stages[step]}
        </p>
      </div>

      <div className="relative mt-stack-md h-[9px] overflow-hidden">
        <div className="absolute inset-0 text-parchment/25" style={TICK_TRACK} />
        <div
          className="absolute inset-y-0 left-0 text-gold-foil transition-[width] duration-500 ease-out"
          style={{ ...TICK_TRACK, width: `${progress}%` }}
        />
      </div>

      <p className="mt-stack-sm font-body-sm text-body-sm text-parchment/45">
        Next: {step < count - 1 ? stages[step + 1].toLowerCase() : "closing the record"}.
      </p>
    </Band>
  );
}
