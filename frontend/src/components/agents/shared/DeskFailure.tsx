"use client";

import { API_BASE_URL, ApiError, POLL_TIMEOUT, UNREACHABLE } from "@/lib/api/client";
import { ExaminationError } from "@/lib/services/agentServices";
import { Slug } from "./layout";

/**
 * What went wrong, in words, plus what the reader can do about it.
 *
 * `title` is the sentence the page sets in display type, `detail` explains it, and
 * `remedy` is only present when there is genuinely something the reader could do —
 * an offline service is fixable from their end, an unbuilt desk is not, and offering
 * a "try again" against the second would be a lie about the third.
 */
export interface Described {
  title: string;
  detail: string;
  remedy: string | null;
  /** The stable code, printed small. It is what a bug report should carry. */
  code: string;
  retryable: boolean;
}

export function describeError(error: unknown): Described {
  if (error instanceof ApiError) {
    if (error.code === UNREACHABLE) {
      return {
        title: "The examination service is not answering",
        detail: `Nothing responded at ${API_BASE_URL}. The desks run in a separate service from this site, so the page loads whether or not that service is up.`,
        remedy:
          "Start the backend, then send the artifact again. If it is running elsewhere, point NEXT_PUBLIC_API_URL at it and rebuild.",
        code: error.code,
        retryable: true,
      };
    }

    if (error.code === POLL_TIMEOUT) {
      return {
        title: "The examination was still running when we stopped watching",
        detail:
          "The desks had not closed the record inside the time this page waits. The examination itself was not cancelled — it may well have finished since.",
        remedy: "Send the artifact again, or check the service logs for the desk that is slow.",
        code: error.code,
        retryable: true,
      };
    }

    if (error.notImplemented) {
      const desk = error instanceof ExaminationError ? error.desk : null;
      return {
        title: desk ? `The ${desk} desk is not open yet` : "That desk is not open yet",
        detail: `${error.message} Nothing was examined, so there is no record to file and nothing on this page is a finding.`,
        remedy: null,
        code: error.code,
        retryable: false,
      };
    }

    if (error.code === "validation_error") {
      return {
        title: "The submission was refused",
        detail: `${error.message} Nothing was examined.`,
        remedy: "Correct the submission and send it again.",
        code: error.code,
        retryable: true,
      };
    }

    if (error.status === 401 || error.status === 403) {
      return {
        title: "This record is not yours to read",
        detail: error.message,
        remedy: null,
        code: error.code,
        retryable: false,
      };
    }

    return {
      title: "The examination did not produce a record",
      detail: error.message,
      remedy: "Send the artifact again.",
      code: error.code,
      retryable: true,
    };
  }

  if (error instanceof Error) {
    return {
      title: "The examination did not produce a record",
      detail: error.message,
      remedy: "Send the artifact again.",
      code: "unexpected_error",
      retryable: true,
    };
  }

  return {
    title: "The examination did not produce a record",
    detail: "Something failed between this page and the desks, without saying what.",
    remedy: "Send the artifact again.",
    code: "unexpected_error",
    retryable: true,
  };
}

/**
 * The page a desk shows when there is no record.
 *
 * Set in the same type as a record so it reads as part of the publication, but it
 * carries no ledger, no determination and no figures — there is nothing to report,
 * and a failure dressed as a finding is worse than a blank page.
 */
export function DeskFailure({
  error,
  onRetry,
  children,
}: {
  error: unknown;
  onRetry?: () => void;
  /** Anything that did come back — a desk that filed before the run stopped. */
  children?: React.ReactNode;
}) {
  const { title, detail, remedy, code, retryable } = describeError(error);

  return (
    <section className="border-t-2 border-ink-black pt-stack-md">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <Slug className="text-ink-black/40">No record</Slug>
        <Slug className="tabular text-ink-black/40">{code}</Slug>
      </div>

      <h2 className="font-headline-md text-headline-md mt-stack-sm max-w-title text-ink-black">
        {title}
      </h2>

      <p className="font-body-lg text-body-lg mt-stack-sm max-w-measure text-ink-black/70">
        {detail}
      </p>

      {remedy ? (
        <p className="font-body-md text-body-md mt-stack-sm max-w-measure text-ink-black/55">
          {remedy}
        </p>
      ) : null}

      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className={`mt-stack-md cursor-pointer border-b-2 pb-1 transition-colors hover:border-ink-black focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink-black ${
            retryable ? "border-secondary" : "border-ink-black/30"
          }`}
        >
          <Slug className={retryable ? "text-secondary" : "text-ink-black/55"}>
            Back to the bench
          </Slug>
        </button>
      ) : null}

      {children ? <div className="pt-stack-xl">{children}</div> : null}
    </section>
  );
}
