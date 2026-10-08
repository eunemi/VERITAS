"use client";

import { useState, useRef } from "react";
import { Slug } from "./layout";
import { extractTextFromFile } from "@/lib/api/client";

/* ------------------------------------------------------------ artifact ---- */

/**
 * Whether an address is one the examining service could be asked to fetch.
 *
 * Only the scheme and the shape are checked here. Whether anything is actually at
 * the address is the desk's business, and it will say so in the record.
 */
export function isFetchableUrl(value: string): boolean {
  try {
    const url = new URL(value.trim());
    return (url.protocol === "http:" || url.protocol === "https:") && !!url.hostname;
  } catch {
    return false;
  }
}

/* --------------------------------------------------------------- bench ---- */

/**
 * The bench the artifact is placed on before examination. Full width, on paper:
 * a heading that says what to hand over, the control, and the seal that opens
 * the examination.
 */
export function SubmissionBench({
  prompt,
  note,
  children,
  hint,
  actionLines,
  onSubmit,
  disabled,
}: {
  prompt: string;
  /** Right-hand slug — what the desk accepts. */
  note?: string;
  children: React.ReactNode;
  hint: string;
  /** Two short words for the seal, one per line. */
  actionLines: [string, string];
  onSubmit: () => void;
  disabled: boolean;
}) {
  return (
    <section className="pb-stack-xl">
      <div className="flex flex-wrap items-baseline justify-between gap-4 border-t-2 border-ink-black pt-stack-sm">
        <Slug>Submission bench</Slug>
        {note ? <Slug className="text-ink-black/40">{note}</Slug> : null}
      </div>

      <h2 className="font-headline-md text-headline-md mt-stack-md max-w-[24ch] text-ink-black">
        {prompt}
      </h2>

      <div className="mt-stack-md">{children}</div>

      <div className="mt-stack-lg flex flex-wrap items-center justify-between gap-stack-md">
        <p className="font-body-sm text-body-sm max-w-[48ch] text-ink-black/55">{hint}</p>
        <button
          type="button"
          onClick={onSubmit}
          disabled={disabled}
          className="wax-seal font-mono-label text-mono-label flex h-28 w-28 shrink-0 cursor-pointer items-center justify-center rounded-full text-center leading-[1.4] tracking-widest text-parchment uppercase transition-all duration-300 hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black active:scale-95 disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:scale-100"
        >
          {actionLines[0]}
          <br />
          {actionLines[1]}
        </button>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------- copy field ---- */

/**
 * A manuscript sheet. Serif, wide measure, with the margin rule the copy desk
 * marks in — the same face the examined copy is set in once the record comes
 * back, so pasting and reading are one continuous surface.
 */
export function CopyField({
  value,
  onChange,
  placeholder,
  rows = 9,
  scanning = false,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  rows?: number;
  /** Draws the examination pass over the copy while the desk reads it. */
  scanning?: boolean;
}) {
  const words = value.trim() ? value.trim().split(/\s+/).length : 0;
  
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractError, setExtractError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (file: File) => {
    if (!file) return;
    setIsExtracting(true);
    setExtractError(null);
    try {
      const text = await extractTextFromFile(file);
      onChange(text);
    } catch (e: unknown) {
      const err = e as Error;
      setExtractError(err.message || "Failed to extract text from file.");
    } finally {
      setIsExtracting(false);
      // Reset input value so the same file can be uploaded again if needed
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleFileUpload(file);
    }
  };

  return (
    <div>
      <div 
        className="ticked relative overflow-hidden bg-parchment text-ink-black/25"
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <span aria-hidden className="absolute inset-y-0 left-[52px] w-px bg-secondary/35" />
        {scanning || isExtracting ? (
          <span
            aria-hidden
            className="animate-proof-scan pointer-events-none absolute inset-x-0 z-10 h-px bg-secondary"
          />
        ) : null}
        {isExtracting && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-parchment/80 backdrop-blur-sm">
            <span className="font-mono-label text-ink-black uppercase tracking-widest text-sm animate-pulse">Extracting text...</span>
          </div>
        )}
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          rows={rows}
          placeholder={placeholder}
          spellCheck={false}
          disabled={isExtracting}
          className="font-proof text-proof relative w-full resize-y bg-transparent py-6 pr-6 pl-[72px] text-ink-black placeholder:text-ink-black/30 focus:outline-none disabled:opacity-50"
        />
        <input 
          type="file" 
          ref={fileInputRef} 
          className="hidden" 
          accept=".pdf,.docx,.md"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFileUpload(file);
          }}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isExtracting}
          className="absolute bottom-4 right-4 z-10 font-mono-label text-xs uppercase tracking-wider text-ink-black/50 hover:text-ink-black transition-colors disabled:opacity-50"
          title="Upload .pdf, .docx, or .md"
        >
          [ UPLOAD FILE ]
        </button>
      </div>
      <div className="mt-2.5 flex items-baseline justify-between">
        <div className="flex flex-col gap-1">
          <Slug className="text-ink-black/35">Plain text · no formatting kept</Slug>
          {extractError && (
            <span className="font-body-sm text-xs text-red-600">{extractError}</span>
          )}
        </div>
        <Slug className="tabular text-ink-black/40">
          {String(words).padStart(3, "0")} words
        </Slug>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------- link field ---- */

