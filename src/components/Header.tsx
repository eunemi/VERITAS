import React from "react";
import Link from "next/link";

export default function Header() {
  return (
    <header className="w-full flex flex-col items-center px-margin-mobile md:px-margin-desktop py-stack-md max-w-[1440px] mx-auto border-b border-primary/20 sticky top-0 bg-parchment/90 backdrop-blur-sm z-40">
      <div className="flex justify-between items-center w-full relative">
        {/* Brand */}
        <Link href="/" className="text-4xl font-bold text-primary tracking-tighter">
          VERITAS
        </Link>
        {/* Desktop Nav */}
        <nav className="hidden md:flex gap-gutter items-center absolute left-1/2 -translate-x-1/2">
          <Link
            href="#"
            className="font-mono-label text-mono-label text-on-surface-variant hover:text-gold-foil transition-colors duration-300"
          >
            WORLD
          </Link>
          <Link
            href="#"
            className="font-mono-label text-mono-label text-on-surface-variant hover:text-gold-foil transition-colors duration-300"
          >
            INTEL
          </Link>
          <Link
            href="#"
            className="font-mono-label text-mono-label text-on-surface-variant hover:text-gold-foil transition-colors duration-300"
          >
            ECONOMY
          </Link>
          <Link
            href="#"
            className="font-mono-label text-mono-label text-on-surface-variant hover:text-gold-foil transition-colors duration-300"
          >
            TECH
          </Link>
          <Link
            href="#"
            className="font-mono-label text-mono-label text-on-surface-variant hover:text-gold-foil transition-colors duration-300"
          >
            ARCHIVE
          </Link>
        </nav>
        {/* Actions */}
        <div className="flex items-center gap-stack-sm">
          <button className="hidden md:flex items-center gap-2 bg-ink-black text-parchment font-mono-label text-mono-label px-6 py-3 border border-ink-black hover:bg-transparent hover:text-ink-black transition-all duration-300">
            LAUNCH INVESTIGATION
          </button>
          <button className="p-2 hover:text-gold-foil transition-colors">
            <span className="material-symbols-outlined">public</span>
          </button>
        </div>
      </div>
    </header>
  );
}
