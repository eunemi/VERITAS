"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence, MotionConfig } from "framer-motion";
import { CommissionButton, CommissionTrigger } from "@/components/CommissionSlip";
import { Slug } from "@/components/agents/shared/layout";

const navLinks = [
  { href: "/world", label: "WORLD" },
  { href: "/intel", label: "INTEL" },
  { href: "/economy", label: "ECONOMY" },
  { href: "/tech", label: "TECH" },
  { href: "/archive", label: "ARCHIVE" },
];

export default function Header() {
  const pathname = usePathname();

  /* The sheet remembers which page it was opened on rather than being closed by an
     effect, so any navigation — link, back button, or slip — closes it for free. */
  const [openedAt, setOpenedAt] = useState<string | null>(null);
  const menuOpen = openedAt !== null && openedAt === pathname;

  useEffect(() => {
    if (!menuOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenedAt(null);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

  return (
    <header className="w-full flex flex-col items-center px-margin-mobile md:px-margin-desktop py-stack-md max-w-[1440px] mx-auto border-b border-primary/20 sticky top-0 bg-parchment/90 backdrop-blur-sm z-40">
      <div className="flex justify-between items-center w-full relative">
        {/* Brand */}
        <Link
          href="/"
          className="text-4xl font-bold text-primary tracking-tighter focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
        >
          VERITAS
        </Link>

        {/* Desktop nav */}
        <nav
          aria-label="Sections"
          className="hidden md:flex gap-gutter items-center absolute left-1/2 -translate-x-1/2"
        >
          {navLinks.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive ? "page" : undefined}
                className={`font-mono-label text-mono-label relative py-1 transition-colors duration-300 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black ${
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
        <div className="flex items-center gap-stack-sm">
          <CommissionButton />

          {/* Mobile menu. Two rules rather than an icon glyph, so the header needs
              no icon font, and the second rule shortens when the sheet is open. */}
          <button
            type="button"
            onClick={() => setOpenedAt(menuOpen ? null : pathname)}
            aria-expanded={menuOpen}
            aria-controls="masthead-menu"
            className="flex md:hidden cursor-pointer flex-col items-end justify-center gap-[5px] px-1 py-2 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            <span className="sr-only">{menuOpen ? "Close menu" : "Open menu"}</span>
            <span aria-hidden className="block h-[2px] w-6 bg-ink-black" />
            <span
              aria-hidden
              className={`block h-[2px] bg-ink-black transition-all duration-300 ${
                menuOpen ? "w-3" : "w-6"
              }`}
            />
          </button>
        </div>
      </div>

      {/* The sheet is absolute, not fixed: the header's backdrop filter makes it a
          containing block, so a fixed panel here would be trapped inside it. */}
      <MotionConfig reducedMotion="user">
        <AnimatePresence>
          {menuOpen ? (
            <motion.nav
              key="masthead-menu"
              id="masthead-menu"
              aria-label="Sections"
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="absolute top-full right-0 left-0 z-40 border-y-2 border-ink-black bg-background px-margin-mobile pb-stack-md shadow-[0_24px_40px_-20px_rgba(26,26,26,0.45)] md:hidden"
            >
              <ul>
                {navLinks.map((link) => {
                  const isActive = pathname === link.href;
                  return (
                    <li key={link.href}>
                      <Link
                        href={link.href}
                        aria-current={isActive ? "page" : undefined}
                        onClick={() => setOpenedAt(null)}
                        className={`font-headline-md flex items-baseline justify-between border-b border-ink-black/12 py-4 text-[26px] leading-none transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black ${
                          isActive ? "text-secondary" : "text-ink-black hover:text-secondary"
                        }`}
                      >
                        {link.label.charAt(0) + link.label.slice(1).toLowerCase()}
                        <Slug className="text-ink-black/30">
                          {isActive ? "Reading" : "Open"}
                        </Slug>
                      </Link>
                    </li>
                  );
                })}
              </ul>

              <CommissionTrigger
                onOpen={() => setOpenedAt(null)}
                className="font-mono-label text-mono-label mt-stack-md flex w-full cursor-pointer items-center justify-center border border-ink-black bg-ink-black px-6 py-4 text-parchment transition-colors duration-300 hover:bg-transparent hover:text-ink-black focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black"
              >
                START INVESTIGATION
              </CommissionTrigger>
            </motion.nav>
          ) : null}
        </AnimatePresence>
      </MotionConfig>
    </header>
  );
}
