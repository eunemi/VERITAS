import React from "react";
import { VerificationBadge, VerificationStatus } from "./VerificationBadge";

interface StoryCardProps {
  category: string;
  headline: string;
  description: string;
  source: string;
  date: string;
  location?: string;
  verificationStatus?: VerificationStatus;
  featured?: boolean;
}

export function StoryCard({
  category,
  headline,
  description,
  source,
  date,
  location,
  verificationStatus,
  featured = false,
}: StoryCardProps) {
  return (
    <article className={`flex flex-col gap-4 border-t border-primary/20 pt-4 ${featured ? 'md:grid md:grid-cols-2 md:gap-8' : ''}`}>
      {/* If featured and we want an image on one side, we could render a placeholder here */}
      {featured && (
        <div className="w-full aspect-[4/3] bg-primary/5 border border-primary/10 relative overflow-hidden flex items-center justify-center grayscale">
          <div className="absolute inset-0 texture-overlay opacity-20"></div>
          <span className="material-symbols-outlined text-4xl text-primary/20">image</span>
        </div>
      )}
      
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-mono-label text-mono-label text-secondary uppercase">
            {category} {location && `— ${location}`}
          </span>
          {verificationStatus && <VerificationBadge status={verificationStatus} />}
        </div>
        
        <h3 className={`${featured ? 'font-masthead text-4xl md:text-5xl leading-tight' : 'font-headline-md text-2xl leading-snug'} text-primary font-bold tracking-tight`}>
          {headline}
        </h3>
        
        <p className="font-body-md text-on-surface-variant line-clamp-3">
          {description}
        </p>
        
        <div className="flex items-center justify-between mt-auto pt-4 border-t border-primary/10">
          <div className="flex flex-col">
            <span className="font-mono-label text-[10px] uppercase text-primary font-bold">{source}</span>
            <span className="font-mono-label text-[10px] uppercase text-on-surface-variant">{date}</span>
          </div>
          <button className="font-mono-label text-xs font-bold text-secondary hover:text-ink-black transition-colors flex items-center gap-1 group">
            READ ANALYSIS
            <span className="material-symbols-outlined text-sm group-hover:translate-x-1 transition-transform">arrow_forward</span>
          </button>
        </div>
      </div>
    </article>
  );
}
