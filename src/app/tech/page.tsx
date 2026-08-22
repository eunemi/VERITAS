import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/ui/PageHeader";
import { StoryCard } from "@/components/ui/StoryCard";
import { SectionHead, Slug, Spread } from "@/components/agents/shared/layout";
import { DESK_ORDER, DESKS, type DeskDefinition } from "@/lib/desks";

export const metadata: Metadata = {
  title: "Technology",
  description:
    "Reporting on the systems that structure reality — and the desks Veritas uses to read what they produce.",
};

/** The five desks that read an artifact. The core signs after them. */
const REPORTING = DESK_ORDER.slice(0, 5).map((id) => DESKS[id]);

/**
 * What a desk looks for, read by key rather than by position. This was
 * `desk.method[1].value` — correct today, and silently the wrong sentence the
 * moment a row is inserted above it.
 */
function looksFor(desk: DeskDefinition): string {
  return desk.method.find((row) => row.key === "Looks for")?.value ?? "";
}

export default function TechPage() {
  return (
    <main className="min-h-screen bg-background">
      <PageHeader
        section="Technology"
        standing="Digital culture"
        kicker="Five desks read the systems"
        title={["Technology", "shapes the story."]}
        lede="Reporting on the systems that structure what we are shown — and on the methods Veritas uses to read back out of them."
      />

      <Spread className="pb-stack-xl">
        <SectionHead title="The lead" note="Signed at the text desk" />
        <div className="mt-stack-md">
          <StoryCard
            featured
            category="Artificial intelligence"
            location="San Francisco"
            headline="New generative models slip past standard detection protocols"
            description="The latest open-weight models can hold a named author's style closely enough that stylometric analysis no longer separates them from the writer. Veritas has moved the text desk onto semantic weighting in response."
            source="Veritas Labs"
            date="21 Aug 2026"
            verificationStatus="VERIFIED"
            desk="text"
          />
        </div>
      </Spread>

      {/* The special report used to sit in a tinted box behind a blurred blob and a
          pinging ring, and its one control went nowhere. It is a spread on the
          page's own grid now, opened by the same section head as everything else,
          and it prints what the desks actually look for. */}
      <Spread className="pb-stack-xl">
        <SectionHead title="Special report" note="How the reading is split" />

        <div className="mt-stack-md grid gap-stack-lg lg:grid-cols-12 lg:gap-gutter">
          <div className="lg:col-span-6">
            <h3 className="font-headline-md text-[26px] leading-[1.2] font-semibold text-ink-black md:text-[30px]">
              AI and information integrity
            </h3>
            <p className="font-body-md text-read mt-stack-sm max-w-measure text-ink-black/70">
              As synthetic media becomes indistinguishable from reality to the human eye, journalism
              has to change how it reads. Veritas splits the reading across five desks that never
              see each other&rsquo;s working, then weighs what they filed — so a fabrication has to
              survive five separate examinations rather than one.
            </p>
            <Link
              href="/intel"
              className="mt-stack-md inline-block border-b-2 border-secondary pb-1 text-ink-black transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              <Slug>Read the full method</Slug>
            </Link>
          </div>

          {/* The keys were set at 40% ink — 2.5:1 on this ground — so the word
              naming each desk was the faintest thing in the table. */}
          <dl className="lg:col-span-6 lg:border-l lg:border-ink-black/15 lg:pl-gutter">
            {REPORTING.map((desk) => (
              <div
                key={desk.id}
                className="grid items-baseline gap-x-gutter gap-y-1 border-b border-ink-black/15 py-stack-sm last:border-b-0 sm:grid-cols-[7rem_minmax(0,1fr)]"
              >
                <dt>
                  <Slug className="text-ink-black">{desk.name}</Slug>
                </dt>
                <dd className="font-body-sm text-body-sm text-ink-black/70">{looksFor(desk)}</dd>
              </div>
            ))}
          </dl>
        </div>
      </Spread>

      <Spread className="pb-stack-xl">
        <SectionHead title="Also reported" note="Three records filed this week" />

        <div className="mt-stack-md grid grid-cols-1 gap-x-gutter gap-y-stack-lg md:grid-cols-2 lg:grid-cols-3">
          <StoryCard
            category="Cybersecurity"
            headline="Zero-day exploit compromises a major cloud provider"
            description="An attack vector built on AI-generated phishing payloads cleared enterprise security and exposed internal communications at three news organisations."
            source="Veritas Sec"
            date="20 Aug 2026"
            verificationStatus="VERIFIED"
            desk="fact-check"
          />
          <StoryCard
            category="Science"
            headline="Quantum decryption milestone reached ahead of schedule"
            description="Researchers say they factored a 2048-bit RSA key with a hybrid quantum-classical algorithm. The consequences for digital signatures are the story."
            source="Nature / Veritas"
            date="19 Aug 2026"
            verificationStatus="UNDER REVIEW"
            desk="fact-check"
          />
          <StoryCard
            category="Digital culture"
            headline="Autonomous personas are running influential accounts"
            description="Fully autonomous agents now hold accounts with large followings and coordinate narratives between them without a person in the loop."
            source="Veritas Intel"
            date="18 Aug 2026"
            verificationStatus="VERIFIED"
            desk="text"
          />
        </div>
      </Spread>
    </main>
  );
}
