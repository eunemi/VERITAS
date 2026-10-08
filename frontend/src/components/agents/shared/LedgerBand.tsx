import { Slug } from "./layout";
import type { LedgerEntry } from "@/lib/types/agents";

export function LedgerBand({ entries }: { entries: LedgerEntry[] }) {
  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <dl className="grid grid-cols-2 gap-8 sm:grid-cols-4 lg:grid-cols-6 border-b-2 border-ink-black/10 pb-8">
        {entries.map((entry) => (
          <div key={entry.key} className="flex flex-col gap-2">
            <dt>
              <Slug className="text-ink-black/50 tracking-wider uppercase text-xs">{entry.key}</Slug>
            </dt>
            <dd className="tabular font-headline-md text-3xl leading-none font-semibold text-ink-black">
              {entry.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
