"use client";

import React, { useState } from "react";
import { AgentBreadcrumb } from "@/components/agents/shared/AgentBreadcrumb";
import { AgentHeader } from "@/components/agents/shared/AgentHeader";
import { AgentNavigation } from "@/components/agents/shared/AgentNavigation";
import { InputWorkspace } from "@/components/agents/shared/InputWorkspace";
import { AnalysisProgress } from "@/components/agents/shared/AnalysisProgress";
import { MetricGrid } from "@/components/agents/shared/MetricGrid";
import { FindingList } from "@/components/agents/shared/FindingList";
import { EditorialDivider } from "@/components/agents/shared/EditorialDivider";
import { analyzeText } from "@/lib/services/agentServices";

const TEXT_STAGES = [
  "CONTENT INGESTION",
  "LANGUAGE DETECTION",
  "CLAIM EXTRACTION",
  "ENTITY ANALYSIS",
  "NARRATIVE ANALYSIS",
  "SIGNAL DETECTION",
  "ASSESSMENT READY"
];

export default function TextAgentPage() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentStage, setCurrentStage] = useState(0);
  const [results, setResults] = useState<any>(null);

  const handleAnalyze = async (content: string) => {
    setIsAnalyzing(true);
    setResults(null);
    setCurrentStage(0);

    // Simulate progress
    const interval = setInterval(() => {
      setCurrentStage((prev) => {
        if (prev >= TEXT_STAGES.length - 1) {
          clearInterval(interval);
          return prev;
        }
        return prev + 1;
      });
    }, 600);

    const data = await analyzeText(content);
    
    setTimeout(() => {
      setResults(data);
      setCurrentStage(TEXT_STAGES.length);
      setIsAnalyzing(false);
    }, 1000);
  };

  return (
    <main className="w-full min-h-screen bg-parchment pb-stack-xl">
      <AgentBreadcrumb agentNumber="AGENT_01" agentName="TEXT" />
      
      <div className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-stack-md">
        <AgentHeader 
          title="TEXT\nANALYSIS"
          label="AGENT_01 / LINGUISTIC INTELLIGENCE"
          description="Analyze articles, captions and written claims for linguistic signals, narrative patterns and potentially misleading statements."
        />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter mt-stack-xl">
          {/* Input & Progress Column */}
          <div className="lg:col-span-7 flex flex-col gap-12">
            <InputWorkspace 
              type="text"
              placeholder="Paste an article, caption, statement or news report here..."
              buttonText="ANALYZE TEXT"
              onAnalyze={handleAnalyze}
              isAnalyzing={isAnalyzing}
            />

            {(isAnalyzing || results) && (
              <AnalysisProgress 
                stages={TEXT_STAGES} 
                currentStage={currentStage} 
                isAnalyzing={isAnalyzing} 
              />
            )}
          </div>

          {/* Results Column */}
          <div className="lg:col-span-5 flex flex-col gap-12 mt-12 lg:mt-0 lg:pl-gutter lg:border-l border-primary/20">
            {results ? (
              <div className="animate-in fade-in slide-in-from-bottom-8 duration-700">
                <MetricGrid metrics={[
                  { label: "CLAIMS DETECTED", value: results.metrics.claimsDetected },
                  { label: "ENTITIES", value: results.metrics.entities },
                  { label: "SUSPICIOUS SIGNALS", value: results.metrics.suspiciousSignals },
                  { label: "CONFIDENCE", value: results.metrics.confidence }
                ]} />

                <EditorialDivider />

                <h3 className="font-headline-md text-3xl font-bold uppercase mb-6 text-ink-black">CLAIMS EXTRACTED</h3>
                <FindingList findings={results.claims} />

                <EditorialDivider />

                <h3 className="font-headline-md text-3xl font-bold uppercase mb-6 text-ink-black">LINGUISTIC SIGNALS</h3>
                <div className="flex flex-col gap-4">
                  {results.signals.map((signal: any, i: number) => (
                    <div key={i} className="flex justify-between items-center border-b border-primary/10 pb-2">
                      <span className="font-mono-label text-xs tracking-widest text-on-surface-variant">{signal.label}</span>
                      <span className="font-mono-label text-sm text-primary font-bold">{signal.level}</span>
                    </div>
                  ))}
                </div>

                <div className="mt-12 p-6 border border-secondary/30 bg-secondary/5 text-center">
                  <h4 className="font-headline-md text-2xl font-bold text-secondary mb-2">TEXT ANALYSIS COMPLETE</h4>
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

        <AgentNavigation nextAgent={{ name: "IMAGE", id: "image" }} />
      </div>
    </main>
  );
}
