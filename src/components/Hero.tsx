import Image from "next/image";
import { CommissionTrigger } from "@/components/CommissionSlip";
import investigationSticker from "../../public/investigation-sticker.png";
import newspaperSticker from "../../public/newspaper-sticker.png";
import noteSticker from "../../public/note-sticker.png";
import truthSticker from "../../public/truth-sticker-hd-cutout.png";

/**
 * The stickers are decoration, so they carry no alt text and are hidden from
 * assistive tech — the headline already says everything they illustrate. They are
 * imported rather than referenced by path so next/image knows their dimensions
 * and can serve them at the two sizes the layout actually uses.
 */
const STICKERS = [
  {
    src: newspaperSticker,
    position: "-top-16 md:-top-4 -left-4 md:-left-[120px]",
    float: "animate-float-1",
  },
  {
    src: truthSticker,
    position: "top-12 md:top-[25%] -right-4 md:-right-[120px]",
    float: "animate-float-2",
  },
  {
    src: investigationSticker,
    position: "bottom-20 md:bottom-[15%] -left-4 md:-left-[140px]",
    float: "animate-float-3",
  },
  {
    src: noteSticker,
    position: "-bottom-16 md:-bottom-10 -right-4 md:-right-[100px]",
    float: "animate-float-4",
  },
];

export default function Hero() {
  return (
    <section className="min-h-[calc(100svh-100px)] flex flex-col items-center justify-center relative py-8 border-x border-primary/20 overflow-hidden">
      <div className="relative z-10 text-center flex flex-col items-center max-w-4xl mx-auto space-y-stack-md w-full">
        {STICKERS.map((sticker) => (
          <Image
            key={sticker.position}
            src={sticker.src}
            alt=""
            aria-hidden
            sizes="(min-width: 768px) 224px, 128px"
            className={`absolute ${sticker.position} ${sticker.float} h-auto w-32 md:w-56 z-0 sticker-shadow opacity-90 pointer-events-none`}
          />
        ))}

        <h2 className="font-headline-md text-headline-md text-secondary italic tracking-wide relative z-10">
          Truth, Verified by Intelligence
        </h2>
        <h1 className="font-masthead text-[42px] leading-[48px] font-bold md:text-[120px] md:leading-[110px] md:font-black md:tracking-[-0.02em] text-primary uppercase text-center drop-shadow-sm relative z-10">
          THE TRUTH BEHIND<br />THE STORY.
        </h1>

        {/* The seal used to be a button with nothing behind it. It now opens the
            same commission slip as the masthead action. */}
        <div className="pt-stack-lg relative z-20">
          <CommissionTrigger className="wax-seal text-parchment font-mono-label text-mono-label rounded-full w-32 h-32 flex items-center justify-center uppercase tracking-widest transition-all duration-300 cursor-pointer motion-safe:hover:scale-105 motion-safe:active:scale-95 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black">
            ANALYZE
            <br />
            NOW
          </CommissionTrigger>
        </div>
      </div>
    </section>
  );
}
