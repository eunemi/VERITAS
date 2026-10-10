"use client";

import { useRef } from "react";
import Link from "next/link";
import { motion, useScroll, useTransform } from "framer-motion";
import { Slug } from "@/components/agents/shared/layout";
import { DESK_ISSUE, DESK_ORDER, DESKS } from "@/lib/desks";

/**
 * The register of desks, as printed on the front.
 *
 * The public cards used to carry their own copy, a Material Symbols glyph each and a
 * status light reading ONLINE — none of which was true of anything. They now read
 * from `@/lib/desks`, the same register the desk pages and the commission slip
 * use, so a tool is described once and the front cannot drift from the desk it
 * links to. Each card prints what the desk actually reads in place of the status.
 */
const DESKS_ON_THE_FRONT = DESK_ORDER.map((id) => DESKS[id]);

export default function AgentsSection() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start 75%", "start 25%"],
  });

  const opacity = useTransform(scrollYProgress, [0, 1], [0, 1]);

  return (
    <div ref={sectionRef} className="relative">
      <motion.div
        aria-hidden
        className="fixed inset-0 h-full w-full pointer-events-none"
        style={{
          opacity,
          backgroundImage: "url('/bg.jpg')",
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
          zIndex: -1,
        }}
      />

      {/* Technical rule */}
      <div aria-hidden className="relative my-0 h-px w-full bg-ink-black/20">
        <div className="absolute -top-[5px] left-0 h-3 w-3 border-t border-l border-ink-black" />
        <div className="absolute -top-[5px] right-0 h-3 w-3 border-t border-r border-ink-black" />
      </div>

      <section id="agents-section" className="relative border-x border-primary/20 py-stack-xl">
        <div className="grid grid-cols-1 gap-x-gutter gap-y-stack-lg md:grid-cols-12">
          <div className="col-span-1 mb-stack-md flex items-end justify-between border-b border-ink-black/20 pb-stack-sm md:col-span-12">
            <h2 className="font-headline-lg text-headline-xl-mobile md:text-headline-lg text-ink-black uppercase">
              Intelligence Assets
            </h2>
            <Slug className="tabular hidden text-ink-black/50 md:block">
              Five tools · Issue {DESK_ISSUE}
            </Slug>
          </div>

          <div className="drop-cap text-body-md col-span-1 hidden border-r border-ink-black/20 pr-gutter text-on-surface-variant md:col-span-4 md:block lg:col-span-3">
            The Veritas tools read an artifact in the form you hand it over. Each one states
            what it reads, what it looks for, and what it can return with evidence.
          </div>

          <div className="col-span-1 grid grid-cols-1 gap-gutter sm:grid-cols-2 md:col-span-8 lg:col-span-9 lg:grid-cols-3">
            {DESKS_ON_THE_FRONT.map((desk) => {
              return (
                <Link href={`/intel/${desk.id}`} key={desk.id} className="group block">
                  <article
                    className="glass-card relative flex h-full cursor-pointer flex-col border border-transparent p-6 transition-all duration-300 hover:-translate-y-1 hover:border-secondary/20 hover:shadow-xl"
                  >
                    <div
                      aria-hidden
                      className="absolute top-0 bottom-0 left-0 z-10 w-1 origin-bottom scale-y-0 bg-secondary transition-transform duration-300 group-hover:scale-y-100"
                    />
                    <div
                      aria-hidden
                      className="absolute top-0 right-0 mt-2 mr-2 h-4 w-4 border-t border-r border-ink-black/40 transition-colors group-hover:border-secondary"
                    />

                    {/* The desk's own number, set as a figure. It was a 3rem icon
                        glyph from a font the app never loaded. */}
                    <span
                      aria-hidden
                      className="font-masthead tabular block text-[52px] leading-none font-black tracking-[-0.04em] text-ink-black/25 transition-colors group-hover:text-gold-foil"
                    >
                      {desk.number}
                    </span>

                    <Slug className="mt-5 block text-ink-black/55">
                      {desk.eyebrow}
                    </Slug>
                    {/* The desk's name is the card's heading; the eyebrow above it
                        is a label, so it is not marked up as one. */}
                    <h3
                      className="font-headline-md mt-2 mb-3 text-2xl text-ink-black transition-colors group-hover:text-primary"
                    >
                      {desk.name}
                    </h3>
                    <p
                      className="font-body-sm mb-4 flex-grow text-sm text-on-surface-variant"
                    >
                      {desk.standfirst}
                    </p>

                    <div className="mt-auto flex items-center justify-between gap-3 border-t border-ink-black/10 pt-4">
                      <Slug className="text-ink-black/50">
                        Reads {desk.method[0].value.toLowerCase()}
                      </Slug>
                      <span
                        aria-hidden
                        className="shrink-0 text-[15px] leading-none text-ink-black/40 transition-transform group-hover:translate-x-1 group-hover:text-secondary"
                      >
                        &rarr;
                      </span>
                    </div>
                  </article>
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      {/* Technical rule */}
      <div aria-hidden className="relative my-0 h-px w-full bg-ink-black/20">
        <div className="absolute -bottom-[5px] left-0 h-3 w-3 border-b border-l border-ink-black" />
        <div className="absolute -bottom-[5px] right-0 h-3 w-3 border-b border-r border-ink-black" />
      </div>
    </div>
  );
}
