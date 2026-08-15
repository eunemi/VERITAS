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
      <header className="w-full relative z-50 bg-transparent transition-all duration-500">
        {/* Layer 1: Intelligence Bar */}
        <div className="hidden md:flex justify-between items-center px-8 py-1.5 text-[9px] uppercase font-sans tracking-[0.2em] text-[#1A1A1A]/50 border-b border-[#1A1A1A]/10 mix-blend-multiply">
          <span className="flex-1">VERITAS INTELLIGENCE NETWORK</span>
          <span className="flex-1 text-center">AUG 15, 2026 · EDITION 01</span>
          <span className="flex-1 text-right">GLOBAL EDITION</span>
        </div>

        {/* Layer 2: Main Masthead */}
        <div className="border-b border-[#1A1A1A]/10">
          <div
            className={`w-full px-6 md:px-8 flex items-center justify-between max-w-[1600px] mx-auto transition-all duration-500 ${
              isScrolled ? "h-[72px]" : "h-[96px]"
            }`}
          >
            {/* Left: Brand */}
            <div className="flex flex-col justify-center mix-blend-multiply">
              <Link
                href="/"
                className="font-serif font-black text-3xl md:text-4xl text-[#1A1A1A]/90 tracking-[-0.04em] leading-none transition-transform hover:opacity-80"
              >
                VERITAS
              </Link>
              <span className="text-[8px] font-sans font-medium uppercase tracking-[0.25em] text-[#1A1A1A]/50 mt-1.5">
                TRUTH INTELLIGENCE
              </span>
            </div>

            {/* Center: Navigation (Desktop) */}
            <nav className="hidden md:flex items-center absolute left-1/2 -translate-x-1/2 mix-blend-multiply">
              <NavLinks />
            </nav>

            {/* Right: Actions (Desktop) */}
            <div className="hidden md:flex items-center gap-8">
              <LiveIndicator />
              <CTAButton />
            </div>

            {/* Mobile Menu Toggle */}
            <div className="md:hidden flex items-center">
              <button
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                className="text-[#1A1A1A] flex items-center justify-center p-2 mix-blend-multiply"
              >
                <span className="material-symbols-outlined text-2xl">
                  {isMobileMenuOpen ? "close" : "menu"}
                </span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Mobile Fullscreen Editorial Menu */}
      <div
        className={`fixed inset-0 bg-[#F4EFE6] z-40 transition-transform duration-500 pt-28 px-8 md:hidden overflow-y-auto ${
          isMobileMenuOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="text-[10px] uppercase font-sans tracking-[0.2em] text-[#1A1A1A]/40 mb-8 border-b border-[#1A1A1A]/10 pb-2 mix-blend-multiply">
          SECTIONS
        </div>
        <nav className="flex flex-col gap-6 text-3xl font-serif text-[#1A1A1A]/90 mix-blend-multiply">
          {["WORLD", "INTEL", "ECONOMY", "TECH", "INVESTIGATIONS", "ARCHIVE"].map(
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
          <div className="mt-8 flex flex-col gap-8">
            <LiveIndicator />
            <CTAButton />
          </div>
        </nav>
      </div>
    </>
  );
}

const NavLinks = () => {
  const links = [
    "WORLD",
    "INTEL",
    "ECONOMY",
    "TECH",
    "INVESTIGATIONS",
    "ARCHIVE",
  ];
  return (
    <>
      {links.map((link, index) => (
        <React.Fragment key={link}>
          <Link
            href="#"
            className="nav-link group relative font-sans font-medium text-[12px] md:text-[13px] uppercase tracking-widest text-[#1A1A1A]/70 hover:text-[#1A1A1A] transition-colors py-1"
          >
            {link}
            {/* Animated editorial red underline */}
            <span className="absolute -bottom-1 left-0 w-0 h-[1px] bg-[#9A2A2A] transition-all duration-300 group-hover:w-full"></span>
          </Link>
          {index < links.length - 1 && (
            <span className="text-[#1A1A1A]/30 text-[10px] px-3 md:px-4 font-black">·</span>
          )}
        </React.Fragment>
      ))}
    </>
  );
};

const LiveIndicator = () => (
  <div className="flex items-center gap-2.5 text-[10px] uppercase tracking-[0.2em] font-sans font-medium text-[#1A1A1A]/80 mix-blend-multiply">
    <span className="w-1.5 h-1.5 rounded-full bg-[#9A2A2A] opacity-80 animate-[pulse_2.5s_cubic-bezier(0.4,0,0.6,1)_infinite]"></span>
    LIVE INTELLIGENCE
  </div>
);

const CTAButton = () => (
  <button className="group relative bg-[#1A1A1A]/95 text-[#F4EFE6] px-7 py-3 text-[10px] uppercase font-sans font-medium tracking-[0.2em] transition-colors border border-[#1A1A1A] rounded-[2px] hover:bg-[#2A2A2A]">
    <span className="relative z-10 flex items-center gap-2">
      START INVESTIGATION{" "}
      <span className="transform group-hover:translate-x-1.5 transition-transform duration-300">
        →
      </span>
    </span>
    {/* Subtle red line on hover */}
    <span className="absolute bottom-0 left-0 w-full h-[2px] bg-[#9A2A2A] scale-x-0 origin-left transition-transform duration-300 group-hover:scale-x-100"></span>
  </button>
);
