import React from "react";
import Header from "@/components/Header";
import Hero from "@/components/Hero";
import AgentsSection from "@/components/AgentsSection";
import Footer from "@/components/Footer";

export default function Home() {
  return (
    <>
      <Header />
      <main className="w-full max-w-[1440px] mx-auto px-margin-mobile md:px-margin-desktop">
        <Hero />
        <AgentsSection />
      </main>
      <Footer />
    </>
  );
}
