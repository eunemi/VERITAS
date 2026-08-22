import React from "react";

interface AgentHeaderProps {
  title: string;
  label: string;
  description: string;
}

export function AgentHeader({ title, label, description }: AgentHeaderProps) {
  return (
    <div className="mb-stack-lg">
      <div className="font-mono-label text-xs tracking-widest uppercase text-secondary mb-4">
        {label}
      </div>
      <h1 className="font-headline-lg text-6xl md:text-8xl lg:text-[120px] leading-[0.85] font-black uppercase tracking-tighter text-ink-black mb-6 whitespace-pre-line">
        {title}
      </h1>
      <p className="font-body-lg italic text-xl md:text-2xl text-on-surface-variant max-w-2xl border-l-2 border-secondary pl-6 py-2">
        {description}
      </p>
    </div>
  );
}
