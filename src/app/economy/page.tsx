import React from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StoryCard } from "@/components/ui/StoryCard";

export default function EconomyPage() {
  return (
    <main className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-8">
      <PageHeader 
        label="ECONOMY / FINANCIAL INTELLIGENCE" 
        headline={<>THE ECONOMY,<br />WITHOUT THE NOISE.</>}
        subheadline="Cutting through market speculation with verified financial intelligence and data analysis."
      />

      {/* Economic Signals Section */}
      <section className="mt-stack-lg mb-stack-xl">
        <div className="w-full flex justify-between items-end border-b border-primary/20 pb-4 mb-8">
          <h2 className="font-headline-md text-3xl font-bold text-primary">ECONOMIC SIGNALS</h2>
        </div>
        
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          <div className="flex flex-col border-l-2 border-secondary pl-4">
            <span className="font-mono-label text-mono-label text-on-surface-variant uppercase mb-2">Global Trade Index</span>
            <span className="font-masthead text-4xl md:text-6xl text-primary font-bold">114.2</span>
            <span className="font-mono-label text-xs text-trust-green flex items-center mt-2">
              <span className="material-symbols-outlined text-sm">trending_up</span> +1.4%
            </span>
          </div>
          <div className="flex flex-col border-l-2 border-primary/20 pl-4">
            <span className="font-mono-label text-mono-label text-on-surface-variant uppercase mb-2">Inflation Core</span>
            <span className="font-masthead text-4xl md:text-6xl text-primary font-bold">2.8%</span>
            <span className="font-mono-label text-xs text-alert-crimson flex items-center mt-2">
              <span className="material-symbols-outlined text-sm">trending_up</span> +0.2%
            </span>
          </div>
          <div className="flex flex-col border-l-2 border-primary/20 pl-4">
            <span className="font-mono-label text-mono-label text-on-surface-variant uppercase mb-2">Synthetic Market Volatility</span>
            <span className="font-masthead text-4xl md:text-6xl text-primary font-bold">42.1</span>
            <span className="font-mono-label text-xs text-secondary flex items-center mt-2">
              <span className="material-symbols-outlined text-sm">warning</span> HIGH
            </span>
          </div>
          <div className="flex flex-col border-l-2 border-primary/20 pl-4">
            <span className="font-mono-label text-mono-label text-on-surface-variant uppercase mb-2">VERITAS Trust Yield</span>
            <span className="font-masthead text-4xl md:text-6xl text-primary font-bold">4.88%</span>
            <span className="font-mono-label text-xs text-on-surface-variant flex items-center mt-2">
              <span className="material-symbols-outlined text-sm">trending_flat</span> STABLE
            </span>
          </div>
        </div>
      </section>

      {/* Market Intelligence Visualization */}
      <section className="mb-stack-xl">
        <div className="w-full h-48 md:h-64 border-y border-primary/20 relative overflow-hidden flex flex-col justify-end">
          <div className="absolute inset-0 grid-bg opacity-50 z-0"></div>
          {/* Subtle SVG chart line simulating market data */}
          <svg className="w-full h-full absolute bottom-0 z-10" preserveAspectRatio="none" viewBox="0 0 100 100">
             <path d="M0,100 L0,50 L10,40 L20,60 L30,30 L40,45 L50,20 L60,35 L70,10 L80,25 L90,5 L100,15 L100,100 Z" fill="rgba(139, 0, 0, 0.05)" />
             <path d="M0,50 L10,40 L20,60 L30,30 L40,45 L50,20 L60,35 L70,10 L80,25 L90,5 L100,15" fill="none" stroke="var(--color-secondary)" strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
          </svg>
          <div className="absolute bottom-4 left-4 z-20">
            <span className="font-mono-label text-xs text-on-surface-variant uppercase bg-parchment/80 px-2 py-1">AI-Driven Trading Anomaly Index (7-Day)</span>
          </div>
        </div>
      </section>

      {/* Featured Economic Stories */}
      <section className="mb-stack-xl">
        <div className="w-full flex justify-between items-end border-b border-primary/20 pb-4 mb-8">
          <h2 className="font-headline-md text-3xl font-bold text-primary">MARKET INTELLIGENCE</h2>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-12">
          <StoryCard 
            category="MARKETS"
            headline="Flash Crash Traced to Coordinated Deepfake Audio Release"
            description="A temporary $200 billion wipeout in the semiconductor sector was triggered by an algorithmic response to synthetic audio clips purportedly from key CEOs. VERITAS agents have confirmed the audio was entirely AI-generated."
            source="BLOOMBERG / VERITAS AUDIT"
            date="AUG 21, 2026"
            verificationStatus="VERIFIED"
          />
          <StoryCard 
            category="CURRENCY"
            headline="Central Bank Digital Currency Adoption Discrepancies"
            description="Official figures regarding the retail adoption of the new digital currency appear artificially inflated. Network analysis reveals that 40% of transactions originate from automated nodes rather than retail wallets."
            source="VERITAS INTEL"
            date="AUG 20, 2026"
            verificationStatus="UNDER REVIEW"
          />
        </div>
      </section>
    </main>
  );
}
