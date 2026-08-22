import type { Metadata } from "next";
import Link from "next/link";
import { Band, SectionHead, Slug, Spread } from "@/components/agents/shared/layout";
import { PageHeader } from "@/components/ui/PageHeader";
import { DESK_ORDER, DESKS, type DeskDefinition } from "@/lib/desks";

export const metadata: Metadata = {
  title: "The intelligence desk",
  description:
    "The six examination desks, what each one reads, what it returns, and the order they work in.",
};

/**
 * The index of the desks.
 *
 * This page used to be six status-pill cards ringed by decorative circles, with
 * the desk copy retyped a third time. It is now the register: what each desk
 * accepts, what it hands back, and — stated plainly — what it will not do. The
 * copy comes from `@/lib/desks`, so the index cannot drift from the desks.
 */

const REPORTING = DESK_ORDER.slice(0, 5).map((id) => DESKS[id]);
const CORE = DESKS[DESK_ORDER[5]];

const MOVEMENTS = [
  {
    heading: "The artifact is typed",
    body: "Whatever you hand over is read for what it is first — copy, frame, recording, footage or a single claim. Only the desks that can read that type open a file on it.",
  },
  {
    heading: "Five desks read it alone",
    body: "No desk sees another's working. Each marks what it finds on the artifact itself, by exhibit number, so every finding has a place on the page. A desk that finds nothing files that too.",
  },
  {
    heading: "The core signs one record",
    body: "Agent 06 reads the five records, weighs each by how reliably it was reached, and signs a single determination. Where the desks disagree, the disagreement is printed rather than resolved away.",
  },
];

/**
 * One entry in the register: the desk on the left, its method on the right.
 *
 * The desk number used to print separately at 38px in 20% ink — 1.4:1 on this
 * ground, so the largest figure in the entry was also the one nobody could read.
 * It is dropped: the eyebrow beside it already says "Agent 01", which is the same
 * number in a place a reader is looking.
 */
function RegisterEntry({ desk }: { desk: DeskDefinition }) {
  return (
    <li className="border-t border-ink-black/25 py-stack-lg first:border-t-0 first:pt-stack-md">
      <div className="grid gap-stack-md lg:grid-cols-12 lg:gap-gutter">
        <div className="lg:col-span-6">
          <Slug className="text-secondary">{desk.eyebrow}</Slug>
          <h3 className="font-headline-md mt-stack-sm text-[24px] leading-[1.2] font-semibold text-ink-black md:text-[28px]">
            {desk.titleLines.join(" ")}
          </h3>
          <p className="font-body-md text-read mt-stack-sm max-w-measure text-ink-black/70">
            {desk.standfirst}
          </p>
          <Link
            href={`/intel/${desk.id}`}
            className="mt-stack-md inline-block border-b-2 border-secondary pb-1 text-ink-black transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            <Slug>Open the {desk.name} desk</Slug>
          </Link>
        </div>

        {/* The keys were 40% ink at 10px. They name the four things worth knowing
            about a desk, so they are set in full ink at label size. */}
        <dl className="lg:col-span-6 lg:border-l lg:border-ink-black/15 lg:pl-gutter">
          {desk.method.map((row) => (
            <div
              key={row.key}
              className="grid items-baseline gap-x-gutter gap-y-1 border-b border-ink-black/15 py-stack-sm last:border-b-0 sm:grid-cols-[7rem_minmax(0,1fr)]"
            >
              <dt>
                <Slug className="text-ink-black">{row.key}</Slug>
              </dt>
              <dd className="font-body-sm text-body-sm text-ink-black/70">{row.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </li>
  );
}

export default function IntelPage() {
  return (
    <main className="min-h-screen bg-background">
      <PageHeader
        section="Intelligence desk"
        standing="Register of desks"
        kicker="Six desks, one record"
        title={["How Veritas", "reads a thing."]}
        lede="Nothing here is a verdict machine. Each desk states what it looked at, what it found, and what it could not tell you."
      />

      <Spread className="pb-stack-xl">
        <SectionHead title="The order of work" note="Five report, one signs" />
        <ol className="mt-stack-md grid gap-stack-md md:grid-cols-3 md:gap-gutter">
          {MOVEMENTS.map((movement, index) => (
            <li key={movement.heading} className="border-t border-ink-black/25 pt-stack-sm">
              <Slug className="tabular text-secondary">
                Movement {String(index + 1).padStart(2, "0")}
              </Slug>
              <h3 className="font-headline-md mt-2.5 text-[21px] leading-[1.3] font-semibold text-ink-black">
                {movement.heading}
              </h3>
              <p className="font-body-md text-body-md mt-2.5 text-ink-black/70">{movement.body}</p>
            </li>
          ))}
        </ol>
      </Spread>

      <Spread className="pb-stack-xl">
        <SectionHead title="The reporting desks" note="Each works on the artifact itself" />
        <ol className="mt-stack-md">
          {REPORTING.map((desk) => (
            <RegisterEntry key={desk.id} desk={desk} />
          ))}
        </ol>
      </Spread>

      <Spread className="pb-stack-xl">
        <SectionHead title="Adjudication" note="Sits after the five have reported" />
        <ol className="mt-stack-md">
          <RegisterEntry desk={CORE} />
        </ol>
      </Spread>

      <Band className="bg-ink-black text-parchment" inner="py-stack-lg">
        <div className="flex flex-wrap items-end justify-between gap-stack-md">
          <div>
            <Slug className="text-parchment/70">All six on one artifact</Slug>
            <p className="font-headline-md mt-2.5 max-w-[26ch] text-[24px] leading-[1.25] font-normal italic md:text-[26px]">
              Open an investigation and let the desks report together.
            </p>
          </div>
          <Link
            href="/investigate"
            className="border border-parchment px-6 py-3 transition-colors hover:bg-parchment hover:text-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-foil"
          >
            <Slug>Open the bench</Slug>
          </Link>
        </div>
      </Band>
    </main>
  );
}
