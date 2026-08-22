"use client";

import React, { useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { IntelligenceAgent } from "@/components/ui/IntelligenceAgent";

type Status = "IDLE" | "ANALYZING" | "COMPLETE";

export default function InvestigatePage() {
  const [status, setStatus] = useState<Status>("IDLE");
  const [activeTab, setActiveTab] = useState<"TEXT" | "IMAGE" | "AUDIO" | "VIDEO">("TEXT");

  const handleInvestigate = () => {
    setStatus("ANALYZING");
    setTimeout(() => {
      setStatus("COMPLETE");
    }, 4000);
  };

  return (
    <main className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-8 min-h-screen flex flex-col">
      <PageHeader 
        label="SUBMIT EVIDENCE" 
        headline={<>INVESTIGATE<br />THE STORY.</>}
        subheadline="Submit text, images, audio or video. VERITAS will analyze the available evidence using specialized AI agents."
      />

      {status === "IDLE" && (
        <section className="flex-1 flex flex-col mt-stack-lg mb-stack-xl max-w-4xl mx-auto w-full">
          {/* Tabs */}
          <div className="flex border-b border-primary/20 mb-8">
            {(["TEXT", "IMAGE", "AUDIO", "VIDEO"] as const).map((tab) => (
              <button 
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 py-4 font-mono-label text-sm uppercase transition-colors relative ${
                  activeTab === tab ? "text-primary font-bold" : "text-on-surface-variant hover:text-primary"
                }`}
              >
                {tab}
                {activeTab === tab && (
                  <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-secondary" />
                )}
              </button>
            ))}
          </div>

          {/* Upload Area */}
          <div className="flex-1 flex flex-col min-h-[400px] border border-primary/20 bg-parchment/30 relative">
            {activeTab === "TEXT" && (
              <textarea 
                className="w-full flex-1 bg-transparent resize-none outline-none p-8 font-body-lg text-primary placeholder:text-primary/30"
                placeholder="PASTE ARTICLE OR CLAIM HERE..."
              />
            )}
            
            {activeTab !== "TEXT" && (
              <div className="flex-1 flex flex-col items-center justify-center p-8 text-center cursor-pointer hover:bg-parchment/50 transition-colors border-dashed border-2 border-transparent hover:border-primary/20 m-4">
                <span className="material-symbols-outlined text-6xl text-primary/30 mb-4">
                  {activeTab === "IMAGE" ? "image" : activeTab === "AUDIO" ? "graphic_eq" : "movie"}
                </span>
                <span className="font-headline-md text-2xl text-primary mb-2">
                  DROP YOUR STORY HERE
                </span>
                <span className="font-mono-label text-xs text-on-surface-variant uppercase">
                  OR SELECT FILE
                </span>
                <div className="mt-4 flex gap-2 font-mono-label text-[10px] text-primary/40 uppercase">
                  {activeTab === "IMAGE" && "SUPPORTED: JPG, PNG, WEBP"}
                  {activeTab === "AUDIO" && "SUPPORTED: MP3, WAV, M4A"}
                  {activeTab === "VIDEO" && "SUPPORTED: MP4, MOV, WEBM"}
                </div>
              </div>
            )}
          </div>

          {/* Action */}
          <div className="mt-8 flex justify-end">
            <button 
              onClick={handleInvestigate}
              className="bg-ink-black text-parchment font-mono-label text-sm px-8 py-4 border border-ink-black hover:bg-transparent hover:text-ink-black transition-all duration-300 flex items-center gap-2 group"
            >
              BEGIN INVESTIGATION 
              <span className="material-symbols-outlined text-sm group-hover:translate-x-1 transition-transform">arrow_forward</span>
            </button>
          </div>
        </section>
      )}

      {status !== "IDLE" && (
        <section className="flex-1 flex flex-col mt-stack-lg mb-stack-xl max-w-4xl mx-auto w-full">
          <div className="flex flex-col items-center justify-center text-center mb-12">
            <span className="font-mono-label text-sm text-secondary uppercase tracking-widest mb-4">
              {status === "ANALYZING" ? "ANALYSIS IN PROGRESS" : "ANALYSIS COMPLETE"}
            </span>
            <h2 className="font-headline-md text-4xl text-primary font-bold">
              {status === "ANALYZING" ? "VERITAS is processing evidence." : "Final verdict reached."}
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
            <IntelligenceAgent 
              name="TEXT AGENT"
              description="Cross-referencing claims and rhetorical structures."
              icon="subject"
              status={status === "ANALYZING" ? "ANALYZING" : "COMPLETE"}
              route="/intel/text"
            />
            <IntelligenceAgent 
              name="IMAGE AGENT" description="Checking for synthetic artifacts." icon="image"
              status={status === "ANALYZING" ? "ANALYZING" : "COMPLETE"}
              route="/intel/image"
            />
            <IntelligenceAgent 
              name="FACT-CHECK AGENT"
              description="Querying immutable ledgers and verified sources."
              icon="fact_check"
              status={status === "ANALYZING" ? "ANALYZING" : "COMPLETE"}
              route="/intel/fact-check"
            />
            <IntelligenceAgent 
              name="DECISION AGENT" description="Synthesizing final verdict." icon="gavel"
              status={status === "ANALYZING" ? "WAITING" : "COMPLETE"}
              route="/intel/decision"
            />
          </div>

          {status === "COMPLETE" && (
            <div className="border border-primary/20 p-8 flex flex-col items-center text-center bg-parchment animate-in fade-in zoom-in duration-500">
              <span className="font-mono-label text-sm text-alert-crimson uppercase tracking-widest mb-2">VERDICT</span>
              <h3 className="font-masthead text-5xl md:text-7xl text-primary font-black mb-4">FAKE NEWS</h3>
              <div className="flex gap-8 mb-8 border-t border-primary/20 pt-4">
                 <div className="flex flex-col">
                   <span className="font-mono-label text-[10px] text-on-surface-variant uppercase">CONFIDENCE SCORE</span>
                   <span className="font-mono-label text-2xl font-bold text-primary">98.5%</span>
                 </div>
                 <div className="flex flex-col">
                   <span className="font-mono-label text-[10px] text-on-surface-variant uppercase">PRIMARY FLAG</span>
                   <span className="font-mono-label text-2xl font-bold text-secondary">SYNTHETIC AUDIO</span>
                 </div>
              </div>
              <p className="font-body-md text-on-surface-variant max-w-2xl text-left border-l-2 border-secondary pl-4 italic">
                Reason for prediction: The provided audio sample exhibits spectral phase inconsistencies matching known generative AI architectures. Furthermore, cross-referencing the claimed event with trusted news databases returned zero verified corroborations.
              </p>
              
              <button 
                onClick={() => setStatus("IDLE")}
                className="mt-8 font-mono-label text-xs font-bold text-primary border-b border-primary hover:text-secondary hover:border-secondary transition-colors uppercase py-1"
              >
                ← START NEW INVESTIGATION
              </button>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
