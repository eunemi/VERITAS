import { SectionHead } from "../shared/layout";
import {
  toneOf,
  type Annotation,
  type DeterminationTone,
} from "@/lib/types/agents";

/** Underline colour of a marked span, matched to the note in the margin. */
const TONE_MARK: Record<DeterminationTone, string> = {
  clear: "decoration-trust-green",
  open: "decoration-gold-foil",
  adverse: "decoration-secondary",
};

interface Piece {
  text: string;
  annotation: Annotation | null;
}

/**
 * Cut the copy at the quoted spans. The annotations quote the submitted copy
 * exactly, so each one is located by search rather than by stored offsets, and a
 * quote that cannot be found is simply left unmarked.
 */
function markUp(copy: string, annotations: Annotation[]): Piece[] {
  const located = annotations
    .map((annotation) => ({ annotation, at: copy.indexOf(annotation.quote) }))
    .filter((found) => found.at >= 0)
    .sort((a, b) => a.at - b.at);

  const pieces: Piece[] = [];
  let cursor = 0;

  for (const { annotation, at } of located) {
    if (at < cursor) continue;
    if (at > cursor) pieces.push({ text: copy.slice(cursor, at), annotation: null });
    pieces.push({ text: annotation.quote, annotation });
    cursor = at + annotation.quote.length;
  }
  if (cursor < copy.length) pieces.push({ text: copy.slice(cursor), annotation: null });

  return pieces;
}

/**
 * The galley proof.
 *
 * The copy you submitted, set in the paper's reading face and marked up in place:
 * every checkable claim underlined, and numbered to the note that answers it in
 * the margin. The findings are not a separate list — they are attached to the
 * words that caused them.
 */
export function GalleyProof({
  copy,
  annotations,
}: {
  copy: string;
  annotations: Annotation[];
}) {
  const pieces = markUp(copy, annotations);

  return (
    <section>
      <SectionHead title="Galley proof" note="Copy as submitted · marked in place" />
      <p className="font-proof text-proof mt-stack-md max-w-[68ch] whitespace-pre-wrap text-ink-black">
        {pieces.map((piece, index) =>
          piece.annotation ? (
            // The numeral sits outside the mark: text-decoration cannot be
            // switched off by a descendant, so an underlined sup is unavoidable
            // if it is nested.
            <span key={`${piece.annotation.ref}-${index}`}>
              <mark
                className={`bg-transparent text-ink-black underline decoration-2 underline-offset-[7px] ${
                  TONE_MARK[toneOf(piece.annotation.determination)]
                }`}
              >
                {piece.text}
              </mark>
              <sup className="font-mono-label ml-0.5 align-super text-[11px] font-bold tracking-normal text-secondary">
                {piece.annotation.ref}
              </sup>
            </span>
          ) : (
            <span key={index}>{piece.text}</span>
          ),
        )}
      </p>
    </section>
  );
}
