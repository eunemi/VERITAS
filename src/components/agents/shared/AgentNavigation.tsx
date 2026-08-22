import React from "react";
import Link from "next/link";

interface AgentNavigationProps {
  prevAgent?: { name: string; id: string };
  nextAgent?: { name: string; id: string };
}

export function AgentNavigation({ prevAgent, nextAgent }: AgentNavigationProps) {
  return (
    <div className="w-full border-t border-primary/20 py-8 flex flex-col md:flex-row justify-between items-center gap-6 mt-stack-xl">
      <Link href="/intel" className="font-mono-label text-xs tracking-widest text-primary/60 hover:text-secondary transition-colors uppercase">
        &larr; BACK TO INTELLIGENCE
      </Link>

      <div className="flex items-center gap-8">
        {prevAgent ? (
          <Link href={`/intel/${prevAgent.id}`} className="font-mono-label text-xs tracking-widest text-primary hover:text-secondary transition-colors uppercase group flex items-center gap-2">
            <span className="material-symbols-outlined text-sm group-hover:-translate-x-1 transition-transform">arrow_back</span>
            {prevAgent.name}
          </Link>
        ) : <div className="w-24"></div>}

        {nextAgent ? (
          <Link href={`/intel/${nextAgent.id}`} className="font-mono-label text-xs tracking-widest text-primary hover:text-secondary transition-colors uppercase group flex items-center gap-2">
            {nextAgent.name}
            <span className="material-symbols-outlined text-sm group-hover:translate-x-1 transition-transform">arrow_forward</span>
          </Link>
        ) : <div className="w-24"></div>}
      </div>
    </div>
  );
}
