"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Slug, Spread } from "@/components/agents/shared/layout";

/**
 * The archive's two sections.
 *
 * Links rather than a tab that holds state, so each half of the archive is a page with
 * an address: the account panel can send a reader straight to their own file, and the
 * back button behaves the way it does everywhere else on the site.
 */

const SECTIONS = [
  { href: "/archive", label: "Public index", note: "Everything we have signed" },
  { href: "/archive/file", label: "My file", note: "Records filed in your name" },
];

export function ArchiveTabs() {
  const pathname = usePathname();

  return (
    <Spread className="pb-stack-md">
      <nav aria-label="Archive sections" className="border-t-2 border-ink-black">
        <ul className="flex flex-wrap">
          {SECTIONS.map((section) => {
            const here = pathname === section.href;
            return (
              <li key={section.href}>
                <Link
                  href={section.href}
                  aria-current={here ? "page" : undefined}
                  className={`flex flex-col gap-1 border-r border-ink-black/15 px-5 py-3 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-black ${
                    here
                      ? "bg-ink-black text-parchment"
                      : "text-ink-black hover:bg-parchment"
                  }`}
                >
                  <Slug className={here ? "font-bold" : ""}>{section.label}</Slug>
                  <span
                    className={`font-body-sm text-body-sm ${
                      here ? "text-parchment/70" : "text-ink-black/55"
                    }`}
                  >
                    {section.note}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </Spread>
  );
}
