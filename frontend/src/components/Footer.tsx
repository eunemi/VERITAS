import Link from "next/link";
import { Slug, Spread } from "@/components/agents/shared/layout";
import { DESK_ORDER, DESKS } from "@/lib/desks";

/**
 * The foot of the paper.
 *
 * Previously a generic kit footer: a hexagon glyph beside the wordmark, three
 * pill icon buttons, and six links, half of which went to `#`. Everything here
 * now resolves, and the desks are read from the register rather than retyped.
 */

interface Column {
  heading: string;
  links: Array<{ href: string; label: string }>;
}

const COLUMNS: Column[] = [
  {
    heading: "Desks",
    links: DESK_ORDER.map((id) => ({
      href: `/intel/${id}`,
      label: `${DESKS[id].number} · ${DESKS[id].name}`,
    })),
  },
  {
    heading: "Sections",
    links: [
      { href: "/world", label: "World" },
      { href: "/economy", label: "Economy" },
      { href: "/tech", label: "Technology" },
      { href: "/archive", label: "The archive" },
    ],
  },
  {
    heading: "The work",
    links: [
      { href: "/intel", label: "How Veritas reads" },
      { href: "/investigate", label: "Submit an artifact" },
      { href: "/privacy", label: "What we keep" },
      { href: "/terms", label: "Terms of use" },
    ],
  },
];

/** Off-site, so each one carries `rel` alongside `target`. */
const ELSEWHERE = [
  { href: "https://x.com", label: "X" },
  { href: "https://github.com", label: "GitHub" },
  { href: "https://linkedin.com", label: "LinkedIn" },
];

export default function Footer() {
  return (
    <footer className="w-full border-t-2 border-ink-black bg-parchment">
      <Spread className="pt-stack-lg pb-stack-md">
        <div className="grid gap-stack-lg lg:grid-cols-12 lg:gap-gutter">
          <div className="lg:col-span-4">
            <Link
              href="/"
              className="font-masthead inline-block text-[46px] leading-none font-black tracking-[-0.03em] text-ink-black transition-colors hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
            >
              VERITAS
            </Link>
            <p className="font-headline-md mt-4 max-w-[26ch] text-[21px] leading-tight font-normal text-ink-black/70 italic">
              Six desks read the artifact. One of them signs.
            </p>
          </div>

          {COLUMNS.map((column) => (
            <nav key={column.heading} aria-labelledby={`foot-${column.heading}`} className="lg:col-span-2">
              <Slug id={`foot-${column.heading}`} className="text-secondary">
                {column.heading}
              </Slug>
              <ul className="mt-stack-sm flex flex-col gap-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="font-body-sm text-body-sm text-ink-black/70 underline decoration-ink-black/20 decoration-1 underline-offset-4 transition-colors hover:text-secondary hover:decoration-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}

          <div className="lg:col-span-2">
            <Slug className="text-secondary">Elsewhere</Slug>
            <ul className="mt-stack-sm flex flex-col gap-2">
              {ELSEWHERE.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-body-sm text-body-sm text-ink-black/70 underline decoration-ink-black/20 decoration-1 underline-offset-4 transition-colors hover:text-secondary hover:decoration-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
                  >
                    {link.label} &nearr;
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Spread>

      <Spread className="border-t border-ink-black/15 py-stack-sm">
        <div className="flex flex-wrap items-baseline justify-between gap-x-gutter gap-y-2">
          <Slug className="text-ink-black/45">
            &copy; 2026 Veritas AI · All truth is traceable
          </Slug>

        </div>
      </Spread>
    </footer>
  );
}
