import { useState, useRef } from "react";
import { Drawer, type Dismiss } from "@/components/ui/Drawer";
import { convene, type Adjudication } from "@/lib/services/agentServices";
import { ExaminationTicker } from "@/components/agents/shared/ExaminationTicker";
import { extractTextFromFile } from "@/lib/api/client";

export function CommissionPanel({ close }: Dismiss) {
  const [inputType, setInputType] = useState<"text" | "image">("text");
  const [text, setText] = useState("");
  const [runningDesks, setRunningDesks] = useState<string[]>([]);
  const [step, setStep] = useState<"input" | "running" | "result">("input");
  const [result, setResult] = useState<Adjudication | null>(null);

  const [isExtracting, setIsExtracting] = useState(false);
  const [extractError, setExtractError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (file: File) => {
    if (!file) return;
    setIsExtracting(true);
    setExtractError(null);
    try {
      if (inputType === "text") {
        const extractedText = await extractTextFromFile(file);
        setText(extractedText);
      } else {
        const { uploadMediaFile } = await import("@/lib/api/client");
        const url = await uploadMediaFile(file);
        setText(url);
      }
    } catch (e: unknown) {
      const err = e as Error;
      setExtractError(err.message || "Failed to process file.");
    } finally {
      setIsExtracting(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleFileUpload(file);
    }
  };

  const handleSubmit = async () => {
    if (!text.trim()) return;
    setStep("running");
    setRunningDesks([]);
    try {
      const payload = inputType === "text" 
        ? { kind: "text" as const, content: text }
        : { kind: inputType, url: text };
      
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
              {(["text", "image"] as const).map((type) => (
                <button
                  key={type}
                  onClick={() => { setInputType(type); setText(""); }}
                  className={`font-mono-label uppercase text-sm pb-1 ${inputType === type ? 'border-b-2 border-ink-black font-bold' : 'text-ink-black/50 hover:text-ink-black'}`}
                >
                  {type}
                </button>
              ))}
            </div>

            

            {inputType === "text" ? (
              <div 
                className="relative"
                onDragOver={handleDragOver}
                onDrop={handleDrop}
              >
                <textarea
                  className="w-full h-48 p-4 border-2 border-ink-black bg-transparent font-serif-body focus:outline-none disabled:opacity-50"
                  placeholder="Paste the news article or text here..."
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  disabled={isExtracting}
                  data-first
                />
                
                {isExtracting && (
                  <div className="absolute inset-0 flex items-center justify-center bg-parchment/80 backdrop-blur-sm z-10 border-2 border-ink-black">
                    <span className="font-mono-label text-ink-black uppercase tracking-widest text-sm animate-pulse">Extracting text...</span>
                  </div>
                )}

                <>
                  <input 
                    type="file" 
                    ref={fileInputRef} 
                    className="hidden" 
                    accept=".pdf,.docx,.md,.txt"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleFileUpload(file);
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isExtracting}
                    className="absolute bottom-4 right-4 z-20 font-mono-label text-xs uppercase tracking-wider text-ink-black/50 hover:text-ink-black transition-colors disabled:opacity-50"
                    title="Upload text file"
                  >
                    [ UPLOAD FILE ]
                  </button>
                </>
              </div>
            ) : inputType === "image" ? (
              <div 
                className="relative w-full h-48 flex flex-col items-center justify-center border-2 border-ink-black/20 bg-ink-black/5 overflow-hidden"
                onDragOver={handleDragOver}
                onDrop={handleDrop}
              >
                {text ? (
                  <img src={text} alt="Uploaded" className="max-h-full max-w-full object-contain" />
                ) : (
                  <span className="font-mono-label text-ink-black/50 uppercase tracking-widest text-center px-4">Drop image here or click to upload</span>
                )}
                
                <input 
                  type="file" 
                  className="absolute inset-0 opacity-0 cursor-pointer"
                  accept="image/*"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileUpload(file);
                  }}
                  disabled={isExtracting}
                />

                {isExtracting && (
                  <div className="absolute inset-0 flex items-center justify-center bg-parchment/80 backdrop-blur-sm z-10 border-2 border-ink-black">
                    <span className="font-mono-label text-ink-black uppercase tracking-widest text-sm animate-pulse">Uploading...</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="w-full h-48 flex items-center justify-center border-2 border-ink-black/20 bg-ink-black/5">
                <span className="font-mono-label text-ink-black/50 uppercase tracking-widest">Coming Soon</span>
              </div>
            )}

            {extractError && (
              <div className="font-body-sm text-sm text-red-600 mt-[-1rem]">
                {extractError}
              </div>
            )}
            
            <button
              onClick={handleSubmit}
              disabled={isExtracting || (inputType !== "text" && inputType !== "image") || !text.trim()}
              className="bg-ink-black text-parchment py-3 px-6 font-mono-label hover:bg-ink-black/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
            
            

            <p className="font-serif-body text-lg italic bg-ink-black/5 p-4 rounded">
              {result.decision.verdict.rationale}
            </p>
            
            <div className="mt-8 border-t-2 border-ink-black pt-6">
              <details className="group">
                <summary className="text-xl font-bold font-serif-heading mb-4 cursor-pointer list-none flex items-center gap-2">
                  <span className="transform transition-transform group-open:rotate-90">▶</span>
                  Extracted Text & Sources
                </summary>
                <div className="flex flex-col gap-4 mt-4">
                  {(() => {
                    const imageDesk = result.examination.filings.find(f => f.desk === "image");
                    if (imageDesk && "extractedText" in imageDesk.record && imageDesk.record.extractedText) {
                      return (
                        <div className="border border-ink-black/20 p-4 bg-ink-black/5">
                          <div className="font-bold font-mono-label text-ink-black">OCR Extracted Text</div>
                          <div className="font-serif-body text-sm mt-2 leading-relaxed whitespace-pre-wrap">{imageDesk.record.extractedText}</div>
                        </div>
                      );
                    }
                    return null;
                  })()}
                  {(() => {
                    const factCheckDesk = result.examination.filings.find(f => f.desk === "fact-check");
                    if (factCheckDesk && "exhibits" in factCheckDesk.record && factCheckDesk.record.exhibits.length > 0) {
                      return factCheckDesk.record.exhibits.map((exhibit, idx) => (
                        <div key={idx} className="border border-ink-black/20 p-4 bg-ink-black/5">
                          <div className="font-bold font-mono-label text-ink-black">{exhibit.source}</div>
                          <div className="font-serif-body text-sm mt-2 leading-relaxed">{exhibit.extract}</div>
                        </div>
                      ));
                    }
                    
                    const hasExtractedText = result.examination.filings.find(f => f.desk === "image" && "extractedText" in f.record && !!f.record.extractedText);
                    if (!hasExtractedText) {
                      return <p className="font-serif-body italic opacity-70">No external sources were referenced.</p>;
                    }
                    return null;
                  })()}
                </div>
              </details>
            </div>
          </div>
        )}
      </div>
    </Drawer>
  );
}
