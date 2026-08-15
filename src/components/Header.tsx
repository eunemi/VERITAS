"use client";
import React, { useState, useEffect } from "react";
import Link from "next/link";

export default function Header() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 40);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <>
      <header
        className={`w-full fixed top-0 left-0 z-50 transition-all duration-500 border-b ${
          isScrolled
            ? "bg-[#F4EFE6]/95 backdrop-blur-md shadow-sm border-[#1A1A1A]/10 py-2"
            : "bg-transparent border-transparent py-0"
        }`}
      >
        {/* Layer 1: Intelligence Bar */}
        <div
          className={`hidden md:flex justify-between items-center px-6 py-1 text-[9px] uppercase font-sans tracking-[0.2em] text-[#1A1A1A]/60 border-b border-[#1A1A1A]/10 transition-all duration-500 overflow-hidden ${
            isScrolled ? "h-0 opacity-0 border-transparent" : "h-7 opacity-100"
          }`}
        >
          <span>VERITAS INTELLIGENCE NETWORK</span>
          <span>FRIDAY · AUGUST 15 · 2026</span>
          <span>EDITION 01</span>
        </div>

        {/* Layer 2: Main Masthead */}
        <div
          className={`px-4 md:px-10 transition-all duration-500 flex items-center w-full max-w-[1600px] mx-auto ${
            isScrolled ? "justify-between py-1" : "flex-col py-6 md:py-10 relative"
          }`}
        >
          {/* Left Metadata */}
          <div
            className={`hidden md:flex flex-col text-[10px] uppercase font-sans tracking-[0.15em] text-[#1A1A1A]/50 absolute left-10 top-1/2 -translate-y-1/2 transition-opacity duration-300 ${
              isScrolled ? "opacity-0 pointer-events-none" : "opacity-100"
            }`}
          >
            <span>VOL. 01</span>
            <span>GLOBAL EDITION</span>
            <span className="mt-2 text-[#9A2A2A] font-medium">ISSN 01–VERITAS</span>
          </div>

          {/* Center Brand */}
          <div
            className={`flex flex-col items-center justify-center transition-all duration-500 ${
              isScrolled ? "items-start" : "items-center"
            }`}
          >
            <Link
              href="/"
              className={`font-serif font-black text-[#1A1A1A] tracking-tighter leading-none transition-all duration-500 ${
                isScrolled ? "text-2xl" : "text-5xl md:text-7xl"
              }`}
            >
              VERITAS
            </Link>
            <span
              className={`text-[9px] font-sans uppercase tracking-[0.25em] text-[#1A1A1A]/60 mt-3 transition-all duration-500 ${
                isScrolled ? "hidden" : "block"
              }`}
            >
              TRUTH, VERIFIED BY INTELLIGENCE
            </span>
          </div>

          {/* Right Metadata */}
          <div
            className={`hidden md:flex flex-col text-right text-[10px] uppercase font-sans tracking-[0.15em] text-[#1A1A1A]/50 absolute right-10 top-1/2 -translate-y-1/2 transition-opacity duration-300 ${
              isScrolled ? "opacity-0 pointer-events-none" : "opacity-100"
            }`}
          >
            <span>MULTIMODAL TRUTH</span>
            <span>INTELLIGENCE</span>
            <span className="mt-2 text-[#1A1A1A]/40">EST. 2026</span>
          </div>

          {/* Scrolled State Layout Elements */}
          {isScrolled && (
            <div className="hidden md:flex items-center gap-8">
              <NavLinks scrolled={true} />
            </div>
          )}

          {isScrolled && (
            <div className="hidden md:flex items-center gap-8">
              <LiveIndicator />
              <CTAButton />
            </div>
          )}

          {/* Mobile Masthead Metadata */}
          <div
            className={`md:hidden flex flex-col text-[8px] uppercase tracking-widest text-[#1A1A1A]/50 absolute left-4 top-1/2 -translate-y-1/2 ${
              isScrolled ? "hidden" : "block"
            }`}
          >
            <span>GLOBAL EDITION</span>
            <span>2026</span>
          </div>

          {/* Mobile Menu Toggle */}
          <div className="md:hidden absolute right-4 top-1/2 -translate-y-1/2">
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="text-[#1A1A1A] flex items-center justify-center p-2"
            >
              <span className="material-symbols-outlined text-2xl">
                {isMobileMenuOpen ? "close" : "menu"}
              </span>
            </button>
          </div>
        </div>

        {/* Layer 3: Navigation */}
        <div
          className={`hidden md:flex justify-between items-center px-10 transition-all duration-500 overflow-hidden w-full max-w-[1600px] mx-auto ${
            isScrolled
              ? "h-0 opacity-0 border-transparent"
              : "h-[60px] opacity-100 border-t border-b border-[#1A1A1A]/10"
          }`}
        >
          <div className="flex items-center gap-6 flex-1 justify-center">
            <NavLinks scrolled={false} />
          </div>

          <div className="flex items-center gap-8 absolute right-10">
            <LiveIndicator />
            <CTAButton />
          </div>
        </div>
      </header>

      {/* Mobile Fullscreen Editorial Menu */}
      <div
        className={`fixed inset-0 bg-[#F4EFE6] z-40 transition-transform duration-500 pt-28 px-8 md:hidden overflow-y-auto ${
          isMobileMenuOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="text-[10px] uppercase font-sans tracking-[0.2em] text-[#1A1A1A]/40 mb-8 border-b border-[#1A1A1A]/10 pb-2">
          SECTIONS
        </div>
        <nav className="flex flex-col gap-6 text-4xl font-serif text-[#1A1A1A]">
          {["WORLD", "INTELLIGENCE", "ECONOMY", "TECHNOLOGY", "INVESTIGATIONS", "ARCHIVE"].map(
            (item) => (
              <Link
                key={item}
                href="#"
                className="border-b border-[#1A1A1A]/10 pb-4 hover:text-[#9A2A2A] transition-colors"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                {item}
              </Link>
            )
          )}
          <div className="mt-8">
            <CTAButton />
          </div>
        </nav>
      </div>
    </>
  );
}

const NavLinks = ({ scrolled }: { scrolled: boolean }) => {
  const links = [
    "WORLD",
    "INTELLIGENCE",
    "ECONOMY",
    "TECHNOLOGY",
    "INVESTIGATIONS",
    "ARCHIVE",
  ];
  return (
    <>
      {links.map((link, index) => (
        <React.Fragment key={link}>
          <Link
            href="#"
            className={`nav-link group relative font-sans uppercase tracking-[0.15em] transition-colors ${
              scrolled ? "text-[10px] text-[#1A1A1A]/80 hover:text-[#1A1A1A]" : "text-[11px] text-[#1A1A1A]/70 hover:text-[#1A1A1A]"
            }`}
          >
            {link}
            {/* Animated editorial red underline */}
            <span className="absolute -bottom-[2px] left-0 w-0 h-[1px] bg-[#9A2A2A] transition-all duration-300 group-hover:w-full"></span>
          </Link>
          {index < links.length - 1 && !scrolled && (
            <span className="text-[#1A1A1A]/20 text-[12px] px-1 font-light">/</span>
          )}
        </React.Fragment>
      ))}
    </>
  );
};

const LiveIndicator = () => (
  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.15em] font-sans text-[#1A1A1A]/60">
    <span className="w-1.5 h-1.5 rounded-full bg-[#9A2A2A] animate-pulse"></span>
    LIVE INTELLIGENCE
  </div>
);

const CTAButton = () => (
  <button className="group relative bg-[#1A1A1A] text-[#F4EFE6] px-6 py-2.5 text-[10px] uppercase font-sans tracking-[0.2em] transition-colors border border-[#1A1A1A] rounded-none hover:bg-[#2A2A2A]">
    <span className="relative z-10 flex items-center gap-2">
      START INVESTIGATION{" "}
      <span className="transform group-hover:translate-x-1 transition-transform">
        →
      </span>
    </span>
    {/* Subtle red line on hover */}
    <span className="absolute bottom-0 left-0 w-full h-[2px] bg-[#9A2A2A] scale-x-0 origin-left transition-transform duration-300 group-hover:scale-x-100"></span>
  </button>
);
