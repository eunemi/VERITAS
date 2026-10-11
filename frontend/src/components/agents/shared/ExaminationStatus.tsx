import { Slug } from "./layout";
import type { DeskProgressOut, VerificationOut } from "@/lib/api/client";

const DESK_NAMES: Record<string, string> = {
  text: "Text desk",
  image: "Image desk",
  docx: "DOCX desk",
  pdf: "PDF desk",
  url: "URL desk",
  "fact-check": "Fact-check desk",
  decision: "Decision desk",
};

const STATUS_COPY: Record<DeskProgressOut["status"], string> = {
  pending: "Waiting",
  running: "Examining now",
  completed: "Filed",
  failed: "Stopped",
};

const STATUS_MARK: Record<DeskProgressOut["status"], string> = {
  pending: "bg-ink-black/25",
  running: "bg-gold-ink animate-pulse",
  completed: "bg-trust-green",
  failed: "bg-secondary",
};

function deskName(desk: string): string {
  return DESK_NAMES[desk] ?? `${desk} desk`;
}

/** A visible, factual progress readout for an open verification. */
export function ExaminationStatus({
  progress,
  onStop,
}: {
  progress: VerificationOut | null;
  onStop: () => void;
}) {
  if (!progress) {
    return (
      <div className="border-y border-ink-black/20 bg-parchment py-5">
        <div role="status" aria-live="polite" className="flex flex-wrap items-center gap-3">
          <span aria-hidden className="h-2 w-2 animate-pulse bg-gold-ink" />
          <Slug>Examination started</Slug>
          <span className="font-body-sm text-body-sm text-ink-black/65">
            Submitting the artifact and opening the live record…
          </span>
        </div>
        <button type="button" onClick={onStop} className="mt-3 text-sm underline underline-offset-4">
          Stop waiting and edit submission
        </button>
      </div>
    );
  }

  const filed = progress.desks.filter((desk) => desk.status === "completed").length;
  const running = progress.desks.find((desk) => desk.status === "running");
  const total = progress.desks.length;
  const completion = total ? Math.round((filed / total) * 100) : 0;

  return (
    <div role="status" aria-live="polite" className="border-y border-ink-black/20 bg-parchment py-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <span aria-hidden className="h-2 w-2 animate-pulse bg-gold-ink" />
            <Slug>Live examination</Slug>
          </div>
          <p className="mt-2 font-headline-md text-[22px] leading-tight text-ink-black">
            {running ? `${deskName(running.desk)} is examining` : "Preparing the next desk"}
          </p>
        </div>
        <div className="text-right">
          <Slug className="tabular text-ink-black/65">{filed} of {total} desks filed</Slug>
          <p className="mt-1 text-sm text-ink-black/55">{completion}% of the desk roster complete</p>
        </div>
      </div>

      <div className="mt-4 h-2 overflow-hidden bg-ink-black/10" aria-hidden>
        <div className="h-full bg-gold-ink transition-[width] duration-500 ease-out" style={{ width: `${completion}%` }} />
      </div>

      <ul className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {progress.desks.map((desk) => (
          <li key={desk.desk} className="flex items-center gap-2 text-sm">
            <span aria-hidden className={`h-1.5 w-1.5 shrink-0 ${STATUS_MARK[desk.status]}`} />
            <span className="text-ink-black/80">{deskName(desk.desk)}</span>
            <span className="ml-auto text-xs uppercase tracking-wider text-ink-black/50">{STATUS_COPY[desk.status]}</span>
          </li>
        ))}
      </ul>

      <button type="button" onClick={onStop} className="mt-4 text-sm underline underline-offset-4">
        Stop waiting and edit submission
      </button>
    </div>
  );
}
