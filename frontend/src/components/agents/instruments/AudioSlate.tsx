import { SectionHead, Slug } from "../shared/layout";
import type { AudioRecord } from "@/lib/types/agents";

/**
 * The slate.
 *
 * The recording drawn as a level trace with the voiced stretches marked where they
 * actually occur, then the transcript underneath. The marks say where the desk could
 * hear speech, not where it found a problem — a bracket in an adverse colour over a
 * stretch nobody objected to would read as an accusation. Lines the desk annotated
 * carry the note's number and are ruled in the margin; nothing else is.
 */
export function AudioSlate({ record }: { record: AudioRecord }) {
  const { envelope, voicedSpans, transcript, duration, fileName, language } = record;
  const count = envelope.length;

  const voicedAt = (index: number) => {
    const at = index / count;
    return voicedSpans.some((span) => at >= span.start && at <= span.end);
  };

  return (
    <section>
      <SectionHead
        title="Analyzed Audio"
        note={`${duration} · ${String(voicedSpans.length).padStart(2, "0")} voiced stretches · ${language}`}
      />

      <figure className="mt-stack-md">
        {/* Brackets sit above the trace so they mark position, not amplitude. */}
        <div className="relative h-4">
          {voicedSpans.map((span, index) => (
            <span
              key={`${span.start}-${index}`}
              className="absolute bottom-0 border-x border-t border-ink-black/45"
              style={{
                left: `${span.start * 100}%`,
                width: `${(span.end - span.start) * 100}%`,
                height: "8px",
              }}
            />
          ))}
        </div>

        <div className="ticked relative flex h-[150px] items-end gap-px bg-ink-black px-1 text-parchment/20">
          {envelope.map((level, index) => (
            <span
              key={index}
              className={`min-w-px flex-1 ${voicedAt(index) ? "bg-parchment/80" : "bg-parchment/25"}`}
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
          <Slug className="tabular text-ink-black/35">0:00</Slug>
          <Slug className="text-ink-black/35">
            Bright bars carry speech
          </Slug>
          <Slug className="tabular text-ink-black/35">{duration}</Slug>
        </figcaption>
      </figure>

      <div className="mt-stack-lg">
        <SectionHead title="Extracted Transcript" note={`${fileName} · timecoded`} />
        <ol className="mt-stack-sm">
          {transcript.map((segment, index) => (
            <li
              key={`${segment.timecode}-${index}`}
              className="grid grid-cols-[58px_1fr] gap-x-4 border-b border-ink-black/12 py-stack-sm"
            >
              <Slug className="tabular pt-1.5 text-ink-black/40">{segment.timecode}</Slug>
              <div
                className={`border-l-2 pl-4 ${
                  segment.flagged ? "border-secondary" : "border-transparent"
                }`}
              >
                <p className="font-proof text-proof max-w-[62ch] text-ink-black">
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
        <p className="font-body-sm text-body-sm mt-stack-sm max-w-[62ch] text-ink-black/55">
          The transcript is not separated by speaker. Nothing in the examination tells
          one voice from another, so no line here is attributed to anyone.
        </p>
      </div>
    </section>
  );
}
