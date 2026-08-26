"use client";

import { motion, useReducedMotion } from "framer-motion";

/**
 * Every route fades up as it is set. `template.tsx` re-mounts on navigation, which
 * is what makes the transition run again on each page — a `layout.tsx` would not.
 *
 * Readers who ask their system for reduced motion get the page with no transform
 * and no fade, rather than a shorter one.
 */
export default function Template({ children }: { children: React.ReactNode }) {
  const still = useReducedMotion();

  if (still) return <div>{children}</div>;

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
