import { SectionHead, Slug } from "../shared/layout";
import type { AudioRecord } from "@/lib/types/agents";

/**
 * The slate.
 *
 * The recording drawn as a level trace, with the two flagged stretches bracketed
 * and numbered where they actually occur, then the transcript underneath with the
 * same numbers set against the lines that were spoken there. Reading down the
 * page moves from where to what was said.
 */
export function AudioSlate({ record }: { record: AudioRecord }) {
  const { envelope, flaggedSpans, transcript, duration, fileName } = record;
  const count = envelope.length;

  const flaggedAt = (index: number) => {
    const at = index / count;
    return flaggedSpans.some((span) => at >= span.start && at <= span.end);
  };

  return (
    <section>
      <SectionHead
        title="Slate"
        note={`${duration} · ${String(flaggedSpans.length).padStart(2, "0")} spans flagged`}
      />

      <figure className="mt-stack-md">
        {/* Brackets sit above the trace so they mark position, not amplitude. */}
        <div className="relative h-6">
          {flaggedSpans.map((span) => (
            <span
              key={span.ref}
              className="absolute bottom-0 border-x-2 border-t-2 border-secondary"
              style={{
                left: `${span.start * 100}%`,
                width: `${(span.end - span.start) * 100}%`,
                height: "10px",
              }}
            >
              <span className="font-mono-label absolute -top-5 left-1/2 -translate-x-1/2 text-[11px] font-bold text-secondary">
                {span.ref}
              </span>
            </span>
          ))}
        </div>

        <div className="ticked relative flex h-[150px] items-end gap-px bg-ink-black px-1 text-parchment/20">
          {envelope.map((level, index) => (
            <span
              key={index}
              className={`min-w-px flex-1 ${flaggedAt(index) ? "bg-secondary" : "bg-parchment/40"}`}
              style={{ height: `${Math.round(level * 100)}%` }}
            />
          ))}
        </div>

        <div className="relative mt-2 h-3 border-t border-ink-black/20">
          {[0, 25, 50, 75, 100].map((mark) => (
            <span
              key={mark}
              className="absolute top-0 h-2 w-px bg-ink-black/25"
              style={{ left: `${mark}%` }}
            />
          ))}
        </div>

        <figcaption className="mt-1.5 flex flex-wrap items-baseline justify-between gap-3">
          <Slug className="tabular text-ink-black/35">00:00</Slug>
          <Slug className="text-ink-black/35">{fileName}</Slug>
          <Slug className="tabular text-ink-black/35">{duration}</Slug>
        </figcaption>
      </figure>

      <div className="mt-stack-lg">
        <SectionHead title="Transcript" note="Speaker-separated · timecoded" />
        <ol className="mt-stack-sm">
          {transcript.map((segment) => (
            <li
              key={`${segment.timecode}-${segment.speaker}`}
              className="grid grid-cols-[58px_1fr] gap-x-4 border-b border-ink-black/12 py-stack-sm"
            >
              <Slug className="tabular pt-1.5 text-ink-black/40">{segment.timecode}</Slug>
              <div
                className={`border-l-2 pl-4 ${
                  segment.flagged ? "border-secondary" : "border-transparent"
                }`}
              >
                <Slug className={segment.flagged ? "text-secondary" : "text-ink-black/40"}>
                  {segment.speaker}
                </Slug>
                <p className="font-proof text-proof mt-1.5 max-w-[62ch] text-ink-black">
                  {segment.line}
                  {segment.ref ? (
                    <sup className="font-mono-label ml-1 align-super text-[11px] font-bold text-secondary">
                      {segment.ref}
                    </sup>
                  ) : null}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
