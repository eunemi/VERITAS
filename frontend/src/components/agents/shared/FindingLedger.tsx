import { Slug, surfaceOf } from "./layout";
import {
  TONE_RULE,
  TONE_TEXT,
  toneOf,
  type Annotation,
  type Signal,
} from "@/lib/types/agents";

/**
 * The examiner's margin.
 *
 * Each finding hangs off the exhibit number that is also printed on the artifact
 * itself, so a note and the thing it refers to are always two ends of the same
 * pointer. Nothing here is a card; it is a ruled column of marginalia.
 */
export function FindingLedger({
  annotations,
  title = "Marginalia",
  showQuote = true,
}: {
  annotations: Annotation[];
  title?: string;
  /** Off when the artifact already shows the quoted span in place. */
  showQuote?: boolean;
}) {
  return (
    <section>
      <div className="flex items-baseline justify-between border-t-2 border-ink-black pt-stack-sm">
        <Slug>{title}</Slug>
        <Slug className="tabular text-ink-black/40">
          {String(annotations.length).padStart(2, "0")} marked
        </Slug>
      </div>

      <ol className="mt-stack-sm">
        {annotations.map((annotation) => {
          const tone = toneOf(annotation.determination);
          return (
            <li
              key={annotation.ref}
              className="grid grid-cols-[30px_1fr] gap-x-3.5 border-t border-ink-black/12 py-stack-md first:border-t-0 first:pt-0"
            >
              <span
                aria-hidden
                className="tabular font-headline-md text-[30px] leading-[0.8] font-bold text-secondary"
              >
                {annotation.ref}
              </span>
              <div>
                {showQuote ? (
                  <Slug className="block text-ink-black/45">{annotation.quote}</Slug>
                ) : null}
                <p
                  className={`font-proof text-proof text-ink-black/85 ${showQuote ? "mt-2.5" : ""}`}
                >
                  {annotation.note}
                </p>
                <span className="mt-3 flex items-center gap-2.5">
                  <span aria-hidden className={`h-[2px] w-6 ${TONE_RULE[tone]}`} />
                  <Slug className={TONE_TEXT[tone]}>{annotation.determination}</Slug>
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/**
 * Measured readings, set as leader rows. The hairline between label and figure
 * is itself the measurement — it fills to the reading's weight — so there is no
 * separate chart to decorate.
 */
export function SignalTable({
  signals,
  title,
  inverted = false,
}: {
  signals: Signal[];
  title: string;
  inverted?: boolean;
}) {
  const surface = surfaceOf(inverted);
  const fill = inverted ? "bg-gold-foil" : "bg-ink-black";

  return (
    <section>
      <div
        className={`flex items-baseline justify-between border-t-2 pt-stack-sm ${
          inverted ? "border-parchment/50" : "border-ink-black"
        }`}
      >
        <Slug className={surface.text}>{title}</Slug>
        <Slug className={surface.faint}>Reading</Slug>
      </div>

      <ul className="mt-1">
        {signals.map((signal) => (
          <li
            key={signal.label}
            className={`flex items-baseline gap-4 border-t py-3.5 ${surface.rule}`}
          >
            <span className={`font-body-sm text-body-sm shrink-0 ${surface.text}`}>
              {signal.label}
            </span>
            <span className={`relative top-[-4px] h-px flex-1 ${surface.ruleBg}`}>
              <span
                aria-hidden
                className={`absolute top-[-1px] left-0 h-[3px] ${fill}`}
                style={{ width: `${Math.round(Math.min(1, Math.max(0, signal.weight)) * 100)}%` }}
              />
            </span>
            <span
              className={`tabular font-mono-label w-[86px] shrink-0 text-right text-[11px] tracking-[0.12em] ${surface.text}`}
            >
              {signal.reading}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
