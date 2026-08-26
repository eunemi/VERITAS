"use client";

import { Slug } from "@/components/agents/shared/layout";
import { API_BASE_URL, ApiError, UNREACHABLE } from "@/lib/api/client";

/**
 * A short ruled failure notice.
 *
 * Not the same object as `DeskFailure`, which is a whole page standing in for a record
 * that does not exist. This is a note in the margin of something that is still there —
 * a form that was refused, a list that could not be read — and it fits above the thing
 * it is about.
 */

export interface Notice {
  detail: string;
  /** The stable code, printed small. It is what a bug report should carry. */
  code: string;
}

/**
 * What went wrong, in words.
 *
 * Only the unreachable case is written here. Everything the API refuses arrives with a
 * sentence it chose deliberately — a rejected sign-in is answered the same way whether
 * the address is unknown, the password wrong or the account closed, and rewording that
 * risks turning one message back into three that tell a stranger which accounts exist.
 */
export function noticeOf(error: unknown): Notice {
  if (error instanceof ApiError) {
    if (error.code === UNREACHABLE) {
      return {
        detail: `Nothing responded at ${API_BASE_URL}. Veritas runs in a separate service from this site, so the page loads whether or not that service is up.`,
        code: error.code,
      };
    }
    return { detail: error.message, code: error.code };
  }
  if (error instanceof Error) {
    return { detail: error.message, code: "unexpected_error" };
  }
  return {
    detail: "Something failed between this page and the service, without saying what.",
    code: "unexpected_error",
  };
}

export function NoticeBlock({
  heading,
  notice,
  className = "",
}: {
  /** What did not happen, in three or four words. */
  heading: string;
  notice: Notice;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={`border-l-2 border-secondary bg-secondary/5 px-4 py-3 ${className}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <Slug className="text-secondary">{heading}</Slug>
        <Slug className="tabular text-ink-black/45">{notice.code}</Slug>
      </div>
      <p className="font-body-md text-body-md mt-1.5 max-w-measure text-ink-black/70">
        {notice.detail}
      </p>
    </div>
  );
}
