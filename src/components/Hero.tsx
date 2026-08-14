import React from "react";

export default function Hero() {
  return (
    <section className="min-h-[calc(100vh-100px)] flex flex-col items-center justify-center relative py-8 border-x border-primary/20 overflow-hidden">

      {/* Decorative Stickers */}
      <img 
        src="/newspaper-sticker.png" 
        alt="Breaking news sticker" 
        className="absolute -left-4 md:left-[10%] top-1/3 w-32 md:w-56 animate-swing origin-top z-0 drop-shadow-xl -rotate-12 opacity-80"
      />
      <img 
        src="/truth-sticker-hd-cutout.png" 
        alt="Truth magnifying glass sticker" 
        className="absolute -right-4 md:right-[10%] top-1/4 w-32 md:w-56 animate-swing origin-top z-0 drop-shadow-xl rotate-12 opacity-80"
      />
      <img 
        src="/investigation-sticker.png" 
        alt="Investigation files sticker" 
        className="absolute left-8 md:left-[20%] bottom-8 w-32 md:w-56 animate-swing origin-top z-0 drop-shadow-xl rotate-3 opacity-80"
      />
      <img 
        src="/note-sticker.png" 
        alt="Not everything you read is true sticker" 
        className="absolute right-4 md:right-[18%] bottom-6 w-32 md:w-56 animate-swing origin-top z-0 drop-shadow-xl -rotate-6 opacity-80"
      />

      <div className="relative z-10 text-center flex flex-col items-center max-w-4xl mx-auto space-y-stack-md">
        <h2 className="font-headline-md text-headline-md text-secondary italic tracking-wide">
          Truth, Verified by Intelligence
        </h2>
        <h1 className="font-masthead text-[42px] leading-[48px] font-bold md:text-[120px] md:leading-[110px] md:font-black md:tracking-[-0.02em] text-primary uppercase text-center drop-shadow-sm">
          THE TRUTH BEHIND<br />THE STORY.
        </h1>
        <div className="pt-stack-lg">
          <button className="wax-seal text-parchment font-mono-label text-mono-label rounded-full w-32 h-32 flex items-center justify-center uppercase tracking-widest transition-all duration-300 cursor-pointer relative z-20 hover:scale-105 active:scale-95">
            ANALYZE<br />NOW
          </button>
        </div>
      </div>
    </section>
  );
}
