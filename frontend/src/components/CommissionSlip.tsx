"use client";

import { DrawerTrigger } from "@/components/ui/Drawer";
import { CommissionPanel } from "@/components/CommissionPanel";

/** Anything that opens the slip. */
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
  return (
    <DrawerTrigger className={className} onOpen={onOpen} panel={CommissionPanel}>
      {children}
    </DrawerTrigger>
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
