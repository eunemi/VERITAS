import React from "react";

/**
 * Page furniture for the examination desks.
 *
 * Bands (slug, ledger, ticker) run edge to edge like press furniture; the body
 * sits on the 1440 measure. Both use the same inner padding so the two align.
 */

const MEASURE = "w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop";

/** Content held to the page measure. */
export function Spread({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`${MEASURE} ${className}`}>{children}</div>;
}

/**
 * A full-bleed horizontal band. The background reaches the viewport edges while
 * the content stays on the measure.
 */
export function Band({
  children,
  className = "",
  inner = "",
}: {
  children: React.ReactNode;
  className?: string;
  inner?: string;
}) {
  return (
    <div className={`w-full ${className}`}>
      <div className={`${MEASURE} ${inner}`}>{children}</div>
    </div>
  );
}

/**
 * Small caps mono label. Used for every key, kicker and eyebrow in the desks.
 *
 * It was `text-[10px] leading-none tracking-[0.18em]`, which stacked three
 * legibility failures in one class and applied them to 147 places: 10px caps have
 * a 7.3px cap height against body copy's 8.7px x-height, `leading-none` gave any
 * label that wrapped a line box smaller than its own glyphs, and 0.18em added
 * roughly 30% to the advance of every character — a look for a two-word key, and
 * unreadable for a sentence. It now takes the `--text-label` role: 12px on 16px,
 * 0.08em.
 *
 * A slug is for one to three words. Anything longer is a sentence and belongs in
 * `Note`, which is set roman and sentence case.
 */
export function Slug({
  children,
  className = "",
  id,
}: {
  children: React.ReactNode;
  className?: string;
  /** Set when the slug names a landmark, e.g. a footer nav. */
  id?: string;
}) {
  return (
    <span id={id} className={`font-mono-label text-label uppercase ${className}`}>
      {children}
    </span>
  );
}

/**
 * A short line of secondary text: a section's note, a count, a qualification.
 *
 * These were being set in `Slug`, so phrases like "Each works on the artifact
 * itself" arrived as 10px tracked capitals. Sentences are set roman, sentence
 * case, at reading size.
 */
export function Note({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <span className={`font-body-sm text-body-sm ${className}`}>{children}</span>;
}

/**
 * The rule and pair of labels that opens every block of a record. Left is what
 * the block is; right is the one fact worth knowing before reading it.
 *
 * The title is a real heading. It used to be a 10px `<span>` doing a heading's
 * job, so the structural landmarks of a page were its smallest type and the
 * document outline jumped from h1 straight to the h3 of individual rows.
 */
export function SectionHead({
  title,
  note,
  inverted = false,
  className = "",
  level = 2,
}: {
  title: string;
  note?: string;
  inverted?: boolean;
  className?: string;
  /** Heading rank. 3 where the block sits inside another titled section. */
  level?: 2 | 3;
}) {
  const surface = surfaceOf(inverted);
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <div
      className={`flex flex-wrap items-baseline justify-between gap-x-gutter gap-y-1 border-t pt-stack-sm ${
        inverted ? "border-parchment/50" : "border-ink-black/25"
      } ${className}`}
    >
      <Heading
        className={`font-headline-md text-[19px] leading-[1.25] font-semibold ${surface.text}`}
      >
        {title}
      </Heading>
      {note ? <Note className={surface.faint}>{note}</Note> : null}
    </div>
  );
}

/**
 * The marked-up spread: the artifact on the wide measure, the examiner's notes in
 * the margin beside it. Exhibit numbers printed on the artifact are the same
 * numbers hanging in the margin, which is what makes the two columns one document.
 */
export function MarkedSpread({
  artifact,
  margin,
}: {
  artifact: React.ReactNode;
  margin: React.ReactNode;
}) {
  return (
    <div className="grid gap-stack-lg lg:grid-cols-12 lg:gap-gutter">
      <div className="min-w-0 lg:col-span-8">{artifact}</div>
      <aside className="lg:col-span-4">{margin}</aside>
    </div>
  );
}

/** Colour set for a light (parchment) or inverted (ink) surface. */
export interface Surface {
  text: string;
  /**
   * Secondary text. A token named "faint" still has to be readable: this was
   * `/35` on paper (2.2:1) and `parchment/40` on ink (3.5:1), and it was carrying
   * the only explanatory line on each section. It is now 6.3:1 and 8.0:1.
   */
  faint: string;
  /** Border colour for row rules. */
  rule: string;
  /** Background colour for a hairline drawn as a filled element. */
  ruleBg: string;
}

export function surfaceOf(inverted = false): Surface {
  return inverted
    ? {
        text: "text-parchment",
        faint: "text-parchment/70",
        rule: "border-parchment/20",
        ruleBg: "bg-parchment/20",
      }
    : {
        text: "text-ink-black",
        faint: "text-ink-black/70",
        rule: "border-ink-black/15",
        ruleBg: "bg-ink-black/15",
      };
}
