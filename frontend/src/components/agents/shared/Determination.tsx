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
    <div className="border-t-2 border-ink-black bg-parchment pt-10 pb-16 px-6">
      <div className="max-w-3xl mx-auto flex flex-col gap-6">
        <p className="font-mono-label text-sm uppercase tracking-wider text-ink-black/60">{scope}</p>
        <h2 className="text-4xl font-bold font-serif-heading uppercase tracking-wide text-ink-black">
          {titleText}
        </h2>
        
        {verdict.confidenceValue > 0 && verdict.determination !== "INSUFFICIENT" && (
          <div className="text-lg font-serif-body font-bold text-ink-black">
            Assessment confidence: {verdict.confidence}
          </div>
        )}

        <div className="font-serif-body text-lg italic bg-ink-black/5 p-6 rounded text-ink-black/85">
          <p className="font-bold mb-2 uppercase text-sm font-mono-label tracking-wider not-italic">{verdict.headline}</p>
          {verdict.rationale}
        </div>
        
        <p className="font-body-sm text-sm text-ink-black/50">
          Result from the {signedBy}.
        </p>

        {exhibits && exhibits.length > 0 && (
          <div className="mt-8 border-t-2 border-ink-black pt-6">
            <details className="group">
              <summary className="text-xl font-bold font-serif-heading mb-4 cursor-pointer list-none flex items-center gap-2 text-ink-black">
                <span className="transform transition-transform group-open:rotate-90">▶</span>
                Sources (Exhibits)
              </summary>
              <ul className="flex flex-col gap-4 mt-4">
                {exhibits.map((exhibit, idx) => (
                  <li key={idx} className="border border-ink-black/20 p-4 bg-ink-black/5">
                    <div className="font-bold font-mono-label text-ink-black">{exhibit.source}</div>
                    <div className="font-serif-body text-sm mt-2 leading-relaxed text-ink-black/80">{exhibit.extract}</div>
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
