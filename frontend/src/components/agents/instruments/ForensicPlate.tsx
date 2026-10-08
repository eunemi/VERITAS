import { SectionHead, Slug } from "../shared/layout";
import {
  TONE_BORDER,
  toneOf,
  type Annotation,
  type PlateRegion,
} from "@/lib/types/agents";

/**
 * The plate.
 *
 * The examined frame, with the regions the desk read ruled onto it. A region that
 * produced a note carries that note's number and its determination's colour; a
 * region the desk merely read — a line of recovered text it drew no conclusion
 * from — is ruled plainly and left unnumbered, because a crimson box with no note
 * behind it accuses the frame of something nobody wrote down. The marks sit on the
 * artifact, which is the whole point: a region called out in a list beside the image
 * tells you nothing about where to look.
 */
export function ForensicPlate({
  previewUrl,
  fileName,
  regions,
  annotations,
}: {
  previewUrl: string | null;
  fileName: string;
  regions: PlateRegion[];
  annotations: Annotation[];
}) {
  const noteFor = (ref: number) =>
    ref ? annotations.find((candidate) => candidate.ref === ref) : undefined;

  return (
    <section>
      <SectionHead title="Plate" note={`${regions.length} regions ruled`} />

      <figure className="mt-stack-md">
        <div className="ticked relative bg-ink-black text-parchment/20">
          <div className="relative mx-auto w-fit">
            {previewUrl ? (
              <>
                {/* A URL the examiner was pointed at, not a project asset — next/image
                    cannot be given an arbitrary remote host without configuring it. */}
                {previewUrl?.match(/\.(mp4|mov|webm|mkv)$/i) ? (
                  <video
                    src={previewUrl}
                    controls
                    className="block max-h-[520px] w-auto"
                  />
                ) : (
                  <img
                    src={previewUrl}
                    alt={`Frame under examination: ${fileName}`}
                    className="block max-h-[520px] w-auto"
                  />
                )}
                {regions.map((region, index) => {
                  const note = noteFor(region.ref);
                  return (
                    <div
                      key={`${region.ref}-${index}`}
                      className={`absolute border-2 ${
                        note
                          ? TONE_BORDER[toneOf(note.determination)]
                          : "border-parchment/50"
                      }`}
                      style={{
                        left: `${region.x}%`,
                        top: `${region.y}%`,
                        width: `${region.w}%`,
                        height: `${region.h}%`,
                      }}
                    >
                      {note ? (
                        <span className="font-mono-label absolute -top-px -left-px bg-secondary px-1.5 py-0.5 text-[10px] leading-tight font-bold text-parchment">
                          {region.ref}
                        </span>
                      ) : null}
                      <span className="font-mono-label absolute -bottom-6 left-0 hidden text-[10px] tracking-[0.14em] whitespace-nowrap text-parchment uppercase sm:block">
                        {region.label}
                      </span>
                    </div>
                  );
                })}
              </>
            ) : (
              <div className="px-6 py-stack-xl text-center">
                <p className="font-headline-md text-[24px] leading-tight font-normal text-parchment/70 italic">
                  No frame on the plate
                </p>
                <p className="font-body-sm text-body-sm mt-2 text-parchment/40">
                  The desk examined {fileName}, but could not display it.
                </p>
              </div>
            )}
          </div>
        </div>

        <figcaption className="mt-2.5 flex flex-wrap items-baseline justify-between gap-3">
          <Slug className="text-ink-black/35">{fileName}</Slug>
          <Slug className="text-ink-black/35">Rules drawn to scale on the frame</Slug>
        </figcaption>
      </figure>
    </section>
  );
}
