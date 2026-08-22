"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { SectionHead, Slug, Spread } from "@/components/agents/shared/layout";
import { PageHeader } from "@/components/ui/PageHeader";
import { ARCHIVE, facetsOf, filedOn, yearOf, type ArchiveRecord } from "@/lib/archive";
import { DESK_ISSUE, DESKS } from "@/lib/desks";
import { TONE_TEXT, toneOf } from "@/lib/types/agents";

/**
 * The record index.
 *
 * Search and the three facets work on the records themselves — the previous
 * version of this page had a search field, five filter buttons and four year
 * buttons, none of which were wired to anything, over three records typed into
 * the markup. The facet values are read off the data, so a filter cannot offer a
 * year or a desk the index does not hold.
 */

const ALL = "all";

/** Two-digit count, the way a printed index sets small figures. */
function figure(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function matches(record: ArchiveRecord, query: string): boolean {
  if (!query) return true;
  const needle = query.toLowerCase();
  return [
    record.id,
    record.headline,
    record.standfirst,
    record.source,
    record.region,
    record.determination,
    record.artifact,
    DESKS[record.desk]?.name ?? "",
  ].some((field) => field.toLowerCase().includes(needle));
}

/** A ruled facet. A real select, set in the index's own label type. */
function Facet({
  label,
  value,
  onChange,
  options,
  allLabel,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  /** What the unfiltered state is called, e.g. "Every year". */
  allLabel: string;
}) {
  return (
    <label className="block">
      {/* The three words naming each filter were set at 40% ink, which is 2.5:1 on
          this ground — the control was legible and its label was not. */}
      <Slug className="block text-ink-black">{label}</Slug>
      <span className="relative mt-2 block">
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="font-body-md text-body-md w-full cursor-pointer appearance-none border-b border-ink-black/40 bg-transparent py-1.5 pr-6 text-ink-black transition-colors hover:border-ink-black focus:border-secondary focus:outline-none"
        >
          <option value={ALL}>{allLabel}</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <span
          aria-hidden
          className="pointer-events-none absolute right-1 bottom-2.5 text-[11px] leading-none text-ink-black/70"
        >
          &#9662;
        </span>
      </span>
    </label>
  );
}

/**
 * One record on the index.
 *
 * A row used to print ten separately-styled pieces across four columns at six
 * different ink levels, including a coloured hairline that repeated in colour
 * exactly what the determination beside it already said in that colour. It is
 * three columns now — the file, the record, the finding — and the provenance is
 * one line rather than three stacked fragments.
 */
function IndexRow({ record }: { record: ArchiveRecord }) {
  const desk = DESKS[record.desk];
  const tone = toneOf(record.determination);

  return (
    <li className="border-t border-ink-black/25 py-stack-md">
      <div className="grid gap-stack-sm lg:grid-cols-12 lg:gap-gutter">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 lg:col-span-2 lg:flex-col lg:gap-y-2">
          <Slug className="tabular text-ink-black">{record.id}</Slug>
          <Slug className="tabular text-ink-black/70">{filedOn(record.filed)}</Slug>
        </div>

        <div className="lg:col-span-7">
          <h3 className="font-headline-md text-[21px] leading-[1.3] font-semibold text-ink-black">
            {record.headline}
          </h3>
          <p className="font-body-md text-read mt-2 max-w-measure text-ink-black/70">
            {record.standfirst}
          </p>
          <Slug className="mt-stack-sm block text-ink-black/70">
            {record.artifact} · {record.source} · {record.region}
          </Slug>
        </div>

        <div className="lg:col-span-3">
          <Slug className={`block ${TONE_TEXT[tone]}`}>{record.determination}</Slug>
          <p className="font-body-sm text-body-sm mt-1.5 text-ink-black/70">
            Confidence <span className="tabular text-ink-black">{record.confidence}</span>
          </p>
          {desk ? (
            <Link
              href={`/intel/${desk.id}`}
              className="mt-stack-sm inline-block border-b border-ink-black/40 pb-0.5 text-ink-black transition-colors hover:border-secondary hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              <Slug>Signed at {desk.name}</Slug>
            </Link>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function ArchiveIndex() {
  const [query, setQuery] = useState("");
  const [year, setYear] = useState(ALL);
  const [desk, setDesk] = useState(ALL);
  const [determination, setDetermination] = useState(ALL);

  const facets = useMemo(() => facetsOf(ARCHIVE), []);

  const results = useMemo(
    () =>
      ARCHIVE.filter(
        (record) =>
          matches(record, query.trim()) &&
          (year === ALL || yearOf(record.filed) === year) &&
          (desk === ALL || record.desk === desk) &&
          (determination === ALL || record.determination === determination),
      ),
    [query, year, desk, determination],
  );

  /* Grouped in filing order rather than sorted again: the index is printed the
     way the records were signed. */
  const groups = useMemo(() => {
    const byYear = new Map<string, ArchiveRecord[]>();
    for (const record of results) {
      const key = yearOf(record.filed);
      const rows = byYear.get(key);
      if (rows) rows.push(record);
      else byYear.set(key, [record]);
    }
    return Array.from(byYear.entries());
  }, [results]);

  const filtered = query.trim() !== "" || year !== ALL || desk !== ALL || determination !== ALL;

  function clear() {
    setQuery("");
    setYear(ALL);
    setDesk(ALL);
    setDetermination(ALL);
  }

  return (
    <main className="min-h-screen bg-background">
      <PageHeader
        section="The archive"
        standing="Index of signed records"
        kicker={`${figure(ARCHIVE.length)} records · ${facets.years.length} years`}
        title={["Everything", "we have signed."]}
        lede="Every examination stays on the index, including the ones that found nothing and the ones the desks could not settle."
      />

      <Spread className="pb-stack-lg">
        <form role="search" onSubmit={(event) => event.preventDefault()}>
          {/* The field was a 38px italic serif, which is display type doing an
              input's job: it outranked every headline on the index below it, and
              the prompt inside it sat at 30% ink. It is set in the body face at
              reading size, with the placeholder readable. */}
          <div className="border-b-2 border-ink-black pb-2 transition-colors focus-within:border-secondary">
            <label htmlFor="archive-search" className="sr-only">
              Search the record index
            </label>
            <input
              id="archive-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search headlines, sources, regions or file numbers…"
              className="font-body-lg text-lede w-full bg-transparent text-ink-black placeholder:text-ink-black/65 focus:outline-none"
            />
          </div>

          <div className="mt-stack-md grid gap-stack-md sm:grid-cols-3 sm:gap-gutter">
            <Facet
              label="Year filed"
              value={year}
              onChange={setYear}
              allLabel="Every year"
              options={facets.years.map((value) => ({ value, label: value }))}
            />
            <Facet
              label="Desk"
              value={desk}
              onChange={setDesk}
              allLabel="Every desk"
              options={facets.desks.map((value) => ({
                value,
                label: DESKS[value]?.name ?? value,
              }))}
            />
            <Facet
              label="Determination"
              value={determination}
              onChange={setDetermination}
              allLabel="Any determination"
              options={facets.determinations.map((value) => ({ value, label: value }))}
            />
          </div>
        </form>

        <div className="mt-stack-md flex flex-wrap items-baseline justify-between gap-4 border-t border-ink-black/25 pt-stack-sm">
          <Slug className="tabular text-ink-black/70" aria-live="polite">
            Showing {figure(results.length)} of {figure(ARCHIVE.length)} records
          </Slug>
          {filtered ? (
            <button
              type="button"
              onClick={clear}
              className="cursor-pointer border-b-2 border-secondary pb-1 transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              <Slug className="text-secondary">Clear the search</Slug>
            </button>
          ) : null}
        </div>
      </Spread>

      <Spread className="pb-stack-xl">
        {groups.length === 0 ? (
          <div className="border-t-2 border-ink-black py-stack-lg">
            <Slug className="text-ink-black/70">Nothing on the index</Slug>
            <p className="font-headline-md mt-stack-sm text-[24px] leading-[1.25] font-semibold text-ink-black">
              No signed record matches that.
            </p>
            <p className="font-body-md text-read mt-stack-sm max-w-measure text-ink-black/70">
              Try a shorter search, widen a filter, or{" "}
              <Link
                href="/investigate"
                className="border-b border-secondary text-ink-black transition-colors hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
              >
                commission an examination
              </Link>{" "}
              of your own artifact.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-stack-lg">
            {groups.map(([groupYear, rows]) => (
              <section key={groupYear}>
                <SectionHead title={groupYear} note={`${figure(rows.length)} records filed`} />
                <ol className="mt-stack-md">
                  {rows.map((record) => (
                    <IndexRow key={record.id} record={record} />
                  ))}
                </ol>
              </section>
            ))}
          </div>
        )}
      </Spread>

      <Spread>
        <div className="border-t border-ink-black/25 pt-stack-sm pb-stack-lg">
          <Slug className="text-ink-black/70">Colophon</Slug>
          <p className="font-body-md text-body-md mt-2.5 max-w-measure text-ink-black/70">
            Set at the Veritas archive · Issue <span className="tabular">{DESK_ISSUE}</span>. The
            examination model is not attached yet, so the records on this index are fixtures held in
            the shape the real index will take, and the full text of each record is not published:
            every entry leads to the desk that signed it, where you can put the same kind of
            artifact through the same examination.
          </p>
        </div>
      </Spread>
    </main>
  );
}
