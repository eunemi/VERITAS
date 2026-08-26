import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/ui/PageHeader";
import { StoryCard } from "@/components/ui/StoryCard";
import { SectionHead, Slug, Spread } from "@/components/agents/shared/layout";
import { ARCHIVE } from "@/lib/archive";
import { TONE_TEXT, toneOf } from "@/lib/types/agents";

export const metadata: Metadata = {
  title: "World",
  description:
    "Reporting from across the globe, with the desk record behind each story — and where the signed records have come from.",
};

/**
 * Where the records come from.
 *
 * This block used to be a "GLOBAL INTELLIGENCE MAP · LIVE TRACKING": a 400px map
 * glyph with three pinging dots placed by hand, tracking nothing. It is now a
 * count of the regions the signed records actually cover, read off the archive,
 * which is the only global picture this publication can honestly print.
 */
const REGIONS = Array.from(new Set(ARCHIVE.map((record) => record.region)))
  .map((region) => {
    const filed = ARCHIVE.filter((record) => record.region === region);
    /* The archive is held in filing order, so the first match is the newest. */
    return { region, count: filed.length, latest: filed[0] };
  })
  .sort((a, b) => b.count - a.count || a.region.localeCompare(b.region));

export default function WorldPage() {
  return (
    <main className="min-h-screen bg-background">
      <PageHeader
        section="World"
        standing="Reporting from the regions"
        kicker={`${REGIONS.length} regions on the index`}
        title={["The world,", "under analysis."]}
        lede="Signals, stories and developments from across the globe, each one carrying the desk record that was signed behind it."
      />

      <Spread className="pb-stack-xl">
        <SectionHead title="The lead" note="Examined at four desks" />
        <div className="mt-stack-md">
          <StoryCard
            featured
            category="Geopolitics"
            location="Geneva"
            headline="New treaties questioned as synthetic media clouds negotiations"
            description="A comprehensive analysis of the recent summit reveals overlapping inconsistencies in the official broadcast feeds. Veritas desks detected audio-visual desyncs consistent with deepfake injection, raising questions about the authenticity of the primary accord."
            source="Reuters / Veritas Intel"
            date="21 Aug 2026"
            verificationStatus="CONTESTED"
            desk="video"
          />
        </div>
      </Spread>

      <Spread className="pb-stack-xl">
        <SectionHead title="Also reported" note="Three records filed this week" />
        <div className="mt-stack-md grid grid-cols-1 gap-x-gutter gap-y-stack-lg md:grid-cols-2 lg:grid-cols-3">
          <StoryCard
            category="Climate"
            location="Jakarta"
            headline="Sea wall breach attributed to sensor malfunction, not sabotage"
            description="Initial reports suggested malicious interference, but forensic analysis of the structural integrity sensors points to a cascading hardware failure."
            source="AP / Veritas Forensics"
            date="20 Aug 2026"
            verificationStatus="VERIFIED"
            desk="fact-check"
          />
          <StoryCard
            category="Conflict"
            location="Eastern Europe"
            headline="Satellite imagery contradicts troop withdrawal claims"
            description="Analysis of 48 hours of synthetic aperture radar data shows concealed movements contradicting the official narrative of de-escalation."
            source="Maxar / Veritas Vision"
            date="19 Aug 2026"
            verificationStatus="UNDER REVIEW"
            desk="image"
          />
          <StoryCard
            category="Election"
            location="Brasília"
            headline="Audio leak authenticated despite candidate's denial"
            description="The audio desk has processed the leaked recording, finding continuous spectral signatures and no evidence of AI generation."
            source="Veritas Intel"
            date="18 Aug 2026"
            verificationStatus="VERIFIED"
            desk="audio"
          />
        </div>
      </Spread>

      <Spread className="pb-stack-xl">
        <SectionHead
          title="Where the records come from"
          note={`${ARCHIVE.length} signed records across ${REGIONS.length} regions`}
        />

        {/* One row used to carry seven separately-styled fragments across twelve
            columns: a 22px italic region, a 10px count at 40% ink, a 14px headline
            at 65%, a coloured hairline, a tone label, and a 10px date at 35%. It
            is three columns now, at two ink levels, and the tone colour on the
            determination is the only colour in the row. The filing date belongs to
            the archive, which is where the whole record is. */}
        <ol className="mt-stack-md">
          {REGIONS.map(({ region, count, latest }) => (
            <li
              key={region}
              className="grid gap-x-gutter gap-y-1 border-b border-ink-black/25 py-stack-sm sm:grid-cols-12 sm:items-baseline"
            >
              <span className="flex flex-wrap items-baseline gap-x-3 sm:col-span-3">
                <span className="font-headline-md text-[19px] leading-[1.3] font-semibold text-ink-black">
                  {region}
                </span>
                <Slug className="tabular text-ink-black/70">
                  {count === 1 ? "01 record" : `${count} records`}
                </Slug>
              </span>
              <span className="font-body-md text-read text-ink-black sm:col-span-6">
                {latest.headline}
              </span>
              <Slug className={`${TONE_TEXT[toneOf(latest.determination)]} sm:col-span-3`}>
                {latest.determination}
              </Slug>
            </li>
          ))}
        </ol>

        <p className="font-body-md text-body-md mt-stack-md max-w-measure text-ink-black/70">
          Counted from the records the desks have signed, not from live monitoring — Veritas watches
          what it is handed.{" "}
          <Link
            href="/archive"
            className="border-b border-secondary text-ink-black transition-colors hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            Search the whole index
          </Link>
          .
        </p>
      </Spread>
    </main>
  );
}
