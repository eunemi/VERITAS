"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { AgentBreadcrumb } from "@/components/agents/shared/AgentBreadcrumb";
import { AgentHeader } from "@/components/agents/shared/AgentHeader";
import { AgentNavigation } from "@/components/agents/shared/AgentNavigation";
import { MetricGrid } from "@/components/agents/shared/MetricGrid";
import { EditorialDivider } from "@/components/agents/shared/EditorialDivider";
import { runDecision } from "@/lib/services/agentServices";

export default function DecisionAgentPage() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [results, setResults] = useState<any>(null);

  const handleAnalyze = async () => {
    setIsAnalyzing(true);
    setResults(null);
    const data = await runDecision([]);
    
    setTimeout(() => {
      setResults(data);
      setIsAnalyzing(false);
    }, 1000);
  };

  return (
    <main className="w-full min-h-screen bg-ink-black pb-stack-xl text-parchment">
      {/* Custom breadcrumb for dark theme */}
      <div className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-4 flex items-center gap-2 font-mono-label text-[10px] tracking-widest uppercase text-parchment/60 border-b border-parchment/10">
        <a href="/intel" className="hover:text-secondary transition-colors">INTELLIGENCE</a>
        <span>/</span>
        <span className="text-parchment/40">AGENT_06</span>
        <span>/</span>
        <span className="text-parchment font-bold">DECISION CORE</span>
      </div>
      
      <div className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-stack-md">
        
        {/* Custom Header for dark theme */}
        <div className="mb-stack-lg">
          <div className="font-mono-label text-xs tracking-widest uppercase text-secondary mb-4">
            AGENT_06 / SYNTHESIS ENGINE
          </div>
          <h1 className="font-headline-lg text-6xl md:text-8xl lg:text-[120px] leading-[0.85] font-black uppercase tracking-tighter text-parchment mb-6 whitespace-pre-line">
            DECISION<br/>CORE
          </h1>
          <p className="font-body-lg italic text-xl md:text-2xl text-parchment/80 max-w-2xl border-l-2 border-secondary pl-6 py-2">
            The Decision Core synthesizes findings from the multimodal agents and prepares the final assessment.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter mt-stack-xl">
          {/* Input Streams Column */}
          <div className="lg:col-span-4 flex flex-col gap-6">
            <h3 className="font-mono-label text-sm text-parchment/60 tracking-widest uppercase mb-4">AGENT INPUT STREAMS</h3>
            
            {["TEXT", "IMAGE", "AUDIO", "VIDEO", "FACT-CHECK"].map((agent, i) => (
              <div key={agent} className="p-4 border border-parchment/20 bg-[#111] flex justify-between items-center group hover:border-secondary/50 transition-colors">
                 <div className="flex items-center gap-4">
                   <span className="font-mono-label text-[10px] text-parchment/40">0{i+1}</span>
                   <span className="font-headline-sm tracking-widest">{agent}</span>
                 </div>
                 <span className="font-mono-label text-[10px] text-trust-green uppercase border border-trust-green/20 px-2 py-1">COMPLETE</span>
              </div>
            ))}

            <button
              onClick={handleAnalyze}
              disabled={isAnalyzing}
              className="mt-8 w-full py-6 bg-secondary text-ink-black font-mono-label text-sm font-bold tracking-widest uppercase hover:bg-white transition-colors disabled:opacity-50"
            >
              {isAnalyzing ? "SYNTHESIZING..." : "RUN DECISION CORE"}
            </button>
          </div>

          {/* Visualization & Results Column */}
          <div className="lg:col-span-8 flex flex-col gap-12 mt-12 lg:mt-0 lg:pl-gutter lg:border-l border-parchment/20">
            {/* Decision Visualization */}
            <div className="w-full h-[500px] border border-parchment/20 relative flex items-center justify-center overflow-hidden">
              {/* Background Data Flow */}
              <div className="absolute inset-0 opacity-10 flex flex-col justify-between py-10 px-4 pointer-events-none">
                 {Array.from({ length: 20 }).map((_, i) => (
                   <div key={i} className="w-full h-px bg-parchment flex items-center">
                     <motion.div 
                       animate={{ x: ["-100%", "1000%"] }} 
                       transition={{ duration: 3 + Math.random() * 5, repeat: Infinity, ease: "linear" }}
                       className="w-16 h-[2px] bg-secondary"
                     />
                   </div>
                 ))}
              </div>

              {/* Central Core */}
              <div className="relative z-10 w-48 h-48 border-2 border-secondary/50 rounded-full flex flex-col items-center justify-center bg-ink-black shadow-[0_0_50px_rgba(183,16,50,0.3)]">
                <span className="font-mono-label text-xs text-secondary font-bold tracking-widest mb-2">DECISION</span>
                <span className="font-headline-lg text-5xl font-black text-parchment">CORE</span>
              </div>
              
              {/* Orbiting Rings */}
              <motion.div 
                animate={{ rotate: 360 }}
                transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
                className="w-80 h-80 border border-parchment/10 rounded-full absolute"
              >
                 <div className="absolute top-0 left-1/2 w-4 h-4 bg-trust-green rounded-full -translate-x-1/2 -translate-y-1/2 shadow-[0_0_10px_rgba(40,167,69,0.8)]"></div>
                 <div className="absolute bottom-0 left-1/2 w-4 h-4 bg-secondary rounded-full -translate-x-1/2 translate-y-1/2 shadow-[0_0_10px_rgba(183,16,50,0.8)]"></div>
              </motion.div>
              
              <motion.div 
                animate={{ rotate: -360 }}
                transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
                className="w-64 h-64 border border-dashed border-parchment/20 rounded-full absolute"
              />
            </div>

            {results && (
              <div className="animate-in fade-in slide-in-from-bottom-8 duration-700 flex flex-col gap-12">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
                  {/* Custom Metric Grid for Dark Theme */}
                  {[
                    { label: "AGENT AGREEMENT", value: results.metrics.agentAgreement },
                    { label: "EVIDENCE STRENGTH", value: results.metrics.evidenceStrength },
                    { label: "SIGNAL CONSISTENCY", value: results.metrics.signalConsistency },
                    { label: "MODEL CONFIDENCE", value: results.metrics.modelConfidence }
                  ].map((metric, i) => (
                    <div key={i} className="flex flex-col border-l-2 border-parchment/20 pl-4 py-2">
                      <span className="font-mono-label text-[10px] text-parchment/60 uppercase tracking-widest mb-2">
                        {metric.label}
                      </span>
                      <span className="font-masthead text-3xl font-bold text-parchment">
                        {metric.value}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="w-full h-px bg-parchment/20 my-stack-sm relative">
                  <div className="absolute -top-[5px] left-0 w-3 h-3 border-t border-l border-parchment"></div>
                  <div className="absolute -top-[5px] right-0 w-3 h-3 border-t border-r border-parchment"></div>
                </div>

                {/* Synthesis Breakdown */}
                <div>
                  <h3 className="font-headline-md text-3xl font-bold uppercase mb-8 text-parchment">SYNTHESIS BREAKDOWN</h3>
                  <div className="flex flex-col md:flex-row justify-between items-center gap-4 text-center border border-parchment/20 p-8">
                    {results.breakdown.map((item: any, i: number) => (
                      <React.Fragment key={i}>
                        <div className="flex flex-col items-center">
                          <span className="font-mono-label text-[10px] text-parchment/60 mb-2">{item.agent}</span>
                          <span className="font-masthead text-2xl text-parchment font-bold">{item.contribution}</span>
                        </div>
                        {i < results.breakdown.length - 1 && (
                          <>
                            <span className="material-symbols-outlined text-secondary md:rotate-[-90deg] hidden md:block">arrow_downward</span>
                            <span className="material-symbols-outlined text-secondary md:hidden">arrow_downward</span>
                          </>
                        )}
                      </React.Fragment>
                    ))}
                  </div>
                </div>

                {/* Final Assessment */}
                <div className="mt-8 p-12 border-2 border-secondary bg-[#111] text-center relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-16 h-16 bg-secondary flex items-center justify-center">
                    <span className="material-symbols-outlined text-ink-black text-3xl">priority_high</span>
                  </div>
                  <h4 className="font-headline-lg text-5xl md:text-7xl font-black text-parchment mb-4 uppercase tracking-tighter">ASSESSMENT READY</h4>
                  <p className="font-body-lg text-parchment/60 max-w-lg mx-auto mb-4">
                    Connect the Decision Agent backend to generate the final verdict and output the comprehensive intelligence dossier.
                  </p>
                  <p className="font-body-sm text-secondary font-bold tracking-widest uppercase mt-4">DEMO ANALYSIS — FRONTEND PREVIEW</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Custom Navigation for Dark Theme */}
        <div className="w-full border-t border-parchment/20 py-8 flex flex-col md:flex-row justify-between items-center gap-6 mt-stack-xl">
          <a href="/intel" className="font-mono-label text-xs tracking-widest text-parchment/60 hover:text-secondary transition-colors uppercase">
            &larr; BACK TO INTELLIGENCE
          </a>

          <div className="flex items-center gap-8">
             <a href="/intel/fact-check" className="font-mono-label text-xs tracking-widest text-parchment hover:text-secondary transition-colors uppercase group flex items-center gap-2">
               <span className="material-symbols-outlined text-sm group-hover:-translate-x-1 transition-transform">arrow_back</span>
               FACT-CHECK
             </a>
             <div className="w-24"></div>
          </div>
        </div>

      </div>
    </main>
  );
}
