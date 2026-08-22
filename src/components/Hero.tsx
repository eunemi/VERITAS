import React from "react";

export default function Hero() {
  return (
    <section className="min-h-[calc(100vh-100px)] flex flex-col items-center justify-center relative py-8 border-x border-primary/20 overflow-hidden">

      <div className="relative z-10 text-center flex flex-col items-center max-w-4xl mx-auto space-y-stack-md w-full">
        {/* Decorative Stickers clustered around the text but pushed outwards to avoid overlap */}
        <img 
          src="/newspaper-sticker.png" 
          alt="Breaking news sticker" 
          className="absolute -top-16 md:-top-4 -left-4 md:-left-[120px] w-32 md:w-56 animate-float-1 z-0 sticker-shadow opacity-90 pointer-events-none"
        />
        <img 
          src="/truth-sticker-hd-cutout.png" 
          alt="Truth magnifying glass sticker" 
          className="absolute top-12 md:top-[25%] -right-4 md:-right-[120px] w-32 md:w-56 animate-float-2 z-0 sticker-shadow opacity-90 pointer-events-none"
        />
        <img 
          src="/investigation-sticker.png" 
          alt="Investigation files sticker" 
          className="absolute bottom-20 md:bottom-[15%] -left-4 md:-left-[140px] w-32 md:w-56 animate-float-3 z-0 sticker-shadow opacity-90 pointer-events-none"
        />
        <img 
          src="/note-sticker.png" 
          alt="Not everything you read is true sticker" 
          className="absolute -bottom-16 md:-bottom-10 -right-4 md:-right-[100px] w-32 md:w-56 animate-float-4 z-0 sticker-shadow opacity-90 pointer-events-none"
        />

        <h2 className="font-headline-md text-headline-md text-secondary italic tracking-wide relative z-10">
          Truth, Verified by Intelligence
        </h2>
        <h1 className="font-masthead text-[42px] leading-[48px] font-bold md:text-[120px] md:leading-[110px] md:font-black md:tracking-[-0.02em] text-primary uppercase text-center drop-shadow-sm relative z-10">
          THE TRUTH BEHIND<br />THE STORY.
        </h1>
        <div className="pt-stack-lg relative z-20">
          <button className="wax-seal text-parchment font-mono-label text-mono-label rounded-full w-32 h-32 flex items-center justify-center uppercase tracking-widest transition-all duration-300 cursor-pointer hover:scale-105 active:scale-95">
            ANALYZE<br />NOW
          </button>
        </div>
      </div>
    </section>
  );
}
