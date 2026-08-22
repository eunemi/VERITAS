import React from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StoryCard } from "@/components/ui/StoryCard";

export default function WorldPage() {
  return (
    <main className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-8">
      <PageHeader 
        label="WORLD / GLOBAL INTELLIGENCE" 
        headline={<>THE WORLD,<br />UNDER ANALYSIS.</>}
        subheadline="Signals, stories and developments from across the globe — examined through evidence and intelligence."
      />

      <section className="mt-stack-lg mb-stack-xl">
        <StoryCard 
          featured
          category="GEOPOLITICS"
          location="GENEVA"
          headline="New Treaties Questioned as Synthetic Media Clouds Negotiations"
          description="A comprehensive analysis of the recent summit reveals overlapping inconsistencies in the official broadcast feeds. VERITAS multi-modal agents detected subtle audio-visual desyncs consistent with deepfake injection, raising questions about the authenticity of the primary accord."
          source="REUTERS / VERITAS INTEL"
          date="AUG 21, 2026"
          verificationStatus="CONTESTED"
        />
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-12 mb-stack-xl">
        <StoryCard 
          category="CLIMATE"
          location="JAKARTA"
          headline="Unprecedented Sea Wall Breach Attributed to Sensor Malfunction, Not Sabotage"
          description="Initial reports suggested malicious interference, but our forensic data analysis of the structural integrity sensors points to a cascading hardware failure."
          source="AP / VERITAS FORENSICS"
          date="AUG 20, 2026"
          verificationStatus="VERIFIED"
        />
        <StoryCard 
          category="CONFLICT"
          location="EASTERN EUROPE"
          headline="Satellite Imagery Contradicts Troop Withdrawal Claims"
          description="Analysis of 48 hours of synthetic aperture radar (SAR) data shows concealed movements contradicting the official narrative of de-escalation."
          source="MAXAR / VERITAS VISION"
          date="AUG 19, 2026"
          verificationStatus="UNDER REVIEW"
        />
        <StoryCard 
          category="ELECTION"
          location="BRASÍLIA"
          headline="Audio Leak Authenticated Despite Candidate's Denial"
          description="The VERITAS Audio Agent has processed the leaked recording, finding continuous spectral signatures and no evidence of AI generation."
          source="VERITAS INTEL"
          date="AUG 18, 2026"
          verificationStatus="VERIFIED"
        />
      </section>

      {/* Global Intelligence Map Mock */}
      <section className="mb-stack-xl">
        <div className="w-full flex justify-between items-end border-b border-primary/20 pb-4 mb-8">
          <h2 className="font-headline-md text-3xl font-bold text-primary">GLOBAL INTELLIGENCE MAP</h2>
          <span className="font-mono-label text-mono-label text-secondary tracking-widest">LIVE TRACKING</span>
        </div>
        <div className="w-full aspect-[21/9] bg-ink-black relative overflow-hidden flex items-center justify-center">
          <div className="absolute inset-0 grid-bg opacity-30"></div>
          {/* Mock Map using SVG/CSS for the vibe */}
          <div className="absolute inset-0 flex items-center justify-center opacity-40">
            <span className="material-symbols-outlined text-[400px] text-parchment">map</span>
          </div>
          
          {/* Signal Markers */}
          <div className="absolute top-1/3 left-1/4 w-3 h-3 bg-secondary rounded-full animate-ping"></div>
          <div className="absolute top-1/3 left-1/4 w-3 h-3 bg-secondary rounded-full"></div>
          
          <div className="absolute top-1/2 left-1/2 w-4 h-4 bg-trust-green rounded-full animate-ping" style={{ animationDelay: '1s' }}></div>
          <div className="absolute top-1/2 left-1/2 w-4 h-4 bg-trust-green rounded-full"></div>

          <div className="absolute top-[40%] right-[30%] w-2 h-2 bg-secondary rounded-full animate-ping" style={{ animationDelay: '0.5s' }}></div>
          <div className="absolute top-[40%] right-[30%] w-2 h-2 bg-secondary rounded-full"></div>

          <div className="absolute bottom-8 left-8 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-trust-green rounded-full"></div>
              <span className="font-mono-label text-[10px] text-parchment uppercase">VERIFIED SIGNAL</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-secondary rounded-full"></div>
              <span className="font-mono-label text-[10px] text-parchment uppercase">CONTESTED SIGNAL</span>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
