import Link from "next/link";
import { Band, Slug, Spread } from "@/components/agents/shared/layout";
import { DESK_ISSUE, DESK_ORDER, DESKS } from "@/lib/desks";

/**
 * 404, set as a returned slip rather than an error screen.
 *
 * The app had no not-found boundary at all, so a mistyped desk or a stale link
 * fell through to the framework's default page — an unstyled screen in a paper
 * that is otherwise typeset throughout. The three destinations below are the only
 * places a reader can usefully be sent: the register, the index, or the bench.
 */

const ELSEWHERE = [
  {
    href: "/intel",
    label: "The register of desks",
    note: "All six desks, what each reads, and what it will not rule on",
  },
  {
    href: "/archive",
    label: "The record index",
    note: "Every examination signed so far, searchable by desk and determination",
  },
  {
    href: "/investigate",
    label: "The submission bench",
    note: "Hand over one artifact and let every desk that can read it report",
  },
];

export default function NotFound() {
  return (
    <main className="min-h-screen bg-background">
      <Band
        className="bg-ink-black text-parchment"
        inner="flex h-9 items-center justify-between gap-gutter"
      >
        <span className="flex items-center gap-3">
          <Slug className="font-bold">Returned</Slug>
          <span aria-hidden className="h-3 w-px bg-parchment/25" />
          <Slug className="text-parchment/50">No such page on file</Slug>
        </span>
        <Slug className="tabular hidden text-parchment/40 md:inline">Issue {DESK_ISSUE}</Slug>
      </Band>

      <Spread className="pt-stack-xl pb-stack-lg">
        <Slug className="text-secondary">Error 404</Slug>
        <h1 className="font-masthead mt-stack-sm max-w-[15ch] text-[clamp(44px,8vw,96px)] leading-[0.92] font-black tracking-[-0.025em] text-ink-black">
          <span className="block">Nothing filed</span>
          <span className="block pl-[0.05em] font-normal italic">at this address.</span>
        </h1>
        <p className="font-headline-md mt-stack-md max-w-[46ch] text-[22px] leading-[1.35] font-normal text-ink-black/70 italic">
          The page you asked for does not exist, or the record that once sat here was never
          published.
        </p>
      </Spread>

      <Spread className="pb-stack-lg">
        <ol className="border-t-2 border-ink-black">
          {ELSEWHERE.map((entry) => (
            <li key={entry.href} className="border-b border-ink-black/12">
              <Link
                href={entry.href}
                className="group grid gap-2 py-stack-md transition-colors hover:bg-parchment/50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink-black sm:grid-cols-12 sm:items-baseline sm:gap-gutter"
              >
                <span className="font-headline-md text-[26px] leading-tight font-bold text-ink-black transition-colors group-hover:text-secondary sm:col-span-4">
                  {entry.label}
                </span>
                <span className="font-body-sm text-body-sm text-ink-black/60 sm:col-span-7">
                  {entry.note}
                </span>
                <span
                  aria-hidden
                  className="text-[15px] leading-none text-ink-black/35 transition-transform group-hover:translate-x-1 group-hover:text-secondary sm:col-span-1 sm:text-right"
                >
                  &rarr;
                </span>
              </Link>
            </li>
          ))}
        </ol>
      </Spread>

      <Spread className="pb-stack-xl">
        <div className="border-t border-ink-black/15 pt-stack-md">
          <Slug className="text-ink-black/40">Desks, in order</Slug>
          <ul className="mt-stack-sm flex flex-wrap gap-x-gutter gap-y-2">
            {DESK_ORDER.map((id) => (
              <li key={id}>
                <Link
                  href={`/intel/${id}`}
                  className="font-body-sm text-body-sm text-ink-black/65 underline decoration-ink-black/20 decoration-1 underline-offset-4 transition-colors hover:text-secondary hover:decoration-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
                >
                  <span className="tabular">{DESKS[id].number}</span> · {DESKS[id].name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </Spread>
    </main>
  );
}
