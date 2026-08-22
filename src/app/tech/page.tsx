import React from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StoryCard } from "@/components/ui/StoryCard";

export default function TechPage() {
  return (
    <main className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-8">
      <PageHeader 
        label="TECHNOLOGY / DIGITAL CULTURE" 
        headline={<>TECHNOLOGY<br />SHAPES THE STORY.</>}
        subheadline="From artificial intelligence to digital security: reporting on the systems that structure reality."
      />

      <section className="mt-stack-lg mb-stack-xl">
        <StoryCard 
          featured
          category="ARTIFICIAL INTELLIGENCE"
          location="SAN FRANCISCO"
          headline="Next-Generation Generative Models Bypass Standard Detection Protocols"
          description="The latest iteration of open-weight LLMs demonstrates an unprecedented ability to mimic specific authorial styles, rendering traditional stylometric analysis obsolete. VERITAS researchers have developed a novel semantic-weighting detection method in response."
          source="VERITAS LABS"
          date="AUG 21, 2026"
          verificationStatus="VERIFIED"
        />
      </section>

      {/* AI & Information Integrity Section */}
      <section className="mb-stack-xl border border-primary/20 p-8 relative overflow-hidden bg-primary/5">
        <div className="absolute top-0 right-0 w-64 h-64 bg-secondary/10 rounded-full blur-3xl mix-blend-multiply"></div>
        <div className="relative z-10 flex flex-col md:flex-row gap-8 items-center">
          <div className="flex-1">
             <h3 className="font-mono-label text-sm text-secondary uppercase tracking-widest mb-4">SPECIAL REPORT</h3>
             <h2 className="font-headline-md text-4xl font-bold text-primary mb-4">AI & Information Integrity</h2>
             <p className="font-body-md text-on-surface-variant max-w-xl">
               As synthetic media becomes indistinguishable from reality to the human eye, journalism must evolve. VERITAS employs adversarial AI models to detect synthetic generation artifacts, maintaining the integrity of the historical record.
             </p>
             <button className="mt-6 font-mono-label text-xs font-bold text-primary border-b border-primary hover:text-secondary hover:border-secondary transition-colors uppercase py-1">
               Read the full methodology →
             </button>
          </div>
          <div className="flex-1 w-full flex justify-center">
             {/* Abstract representation of AI detection */}
             <div className="w-48 h-48 border border-primary/20 relative grid grid-cols-4 grid-rows-4">
                {Array.from({ length: 16 }).map((_, i) => (
                  <div key={i} className={`border border-primary/5 ${[2, 5, 11, 14].includes(i) ? 'bg-secondary/20' : ''} transition-colors duration-1000`}></div>
                ))}
                <div className="absolute inset-0 flex items-center justify-center">
                   <div className="w-16 h-16 border border-secondary rounded-full animate-ping"></div>
                </div>
             </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-12 mb-stack-xl">
        <StoryCard 
          category="CYBERSECURITY"
          headline="Zero-Day Exploit Compromises Major Cloud Provider"
          description="A sophisticated attack vector utilizing AI-generated phishing payloads has bypassed enterprise security, exposing internal communications of three major news organizations."
          source="VERITAS SEC"
          date="AUG 20, 2026"
          verificationStatus="VERIFIED"
        />
        <StoryCard 
          category="SCIENCE"
          headline="Quantum Decryption Milestones Reached Ahead of Schedule"
          description="Researchers claim to have successfully factored a 2048-bit RSA key using a hybrid quantum-classical algorithm. The implications for digital signatures are profound."
          source="NATURE / VERITAS"
          date="AUG 19, 2026"
          verificationStatus="UNDER REVIEW"
        />
        <StoryCard 
          category="DIGITAL CULTURE"
          headline="The Rise of Autonomous AI Personas on Social Media"
          description="Fully autonomous AI agents are now managing highly influential accounts, coordinating narratives without human oversight."
          source="VERITAS INTEL"
          date="AUG 18, 2026"
          verificationStatus="VERIFIED"
        />
      </section>
    </main>
  );
}
