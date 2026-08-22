import { Slug } from "./layout";
import type { DeskDefinition } from "@/lib/desks";

/**
 * What this desk does, and — as importantly — what it doesn't. Four hanging rows
 * next to the masthead, so the scope of the examination is on the page before
 * anyone submits anything to it.
 */
export function MethodNote({ desk }: { desk: DeskDefinition }) {
  return (
    <div>
      <div className="flex items-baseline justify-between border-t-2 border-ink-black pt-stack-sm">
        <Slug>Method</Slug>
        <Slug className="tabular text-ink-black/40">File {desk.file}</Slug>
      </div>
      <dl className="mt-stack-sm">
        {desk.method.map((row) => (
          <div
            key={row.key}
            className="flex items-baseline gap-4 border-t border-ink-black/12 py-2.5"
          >
            <dt className="w-[74px] shrink-0">
              <Slug className="text-ink-black/40">{row.key}</Slug>
            </dt>
            <dd className="font-body-sm text-body-sm text-ink-black/75">{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/**
 * The desk's masthead. The title is set as separate lines — the second in
 * italic — the way a standing head is set in the paper, and the standfirst
 * explains the desk in one sentence of plain English.
 */
export function DeskMasthead({ desk }: { desk: DeskDefinition }) {
  return (
    <header className="grid gap-stack-lg pt-stack-lg pb-stack-md lg:grid-cols-12 lg:gap-gutter">
      <div className="lg:col-span-8">
        <Slug className="text-secondary">{desk.eyebrow}</Slug>
        <h1 className="mt-stack-sm font-masthead text-[clamp(46px,8.5vw,100px)] leading-[0.92] font-black tracking-[-0.025em] text-ink-black">
          {desk.titleLines.map((line, index) => (
            <span
              key={line}
              className={index === 0 ? "block" : "block pl-[0.06em] font-normal italic"}
            >
              {line}
            </span>
          ))}
        </h1>
        <p className="mt-stack-md max-w-[52ch] font-headline-md text-[19px] leading-[31px] font-normal text-ink-black/70 italic">
          {desk.standfirst}
        </p>
      </div>
      <div className="lg:col-span-4 lg:pt-3">
        <MethodNote desk={desk} />
      </div>
    </header>
  );
}
