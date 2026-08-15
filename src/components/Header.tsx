"use client";
import React, { useState } from "react";
import Link from "next/link";

export default function Header() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  return (
    <>
      <header className="w-full relative z-50 border-b border-[#1A1A1A]/15 bg-[#F4EFE6]">
        {/* Optional Metadata Bar */}
        <div className="hidden md:flex justify-between items-center px-8 py-1.5 text-[9px] uppercase font-sans tracking-[0.2em] text-[#1A1A1A]/50 border-b border-[#1A1A1A]/10">
          <span>VERITAS INTELLIGENCE NETWORK</span>
          <span>AUG 15, 2026</span>
          <span>GLOBAL EDITION</span>
        </div>

        {/* Main Navbar */}
        <div className="w-full px-6 md:px-8 h-[88px] flex items-center justify-between max-w-[1600px] mx-auto">
          
          {/* Left: Brand */}
          <div className="flex flex-col justify-center">
            <Link
              href="/"
              className="font-serif font-black text-3xl md:text-4xl text-[#1A1A1A] tracking-tighter leading-none"
            >
              VERITAS
            </Link>
            <span className="text-[8px] md:text-[9px] font-sans uppercase tracking-[0.2em] text-[#1A1A1A]/60 mt-1">
              TRUTH INTELLIGENCE
            </span>
          </div>

          {/* Center: Navigation (Desktop) */}
          <nav className="hidden md:flex items-center gap-6 absolute left-1/2 -translate-x-1/2">
            <NavLinks />
          </nav>

          {/* Right: Actions (Desktop) */}
          <div className="hidden md:flex items-center gap-6">
            <LiveIndicator />
            <CTAButton />
          </div>

          {/* Mobile Menu Toggle */}
          <div className="md:hidden flex items-center">
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
        <nav className="flex flex-col gap-6 text-3xl font-serif text-[#1A1A1A]">
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
          <div className="mt-8 flex flex-col gap-6">
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
            className="nav-link group relative font-sans text-[11px] uppercase tracking-[0.15em] text-[#1A1A1A]/80 hover:text-[#1A1A1A] transition-colors py-1"
          >
            {link}
            {/* Animated editorial red underline */}
            <span className="absolute bottom-0 left-0 w-0 h-[1px] bg-[#9A2A2A] transition-all duration-300 group-hover:w-full"></span>
          </Link>
          {index < links.length - 1 && (
            <span className="text-[#1A1A1A]/40 text-[12px] px-1 font-black">·</span>
          )}
        </React.Fragment>
      ))}
    </>
  );
};

const LiveIndicator = () => (
  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.15em] font-sans text-[#1A1A1A]">
    <span className="w-1.5 h-1.5 rounded-full bg-[#9A2A2A] animate-pulse"></span>
    LIVE
  </div>
);

const CTAButton = () => (
  <button className="group relative bg-[#1A1A1A] text-[#F4EFE6] px-5 py-2.5 text-[10px] uppercase font-sans tracking-[0.15em] transition-colors border border-[#1A1A1A] rounded-sm hover:bg-[#2A2A2A]">
    <span className="relative z-10 flex items-center gap-2">
      START INVESTIGATION{" "}
      <span className="transform group-hover:translate-x-1 transition-transform">
        →
      </span>
    </span>
  </button>
);
