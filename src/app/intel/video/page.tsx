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
import { analyzeVideo } from "@/lib/services/agentServices";

const VIDEO_STAGES = [
  "VIDEO INGESTION",
  "FRAME EXTRACTION",
  "SCENE DETECTION",
  "VISUAL ANALYSIS",
  "AUDIO EXTRACTION",
  "TEMPORAL CONSISTENCY",
  "ASSESSMENT READY"
];

export default function VideoAgentPage() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentStage, setCurrentStage] = useState(0);
  const [results, setResults] = useState<any>(null);
  const [activeFrame, setActiveFrame] = useState<number | null>(null);

  const handleAnalyze = async (file: File | null) => {
    setIsAnalyzing(true);
    setResults(null);
    setCurrentStage(0);
    setActiveFrame(null);

    const interval = setInterval(() => {
      setCurrentStage((prev) => {
        if (prev >= VIDEO_STAGES.length - 1) {
          clearInterval(interval);
          return prev;
        }
        return prev + 1;
      });
    }, 650);

    const data = await analyzeVideo(file);
    
    setTimeout(() => {
      setResults(data);
      setCurrentStage(VIDEO_STAGES.length);
      setIsAnalyzing(false);
    }, 1000);
  };

  return (
    <main className="w-full min-h-screen bg-parchment pb-stack-xl">
      <AgentBreadcrumb agentNumber="AGENT_04" agentName="VIDEO" />
      
      <div className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-stack-md">
        <AgentHeader 
          title="VIDEO\nFORENSICS"
          label="AGENT_04 / TEMPORAL INTELLIGENCE"
          description="Frame-by-frame temporal consistency checks, detecting AI-generated motion, face-swapping, and spatial impossibilities."
        />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter mt-stack-xl">
          <div className="lg:col-span-7 flex flex-col gap-12">
            <InputWorkspace 
              type="upload"
              accept=".mp4,.mov,.webm"
              placeholder="DROP VIDEO HERE"
              buttonText="ANALYZE VIDEO"
              onAnalyze={handleAnalyze}
              isAnalyzing={isAnalyzing}
            />

            {(isAnalyzing || results) && (
              <AnalysisProgress 
                stages={VIDEO_STAGES} 
                currentStage={currentStage} 
                isAnalyzing={isAnalyzing} 
              />
            )}
          </div>

          <div className="lg:col-span-5 flex flex-col gap-12 mt-12 lg:mt-0 lg:pl-gutter lg:border-l border-primary/20">
            {results ? (
              <div className="animate-in fade-in slide-in-from-bottom-8 duration-700">
                {/* Video Workspace */}
                <div className="w-full flex flex-col border border-primary/20 bg-ink-black text-parchment mb-8 relative">
                   <div className="w-full aspect-video flex items-center justify-center relative overflow-hidden">
                     {/* Video Preview Mock */}
                     <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/stardust.png')] opacity-10 mix-blend-screen"></div>
                     <span className="material-symbols-outlined text-6xl text-parchment/20">play_circle</span>
                     
                     {/* Bounding Box if active */}
                     {activeFrame === 2 && (
                       <div className="absolute top-1/4 left-1/3 w-32 h-32 border border-secondary bg-secondary/10 flex items-end">
                         <span className="font-mono-label text-[10px] text-secondary bg-ink-black/80 px-1">SPATIAL ANOMALY</span>
                       </div>
                     )}
                   </div>
                   
                   {/* Timeline */}
                   <div className="w-full h-24 border-t border-parchment/20 bg-[#111] p-2 flex flex-col justify-between">
                      <div className="flex justify-between font-mono-label text-[10px] text-parchment/40">
                         <span>00:00:00</span>
                         <span>00:01:45</span>
                      </div>
                      
                      {/* Frame Markers */}
                      <div className="flex items-center gap-[2px] w-full h-6">
                         {Array.from({ length: 48 }).map((_, i) => (
                           <div 
                             key={i}
                             onClick={() => setActiveFrame(i % 5)}
                             className={`flex-1 h-full cursor-pointer transition-colors ${i % 12 === 0 ? "bg-secondary" : "bg-parchment/10 hover:bg-parchment/30"}`}
                           />
                         ))}
                      </div>

                      {/* Scene Markers */}
                      <div className="w-full flex">
                         <div className="w-1/3 h-1 border-r border-parchment/20 bg-trust-green/40"></div>
                         <div className="w-1/3 h-1 border-r border-parchment/20 bg-trust-green/40"></div>
                         <div className="w-1/3 h-1 bg-secondary/40"></div>
                      </div>
                   </div>
                </div>

                <MetricGrid metrics={[
                  { label: "FRAMES ANALYZED", value: results.metrics.framesAnalyzed },
                  { label: "SCENES", value: results.metrics.scenes },
                  { label: "VISUAL SIGNALS", value: results.metrics.visualSignals },
                  { label: "CONFIDENCE", value: results.metrics.confidence }
                ]} />

                <EditorialDivider />

                <h3 className="font-headline-md text-3xl font-bold uppercase mb-6 text-ink-black">VIDEO FINDINGS</h3>
                <FindingList findings={results.findings} />

                <div className="mt-12 p-6 border border-secondary/30 bg-secondary/5 text-center">
                  <h4 className="font-headline-md text-2xl font-bold text-secondary mb-2">VIDEO ANALYSIS COMPLETE</h4>
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

        <AgentNavigation prevAgent={{ name: "AUDIO", id: "audio" }} nextAgent={{ name: "FACT-CHECK", id: "fact-check" }} />
      </div>
    </main>
  );
}
