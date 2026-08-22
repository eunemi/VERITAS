"use client";

import React from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { IntelligenceAgent } from "@/components/ui/IntelligenceAgent";

export default function IntelPage() {
  return (
    <main className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-8">
      <PageHeader 
        label="VERITAS INTELLIGENCE LAYER" 
        headline={<>INTELLIGENCE<br />BEHIND INFORMATION.</>}
        subheadline="VERITAS analyzes multimodal content using specialized AI agents to establish the truth behind the story."
      />

      {/* Central Visualization Area */}
      <section className="my-stack-xl flex flex-col items-center justify-center relative">
        <div className="w-full max-w-4xl mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 relative z-10">
          <IntelligenceAgent 
            name="TEXT AGENT"
            description="Analyzes articles, captions and claims for linguistic anomalies and rhetorical manipulation."
            icon="subject"
            delay={0.1}
            route="/intel/text"
          />
          <IntelligenceAgent 
            name="IMAGE AGENT"
            description="Detects manipulation, synthetic imagery, and traces digital artifacts invisible to the human eye."
            icon="image"
            delay={0.2}
            route="/intel/image"
          />
          <IntelligenceAgent 
            name="AUDIO AGENT"
            description="Transcribes and analyzes speech patterns, detecting voice cloning and synthetic generation."
            icon="mic"
            delay={0.3}
            route="/intel/audio"
          />
          <IntelligenceAgent 
            name="VIDEO AGENT"
            description="Analyzes frames, scenes and audio-visual synchronization to detect deepfakes."
            icon="movie"
            delay={0.4}
            route="/intel/video"
          />
          <IntelligenceAgent 
            name="FACT-CHECKING AGENT"
            description="Cross-checks claims against trusted evidence databases and historical records."
            icon="fact_check"
            delay={0.5}
            route="/intel/fact-check"
          />
          <IntelligenceAgent 
            name="DECISION AGENT"
            description="Combines evidence and produces the final assessment and confidence score."
            icon="gavel"
            delay={0.6}
            route="/intel/decision"
          />
        </div>
        
        {/* Core Visualization */}
        <div className="hidden md:flex absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] border border-primary/5 rounded-full items-center justify-center -z-10">
           <div className="w-[400px] h-[400px] border border-primary/10 rounded-full flex items-center justify-center">
             <div className="w-[200px] h-[200px] bg-ink-black rounded-full flex flex-col items-center justify-center text-center p-4">
                <span className="material-symbols-outlined text-parchment text-4xl mb-2">memory</span>
                <span className="font-mono-label text-mono-label text-parchment">VERITAS<br/>INTELLIGENCE<br/>CORE</span>
             </div>
           </div>
        </div>
      </section>

      {/* How VERITAS Thinks */}
      <section className="mb-stack-xl">
        <div className="w-full flex justify-between items-end border-b border-primary/20 pb-4 mb-16">
          <h2 className="font-headline-md text-3xl font-bold text-primary">HOW VERITAS THINKS</h2>
        </div>
        
        <div className="flex flex-col md:flex-row justify-between items-center gap-4 text-center">
          <div className="flex flex-col items-center">
            <span className="font-masthead text-2xl md:text-4xl text-primary font-bold">CONTENT</span>
            <span className="material-symbols-outlined text-secondary mt-2">arrow_downward</span>
          </div>
          <div className="hidden md:block flex-1 h-[1px] bg-primary/20 mx-4"></div>
          
          <div className="flex flex-col items-center">
            <span className="font-masthead text-2xl md:text-4xl text-primary font-bold">CLAIMS</span>
            <span className="material-symbols-outlined text-secondary mt-2">arrow_downward</span>
          </div>
          <div className="hidden md:block flex-1 h-[1px] bg-primary/20 mx-4"></div>
          
          <div className="flex flex-col items-center">
            <span className="font-masthead text-2xl md:text-4xl text-primary font-bold">SIGNALS</span>
            <span className="material-symbols-outlined text-secondary mt-2">arrow_downward</span>
          </div>
          <div className="hidden md:block flex-1 h-[1px] bg-primary/20 mx-4"></div>
          
          <div className="flex flex-col items-center">
            <span className="font-masthead text-2xl md:text-4xl text-primary font-bold">EVIDENCE</span>
            <span className="material-symbols-outlined text-secondary mt-2">arrow_downward</span>
          </div>
          <div className="hidden md:block flex-1 h-[1px] bg-primary/20 mx-4"></div>
          
          <div className="flex flex-col items-center">
            <span className="font-masthead text-2xl md:text-4xl text-primary font-bold">VERIFICATION</span>
            <span className="material-symbols-outlined text-secondary mt-2">arrow_downward</span>
          </div>
          <div className="hidden md:block flex-1 h-[1px] bg-primary/20 mx-4"></div>
          
          <div className="flex flex-col items-center">
            <span className="font-masthead text-2xl md:text-4xl text-secondary font-black">DECISION</span>
            <span className="material-symbols-outlined text-secondary mt-2">done_all</span>
          </div>
        </div>
      </section>
    </main>
  );
}
