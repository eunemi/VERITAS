"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { Band, Slug, Spread } from "@/components/agents/shared/layout";
import { DESK_ISSUE, DESK_ORDER, DESKS, type DeskDefinition } from "@/lib/desks";

/**
 * Commissioning the work.
 *
 * The masthead action used to jump straight to /investigate, which made the reader
 * guess what the site could do before it showed them. It now pulls down the
 * assignment slip: all six desks on one docket, each line stating what that desk
 * reads, so the choice is made before anything is handed over.
 *
 * A docket of ruled lines rather than a grid of cards — the same row language the
 * records themselves are set in, and faster to scan when the reader is deciding.
 */

/* Held in one place so the column heads and the rows can never drift apart.
   `grid` is applied at each use site, because the heads are `hidden lg:grid`
   and a display utility inside this string would fight that one. */
const ROW_GRID =
  "grid-cols-[46px_minmax(0,1fr)] items-baseline gap-x-4 gap-y-1.5 lg:grid-cols-[64px_minmax(0,1fr)_minmax(0,1.05fr)_112px] lg:items-center lg:gap-x-gutter";

/** Five desks report on an artifact; the sixth reads the other five. */
const REPORTING = DESK_ORDER.slice(0, 5).map((id) => DESKS[id]);
const CORE = DESKS[DESK_ORDER[5]];

function readsOf(desk: DeskDefinition): string {
  return desk.method.find((row) => row.key === "Reads")?.value ?? "";
}

function focusablesIn(root: HTMLElement | null): HTMLElement[] {
  if (!root) return [];
  return Array.from(root.querySelectorAll<HTMLElement>("a[href], button:not([disabled])"));
}

const DOCKET = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.04, delayChildren: 0.06 } },
};

const LINE = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.24 } },
};

/* The core line lands after the five it depends on, so its delay is set here —
   a transition inside a variant wins over the component's transition prop. */
const CORE_LINE = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.24, delay: 0.3 } },
};

/* ---------------------------------------------------------------- a line ---- */

/**
 * One line of the docket: the agent number hanging in the margin, the desk, what
 * it reads, and the way in. Hovering strikes the line in ink — the same inversion
 * the masthead action and the core card already use.
 */
function DocketRow({
  desk,
  onPick,
  first = false,
}: {
  desk: DeskDefinition;
  onPick: () => void;
  /** Marks the line that takes focus when the slip opens. */
  first?: boolean;
}) {
  return (
    <Link
      href={`/intel/${desk.id}`}
      onClick={onPick}
      data-first={first ? "" : undefined}
      className={`group grid ${ROW_GRID} border-b border-ink-black/12 px-3 py-4 transition-colors duration-200 hover:bg-ink-black focus-visible:bg-ink-black focus-visible:outline-none`}
    >
      <span className="font-headline-md tabular text-[32px] leading-none font-bold text-ink-black/20 transition-colors group-hover:text-secondary group-focus-visible:text-secondary lg:text-[38px]">
        {desk.number}
      </span>

      <span className="font-headline-md text-[21px] leading-tight text-ink-black transition-colors group-hover:text-parchment group-focus-visible:text-parchment lg:text-[24px]">
        {desk.titleLines.join(" ")}
      </span>

      <Slug className="col-start-2 text-ink-black/45 transition-colors group-hover:text-parchment/60 group-focus-visible:text-parchment/60 lg:col-start-3">
        {readsOf(desk)}
      </Slug>

      <Slug className="col-start-2 text-ink-black/35 transition-colors group-hover:text-gold-foil group-focus-visible:text-gold-foil lg:col-start-4 lg:text-right">
        Open desk &rarr;
      </Slug>
    </Link>
  );
}

/* ----------------------------------------------------------------- slip ---- */

