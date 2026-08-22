import React from "react";
import Hero from "@/components/Hero";
import AgentsSection from "@/components/AgentsSection";

export default function Home() {
  return (
    <main className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop">
      <Hero />
      <AgentsSection />
    </main>
  );
}
