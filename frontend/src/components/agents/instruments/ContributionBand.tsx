import Link from "next/link";
import { SectionHead, Slug } from "../shared/layout";
import { DESKS } from "@/lib/desks";
import { TONE_RULE, TONE_TEXT, toneOf, type Contribution } from "@/lib/types/agents";

/**
 * What each desk filed.
 *
 * One row per desk, its bar as long as that desk's own confidence — so the
 * determination can be read against the certainty behind it. The bars do not add up
 * to anything and are not meant to: they are four separate readings, not four slices
 * of one. Each row links back to the record the desk filed.
 */
export function ContributionBand({ contributions }: { contributions: Contribution[] }) {
  const adverse = contributions.filter(
    (contribution) => toneOf(contribution.determination) === "adverse",
  ).length;

  return (
    <section>
      <SectionHead
        title="Desks reporting"
        note={`${String(contributions.length).padStart(2, "0")} filed · ${String(adverse).padStart(2, "0")} adverse`}
      />

      <ul className="mt-stack-sm">
        {contributions.map((contribution) => {
          const tone = toneOf(contribution.determination);
          const named = DESKS[contribution.desk]?.name ?? `${contribution.desk} desk`;
          return (
            <li key={contribution.desk} className="border-b border-ink-black/12">
              <Link
                href={`/intel/${contribution.desk}`}
                className="group block py-3.5 transition-colors hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black"
              >
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5">
                  <span aria-hidden className={`h-2.5 w-2.5 shrink-0 ${TONE_RULE[tone]}`} />
                  <span className="font-body-md text-body-md flex-1 text-ink-black group-hover:text-secondary">
                    {named}
                  </span>
                  <Slug className="tabular text-ink-black/40">
                    {Math.round(contribution.confidence * 100)}% confidence
                  </Slug>
                  <Slug className={`w-[168px] sm:text-right ${TONE_TEXT[tone]}`}>
                    {contribution.determination}
                  </Slug>
                </div>
                <div aria-hidden className="mt-2.5 h-1.5 bg-ink-black/8">
                  <div
                    className={`h-full ${TONE_RULE[tone]}`}
                    style={{ width: `${Math.round(contribution.confidence * 100)}%` }}
                  />
                </div>
              </Link>
            </li>
          );
        })}
      </ul>

      <p className="font-body-sm text-body-sm mt-stack-md max-w-[62ch] text-ink-black/55">
        The record takes the gravest determination any desk filed and reports the
        confidence of the desks that filed it. A confident finding from one desk does
        not soften a graver one from another. Follow any desk to see the record it
        filed.
      </p>
    </section>
  );
}
