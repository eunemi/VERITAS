import { Band, Slug, Spread } from "@/components/agents/shared/layout";
import { DESK_ISSUE } from "@/lib/desks";

interface PageHeaderProps {
  /** The section, as it appears in the navigation. */
  section: string;
  /** What the section stands for, in three or four words. */
  standing: string;
  /** One true count or fact, printed above the title. */
  kicker: string;
  /** The masthead, in two lines: the first roman, the second italic. */
  title: [string, string];
  /** The paragraph that says what the reader is looking at. */
  lede: string;
}

/**
 * The masthead every page reached from the navigation opens with.
 *
 * There were two of these. `/world`, `/economy` and `/tech` used this component —
 * an 80px all-caps Playfair headline at weight 900 over an italic serif deck —
 * while `/intel` and `/archive` built an ink slug bar and a two-line masthead
 * inline. Five routes in the same navigation opened two different ways, and the
 * 80px caps were the least legible setting available in the family: caps hide the
 * word shapes a reader recognises, and weight 900 closes the counters.
 *
 * One opening now, at a size that leaves the lede above the fold: 56px at desktop,
 * weight 700, sentence case, with the second line italic. The deck is set roman in
 * Inter — an italic display serif is for a line, not a paragraph.
 */
export function PageHeader({ section, standing, kicker, title, lede }: PageHeaderProps) {
  return (
    <>
      {/* `min-h-10` rather than `h-10`: the band is allowed to wrap, and a fixed
          forty pixels would have spilled the second label out of the ink at the
          narrowest widths instead of growing to hold it. */}
      <Band
        className="bg-ink-black text-parchment"
        inner="flex min-h-10 flex-wrap items-center justify-between gap-x-gutter gap-y-1 py-2"
      >
        <span className="flex flex-wrap items-center gap-x-4">
          <Slug className="font-bold">{section}</Slug>
          <Slug className="text-parchment/70">{standing}</Slug>
        </span>
        <Slug className="tabular hidden text-parchment/70 md:inline">Issue {DESK_ISSUE}</Slug>
      </Band>

      <Spread className="pt-stack-lg pb-stack-md">
        <Slug className="text-secondary">{kicker}</Slug>
        <h1 className="font-masthead mt-stack-sm max-w-title text-[34px] leading-[1.06] font-bold tracking-[-0.01em] text-ink-black sm:text-[44px] md:text-[56px] md:leading-[1.04]">
          <span className="block">{title[0]}</span>
          <span className="block font-normal italic">{title[1]}</span>
        </h1>
        <p className="font-body-lg text-lede mt-stack-md max-w-lede text-ink-black/70">{lede}</p>
      </Spread>
    </>
  );
}
