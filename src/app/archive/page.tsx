import React from "react";
import { PageHeader } from "@/components/ui/PageHeader";

export default function ArchivePage() {
  return (
    <main className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-8">
      <PageHeader 
        label="VERITAS HISTORICAL RECORD" 
        headline={<>THE ARCHIVE</>}
        subheadline="Stories investigated. Evidence preserved."
      />

      {/* Search Interface */}
      <section className="mt-stack-lg mb-stack-md">
        <div className="relative w-full max-w-4xl border-b-2 border-primary focus-within:border-secondary transition-colors pb-2 flex items-center">
          <input 
            type="text" 
            placeholder="Search investigations, stories, claims or sources..." 
            className="w-full bg-transparent outline-none font-headline-md text-2xl md:text-4xl text-primary placeholder:text-primary/30"
          />
          <button className="font-mono-label text-mono-label text-secondary whitespace-nowrap ml-4 flex items-center gap-1 group">
            SEARCH <span className="material-symbols-outlined group-hover:translate-x-1 transition-transform">arrow_forward</span>
          </button>
        </div>
      </section>

      {/* Filters */}
      <section className="mb-stack-xl flex flex-wrap gap-4">
        {["YEAR", "CATEGORY", "REGION", "VERDICT", "MEDIA TYPE"].map((filter) => (
          <button key={filter} className="font-mono-label text-xs tracking-widest text-on-surface-variant border border-primary/20 px-4 py-2 hover:bg-primary hover:text-parchment transition-colors uppercase">
            {filter} <span className="material-symbols-outlined text-[10px] ml-1">expand_more</span>
          </button>
        ))}
      </section>

      <div className="flex flex-col md:flex-row gap-12">
        {/* Archive Timeline */}
        <aside className="w-full md:w-48 flex-shrink-0">
          <div className="sticky top-32 flex flex-col gap-4 border-l border-primary/20 pl-4">
            {["2026", "2025", "2024", "2023"].map((year, i) => (
              <button key={year} className={`text-left font-mono-label text-lg ${i === 0 ? 'text-secondary font-bold' : 'text-on-surface-variant hover:text-primary transition-colors'}`}>
                {year}
              </button>
            ))}
          </div>
        </aside>

        {/* Archived Investigation Cards */}
        <div className="flex-1 flex flex-col gap-8">
          {[
            {
              headline: "Authentication of the August Diplomatic Cables",
              date: "AUG 15, 2026",
              category: "GEOPOLITICS",
              source: "INTERNAL LEAK",
              verdict: "VERIFIED",
              confidence: "99.8%"
            },
            {
              headline: "Synthetic Origin of the Viral 'Market Panic' Audio",
              date: "JUL 02, 2026",
              category: "ECONOMY",
              source: "SOCIAL MEDIA",
              verdict: "FAKE NEWS",
              confidence: "98.5%"
            },
            {
              headline: "Analysis of the Alleged Deep-Sea Sabotage Footage",
              date: "JUN 14, 2026",
              category: "CONFLICT",
              source: "ANONYMOUS SUBMISSION",
              verdict: "INCONCLUSIVE",
              confidence: "42.0%"
            }
          ].map((item, i) => (
            <article key={i} className="flex flex-col md:flex-row gap-6 p-6 border border-primary/20 bg-parchment/50 hover:bg-parchment transition-colors relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity pointer-events-none">
                 <span className="font-masthead text-8xl leading-none text-primary/30">V</span>
              </div>
              <div className="flex-1 flex flex-col gap-4 relative z-10">
                <div className="flex items-center gap-4 text-xs font-mono-label uppercase text-on-surface-variant">
                  <span>{item.date}</span>
                  <span className="w-1 h-1 rounded-full bg-primary/20"></span>
                  <span>{item.category}</span>
                  <span className="w-1 h-1 rounded-full bg-primary/20"></span>
                  <span>SRC: {item.source}</span>
                </div>
                <h3 className="font-headline-md text-2xl md:text-3xl font-bold text-primary max-w-2xl">
                  {item.headline}
                </h3>
                <div className="flex items-center gap-6 mt-4">
                  <div className="flex flex-col">
                    <span className="font-mono-label text-[10px] text-on-surface-variant uppercase">VERDICT</span>
                    <span className={`font-mono-label text-sm font-bold ${
                      item.verdict === 'VERIFIED' ? 'text-trust-green' : 
                      item.verdict === 'FAKE NEWS' ? 'text-alert-crimson' : 
                      'text-secondary'
                    }`}>{item.verdict}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-mono-label text-[10px] text-on-surface-variant uppercase">CONFIDENCE</span>
                    <span className="font-mono-label text-sm font-bold text-primary">{item.confidence}</span>
                  </div>
                </div>
              </div>
              <div className="flex items-end justify-end relative z-10">
                <button className="font-mono-label text-xs font-bold text-primary hover:text-secondary transition-colors flex items-center gap-1 group/btn border-b border-transparent hover:border-secondary pb-1">
                  VIEW REPORT
                  <span className="material-symbols-outlined text-sm group-hover/btn:translate-x-1 transition-transform">arrow_forward</span>
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>
    </main>
  );
}