/**
 * The intake docket for media.
 *
 * An address, not a file. The examination happens in a service that has to fetch the
 * artifact itself, and there is no upload path into it, so a recording sitting on the
 * reader's own disk cannot be examined — it has to be somewhere the service can
 * reach. Saying that plainly on the docket is better than a file picker that accepts
 * a drop and then fails.
 *
 * For a frame the address doubles as the preview, so what is on the bench is the
 * same bytes the desk will read.
 */
export function LinkField({
  value,
  onChange,
  kind,
  formats,
  scanning = false,
}: {
  value: string;
  onChange: (value: string) => void;
  kind: "image" | "audio" | "video";
  /** Human-readable list, e.g. "JPG · PNG · WEBP". */
  formats: string;
  /** Draws the examination pass over the artifact while the desk reads it. */
  scanning?: boolean;
}) {
  // Holds the address that failed to load rather than a flag, so a new address
  // clears the failure without an effect to reset it.
  const [broken, setBroken] = useState<string | null>(null);

  const trimmed = value.trim();
  const fetchable = isFetchableUrl(trimmed);
  const preview = kind === "image" && fetchable && broken !== trimmed;

  return (
    <div>
      <div className="ticked relative overflow-hidden bg-parchment text-ink-black/25">
        {scanning ? (
          <span
            aria-hidden
            className="animate-proof-scan pointer-events-none absolute inset-x-0 z-10 h-px bg-secondary"
          />
        ) : null}

        <label className="block px-6 pt-6 pb-4">
          <Slug className="text-ink-black/45">Address of the {kind}</Slug>
          <input
            type="url"
            inputMode="url"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="https://"
            spellCheck={false}
            className="font-proof text-proof mt-2.5 w-full border-b border-ink-black/25 bg-transparent pb-2 text-ink-black placeholder:text-ink-black/30 focus:border-secondary focus:outline-none"
          />
        </label>

        {preview ? (
          <div className="px-6 pb-6">
            {/* An address the reader supplied, on a host next/image has not been
                configured for — so it cannot be routed through the optimiser. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={trimmed}
              alt="The frame on the bench, as fetched from the address given"
              onError={() => setBroken(trimmed)}
              className="mx-auto max-h-[340px] w-auto object-contain"
            />
          </div>
        ) : (
          <p className="font-body-sm text-body-sm px-6 pb-6 text-ink-black/50">
            {trimmed && !fetchable
              ? "That is not an http or https address the desk could fetch."
              : broken === trimmed && trimmed
                ? "Nothing loaded from that address here. The desk will try it too, and will say so in the record if it cannot read it."
                : `The desk fetches the ${kind} from this address. A file on your own disk cannot be sent to it yet.`}
          </p>
        )}
      </div>

      <div className="mt-2.5 flex flex-wrap items-baseline justify-between gap-3">
        <Slug className="text-ink-black/35">Accepts {formats}</Slug>
        {trimmed ? (
          <button
            type="button"
            onClick={() => onChange("")}
            className="cursor-pointer transition-colors hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black"
          >
            <Slug className="text-ink-black/40 underline decoration-1 underline-offset-4">
              Clear the bench
            </Slug>
          </button>
        ) : null}
      </div>
    </div>
  );
}
