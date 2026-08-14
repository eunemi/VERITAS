import React from "react";

const agents = [
  {
    id: "Agent_01",
    title: "TEXT",
    icon: "match_word",
    description: "Semantic interrogation of written narratives, detecting rhetorical shifts, propaganda patterns, and origin anomalies.",
    status: "ONLINE",
    core: false,
  },
  {
    id: "Agent_02",
    title: "IMAGE",
    icon: "image_search",
    description: "Forensic pixel analysis to identify generative synthesis, manipulative cropping, and lighting inconsistencies.",
    status: "ONLINE",
    core: false,
  },
  {
    id: "Agent_03",
    title: "AUDIO",
    icon: "mic_external_on",
    description: "Spectral analysis to detect deepfake voice cloning, background noise anomalies, and splicing artifacts.",
    status: "ONLINE",
    core: false,
  },
  {
    id: "Agent_04",
    title: "VIDEO",
    icon: "videocam",
    description: "Frame-by-frame temporal consistency checks, detecting AI-generated motion, face-swapping, and spatial impossibilities.",
    status: "ONLINE",
    core: false,
  },
  {
    id: "Agent_05",
    title: "FACT-CHECK",
    icon: "fact_check",
    description: "Cross-referencing claims against an immutable, decentralized ledger of historical events and verified primary sources.",
    status: "ONLINE",
    core: false,
  },
  {
    id: "Agent_06 (Core)",
    title: "DECISION",
    icon: "gavel",
    description: "The synthesis engine. Aggregates findings from sub-agents to render a final, statistically weighted verdict on veracity.",
    status: "AWAITING INPUT",
    core: true,
  },
];

export default function AgentsSection() {
  return (
    <>
      {/* Technical Rule */}
      <div className="w-full h-px bg-ink-black/20 my-0 relative">
        <div className="absolute -top-[5px] left-0 w-3 h-3 border-t border-l border-ink-black"></div>
        <div className="absolute -top-[5px] right-0 w-3 h-3 border-t border-r border-ink-black"></div>
      </div>

      {/* AI Agents Section */}
      <section className="py-stack-xl border-x border-primary/20 relative">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-x-gutter gap-y-stack-lg">
          {/* Section Header */}
          <div className="col-span-1 md:col-span-12 border-b border-ink-black/20 pb-stack-sm mb-stack-md flex justify-between items-end">
            <h2 className="font-headline-lg text-headline-xl-mobile md:text-headline-lg text-ink-black uppercase">
              Intelligence Assets
            </h2>
            <span className="font-mono-label text-mono-label text-ink-black/60 hidden md:block">
              SYS_STATUS: OPTIMAL
            </span>
          </div>

          <div className="col-span-1 md:col-span-4 lg:col-span-3 drop-cap text-body-md text-on-surface-variant pr-gutter border-r border-ink-black/20 hidden md:block">
            The Veritas AI cluster employs a specialized phalanx of agentic models. Each model is trained on distinct sensory inputs to deconstruct narratives across all modern media formats. They do not merely analyze; they interrogate.
          </div>

          {/* Cards Grid */}
          <div className="col-span-1 md:col-span-8 lg:col-span-9 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-gutter">
            {agents.map((agent) => (
              <article
                key={agent.id}
                className={`glass-card p-6 flex flex-col h-full hover:-translate-y-1 transition-transform duration-300 relative group cursor-pointer ${
                  agent.core ? "bg-ink-black text-parchment" : ""
                }`}
              >
                <div
                  className={`absolute top-0 right-0 w-4 h-4 border-t border-r mt-2 mr-2 ${
                    agent.core ? "border-parchment/40" : "border-ink-black/40"
                  }`}
                ></div>
                <div className="mb-8 relative h-16 w-16">
                  <span
                    className={`material-symbols-outlined text-[4rem] transition-colors group-hover:text-gold-foil ${
                      agent.core ? "text-secondary" : "text-ink-black"
                    }`}
                  >
                    {agent.icon}
                  </span>
                </div>
                <h3
                  className={`font-mono-label text-mono-label uppercase tracking-widest mb-2 ${
                    agent.core ? "text-parchment/70" : "text-ink-black/70"
                  }`}
                >
                  {agent.id}
                </h3>
                <h4
                  className={`font-headline-md text-headline-md mb-4 ${
                    agent.core ? "text-parchment" : "text-ink-black"
                  }`}
                >
                  {agent.title}
                </h4>
                <p
                  className={`font-body-md text-body-md flex-grow ${
                    agent.core ? "text-parchment/80" : "text-on-surface-variant"
                  }`}
                >
                  {agent.description}
                </p>
                <div
                  className={`mt-4 pt-4 border-t flex justify-between items-center ${
                    agent.core ? "border-parchment/20" : "border-ink-black/10"
                  }`}
                >
                  <span
                    className={`font-mono-label text-mono-label ${
                      agent.core ? "text-secondary" : "text-trust-green"
                    }`}
                  >
                    {agent.status}
                  </span>
                  <span
                    className={`material-symbols-outlined ${
                      agent.core ? "text-parchment/40" : "text-ink-black/40"
                    }`}
                  >
                    arrow_forward
                  </span>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Technical Rule */}
      <div className="w-full h-px bg-ink-black/20 my-0 relative">
        <div className="absolute -bottom-[5px] left-0 w-3 h-3 border-b border-l border-ink-black"></div>
        <div className="absolute -bottom-[5px] right-0 w-3 h-3 border-b border-r border-ink-black"></div>
      </div>
    </>
  );
}
