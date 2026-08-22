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
 * The submitted frame, with the flagged regions ruled onto it and each rule
 * carrying the number of the note that explains it. The marks sit on the
 * artifact, which is the whole point — a region called out in a list beside the
 * image tells you nothing about where to look.
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
  const toneFor = (ref: number) => {
    const annotation = annotations.find((candidate) => candidate.ref === ref);
    return annotation ? toneOf(annotation.determination) : "adverse";
  };

  return (
    <section>
      <SectionHead title="Plate" note={`${regions.length} regions ruled`} />

      <figure className="mt-stack-md">
        <div className="ticked relative bg-ink-black text-parchment/20">
          <div className="relative mx-auto w-fit">
            {previewUrl ? (
              <>
                {/* Object URL from the visitor's own disk — next/image cannot optimise it. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={previewUrl}
                  alt={`Frame under examination: ${fileName}`}
                  className="block max-h-[520px] w-auto"
                />
                {regions.map((region) => {
                  const tone = toneFor(region.ref);
                  return (
                    <div
                      key={region.ref}
                      className={`absolute border-2 ${TONE_BORDER[tone]}`}
                      style={{
                        left: `${region.x}%`,
                        top: `${region.y}%`,
                        width: `${region.w}%`,
                        height: `${region.h}%`,
                      }}
                    >
                      <span className="font-mono-label absolute -top-px -left-px bg-secondary px-1.5 py-0.5 text-[10px] leading-tight font-bold text-parchment">
                        {region.ref}
                      </span>
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
