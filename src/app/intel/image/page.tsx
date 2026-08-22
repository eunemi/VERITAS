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
import { analyzeImage } from "@/lib/services/agentServices";

const IMAGE_STAGES = [
  "IMAGE INGESTION",
  "METADATA INSPECTION",
  "OCR EXTRACTION",
  "PIXEL ANALYSIS",
  "SYNTHETIC MEDIA CHECK",
  "VISUAL CONSISTENCY",
  "ASSESSMENT READY"
];

export default function ImageAgentPage() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentStage, setCurrentStage] = useState(0);
  const [results, setResults] = useState<any>(null);

  const handleAnalyze = async (file: File | null) => {
    setIsAnalyzing(true);
    setResults(null);
    setCurrentStage(0);

    const interval = setInterval(() => {
      setCurrentStage((prev) => {
        if (prev >= IMAGE_STAGES.length - 1) {
          clearInterval(interval);
          return prev;
        }
        return prev + 1;
      });
    }, 550);

    const data = await analyzeImage(file);
    
    setTimeout(() => {
      setResults(data);
      setCurrentStage(IMAGE_STAGES.length);
      setIsAnalyzing(false);
    }, 1000);
  };

  return (
    <main className="w-full min-h-screen bg-parchment pb-stack-xl">
      <AgentBreadcrumb agentNumber="AGENT_02" agentName="IMAGE" />
      
      <div className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-stack-md">
        <AgentHeader 
          title="IMAGE\nFORENSICS"
          label="AGENT_02 / VISUAL INTELLIGENCE"
          description="Analyze photographs, screenshots and visual media for manipulation, synthetic generation and visual inconsistencies."
        />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter mt-stack-xl">
          <div className="lg:col-span-7 flex flex-col gap-12">
            <InputWorkspace 
              type="upload"
              accept=".jpg,.jpeg,.png,.webp"
              placeholder="DROP IMAGE HERE"
              buttonText="ANALYZE IMAGE"
              onAnalyze={handleAnalyze}
              isAnalyzing={isAnalyzing}
            />

            {(isAnalyzing || results) && (
              <AnalysisProgress 
                stages={IMAGE_STAGES} 
                currentStage={currentStage} 
                isAnalyzing={isAnalyzing} 
              />
            )}
          </div>

          <div className="lg:col-span-5 flex flex-col gap-12 mt-12 lg:mt-0 lg:pl-gutter lg:border-l border-primary/20">
            {results ? (
              <div className="animate-in fade-in slide-in-from-bottom-8 duration-700">
                {/* Forensic Visualization */}
                <div className="w-full aspect-video bg-ink-black mb-8 relative overflow-hidden flex items-center justify-center border border-primary/20">
                  <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/stardust.png')] opacity-20 mix-blend-screen"></div>
                  <div className="w-32 h-32 border border-secondary/50 relative">
                     <div className="absolute top-0 right-0 w-2 h-2 bg-secondary animate-ping"></div>
                     <span className="absolute -bottom-6 left-0 font-mono-label text-[10px] text-secondary">ANOMALY DETECTED [87%]</span>
                  </div>
                  <div className="absolute top-0 bottom-0 left-1/3 w-[1px] bg-trust-green/40"></div>
                  <div className="absolute top-1/4 left-0 right-0 h-[1px] bg-trust-green/40"></div>
                  <div className="absolute top-4 left-4 font-mono-label text-[10px] text-trust-green">FORENSIC SCAN COMPLETE</div>
                </div>

                <MetricGrid metrics={[
                  { label: "AI GENERATION", value: results.metrics.aiGenerationSignal },
                  { label: "MANIPULATIONS", value: results.metrics.manipulationSignals },
                  { label: "OCR TEXT", value: results.metrics.ocrText },
                  { label: "VISUAL ANOMALIES", value: results.metrics.visualAnomalies }
                ]} />

                <EditorialDivider />

                <h3 className="font-headline-md text-3xl font-bold uppercase mb-6 text-ink-black">VISUAL FINDINGS</h3>
                <FindingList findings={results.findings} />

                <div className="mt-12 p-6 border border-secondary/30 bg-secondary/5 text-center">
                  <h4 className="font-headline-md text-2xl font-bold text-secondary mb-2">IMAGE ANALYSIS COMPLETE</h4>
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

        <AgentNavigation prevAgent={{ name: "TEXT", id: "text" }} nextAgent={{ name: "AUDIO", id: "audio" }} />
      </div>
    </main>
  );
}
