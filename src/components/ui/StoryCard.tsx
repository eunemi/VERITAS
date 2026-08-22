import Link from "next/link";
import { Slug } from "@/components/agents/shared/layout";
import { VerificationBadge, type VerificationStatus } from "./VerificationBadge";
import { DESKS } from "@/lib/desks";

interface StoryCardProps {
  category: string;
  headline: string;
  description: string;
  source: string;
  date: string;
  location?: string;
  verificationStatus?: VerificationStatus;
  featured?: boolean;
  /**
   * Which desk examined the story, e.g. "audio". Prints the way through to that
   * desk's record. Omit it and the card carries no action rather than a control
   * that goes nowhere.
   */
  desk?: string;
}

export function StoryCard({
  category,
  headline,
  description,
  source,
  date,
  location,
  verificationStatus,
  featured = false,
  desk,
}: StoryCardProps) {
  const examinedAt = desk ? DESKS[desk] : undefined;

  return (
    <article
      className={`flex flex-col gap-stack-sm pt-stack-sm ${
        featured
          ? "border-t-2 border-ink-black md:grid md:grid-cols-12 md:gap-gutter"
          : "border-t border-ink-black/25"
      }`}
    >
      {/* `justify-between` is right on one line and wrong in a column: on the
          featured layout this cell becomes a stretched grid track, and the status
          was being pushed to the far bottom of it, a hundred-odd pixels below the
          category it belongs beside. */}
      <div
        className={`flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2 ${
          featured ? "md:col-span-4 md:flex-col md:items-start md:justify-start md:gap-4" : ""
        }`}
      >
        <Slug className="text-secondary">
          {category}
          {location && ` — ${location}`}
        </Slug>
        {verificationStatus && <VerificationBadge status={verificationStatus} />}
      </div>

      <div className={`flex flex-col gap-stack-sm ${featured ? "md:col-span-8" : ""}`}>
        {/* The featured headline was 64px against a 30px section heading, so a
            level-three heading outranked the level-two above it by more than
            twice. Playfair also needs a line box larger than its own glyphs:
            `leading-[1.02]` was collapsing descenders into the next line.

            Level three is right for every card, featured or not: each one sits
            inside a section the page has already titled at level two. */}
        <h3
          className={`text-ink-black ${
            featured
              ? "font-masthead text-[28px] leading-[1.14] font-bold tracking-[-0.005em] md:text-[36px]"
              : "font-headline-md text-[21px] leading-[1.3] font-semibold"
          }`}
        >
          {headline}
        </h3>

        {/* `font-body-md` sets the family only — with no `text-body-md` beside it
            this paragraph had no size or leading of its own at all. The measure
            was also applied to the featured branch alone, so the grid cards ran
            to whatever width their column happened to be. */}
        <p className="font-body-md text-read max-w-measure text-ink-black/70">{description}</p>

        {/* Source and date were two separate 10px lines. They are one line: a
            reader wants the provenance as a single fact, not as a stack. */}
        <div className="mt-auto flex flex-wrap items-baseline justify-between gap-x-gutter gap-y-2 border-t border-ink-black/20 pt-stack-sm">
          <Slug className="text-ink-black/70">
            {source} · {date}
          </Slug>

          {examinedAt ? (
            <Link
              href={`/intel/${examinedAt.id}`}
              className="border-b border-ink-black/40 pb-0.5 text-ink-black transition-colors hover:border-secondary hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              <Slug>{examinedAt.name} desk</Slug>
            </Link>
          ) : null}
        </div>
      </div>
    </article>
  );
}
