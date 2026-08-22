"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Slug } from "./layout";

/* ------------------------------------------------------------ artifact ---- */

export interface Artifact {
  file: File | null;
  /** Object URL, created only for artifacts the page needs to display. */
  url: string | null;
}

/**
 * Holds the submitted file and its preview URL as one value, and revokes the URL
 * when it is replaced or the desk unmounts. Creating the URL in the change
 * handler — not in an effect — keeps file and preview in step at all times.
 */
export function useArtifact() {
  const [artifact, setArtifact] = useState<Artifact>({ file: null, url: null });
  const urlRef = useRef<string | null>(null);

  const pick = useCallback((file: File | null, withPreview = false) => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
    const url = file && withPreview ? URL.createObjectURL(file) : null;
    urlRef.current = url;
    setArtifact({ file, url });
  }, []);

  useEffect(
    () => () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    },
    [],
  );

  return { artifact, pick };
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

  return (
    <div>
      <div className="ticked relative overflow-hidden bg-parchment text-ink-black/25">
        <span aria-hidden className="absolute inset-y-0 left-[52px] w-px bg-secondary/35" />
        {scanning ? (
          <span
            aria-hidden
            className="animate-proof-scan pointer-events-none absolute inset-x-0 z-10 h-px bg-secondary"
          />
        ) : null}
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          rows={rows}
          placeholder={placeholder}
          spellCheck={false}
          className="font-proof text-proof relative w-full resize-y bg-transparent py-6 pr-6 pl-[72px] text-ink-black placeholder:text-ink-black/30 focus:outline-none"
        />
      </div>
      <div className="mt-2.5 flex items-baseline justify-between">
        <Slug className="text-ink-black/35">Plain text · no formatting kept</Slug>
        <Slug className="tabular text-ink-black/40">
          {String(words).padStart(3, "0")} words
        </Slug>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------- file field ---- */

function readableSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * The intake docket. A real file input behind a full-width label, so it works by
 * click, keyboard and drop. Once an artifact is in, the docket becomes the
 * artifact: the frame on the plate, or a typed file plate for sound and footage.
 */
export function FileField({
  artifact,
  onPick,
  accept,
  formats,
  kind,
  scanning = false,
}: {
  artifact: Artifact;
  onPick: (file: File | null) => void;
  accept: string;
  /** Human-readable list, e.g. "JPG · PNG · WEBP". */
  formats: string;
  kind: "image" | "audio" | "video";
  /** Draws the examination pass over the artifact while the desk reads it. */
  scanning?: boolean;
}) {
  const [over, setOver] = useState(false);
  const { file, url } = artifact;

  return (
    <div>
      <label
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          const dropped = event.dataTransfer.files?.[0];
          if (dropped) onPick(dropped);
        }}
        className={`ticked relative block cursor-pointer overflow-hidden bg-parchment transition-colors ${
          over ? "text-secondary" : "text-ink-black/25"
        } focus-within:text-ink-black/60`}
      >
        <input
          type="file"
          accept={accept}
          className="sr-only"
          onChange={(event) => onPick(event.target.files?.[0] ?? null)}
        />

        {scanning ? (
          <span
            aria-hidden
            className="animate-proof-scan pointer-events-none absolute inset-x-0 z-10 h-px bg-secondary"
          />
        ) : null}

        {url && kind === "image" ? (
          <div className="p-4">
            {/* Object URL from the visitor's own disk — next/image cannot optimise it. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={url}
              alt={`Submitted frame: ${file?.name ?? "untitled"}`}
              className="mx-auto max-h-[340px] w-auto object-contain"
            />
          </div>
        ) : (
          <div className="px-6 py-stack-xl text-center">
            <p className="font-headline-md text-[27px] leading-tight font-normal text-ink-black italic">
              {file ? file.name : over ? "Let go to file it" : "Choose a file, or drop it here"}
            </p>
            <p className="font-body-sm text-body-sm mt-2 text-ink-black/50">
              {file
                ? `${readableSize(file.size)} · ${file.type || "type unknown"}`
                : "Nothing is uploaded — the desk reads it in this browser."}
            </p>
          </div>
        )}
      </label>

      <div className="mt-2.5 flex flex-wrap items-baseline justify-between gap-3">
        <Slug className="text-ink-black/35">Accepts {formats}</Slug>
        {file ? (
          <button
            type="button"
            onClick={() => onPick(null)}
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
