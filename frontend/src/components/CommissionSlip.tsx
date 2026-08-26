"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "framer-motion";


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
  const pathname = usePathname();
  const router = useRouter();

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    if (onOpen) onOpen();

    if (pathname === "/") {
      const el = document.getElementById("agents-section");
      if (el) {
        el.scrollIntoView({ behavior: "smooth" });
      }
    } else {
      router.push("/#agents-section");
    }
  };

  return (
    <a href="/#agents-section" className={className} onClick={handleClick}>
      {children}
    </a>
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
