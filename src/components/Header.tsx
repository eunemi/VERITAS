"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";

const navLinks = [
  { href: "/world", label: "WORLD" },
  { href: "/intel", label: "INTEL" },
  { href: "/economy", label: "ECONOMY" },
  { href: "/tech", label: "TECH" },
  { href: "/archive", label: "ARCHIVE" },
];

const globalEditions = [
  "WORLD",
  "NORTH AMERICA",
  "EUROPE",
  "ASIA",
  "MIDDLE EAST",
  "AFRICA",
  "LATIN AMERICA",
];

export default function Header() {
  const pathname = usePathname();
  const [isEditionOpen, setIsEditionOpen] = useState(false);

  return (
    <header className="w-full flex flex-col items-center px-margin-mobile md:px-margin-desktop py-stack-md max-w-[1440px] mx-auto border-b border-primary/20 sticky top-0 bg-parchment/90 backdrop-blur-sm z-40">
      <div className="flex justify-between items-center w-full relative">
        {/* Brand */}
        <Link href="/" className="text-4xl font-bold text-primary tracking-tighter">
          VERITAS
        </Link>
        {/* Desktop Nav */}
        <nav className="hidden md:flex gap-gutter items-center absolute left-1/2 -translate-x-1/2">
          {navLinks.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`font-mono-label text-mono-label relative py-1 transition-colors duration-300 ${
                  isActive ? "text-secondary" : "text-on-surface-variant hover:text-ink-black"
                }`}
              >
                {link.label}
                {isActive && (
                  <motion.div
                    layoutId="active-nav-underline"
                    className="absolute left-0 right-0 bottom-0 h-[2px] bg-secondary"
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                  />
                )}
              </Link>
            );
          })}
        </nav>
        {/* Actions */}
        <div className="flex items-center gap-stack-sm relative">
          <Link href="/investigate" className="hidden md:flex items-center gap-2 bg-ink-black text-parchment font-mono-label text-mono-label px-6 py-3 border border-ink-black hover:bg-transparent hover:text-ink-black transition-all duration-300">
            START INVESTIGATION
          </Link>
          <div className="relative">
            <button 
              onClick={() => setIsEditionOpen(!isEditionOpen)}
              className={`p-2 transition-colors flex items-center ${isEditionOpen ? 'text-secondary' : 'hover:text-ink-black text-on-surface-variant'}`}
            >
              <span className="material-symbols-outlined">public</span>
            </button>
            <AnimatePresence>
              {isEditionOpen && (
                <motion.div
                  initial={{ opacity: 0, y: 10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 10, scale: 0.95 }}
                  transition={{ duration: 0.2 }}
                  className="absolute right-0 top-full mt-4 w-56 bg-parchment border border-primary/20 shadow-xl z-50 flex flex-col p-4 glass-card"
                >
                  <span className="font-mono-label text-mono-label text-secondary mb-4 border-b border-primary/10 pb-2">GLOBAL EDITION</span>
                  {globalEditions.map((edition) => (
                    <button
                      key={edition}
                      onClick={() => setIsEditionOpen(false)}
                      className="text-left font-body-md text-sm py-2 px-2 hover:bg-primary/5 hover:text-secondary transition-colors"
                    >
                      {edition}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </header>
  );
}
