import React from "react";
import Link from "next/link";

export default function Footer() {
  return (
    <footer className="bg-parchment dark:bg-ink-black grid grid-cols-1 md:grid-cols-12 gap-gutter px-margin-desktop py-stack-xl w-full border-t border-primary/20 mt-stack-xl max-w-[1440px] mx-auto">
      <div className="col-span-1 md:col-span-4 flex flex-col justify-between">
        <div className="font-headline-md text-headline-md text-primary dark:text-on-primary">
          VERITAS
        </div>
        <p className="font-mono-label text-mono-label text-on-surface-variant dark:text-on-primary-container mt-4 md:mt-0">
          © 2026 VERITAS AI. ALL TRUTH IS TRACEABLE.
        </p>
      </div>
      <div className="col-span-1 md:col-span-8 flex flex-col md:flex-row gap-stack-md md:justify-end">
        <nav className="flex flex-col gap-stack-sm">
          <h4 className="font-mono-label text-mono-label font-bold text-ink-black mb-2">
            PROTOCOLS
          </h4>
          <Link
            href="#"
            className="font-body-md text-body-md text-on-surface-variant dark:text-on-primary-container hover:text-secondary dark:hover:text-secondary-fixed transition-all duration-200 hover:scale-95 hover:opacity-90"
          >
            Archival Ethics
          </Link>
          <Link
            href="#"
            className="font-body-md text-body-md text-on-surface-variant dark:text-on-primary-container hover:text-secondary dark:hover:text-secondary-fixed transition-all duration-200 hover:scale-95 hover:opacity-90"
          >
            Chain of Custody
          </Link>
          <Link
            href="#"
            className="font-body-md text-body-md text-on-surface-variant dark:text-on-primary-container hover:text-secondary dark:hover:text-secondary-fixed transition-all duration-200 hover:scale-95 hover:opacity-90"
          >
            Whistleblower Protocols
          </Link>
        </nav>
      </div>
    </footer>
  );
}
