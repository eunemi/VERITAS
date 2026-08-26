import type { ReactNode } from "react";

/**
 * The four decorative stickers on the front page, drawn rather than loaded.
 *
 * These were four PNGs statically imported from `public/`. A static image import is
 * resolved by the bundler, so when those files left the repository `next build`
 * stopped with a ModuleNotFoundError — a missing piece of decoration took the whole
 * site down. Drawing them removes that class of failure rather than working around
 * it: there is no file to go missing, nothing to 404, and no binary in the tree.
 *
 * They illustrate what the headline already says, so each is `aria-hidden` and none
 * carries a label. Nothing here is rotated — the tilt belongs to the `float-*`
 * keyframes in `globals.css`, which also stop under `prefers-reduced-motion`.
 */

const INK = "var(--color-ink-black)";
const PAPER = "var(--color-parchment)";
const CRIMSON = "var(--color-secondary)";
const NOTE = "var(--color-tertiary-fixed)";
const LABEL = "var(--font-mono-label)";

export interface StickerProps {
  /** Placement, size and float classes, applied to the `<svg>` itself. */
  className?: string;
}

function Sticker({ className, children }: StickerProps & { children: ReactNode }) {
  return (
    <svg viewBox="0 0 100 100" aria-hidden className={className}>
      {children}
    </svg>
  );
}

/** A folded front page. */
export function NewspaperSticker({ className }: StickerProps) {
  return (
    <Sticker className={className}>
      <rect
        x="9"
        y="15"
        width="82"
        height="70"
        rx="2"
        fill={PAPER}
        stroke={INK}
        strokeWidth="3"
      />
      <rect x="15" y="21" width="70" height="11" fill={INK} />
      <g stroke={INK} strokeWidth="2.5" strokeLinecap="round">
        <path d="M15 39h70" />
        <path d="M15 48h30M15 55h30M15 62h30M15 69h22" />
        <path d="M55 48h30M55 55h30M55 62h30M55 69h18" />
      </g>
      <circle cx="76" cy="72" r="7" fill={CRIMSON} />
    </Sticker>
  );
}

/** A rubber stamp reading TRUTH. */
export function TruthSticker({ className }: StickerProps) {
  return (
    <Sticker className={className}>
      <circle cx="50" cy="50" r="43" fill={PAPER} stroke={CRIMSON} strokeWidth="4" />
      <circle cx="50" cy="50" r="35" fill="none" stroke={CRIMSON} strokeWidth="1.5" />
      <g stroke={CRIMSON} strokeWidth="2" strokeLinecap="round">
        <path d="M26 38h48M26 62h48" />
      </g>
      <text
        x="50"
        y="52"
        fill={CRIMSON}
        fontFamily={LABEL}
        fontSize="15"
        fontWeight="700"
        letterSpacing="2"
        textAnchor="middle"
        dominantBaseline="middle"
      >
        TRUTH
      </text>
      <text
        x="50"
        y="75"
        fill={CRIMSON}
        fontFamily={LABEL}
        fontSize="7"
        letterSpacing="1.5"
        textAnchor="middle"
      >
        VERIFIED
      </text>
    </Sticker>
  );
}

/** A magnifier over a dossier. */
export function InvestigationSticker({ className }: StickerProps) {
  return (
    <Sticker className={className}>
      <rect
        x="14"
        y="12"
        width="54"
        height="70"
        rx="2"
        fill={PAPER}
        stroke={INK}
        strokeWidth="3"
      />
      <g stroke={INK} strokeWidth="2.5" strokeLinecap="round">
        <path d="M22 24h38M22 33h38M22 42h24" />
      </g>
      <circle
        cx="59"
        cy="58"
        r="21"
        fill={PAPER}
        fillOpacity="0.75"
        stroke={INK}
        strokeWidth="4"
      />
      <path
        d="M74 73 89 88"
        stroke={INK}
        strokeWidth="7"
        strokeLinecap="round"
      />
      <path d="M52 58h14M59 51v14" stroke={CRIMSON} strokeWidth="2.5" />
    </Sticker>
  );
}

/** A taped note in a reporter's hand. */
export function NoteSticker({ className }: StickerProps) {
  return (
    <Sticker className={className}>
      <path
        d="M13 18h74v56L71 88H13Z"
        fill={NOTE}
        stroke={INK}
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path d="M87 74H71v14Z" fill={PAPER} stroke={INK} strokeWidth="3" />
      <g stroke={INK} strokeWidth="2.5" strokeLinecap="round" opacity="0.75">
        <path d="M22 34h56M22 45h56M22 56h44M22 67h30" />
      </g>
      <rect
        x="33"
        y="8"
        width="34"
        height="14"
        fill={PAPER}
        fillOpacity="0.85"
        stroke={INK}
        strokeWidth="2"
      />
    </Sticker>
  );
}
