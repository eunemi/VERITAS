import { SectionHead, Slug } from "../shared/layout";
import { TONE_TEXT, toneOf, type Exhibit } from "@/lib/types/agents";

/**
 * The exhibit table.
 *
 * Every record the desk found, including the ones that disagree with each other,
 * ruled into a ledger: what it is, when it was published, how far it can be
 * relied on, and what it says. Nothing is filtered out for tidiness — a check
 * that only shows agreeing sources is not a check.
 */
export function ExhibitLedger({ claim, exhibits }: { claim: string; exhibits: Exhibit[] }) {
  return (
    <section>
      <SectionHead title="The claim, as stated" note="Examined verbatim" />

      <blockquote className="mt-stack-md border-l-2 border-secondary pl-5 md:pl-7">
        <p className="font-headline-md text-[clamp(22px,2.6vw,31px)] leading-[1.28] font-normal text-ink-black italic">
          &ldquo;{claim}&rdquo;
        </p>
      </blockquote>

      <div className="mt-stack-xl">
        <SectionHead
          title="Exhibits"
          note={`${String(exhibits.length).padStart(2, "0")} returned · listed as found`}
        />

        {/* Column heads only where there is room to rule real columns. */}
        <div className="mt-stack-sm hidden grid-cols-[30px_2.2fr_1fr_1fr_3fr] gap-x-5 border-b border-ink-black/20 pb-2 lg:grid">
          <Slug className="text-ink-black/35">No.</Slug>
          <Slug className="text-ink-black/35">Source</Slug>
          <Slug className="text-ink-black/35">Published</Slug>
          <Slug className="text-ink-black/35">Reliability</Slug>
          <Slug className="text-ink-black/35">What it says</Slug>
        </div>

        <ol>
          {exhibits.map((exhibit) => {
            const tone = toneOf(exhibit.determination);
            return (
              <li
                key={exhibit.ref}
                className="grid grid-cols-[30px_1fr] gap-x-5 gap-y-2 border-b border-ink-black/12 py-stack-md lg:grid-cols-[30px_2.2fr_1fr_1fr_3fr] lg:items-baseline"
              >
                <span
                  aria-hidden
                  className="tabular font-headline-md text-[26px] leading-[0.85] font-bold text-secondary"
                >
                  {exhibit.ref}
                </span>

                <div>
                  <p className="font-body-md text-body-md leading-snug text-ink-black">
                    {exhibit.source}
                  </p>
                  <Slug className={`mt-2 block ${TONE_TEXT[tone]}`}>{exhibit.determination}</Slug>
                </div>

                <Slug className="tabular col-start-2 text-ink-black/45 lg:col-start-auto">
                  {exhibit.published}
                </Slug>

                <Slug className="col-start-2 text-ink-black/45 lg:col-start-auto">
                  {exhibit.reliability} · {exhibit.relevance} relevance
                </Slug>

                <p className="font-proof col-start-2 max-w-[52ch] text-[16px] leading-[27px] text-ink-black/80 lg:col-start-auto">
                  {exhibit.extract}
                </p>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
