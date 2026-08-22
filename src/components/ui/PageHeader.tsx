import React from "react";

interface PageHeaderProps {
  label: string;
  headline: React.ReactNode;
  subheadline: React.ReactNode;
}

export function PageHeader({ label, headline, subheadline }: PageHeaderProps) {
  return (
    <div className="flex flex-col items-start w-full py-stack-lg border-b border-primary/20 mb-stack-md">
      <span className="font-mono-label text-mono-label text-secondary mb-4 tracking-widest uppercase">
        {label}
      </span>
      <h1 className="font-masthead text-[42px] leading-[48px] md:text-[80px] md:leading-[80px] font-black text-primary uppercase mb-6 tracking-[-0.02em]">
        {headline}
      </h1>
      <p className="font-headline-md text-2xl md:text-3xl text-on-surface-variant max-w-3xl italic">
        {subheadline}
      </p>
    </div>
  );
}
