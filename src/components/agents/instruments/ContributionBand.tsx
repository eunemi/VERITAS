import Link from "next/link";
import { SectionHead, Slug } from "../shared/layout";
import { TONE_RULE, TONE_TEXT, toneOf, type Contribution } from "@/lib/types/agents";

/**
 * The weighting.
 *
 * One bar, five segments, each as wide as the share that desk carried in the
 * final ruling — so the arithmetic behind the determination is visible rather
 * than asserted. Each desk's row links back to its own record.
 */
export function ContributionBand({ contributions }: { contributions: Contribution[] }) {
  const adverse = contributions.filter(
    (contribution) => toneOf(contribution.determination) === "adverse",
  ).length;

  return (
    <section>
      <SectionHead
        title="Weighting"
        note={`${String(contributions.length).padStart(2, "0")} desks reporting · ${String(adverse).padStart(2, "0")} adverse`}
      />

      <div aria-hidden className="mt-stack-md flex h-11 gap-px">
        {contributions.map((contribution) => (
          <span
            key={contribution.desk}
            className={`flex items-center justify-center ${TONE_RULE[toneOf(contribution.determination)]}`}
            style={{ width: `${contribution.share * 100}%` }}
          >
            <span className="tabular font-mono-label text-[11px] font-bold text-parchment">
              {Math.round(contribution.share * 100)}
            </span>
          </span>
        ))}
      </div>

      <ul className="mt-stack-sm">
        {contributions.map((contribution) => {
          const tone = toneOf(contribution.determination);
          return (
            <li key={contribution.desk} className="border-b border-ink-black/12">
              <Link
                href={`/intel/${contribution.desk.toLowerCase()}`}
                className="group flex flex-wrap items-baseline gap-x-4 gap-y-1.5 py-3.5 transition-colors hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black"
              >
                <span aria-hidden className={`h-2.5 w-2.5 shrink-0 ${TONE_RULE[tone]}`} />
                <span className="font-body-md text-body-md flex-1 text-ink-black group-hover:text-secondary">
                  {contribution.desk} desk
                </span>
                <Slug className="tabular text-ink-black/40">
                  {Math.round(contribution.share * 100)}% weight
                </Slug>
                <Slug className={`w-[168px] sm:text-right ${TONE_TEXT[tone]}`}>
                  {contribution.determination}
                </Slug>
              </Link>
            </li>
          );
        })}
      </ul>

      <p className="font-body-sm text-body-sm mt-stack-md max-w-[62ch] text-ink-black/55">
        Weight follows how much of the artifact a desk could actually read, not how
        confident it says it is. Follow any desk to see the record it filed.
      </p>
    </section>
  );
}
