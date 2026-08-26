"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { Band, Slug } from "@/components/agents/shared/layout";
import { DESK_ISSUE } from "@/lib/desks";

/**
 * The panel that pulls down from the masthead.
 *
 * Both of the site's overlays are the same object — a sheet of the paper, dropped
 * over the page under its own ink band — and they were each about to own a focus
 * trap, a scroll lock and an Escape handler. Those are here once. What differs
 * between the commission slip and the account panel is only what is printed on them.
 */

const FOCUSABLE =
  "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])";

function focusablesIn(root: HTMLElement | null): HTMLElement[] {
  if (!root) return [];
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) => element.offsetParent !== null,
  );
}

export function Drawer({
  onClose,
  labelledBy,
  standing,
  children,
}: {
  /** Dismiss. Wired to the close action, Escape and the backdrop alike. */
  onClose: () => void;
  /** Id of the heading inside `children` that names this panel. */
  labelledBy: string;
  /** One or two words for the ink band, after the masthead and section. */
  standing: string;
  children: React.ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    /* Whatever the panel marks as its opening element, or its first focusable if it
       marks none — never the page behind it. */
    const panel = panelRef.current;
    const opener =
      panel?.querySelector<HTMLElement>("[data-first]") ?? focusablesIn(panel)[0];
    opener?.focus();
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

      // Keep tabbing inside the panel while it covers the page.
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
          aria-labelledby={labelledBy}
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
              <Slug className="hidden text-parchment/40 sm:inline">{standing}</Slug>
              <Slug className="hidden text-parchment/40 md:inline">
                Issue {DESK_ISSUE}
              </Slug>
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

          {children}
        </motion.div>
      </div>
    </MotionConfig>
  );
}

/** The two ways a panel can go away, handed to whatever is printed on it. */
export interface Dismiss {
  /** Done here — hand focus back to the action that opened the panel. */
  close: () => void;
  /** Leaving for somewhere else — close without pulling focus off the way out. */
  leave: () => void;
}

/**
 * Anything that opens a drawer.
 *
 * The panel is portalled to the body because the masthead carries a backdrop
 * filter, which makes it a containing block for fixed children — a panel rendered
 * inside the header would be trapped in the header.
 */
export function DrawerTrigger({
  className,
  children,
  onOpen,
  panel: Panel,
}: {
  className: string;
  children: React.ReactNode;
  /** Fires as the panel opens, so a host menu can close itself behind it. */
  onOpen?: () => void;
  /**
   * What is printed on the panel. A component rather than a render callback: it is
   * mounted here, so it must be the same component across renders or React would
   * tear the open panel down and build it again on every one.
   */
  panel: React.ComponentType<Dismiss>;
}) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    buttonRef.current?.focus();
  }, []);

  const leave = useCallback(() => setOpen(false), []);

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
              {/* Keyed so the panel is one element entering and leaving, rather than a
                  different element each render that never gets to animate out. */}
              {open ? <Panel key="panel" close={close} leave={leave} /> : null}
            </AnimatePresence>,
            document.body,
          )}
    </>
  );
}
