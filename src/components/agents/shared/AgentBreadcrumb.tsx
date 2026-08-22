import React from "react";
import Link from "next/link";

interface AgentBreadcrumbProps {
  agentNumber: string;
  agentName: string;
}

export function AgentBreadcrumb({ agentNumber, agentName }: AgentBreadcrumbProps) {
  return (
    <div className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop py-4 flex items-center gap-2 font-mono-label text-[10px] tracking-widest uppercase text-on-surface-variant border-b border-primary/10">
      <Link href="/intel" className="hover:text-secondary transition-colors">INTELLIGENCE</Link>
      <span>/</span>
      <span className="text-primary/60">{agentNumber}</span>
      <span>/</span>
      <span className="text-primary font-bold">{agentName}</span>
    </div>
  );
}
