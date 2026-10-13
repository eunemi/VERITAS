import {
  TONE_TEXT,
  toneOf,
  type Annotation,
  type Exhibit,
  type Verdict,
  confidenceLabel,
} from "@/lib/types/agents";

const TITLE_TEXT: Record<Verdict["determination"], string> = {
  SUPPORTED: "✅ TRUE — SUPPORTED",
  CONTRADICTED: "❌ FALSE — CONTRADICTED",
  CONTESTED: "⚖ MIXED / CONTESTED",
  INSUFFICIENT: "⚠ UNVERIFIED",
  "REQUIRES VERIFICATION": "VERIFICATION REQUIRED",
  CONSISTENT: "CONSISTENT",
  CLEAR: "CLEAR",
  ANOMALOUS: "ANOMALIES FOUND",
  SYNTHETIC: "SYNTHETIC",
};

interface RationaleClaim {
  label: string;
  text: string;
}

/** Split the structured claim notes the semantic judge appends to its summary. */
function rationaleParts(rationale: string): {
  overview: string;
  claims: RationaleClaim[];
} {
  const markers = Array.from(rationale.matchAll(/\bClaim\s+\d+:/gi));
  if (markers.length === 0) return { overview: rationale, claims: [] };

  const first = markers[0].index ?? 0;
  return {
    overview: rationale.slice(0, first).trim(),
    claims: markers.map((marker, index) => {
      const start = marker.index ?? 0;
      const contentStart = start + marker[0].length;
      const end = markers[index + 1]?.index ?? rationale.length;
      return {
        label: marker[0].slice(0, -1),
        text: rationale.slice(contentStart, end).trim(),
      };
    }),
  };
}

export function Determination({
  verdict,
  signedBy,
  exhibits,
  annotations,
  scope = "Verification result",
}: {
  verdict: Verdict;
  signedBy: string;
  exhibits?: Exhibit[];
  annotations?: Annotation[];
  scope?: string;
}) {
  const parts = rationaleParts(verdict.rationale);
  const annotatedClaims = annotations ?? [];
  const hasSupportedClaim = annotatedClaims.some(
    (annotation) => toneOf(annotation.determination) === "clear",
  );
  const hasUnresolvedClaim = annotatedClaims.some(
    (annotation) => toneOf(annotation.determination) === "open",
  );
  const partiallyVerified =
    verdict.determination === "INSUFFICIENT" &&
    hasSupportedClaim &&
    hasUnresolvedClaim;
  const titleText = partiallyVerified
    ? "⚖ PARTIAL — SOME CLAIMS VERIFIED"
    : TITLE_TEXT[verdict.determination];
  const claimCounts = {
    clear: annotatedClaims.filter((annotation) => toneOf(annotation.determination) === "clear").length,
    open: annotatedClaims.filter((annotation) => toneOf(annotation.determination) === "open").length,
    adverse: annotatedClaims.filter((annotation) => toneOf(annotation.determination) === "adverse").length,
  };
  const claimSummary = [
    claimCounts.clear ? `${claimCounts.clear} supported` : null,
    claimCounts.adverse ? `${claimCounts.adverse} adverse` : null,
    claimCounts.open ? `${claimCounts.open} unresolved` : null,
  ].filter(Boolean).join(" · ");
  const claimRows =
    parts.claims.length > 0
      ? parts.claims
      : annotatedClaims.map((annotation) => ({
          label: `Claim ${annotation.ref}`,
          text: annotation.note || annotation.quote,
        }));

  return (
    <div className="border-t-2 border-ink-black bg-parchment px-5 pt-8 pb-10 sm:px-8">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        <p className="font-mono-label text-label text-ink-black/60 uppercase">{scope}</p>
        <h2 className="font-headline-md text-[clamp(26px,4vw,36px)] leading-tight font-bold uppercase tracking-wide text-ink-black">
          {titleText}
        </h2>
        
        <div className="font-body-md text-body-md font-bold text-ink-black">
          Assessment confidence: {confidenceLabel(verdict.determination, verdict.confidence)}
          <span className="ml-2 font-normal text-sm text-ink-black/55">
            (not a truth probability)
          </span>
        </div>
        {claimSummary ? (
          <p className="font-mono-label text-sm font-bold tracking-wider text-ink-black/65 uppercase">
            Claim coverage: {claimSummary}
          </p>
        ) : null}

        <div className="rounded-sm bg-ink-black/5 p-5 text-ink-black/85 sm:p-6">
          <p className="font-mono-label mb-3 text-sm font-bold tracking-wider uppercase">{verdict.headline}</p>
          <p className="font-body-md text-body-md leading-7">{parts.overview || verdict.rationale}</p>

          {claimRows.length > 0 ? (
            <div className="mt-5 border-t border-ink-black/15 pt-4">
              <p className="font-mono-label text-sm font-bold tracking-wider text-ink-black/60 uppercase">
                Claim-by-claim findings
              </p>
              <ol className="mt-2">
                {claimRows.map((claim, index) => {
                  const claimNumber = Number(claim.label.match(/\d+/)?.[0]);
                  const annotation = Number.isFinite(claimNumber)
                    ? annotatedClaims.find((item) => item.ref === claimNumber)
                    : annotatedClaims[index];
                  const tone = annotation ? toneOf(annotation.determination) : null;
                  return (
                    <li key={`${claim.label}-${index}`} className="border-t border-ink-black/12 py-3 first:border-t-0">
                      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                        <span className="font-mono-label text-sm font-bold tracking-wider uppercase">{claim.label}</span>
                        {annotation && tone ? (
                          <span className={`font-mono-label text-sm font-bold tracking-wider uppercase ${TONE_TEXT[tone]}`}>
                            {annotation.determination}
                          </span>
                        ) : null}
                      </div>
                      <p className="font-body-md text-body-md mt-1.5 leading-7">{claim.text}</p>
                    </li>
                  );
                })}
              </ol>
            </div>
          ) : null}
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
