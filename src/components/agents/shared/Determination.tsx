import { Band, Slug } from "./layout";
import { TONE_TEXT, toneOf, type Verdict } from "@/lib/types/agents";

/**
 * The closing determination — the one place on the page allowed to be loud.
 *
 * The stamp carries the ruling and the confidence together, because a ruling
 * without its confidence is the thing that gets misquoted. The reasoning sits
 * beside it in the paper's own reading face, set with a drop cap, so the record
 * closes the way a leader column closes.
 */
export function Determination({
  verdict,
  signedBy,
}: {
  verdict: Verdict;
  /** Which desk signed. Printed under the stamp. */
  signedBy: string;
}) {
  const tone = toneOf(verdict.determination);

  return (
    <Band
      className="border-t-2 border-ink-black bg-parchment"
      inner="grid gap-stack-lg py-stack-xl lg:grid-cols-12 lg:gap-gutter"
    >
      <div className="lg:col-span-4">
        <Slug className="text-ink-black/45">Determination</Slug>

        <div
          className={`stamp mt-stack-md inline-block -rotate-[2.5deg] px-5 py-3.5 ${TONE_TEXT[tone]}`}
        >
          <span className="font-mono-label block text-[15px] leading-none font-bold tracking-[0.16em] uppercase">
            {verdict.determination}
          </span>
          <span className="tabular font-mono-label mt-2 block text-center text-[10px] leading-none tracking-[0.18em] uppercase">
            Confidence {verdict.confidence}
          </span>
        </div>

        <p className="mt-stack-lg font-body-sm text-body-sm text-ink-black/55">
          Signed at the {signedBy}.
        </p>
      </div>

      <div className="lg:col-span-8">
        <h2 className="font-headline-lg text-[clamp(30px,3.6vw,46px)] leading-[1.08] font-bold text-ink-black">
          {verdict.headline}
        </h2>
        <p className="drop-cap font-proof text-proof mt-stack-md max-w-[64ch] text-ink-black/85">
          {verdict.rationale}
        </p>
      </div>
    </Band>
  );
}
