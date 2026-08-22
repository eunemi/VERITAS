"use client";

import React, { useState } from "react";
import { AgentBreadcrumb } from "@/components/agents/shared/AgentBreadcrumb";
import { AgentHeader } from "@/components/agents/shared/AgentHeader";
import { AgentNavigation } from "@/components/agents/shared/AgentNavigation";
import { InputWorkspace } from "@/components/agents/shared/InputWorkspace";
import { AnalysisProgress } from "@/components/agents/shared/AnalysisProgress";
import { MetricGrid } from "@/components/agents/shared/MetricGrid";
import { EditorialDivider } from "@/components/agents/shared/EditorialDivider";
import { factCheckClaim } from "@/lib/services/agentServices";

const FACT_CHECK_STAGES = [
  "CLAIM IDENTIFICATION",
  "SOURCE DISCOVERY",
  "EVIDENCE RETRIEVAL",
  "SOURCE COMPARISON",
  "CLAIM ASSESSMENT",
  "EVIDENCE SYNTHESIS"
];

export default function FactCheckAgentPage() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentStage, setCurrentStage] = useState(0);
  const [results, setResults] = useState<any>(null);

  const handleAnalyze = async (claim: string) => {
    setIsAnalyzing(true);
    setResults(null);
    setCurrentStage(0);

    const interval = setInterval(() => {
      setCurrentStage((prev) => {
        if (prev >= FACT_CHECK_STAGES.length - 1) {
          clearInterval(interval);
          return prev;
        }
        return prev + 1;
      });
    }, 600);

    const data = await factCheckClaim(claim);
    
    setTimeout(() => {
      setResults(data);
      setCurrentStage(FACT_CHECK_STAGES.length);
      setIsAnalyzing(false);
    }, 1000);
  };

  return (
    <main className="w-full min-h-screen bg-parchment pb-stack-xl">
      <AgentBreadcrumb agentNumber="AGENT_05" agentName="FACT-CHECK" />
      
      <div className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-stack-md">
        <AgentHeader 
          title="FACT-CHECK\nEVIDENCE DESK"
          label="AGENT_05 / SOURCE INTELLIGENCE"
          description="Cross-reference claims against an immutable, decentralized ledger of historical events and verified primary sources."
        />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter mt-stack-xl">
          <div className="lg:col-span-7 flex flex-col gap-12">
            <InputWorkspace 
              type="claim"
              placeholder="Paste a claim that requires verification..."
              buttonText="VERIFY CLAIM"
              onAnalyze={handleAnalyze}
              isAnalyzing={isAnalyzing}
            />

            {(isAnalyzing || results) && (
              <AnalysisProgress 
                stages={FACT_CHECK_STAGES} 
                currentStage={currentStage} 
                isAnalyzing={isAnalyzing} 
              />
            )}
          </div>

          <div className="lg:col-span-5 flex flex-col gap-12 mt-12 lg:mt-0 lg:pl-gutter lg:border-l border-primary/20">
            {results ? (
              <div className="animate-in fade-in slide-in-from-bottom-8 duration-700">
                {/* Evidence Board Workspace */}
                <div className="w-full min-h-[400px] border border-primary/20 bg-primary/5 mb-8 relative flex items-center justify-center p-8 overflow-hidden">
                   {/* Connections */}
                   <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-20">
                     <path d="M 50%,50% L 20%,20%" stroke="var(--color-primary)" strokeWidth="2" strokeDasharray="4 4" />
                     <path d="M 50%,50% L 80%,20%" stroke="var(--color-primary)" strokeWidth="2" strokeDasharray="4 4" />
                     <path d="M 50%,50% L 20%,80%" stroke="var(--color-secondary)" strokeWidth="2" strokeDasharray="4 4" />
                     <path d="M 50%,50% L 80%,80%" stroke="var(--color-primary)" strokeWidth="2" strokeDasharray="4 4" />
                   </svg>
                   
                   {/* Central Claim */}
                   <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10 w-48 bg-parchment border-2 border-primary/40 p-4 text-center shadow-lg">
                      <span className="font-mono-label text-[10px] tracking-widest uppercase text-primary/60 block mb-2">TARGET CLAIM</span>
                      <span className="font-body-md text-primary font-bold">"The submitted claim text is presented here for analysis."</span>
                      <div className="mt-4 pt-4 border-t border-primary/10">
                        <span className="font-mono-label text-sm text-secondary font-bold">CONTRADICTED</span>
                      </div>
                   </div>

                   {/* Sources Nodes */}
                   {results.evidence.map((ev: any, i: number) => {
                     const positions = [
                       "top-[10%] left-[10%]",
                       "top-[10%] right-[10%]",
                       "bottom-[10%] left-[10%]",
                       "bottom-[10%] right-[10%]"
                     ];
                     let statusColor = "text-primary border-primary/20";
                     if (ev.status === "SUPPORTED") statusColor = "text-trust-green border-trust-green/40";
                     if (ev.status === "CONTRADICTED") statusColor = "text-secondary border-secondary/40";

                     return (
                       <div key={i} className={`absolute ${positions[i]} z-0 w-40 bg-parchment/80 backdrop-blur-sm border p-3 ${statusColor}`}>
                          <span className="font-mono-label text-[8px] tracking-widest block mb-1 opacity-60">SOURCE {i + 1}</span>
                          <span className="font-headline-sm text-sm block mb-2 truncate">{ev.sourceName}</span>
                          <span className={`font-mono-label text-[10px] font-bold ${statusColor}`}>{ev.status}</span>
                       </div>
                     );
                   })}
                </div>

                <MetricGrid metrics={[
                  { label: "CLAIMS ANALYZED", value: results.metrics.claims },
                  { label: "SOURCES", value: results.metrics.sources },
                  { label: "SUPPORTING", value: results.metrics.supporting },
                  { label: "EVIDENCE STRENGTH", value: results.metrics.evidenceStrength }
                ]} />

                <EditorialDivider />

                <div className="mt-12 p-6 border border-secondary/30 bg-secondary/5 text-center">
                  <h4 className="font-headline-md text-2xl font-bold text-secondary mb-2">FACT-CHECK COMPLETE</h4>
                  <p className="font-body-sm text-on-surface-variant font-bold tracking-widest uppercase mt-4">DEMO ANALYSIS — FRONTEND PREVIEW</p>
                </div>
              </div>
            ) : (
              <div className="w-full h-full min-h-[400px] flex items-center justify-center border border-dashed border-primary/20 text-primary/40 font-mono-label text-sm tracking-widest uppercase">
                AWAITING INPUT
              </div>
            )}
          </div>
        </div>

        <AgentNavigation prevAgent={{ name: "VIDEO", id: "video" }} nextAgent={{ name: "DECISION CORE", id: "decision" }} />
      </div>
    </main>
  );
}
