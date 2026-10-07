import { useState } from "react";
import { Drawer, type Dismiss } from "@/components/ui/Drawer";
import { convene, type Adjudication } from "@/lib/services/agentServices";
import { ExaminationTicker } from "@/components/agents/shared/ExaminationTicker";

export function CommissionPanel({ close }: Dismiss) {
  const [inputType, setInputType] = useState<"text" | "image" | "audio" | "video">("text");
  const [text, setText] = useState("");
  const [runningDesks, setRunningDesks] = useState<string[]>([]);
  const [step, setStep] = useState<"input" | "running" | "result">("input");
  const [result, setResult] = useState<Adjudication | null>(null);

  const handleSubmit = async () => {
    if (!text.trim()) return;
    setStep("running");
    setRunningDesks([]);
    try {
      const payload = inputType === "text" 
        ? { kind: "text" as const, content: text }
        : inputType === "video" 
          ? { kind: "audio" as const, url: text } // route video to audio
          : { kind: inputType, url: text };
      
      const adjudication = await convene(payload as any, {
        onReading: (record) => {
          const active = record.desks
            .filter((d) => d.status === "running")
            .map((d) => d.desk);
          setRunningDesks(active);
        }
      });
      setResult(adjudication);
      setStep("result");
    } catch (e) {
      console.error(e);
      setStep("input");
    }
  };

  return (
    <Drawer onClose={close} labelledBy="commission-heading" standing="Analysis">
      <div className="p-8 max-w-2xl mx-auto min-h-[50vh]">
        {step === "input" && (
          <div className="flex flex-col gap-6">
            <h2 id="commission-heading" className="text-2xl font-bold font-serif-heading">Submit News for Verification</h2>
            
            <div className="flex gap-4 border-b border-ink-black/20 pb-2">
              {(["text", "image", "audio", "video"] as const).map((type) => (
                <button
                  key={type}
                  onClick={() => { setInputType(type); setText(""); }}
                  className={`font-mono-label uppercase text-sm pb-1 ${inputType === type ? 'border-b-2 border-ink-black font-bold' : 'text-ink-black/50 hover:text-ink-black'}`}
                >
                  {type}
                </button>
              ))}
            </div>

            {inputType === "video" && (
              <div className="bg-gold-foil/20 p-4 font-serif-body text-sm italic">
                Notice: Visual content analysis is coming soon. The audio track of this video will be extracted and analyzed.
              </div>
            )}

            <textarea
              className="w-full h-48 p-4 border-2 border-ink-black bg-transparent font-serif-body focus:outline-none"
              placeholder={inputType === "text" ? "Paste the news article or text here..." : `Paste the ${inputType} URL here...`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              data-first
            />
            
            <button
              onClick={handleSubmit}
              className="bg-ink-black text-parchment py-3 px-6 font-mono-label hover:bg-ink-black/80 transition-colors"
            >
              ANALYZE NOW
            </button>
          </div>
        )}
        {step === "running" && (
          <div className="flex flex-col gap-4">
            <h2 id="commission-heading" className="sr-only">Running Verification</h2>
            <div className="my-8">
              <ExaminationTicker stages={["Reading input", "Extracting claims", "Evaluating evidence", "Adjudicating"]} durationMs={8000} />
              
              <div className="mt-8 border border-ink-black/20 p-4 bg-ink-black/5 rounded">
                <h3 className="font-mono-label text-sm uppercase text-ink-black mb-2">Live Progress</h3>
                <div className="font-serif-body text-ink-black/80">
                  {runningDesks.length > 0 
                    ? `Currently active desks: ${runningDesks.join(', ')}`
                    : "Initializing analysis..."}
                </div>
              </div>
            </div>
          </div>
        )}
        {step === "result" && result && (
          <div className="flex flex-col gap-6">
            <h2 id="commission-heading" className="text-4xl font-bold font-serif-heading uppercase tracking-wide">
              {["SUPPORTED", "CONSISTENT", "CLEAR"].includes(result.decision.verdict.determination) ? "✅ TRUE" : 
               ["CONTRADICTED", "CONTESTED", "ANOMALOUS", "SYNTHETIC"].includes(result.decision.verdict.determination) ? "❌ FALSE" : 
               "⚠️ UNVERIFIED"}
            </h2>
            <div className="text-lg font-serif-body font-bold">
              Confidence: {result.decision.verdict.confidence}
            </div>
            
            {inputType === "video" && (
              <div className="bg-gold-foil/20 p-3 font-serif-body text-sm italic">
                Note: This result is based on audio track analysis only.
              </div>
            )}

            <p className="font-serif-body text-lg italic bg-ink-black/5 p-4 rounded">
              {result.decision.verdict.rationale}
            </p>
            
            <div className="mt-8 border-t-2 border-ink-black pt-6">
              <details className="group">
                <summary className="text-xl font-bold font-serif-heading mb-4 cursor-pointer list-none flex items-center gap-2">
                  <span className="transform transition-transform group-open:rotate-90">▶</span>
                  Sources (Exhibits)
                </summary>
                <ul className="flex flex-col gap-4 mt-4">
                  {(() => {
                    const factCheckDesk = result.examination.filings.find(f => f.desk === "fact-check");
                    if (factCheckDesk && "exhibits" in factCheckDesk.record && factCheckDesk.record.exhibits.length > 0) {
                      return factCheckDesk.record.exhibits.map((exhibit, idx) => (
                        <li key={idx} className="border border-ink-black/20 p-4 bg-ink-black/5">
                          <div className="font-bold font-mono-label text-ink-black">{exhibit.source}</div>
                          <div className="font-serif-body text-sm mt-2 leading-relaxed">{exhibit.extract}</div>
                        </li>
                      ));
                    }
                    return <p className="font-serif-body italic opacity-70">No external sources were referenced.</p>;
                  })()}
                </ul>
              </details>
            </div>
          </div>
        )}
      </div>
    </Drawer>
  );
}
