import { Band, Slug } from "./layout";
import type { LedgerEntry } from "@/lib/types/agents";

/**
 * The counted facts of the record, ruled into columns and struck across the page
 * in ink. Everything here is a figure the desk actually counted — no scores, no
 * gauges. The rules are drawn by the grid's own gap, so no cell can be left with
 * a dangling edge at any width.
 */
export function LedgerBand({ entries }: { entries: LedgerEntry[] }) {
  return (
    <Band className="bg-ink-black text-parchment">
      <dl className="grid grid-cols-2 gap-px bg-parchment/15 sm:grid-cols-3 lg:grid-cols-6">
        {entries.map((entry) => (
          <div key={entry.key} className="bg-ink-black px-4 py-5">
            <dt>
              <Slug className="text-parchment/40">{entry.key}</Slug>
            </dt>
            <dd className="tabular font-headline-md mt-3 text-[26px] leading-none font-semibold text-parchment">
              {entry.value}
            </dd>
          </div>
        ))}
      </dl>
    </Band>
  );
}
