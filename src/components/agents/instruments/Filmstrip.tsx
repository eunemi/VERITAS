import { SectionHead, Slug } from "../shared/layout";
import { TONE_RULE, TONE_TEXT, toneOf, type VideoRecord } from "@/lib/types/agents";

/**
 * The strip.
 *
 * Footage read as a contact sheet: the frames the desk actually pulled, in order,
 * with the flagged ones ruled and numbered. Below it the scenes are laid out at
 * their true length, so a finding in a nine-second scene doesn't read as loudly
 * as one in a forty-second scene.
 */
export function Filmstrip({ record }: { record: VideoRecord }) {
  const { frames, scenes, runtime, fileName } = record;
  const flagged = frames.filter((frame) => frame.ref !== null).length;

  const sprocketStrip = (
    <div aria-hidden className="bg-ink-black py-1.5">
      <div className="sprockets mx-2 h-2 text-background/75" />
    </div>
  );

  return (
    <section>
      <SectionHead
        title="Strip"
        note={`${runtime} · ${String(flagged).padStart(2, "0")} frames flagged`}
      />

      <figure className="mt-stack-md">
        <div className="ticked bg-ink-black text-parchment/20">
          {sprocketStrip}
          <div className="grid grid-cols-4 gap-px bg-parchment/10 sm:grid-cols-6">
            {frames.map((frame) => (
              <div
                key={frame.index}
                className={`relative flex aspect-[4/3] flex-col justify-between bg-ink-black p-2 ${
                  frame.ref !== null ? "outline-2 -outline-offset-2 outline-secondary" : ""
                }`}
              >
                <Slug
                  className={`tabular ${
                    frame.ref !== null ? "text-secondary" : "text-parchment/35"
                  }`}
                >
                  {String(frame.index + 1).padStart(2, "0")}
                </Slug>
                <span className="tabular font-mono-label text-[10px] tracking-[0.1em] text-parchment/50">
                  {frame.timecode}
                </span>
                {frame.ref !== null ? (
                  <span className="font-mono-label absolute top-0 right-0 bg-secondary px-1.5 py-0.5 text-[10px] leading-tight font-bold text-parchment">
                    {frame.ref}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
          {sprocketStrip}
        </div>

        <figcaption className="mt-2.5 flex flex-wrap items-baseline justify-between gap-3">
          <Slug className="text-ink-black/35">{fileName}</Slug>
          <Slug className="text-ink-black/35">
            {String(frames.length).padStart(2, "0")} frames pulled from the strip
          </Slug>
        </figcaption>
      </figure>

      <div className="mt-stack-lg">
        <SectionHead title="Scenes" note="Set at true length" />

        <div aria-hidden className="mt-stack-md flex h-9 gap-px">
          {scenes.map((scene, index) => (
            <span
              key={scene.label}
              className={`flex items-center justify-center ${TONE_RULE[toneOf(scene.determination)]}`}
              style={{ width: `${scene.span * 100}%` }}
            >
              <span className="font-mono-label text-[11px] font-bold text-parchment">
                {index + 1}
              </span>
            </span>
          ))}
        </div>

        <dl className="mt-stack-sm grid gap-x-gutter sm:grid-cols-2">
          {scenes.map((scene, index) => {
            const tone = toneOf(scene.determination);
            return (
              <div
                key={scene.label}
                className="flex items-baseline gap-3 border-b border-ink-black/12 py-3"
              >
                <span
                  className={`tabular font-mono-label text-[11px] font-bold ${TONE_TEXT[tone]}`}
                >
                  {index + 1}
                </span>
                <dt className="font-body-sm text-body-sm flex-1 text-ink-black">{scene.label}</dt>
                <dd className="flex items-baseline gap-3">
                  <Slug className="tabular text-ink-black/40">
                    {Math.round(scene.span * 100)}%
                  </Slug>
                  <Slug className={TONE_TEXT[tone]}>{scene.determination}</Slug>
                </dd>
              </div>
            );
          })}
        </dl>
      </div>
    </section>
  );
}
