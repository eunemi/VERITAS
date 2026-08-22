import { Slug } from "@/components/agents/shared/layout";

export type VerificationStatus = "VERIFIED" | "UNDER REVIEW" | "CONTESTED" | string;

/**
 * Mark colour and rule per determination. Keyed on the upper-cased status.
 *
 * "UNDER REVIEW" is keyed deliberately rather than left to fall through: it was
 * landing on the unsettled fallback below, which meant the one status that says
 * "we have not finished" was styled by accident. It takes gold-ink, the same
 * colour the archive prints an unsettled determination in, so an unfinished
 * examination reads the same wherever it appears.
 */
const MARKS: Record<string, { text: string; rule: string }> = {
  VERIFIED: { text: "text-trust-green", rule: "border-trust-green/50" },
  "UNDER REVIEW": { text: "text-gold-ink", rule: "border-gold-ink/50" },
  CONTESTED: { text: "text-alert-crimson", rule: "border-alert-crimson/50" },
  ERROR: { text: "text-alert-crimson", rule: "border-alert-crimson/50" },
};

/** Anything not keyed above. `/70` is 6.3:1; this was `/55`, which is 3.9:1. */
const UNSETTLED = { text: "text-ink-black/70", rule: "border-ink-black/40" };

/**
 * How settled a story is. Set as a ruled tag in the same label type the desk slug
 * bars use.
 *
 * The struck square that used to sit to the left of the word is gone: it was
 * `aria-hidden`, so it said nothing to a screen reader, and it repeated in colour
 * what the word beside it already said in that same colour. The word carries the
 * status.
 */
export function VerificationBadge({ status }: { status: VerificationStatus }) {
  const tone = MARKS[status.toUpperCase()] ?? UNSETTLED;

  return (
    <Slug className={`inline-block border-b pb-1 ${tone.rule} ${tone.text}`}>{status}</Slug>
  );
}