function CommissionSlip({
  onClose,
  onPick,
}: {
  /** Dismiss and hand focus back to the action that opened the slip. */
  onClose: () => void;
  /** Dismiss on the way to a desk, leaving focus to the arriving page. */
  onPick: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.querySelector<HTMLElement>("[data-first]")?.focus();
  }, []);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      // Keep tabbing inside the slip while it covers the page.
      const items = focusablesIn(panelRef.current);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <MotionConfig reducedMotion="user">
      <div className="fixed inset-0 z-50">
        <motion.div
          aria-hidden
          onClick={onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="absolute inset-0 bg-ink-black/55"
        />

        <motion.div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="commission-heading"
          initial={{ opacity: 0, y: -22 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -22 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="relative max-h-dvh w-full overflow-y-auto border-b-2 border-ink-black bg-background shadow-[0_36px_70px_-24px_rgba(26,26,26,0.55)]"
        >
          <Band
            className="bg-ink-black text-parchment"
            inner="flex h-9 items-center justify-between gap-gutter"
          >
            <span className="flex items-baseline gap-3">
              <Slug className="font-bold">Veritas</Slug>
              <Slug className="text-parchment/40">Commission</Slug>
              <Slug className="hidden text-parchment/40 sm:inline">Six desks open</Slug>
              <Slug className="hidden text-parchment/40 md:inline">Issue {DESK_ISSUE}</Slug>
            </span>
            <button
              type="button"
              onClick={onClose}
              className="flex shrink-0 cursor-pointer items-center gap-2 py-1 transition-colors hover:text-gold-foil focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-parchment"
            >
              <Slug>Close</Slug>
              <span aria-hidden className="text-[13px] leading-none">
                &#10005;
              </span>
            </button>
          </Band>

          <Spread className="py-stack-lg">
            <div className="flex flex-wrap items-end justify-between gap-stack-md border-b-2 border-ink-black pb-stack-sm">
              <div>
                <Slug className="text-secondary">Assignment slip</Slug>
                <h2
                  id="commission-heading"
                  className="font-masthead mt-stack-sm text-[clamp(34px,5.2vw,58px)] leading-[0.94] font-black tracking-[-0.02em] text-ink-black"
                >
                  <span className="block">What are you</span>
                  <span className="block pl-[0.06em] font-normal italic">holding?</span>
                </h2>
              </div>
              <p className="font-body-sm text-body-sm max-w-[40ch] text-ink-black/60">
                Pick the desk that reads it. Each one takes the artifact, marks what it finds on
                the artifact itself, and signs a record.
              </p>
            </div>

            <div className="-mx-3 mt-stack-lg">
              <div className={`hidden ${ROW_GRID} px-3 pb-2 lg:grid`}>
                <span />
                <Slug className="text-ink-black/35">Desk</Slug>
                <Slug className="text-ink-black/35">Reads</Slug>
                <span />
              </div>

              <motion.ol
                variants={DOCKET}
                initial="hidden"
                animate="shown"
                className="border-t-2 border-ink-black"
              >
                {REPORTING.map((desk, index) => (
                  <motion.li key={desk.id} variants={LINE}>
                    <DocketRow desk={desk} onPick={onPick} first={index === 0} />
                  </motion.li>
                ))}
              </motion.ol>

              <div className="mt-stack-md flex flex-wrap items-baseline justify-between gap-3 px-3 pb-2">
                <Slug className="text-ink-black/35">Adjudication</Slug>
                <Slug className="text-ink-black/35">Sits after the five have reported</Slug>
              </div>

              <motion.div
                variants={CORE_LINE}
                initial="hidden"
                animate="shown"
                className="border-t-2 border-ink-black"
              >
                <DocketRow desk={CORE} onPick={onPick} />
              </motion.div>
            </div>

            <div className="mt-stack-lg flex flex-wrap items-center justify-between gap-stack-sm border-t border-ink-black/15 pt-stack-sm">
              <p className="font-body-sm text-body-sm text-ink-black/55">
                All six on one artifact?{" "}
                <Link
                  href="/investigate"
                  onClick={onPick}
                  className="text-ink-black underline decoration-secondary decoration-2 underline-offset-4 transition-colors hover:text-secondary"
                >
                  Open the investigation bench
                </Link>
              </p>
              <Slug className="text-ink-black/35">Esc closes this slip</Slug>
            </div>
          </Spread>
        </motion.div>
      </div>
    </MotionConfig>
  );
}

/* --------------------------------------------------------------- action ---- */

/**
 * Anything that opens the slip. The slip is portalled to the body: the header
 * carries a backdrop filter, which makes it a containing block for fixed
 * children, so a panel rendered inside it would be trapped in the header.
 */
export function CommissionTrigger({
  className,
  children,
  onOpen,
}: {
  className: string;
  children: React.ReactNode;
  /** Fires as the slip opens, so a host menu can close itself behind it. */
  onOpen?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    buttonRef.current?.focus();
  }, []);

  const pick = useCallback(() => setOpen(false), []);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => {
          setOpen(true);
          onOpen?.();
        }}
        aria-haspopup="dialog"
        aria-expanded={open}
        className={className}
      >
        {children}
      </button>

      {typeof document === "undefined"
        ? null
        : createPortal(
            <AnimatePresence>
              {open ? <CommissionSlip key="commission" onClose={close} onPick={pick} /> : null}
            </AnimatePresence>,
            document.body,
          )}
    </>
  );
}

/** The masthead action. Desktop only — the mobile menu carries its own. */
export function CommissionButton() {
  return (
    <CommissionTrigger className="hidden md:flex items-center gap-2 bg-ink-black text-parchment font-mono-label text-mono-label px-6 py-3 border border-ink-black cursor-pointer hover:bg-transparent hover:text-ink-black transition-all duration-300">
      START INVESTIGATION
    </CommissionTrigger>
  );
}
