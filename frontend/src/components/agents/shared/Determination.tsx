import { type Verdict, type Exhibit } from "@/lib/types/agents";

export function Determination({
  verdict,
  signedBy,
  exhibits,
  scope = "Verification result",
}: {
  verdict: Verdict;
  signedBy: string;
  exhibits?: Exhibit[];
  scope?: string;
}) {
  const titleText = {
    SUPPORTED: "✅ TRUE — SUPPORTED",
    CONTRADICTED: "❌ FALSE — CONTRADICTED",
    CONTESTED: "⚖ MIXED / CONTESTED",
    INSUFFICIENT: "⚠ UNVERIFIED",
    "REQUIRES VERIFICATION": "VERIFICATION REQUIRED",
    CONSISTENT: "CONSISTENT",
    CLEAR: "CLEAR",
    ANOMALOUS: "ANOMALIES FOUND",
    SYNTHETIC: "SYNTHETIC",
  }[verdict.determination];


  return (
    <div className="border-t-2 border-ink-black bg-parchment px-5 pt-8 pb-10 sm:px-8">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        <p className="font-mono-label text-label text-ink-black/60 uppercase">{scope}</p>
        <h2 className="font-headline-md text-[clamp(26px,4vw,36px)] leading-tight font-bold uppercase tracking-wide text-ink-black">
          {titleText}
        </h2>
        
        <div className="font-body-md text-body-md font-bold text-ink-black">
          Assessment confidence: {verdict.confidence}
          <span className="ml-2 font-normal text-sm text-ink-black/55">
            (not a truth probability)
          </span>
        </div>

        <div className="font-proof text-[17px] leading-7 italic rounded-sm bg-ink-black/5 p-5 text-ink-black/85">
          <p className="font-mono-label mb-2 text-sm font-bold tracking-wider not-italic uppercase">{verdict.headline}</p>
          {verdict.rationale}
        </div>
        
        <p className="font-body-sm text-sm text-ink-black/50">
          Result from the {signedBy}.
        </p>

        {exhibits && exhibits.length > 0 && (
          <div className="mt-5 border-t border-ink-black/25 pt-5">
            <details className="group">
              <summary className="font-headline-md mb-3 flex cursor-pointer list-none items-center gap-2 text-lg font-bold text-ink-black">
                <span className="transform transition-transform group-open:rotate-90">▶</span>
                Sources (Exhibits)
              </summary>
              <ul className="mt-3 flex flex-col gap-3">
                {exhibits.map((exhibit, idx) => (
                  <li key={idx} className="border border-ink-black/15 bg-ink-black/5 p-3.5">
                    <div className="font-mono-label text-sm font-bold text-ink-black">{exhibit.source}</div>
                    <div className="font-proof mt-1.5 text-sm leading-relaxed text-ink-black/80">{exhibit.extract}</div>
                  </li>
                ))}
              </ul>
            </details>
          </div>
        )}
      </div>
    </div>
  );
}
