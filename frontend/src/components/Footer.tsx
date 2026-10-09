import Link from "next/link";
import { CommissionTrigger } from "@/components/CommissionSlip";
import { Spread } from "@/components/agents/shared/layout";
import { DESK_ORDER, DESKS } from "@/lib/desks";
import styles from "./Footer.module.css";

interface FooterLink {
  href: string;
  label: string;
  number?: string;
}

interface Column {
  id: string;
  heading: string;
  links: FooterLink[];
}

const COLUMNS: Column[] = [
  {
    id: "desks",
    heading: "The desks",
    links: DESK_ORDER.map((id) => ({
      href: `/intel/${id}`,
      label: DESKS[id].name,
      number: DESKS[id].number,
    })),
  },
  {
    id: "sections",
    heading: "Explore",
    links: [
      { href: "/world", label: "World" },
      { href: "/economy", label: "Economy" },
      { href: "/tech", label: "Technology" },
      { href: "/archive", label: "The archive" },
    ],
  },
  {
    id: "work",
    heading: "The work",
    links: [
      { href: "/intel", label: "Our method" },
      { href: "/privacy", label: "What we keep" },
      { href: "/terms", label: "Terms of use" },
    ],
  },
];

const ELSEWHERE = [
  { href: "https://x.com", label: "X / Twitter" },
  { href: "https://github.com", label: "GitHub" },
  { href: "https://linkedin.com", label: "LinkedIn" },
];

function Arrow({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      className={className}
    >
      <path
        d="M5 19 19 5M5 5h14v14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** A printer's monogram, rather than a verification or service-status badge. */
function Monogram() {
  return (
    <svg aria-hidden="true" viewBox="0 0 80 80" className="h-[76px] w-[76px] shrink-0">
      <circle cx="40" cy="40" r="34" fill="none" stroke="currentColor" strokeOpacity=".35" />
      <circle cx="40" cy="40" r="29" fill="none" stroke="currentColor" strokeOpacity=".15" />
      <path d="M40 1v11m0 56v11M1 40h11m56 0h11" stroke="currentColor" strokeOpacity=".6" />
      <path d="m21 24 18 34h3l16-34h-9v2h5L42 51 29 26h6v-2Z" fill="currentColor" />
      <path d="m40 13 2 4-2 4-2-4Z" fill="#d88876" />
    </svg>
  );
}

export default function Footer() {
  return (
    <footer className={`${styles.footer} w-full text-parchment`}>
      <Spread>
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-parchment/15 py-5">
          <p className={`${styles.eyebrow} flex items-center gap-3`}>
            <span aria-hidden="true" className="h-1.5 w-1.5 bg-[#d88876]" />
            The pursuit of truth
          </p>
          <p className={`${styles.eyebrow} hidden text-parchment/60 sm:block`}>
            Evidence over everything
          </p>
        </div>

        <div className="grid items-end gap-9 border-b border-parchment/20 py-10 md:py-12 lg:grid-cols-[1.5fr_1fr] lg:gap-20">
          <h2 className={`${styles.editorial} text-[clamp(2.5rem,4.6vw,4.125rem)] leading-[1.12] font-normal tracking-[-0.045em]`}>
            Question the story.
            <br />
            <em className="font-normal text-[#d88876]">Find the truth.</em>
          </h2>

          <div className="max-w-[23rem] lg:ml-auto lg:w-full">
            <p className="text-[15px] leading-[1.8] text-parchment/70">
              A claim. A frame. A story that doesn&rsquo;t add up.
              Bring it to the desk. Follow the evidence.
            </p>
            <CommissionTrigger className={`${styles.investigate} mt-6 flex w-full cursor-pointer items-center justify-between gap-5 border-b border-parchment/35 pb-4 text-left`}>
              <span className="text-[15px] font-medium">Start an investigation</span>
              <span className={styles.actionArrow}>
                <Arrow className="h-5 w-5" />
              </span>
            </CommissionTrigger>
          </div>
        </div>

        <div className="grid gap-10 py-10 lg:grid-cols-[1.05fr_2fr] lg:gap-14">
          <div className="flex items-start gap-5 lg:flex-col lg:gap-4 xl:flex-row xl:gap-5">
            <Monogram />
            <div>
              <p className={`${styles.editorial} max-w-[16rem] text-[24px] leading-[1.3] tracking-[-0.02em]`}>
                Clarity in a world<br className="hidden lg:block" /> of noise.
              </p>
              <p className="mt-3 max-w-[16rem] text-[13px] leading-[1.8] text-parchment/60">
                Look closer. Ask better questions.
                <br />
                Know what stands behind the story.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-x-6 gap-y-8 sm:grid-cols-4 sm:gap-x-5">
            {COLUMNS.map((column) => (
              <nav key={column.id} aria-labelledby={`foot-${column.id}`}>
                <h3 id={`foot-${column.id}`} className={`${styles.eyebrow} mb-4 text-[#d88876]`}>
                  {column.heading}
                </h3>
                <ul>
                  {column.links.map((link) => (
                    <li key={link.href}>
                      <Link href={link.href} className={styles.navLink}>
                        {link.number ? (
                          <span className="text-[12px] tabular-nums text-parchment/60">
                            {link.number}
                          </span>
                        ) : null}
                        <span>{link.label}</span>
                      </Link>
                    </li>
                  ))}
                  {column.id === "work" ? (
                    <li>
                      <CommissionTrigger className={`${styles.navLink} cursor-pointer text-left`}>
                        Submit an artifact
                      </CommissionTrigger>
                    </li>
                  ) : null}
                </ul>
              </nav>
            ))}

            <nav aria-labelledby="foot-elsewhere">
              <h3 id="foot-elsewhere" className={`${styles.eyebrow} mb-4 text-[#d88876]`}>
                Elsewhere
              </h3>
              <ul>
                {ELSEWHERE.map((link) => (
                  <li key={link.href}>
                    <a
                      href={link.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`${styles.navLink} justify-between gap-3 sm:max-w-[8rem]`}
                    >
                      <span>{link.label}<span className="sr-only"> (opens in a new tab)</span></span>
                      <Arrow className="h-3 w-3 shrink-0 text-parchment/50" />
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </div>

        <div className={styles.signature}>
          <div className="flex items-center justify-between gap-4">
            <span className={`${styles.eyebrow} text-parchment/60`}>All truth is traceable</span>
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 shrink-0 text-[#d88876]">
              <path d="M12 2v20M2 12h20M5 5l14 14M5 19 19 5" fill="none" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </div>
          <Link href="/" aria-label="Veritas — home" className={styles.wordmark}>
            <span aria-hidden="true" className="flex w-full justify-between">
              {"VERITAS".split("").map((letter, index) => <span key={index}>{letter}</span>)}
            </span>
          </Link>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-3 border-t border-parchment/20 py-4 text-[12px] leading-6 text-parchment/60">
          <p>&copy; 2026 Veritas AI</p>
          <p className={`${styles.editorial} hidden text-[14px] italic sm:block`}>The last word belongs to the evidence.</p>
          <a href="#" className={`${styles.backToTop} flex min-h-11 items-center gap-3`}>
            Back to top
            <Arrow className="h-3.5 w-3.5 -rotate-45" />
          </a>
        </div>
      </Spread>
    </footer>
  );
}
