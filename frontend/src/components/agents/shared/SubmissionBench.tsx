"use client";

import { useState, useRef } from "react";
import { Slug } from "./layout";
import { extractTextFromFile, uploadMediaFile } from "@/lib/api/client";

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
          className="wax-seal font-mono-label text-mono-label flex h-24 w-24 shrink-0 cursor-pointer items-center justify-center rounded-full text-center leading-[1.4] tracking-widest text-parchment uppercase transition-all duration-300 hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black active:scale-95 disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:scale-100"
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
  onBusy,
  allowUpload = true,
  accept = ".pdf,.docx,.md,.txt",
  uploadLabel = "[ UPLOAD FILE ]",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  rows?: number;
  /** Draws the examination pass over the copy while the desk reads it. */
  scanning?: boolean;
  onBusy?: (busy: boolean) => void;
  allowUpload?: boolean;
  accept?: string;
  uploadLabel?: string;
}) {
  const words = value.trim() ? value.trim().split(/\s+/).length : 0;
  
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractError, setExtractError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (file: File) => {
    if (!file || scanning || isExtracting) return;
    const allowed = accept.split(",").map((extension) => extension.trim().toLowerCase()).filter(Boolean);
    if (allowed.length && !allowed.some((extension) => file.name.toLowerCase().endsWith(extension.replace("*", "")))) {
      setExtractError(`Choose a supported file: ${allowed.join(", ")}.`);
      return;
    }
    setIsExtracting(true);
    onBusy?.(true);
    setExtractError(null);
    try {
      const text = await extractTextFromFile(file);
      onChange(text);
    } catch (e: unknown) {
      const err = e as Error;
      setExtractError(err.message || "Failed to extract text from file.");
    } finally {
      setIsExtracting(false);
      onBusy?.(false);
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
        onDragOver={allowUpload ? handleDragOver : undefined}
        onDrop={allowUpload ? handleDrop : undefined}
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
          aria-label="Text to verify"
          maxLength={100000}
          disabled={isExtracting || scanning}
          className="font-proof text-proof relative w-full resize-y bg-transparent py-6 pr-6 pl-[72px] text-ink-black placeholder:text-ink-black/30 focus:outline-none disabled:opacity-50"
        />
        {allowUpload ? <>
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            accept={accept}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFileUpload(file);
            }}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isExtracting || scanning}
            className="absolute bottom-4 right-4 z-10 font-mono-label text-xs uppercase tracking-wider text-ink-black/50 hover:text-ink-black transition-colors disabled:opacity-50"
            title="Upload a document"
          >
            {uploadLabel}
          </button>
        </> : null}
      </div>
      <div className="mt-2.5 flex items-baseline justify-between">
        <div className="flex flex-col gap-1">
          <Slug className="text-ink-black/35">{allowUpload ? "Plain text · no formatting kept" : "Paste plain text · no formatting kept"}</Slug>
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
  onBusy,
}: {
  value: string;
  onChange: (value: string) => void;
  kind: "image" | "audio" | "video";
  /** Human-readable list, e.g. "JPG · PNG · WEBP". */
  formats: string;
  /** Draws the examination pass over the artifact while the desk reads it. */
  scanning?: boolean;
  onBusy?: (busy: boolean) => void;
}) {
  // Holds the address that failed to load rather than a flag, so a new address
  // clears the failure without an effect to reset it.
  const [broken, setBroken] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const trimmed = value.trim();
  const fetchable = isFetchableUrl(trimmed);
  const preview = kind === "image" && fetchable && broken !== trimmed;

  const handleFileUpload = async (file: File) => {
    if (!file || scanning || isUploading) return;
    if (!/\.(jpe?g|png|webp|gif|avif)$/i.test(file.name)) {
      setUploadError("Choose a JPG, PNG, WEBP, GIF or AVIF image.");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setUploadError("The image must be smaller than 50 MB.");
      return;
    }
    setIsUploading(true);
    onBusy?.(true);
    setUploadError(null);
    try {
      const url = await uploadMediaFile(file);
      onChange(url);
    } catch (e: unknown) {
      const err = e as Error;
      setUploadError(err.message || "Failed to upload media file.");
    } finally {
      setIsUploading(false);
      onBusy?.(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileUpload(file);
  };

  return (
    <div>
      <div 
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
        className="ticked relative overflow-hidden bg-parchment flex min-h-48 flex-col items-center justify-center gap-5 border border-ink-black/20 p-6"
      >
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element -- User-supplied image preview.
          <img src={trimmed} alt="Image selected for verification" onError={() => setBroken(trimmed)} className="max-h-80 max-w-full object-contain" />
        ) : <p className="text-center text-ink-black/60">Drop an image here or choose a file from your device.</p>}
        <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif,image/avif" className="hidden" disabled={scanning || isUploading} onChange={(event) => { const file = event.target.files?.[0]; if (file) void handleFileUpload(file); }} />
        <button type="button" disabled={scanning || isUploading} onClick={() => fileInputRef.current?.click()} className="border border-ink-black px-5 py-3 text-ink-black disabled:opacity-50 hover:bg-ink-black/5">
          {isUploading ? "Uploading image…" : "Choose image"}
        </button>
        <label className="w-full text-sm text-ink-black/60">
          Or paste a direct image URL
          <input type="url" value={value} onChange={(event) => { onChange(event.target.value); setUploadError(null); }} disabled={scanning || isUploading} placeholder="https://example.com/photo.jpg" className="mt-2 w-full border-b border-ink-black/30 bg-transparent py-3 text-ink-black focus:outline-2 focus:outline-ink-black" />
        </label>
        {broken === trimmed ? <p className="text-sm text-secondary">The preview could not load. Check that this URL points directly to a public image.</p> : null}
      </div>

      <div className="mt-2.5 flex flex-wrap items-baseline justify-between gap-3">
        <div className="flex flex-col gap-1">
          <Slug className="text-ink-black/35">Accepts {formats}</Slug>
          {uploadError && (
            <span className="font-body-sm text-xs text-red-600">{uploadError}</span>
          )}
        </div>
        {trimmed && !scanning && !isUploading ? (
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
