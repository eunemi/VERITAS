import React from "react";
import Hero from "@/components/Hero";
import AgentsSection from "@/components/AgentsSection";

/**
 * The front page carries the photographic ground. It used to sit on <body>, which
 * put a vignetted photograph behind the running text of every section page; here
 * it is behind a masthead and four floating stickers, which is what it was made
 * for, and no paragraph is set on top of it.
 */
export default function Home() {
  return (
    <main className="custom-bg w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop">
      <Hero />
      <AgentsSection />
    </main>
  );
}
