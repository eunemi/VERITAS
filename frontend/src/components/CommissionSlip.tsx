"use client";

import { useRouter, usePathname } from "next/navigation";

/** Anything that used to open the slip now scrolls to agents-section. */
export function CommissionTrigger({
  className,
  children,
  onOpen,
}: {
  className?: string;
  children: React.ReactNode;
  onOpen?: () => void;
}) {
  const router = useRouter();
  const pathname = usePathname();

  const handleScroll = () => {
    if (onOpen) onOpen();
    if (pathname !== "/") {
      router.push("/#agents-section");
    } else {
      document.getElementById("agents-section")?.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <button onClick={handleScroll} className={className}>
      {children}
    </button>
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
