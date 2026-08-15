import React from "react";
import Link from "next/link";

export default function Header() {
  return (
    <header className="fixed top-6 left-1/2 -translate-x-1/2 w-[95%] max-w-[1200px] flex flex-col items-center px-6 md:px-10 py-4 mx-auto border border-white/40 rounded-full shadow-[0_8px_32px_rgba(0,0,0,0.12)] bg-white/20 backdrop-blur-xl z-50 transition-all duration-300">
      <div className="flex justify-between items-center w-full relative">
        {/* Brand */}
        <Link href="/" className="text-3xl font-black text-primary tracking-tighter">
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
          <button className="hidden md:flex items-center gap-2 bg-ink-black text-white font-mono-label text-mono-label px-6 py-2.5 rounded-full border border-ink-black hover:bg-white hover:text-ink-black transition-all duration-300 shadow-md">
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
