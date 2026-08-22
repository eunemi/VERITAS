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
import { analyzeAudio } from "@/lib/services/agentServices";

const AUDIO_STAGES = [
  "AUDIO INGESTION",
  "SPEECH DETECTION",
  "TRANSCRIPTION",
  "SPEAKER SEGMENTATION",
  "SPECTRAL ANALYSIS",
  "SYNTHETIC VOICE CHECK",
  "ASSESSMENT READY"
];

export default function AudioAgentPage() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentStage, setCurrentStage] = useState(0);
  const [results, setResults] = useState<any>(null);
  const [activeSegment, setActiveSegment] = useState<number | null>(null);

  const handleAnalyze = async (file: File | null) => {
    setIsAnalyzing(true);
    setResults(null);
    setCurrentStage(0);
    setActiveSegment(null);

    const interval = setInterval(() => {
      setCurrentStage((prev) => {
        if (prev >= AUDIO_STAGES.length - 1) {
          clearInterval(interval);
          return prev;
        }
        return prev + 1;
      });
    }, 600);

    const data = await analyzeAudio(file);
    
    setTimeout(() => {
      setResults(data);
      setCurrentStage(AUDIO_STAGES.length);
      setIsAnalyzing(false);
    }, 1000);
  };

  return (
    <main className="w-full min-h-screen bg-parchment pb-stack-xl">
      <AgentBreadcrumb agentNumber="AGENT_03" agentName="AUDIO" />
      
      <div className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-stack-md">
        <AgentHeader 
          title="AUDIO\nFORENSICS"
          label="AGENT_03 / SPEECH INTELLIGENCE"
          description="Spectral analysis to detect deepfake voice cloning, background noise anomalies, and splicing artifacts."
        />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter mt-stack-xl">
          <div className="lg:col-span-7 flex flex-col gap-12">
            <InputWorkspace 
              type="upload"
              accept=".mp3,.wav,.m4a,.ogg"
              placeholder="DROP AUDIO HERE"
              buttonText="ANALYZE AUDIO"
              onAnalyze={handleAnalyze}
              isAnalyzing={isAnalyzing}
            />

            {(isAnalyzing || results) && (
              <AnalysisProgress 
                stages={AUDIO_STAGES} 
                currentStage={currentStage} 
                isAnalyzing={isAnalyzing} 
              />
            )}
          </div>

          <div className="lg:col-span-5 flex flex-col gap-12 mt-12 lg:mt-0 lg:pl-gutter lg:border-l border-primary/20">
            {results ? (
              <div className="animate-in fade-in slide-in-from-bottom-8 duration-700">
                {/* Audio Workspace */}
                <div className="w-full h-40 bg-primary/5 border border-primary/20 mb-8 p-4 flex flex-col justify-between">
                   <div className="flex justify-between items-center text-primary/60">
                     <span className="material-symbols-outlined hover:text-secondary cursor-pointer transition-colors">play_circle</span>
                     <span className="font-mono-label text-xs">02:48</span>
                   </div>
                   
                   {/* Waveform Visualization */}
                   <div className="flex items-end h-16 gap-1 w-full justify-between mt-4">
                     {Array.from({ length: 40 }).map((_, i) => (
                       <div 
                         key={i} 
                         className={`w-1 transition-colors duration-300 ${activeSegment !== null && i > activeSegment * 10 && i < (activeSegment + 1) * 10 ? "bg-secondary h-[80%]" : "bg-primary/30"}`} 
                         style={{ height: activeSegment !== null && i > activeSegment * 10 && i < (activeSegment + 1) * 10 ? '80%' : `${Math.random() * 80 + 20}%` }}
                       />
                     ))}
                   </div>
                </div>

                <MetricGrid metrics={[
                  { label: "DURATION", value: results.metrics.duration },
                  { label: "WORDS", value: results.metrics.words },
                  { label: "SPEAKERS", value: results.metrics.speakers },
                  { label: "CONFIDENCE", value: results.metrics.confidence }
                ]} />

                <EditorialDivider />

                <h3 className="font-headline-md text-3xl font-bold uppercase mb-6 text-ink-black">TRANSCRIPT PANEL</h3>
                <div className="p-6 border border-primary/20 bg-parchment font-body-md text-primary leading-relaxed flex flex-col gap-4">
                  <p 
                    className={`cursor-pointer transition-colors p-2 -mx-2 rounded ${activeSegment === 0 ? "bg-secondary/10 border-l-2 border-secondary" : "hover:bg-primary/5"}`}
                    onClick={() => setActiveSegment(0)}
                  >
                    <span className="font-bold text-xs uppercase tracking-widest text-primary/60 block mb-1">SPEAKER 01</span>
                    "The timeline of events is exactly as I stated in the previous briefing."
                  </p>
                  <p 
                    className={`cursor-pointer transition-colors p-2 -mx-2 rounded ${activeSegment === 1 ? "bg-secondary/10 border-l-2 border-secondary" : "hover:bg-primary/5"}`}
                    onClick={() => setActiveSegment(1)}
                  >
                    <span className="font-bold text-xs uppercase tracking-widest text-primary/60 block mb-1">SPEAKER 02</span>
                    "Can you confirm the precise location of the secondary meeting?"
                  </p>
                  <p 
                    className={`cursor-pointer transition-colors p-2 -mx-2 rounded ${activeSegment === 2 ? "bg-secondary/10 border-l-2 border-secondary" : "hover:bg-primary/5"}`}
                    onClick={() => setActiveSegment(2)}
                  >
                    <span className="font-bold text-xs uppercase tracking-widest text-secondary block mb-1">SPEAKER 01 <span className="lowercase font-normal tracking-normal text-on-surface-variant">(Anomaly detected)</span></span>
                    "I cannot comment on the secondary location at this time."
                  </p>
                </div>

                <EditorialDivider />

                <h3 className="font-headline-md text-3xl font-bold uppercase mb-6 text-ink-black">AUDIO FINDINGS</h3>
                <FindingList findings={results.findings} />

                <div className="mt-12 p-6 border border-secondary/30 bg-secondary/5 text-center">
                  <h4 className="font-headline-md text-2xl font-bold text-secondary mb-2">AUDIO ANALYSIS COMPLETE</h4>
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

        <AgentNavigation prevAgent={{ name: "IMAGE", id: "image" }} nextAgent={{ name: "VIDEO", id: "video" }} />
      </div>
    </main>
  );
}
